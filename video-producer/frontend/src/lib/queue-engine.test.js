import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { clean, hostUis, renderComponent, textOf } from './svelte-harness.js';
import { createClient, normalizeQueue, normalizeTake } from './api.js';
import { SEED_MAX, effectiveEngine, hasOwnEngine, migrateShotEngine, projectQuality, randomSeed, setShotEngine, shotEngineOf, validSeed } from './engine.js';
import { canPrioritize, handedOver, isWaiting, prioritized, queueOrder } from './queue.js';
import { applyShotDraft, revisionOf, shotDraft } from './shots.js';
import { emptyDoc, migrate } from './starter.js';

const WAN = '01KX47WANVIDEO0000000000TV';
const LTX = '01KX47LTX25VIDEO00000000TV';
const at = (n) => `2026-10-23T10:00:0${n}+00:00`;
const take = (id, extra = {}) => ({ id, shotId: 's1', status: 'queued', generationId: null, priority: 0, createdAt: at(0), ...extra });

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project, bindClient, flushSave } = await import('./project.svelte.js');
const { estimateRequest, openQueue, QUEUE_MENU } = await import('./production.svelte.js');
const { setTakes, takeStore } = await import('./takes.svelte.js');
const { commandById } = await import('./commands.js');
const { t } = await import('../i18n/index.svelte.js');

after(() => {
	dispose();
	bindClient(null);
});

test('queue: the takes handed to the engine come first, then the waiting ones by priority, then oldest first', () => {
	const list = [
		take('w-old', { createdAt: at(1) }),
		take('done', { status: 'done', createdAt: at(0) }),
		take('w-top', { createdAt: at(5), priority: 2 }),
		take('running', { status: 'running', generationId: 'g1', createdAt: at(4) }),
		take('handed', { generationId: 'g2', createdAt: at(3) }),
		take('w-new', { createdAt: at(2) }),
		take('failed', { status: 'failed' })
	];

	assert.deepEqual(
		queueOrder(list).map((x) => x.id),
		['handed', 'running', 'w-top', 'w-old', 'w-new']
	);
	assert.deepEqual([handedOver(list[3]), handedOver(list[4]), handedOver(list[0])], [true, true, false]);
	assert.deepEqual([isWaiting(list[0]), isWaiting(list[4]), isWaiting(list[1])], [true, false, false]);
});

test('queue: two takes of the same age keep the order of their ids, as the server sorts them', () => {
	assert.deepEqual(queueOrder([take('b'), take('a')]).map((x) => x.id), ['a', 'b']);
});

test('queue: only a waiting take that is not first can move to the head, one priority above the highest', () => {
	const list = [take('first', { createdAt: at(1) }), take('second', { createdAt: at(2), priority: 0 }), take('third', { createdAt: at(3) }), take('handed', { generationId: 'g' })];
	const ordered = queueOrder(list);

	assert.deepEqual(ordered.map((x) => canPrioritize(x, ordered)), [false, false, true, true]);
	assert.equal(prioritized(list, 'third'), 1);
	assert.equal(prioritized(list, 'first'), null);
	assert.equal(prioritized(list, 'handed'), null);
	assert.equal(prioritized(list, 'missing'), null);
	list[2].priority = 1;
	assert.deepEqual(queueOrder(list).map((x) => x.id), ['handed', 'third', 'first', 'second']);
	assert.equal(prioritized(list, 'second'), 2);
});

test('queue: the take keeps its priority and the queue route its places, slots and other projects', () => {
	assert.equal(normalizeTake({ id: 't1', priority: 3 }).priority, 3);
	assert.equal(normalizeTake({ id: 't1', priority: 'high' }).priority, 0);
	assert.equal(normalizeTake({ id: 't1' }).priority, 0);
	const queue = normalizeQueue({
		takes: [
			{ id: 't1', status: 'running', queue_position: null },
			{ id: 't2', status: 'queued', queue_position: 2 },
			{ id: 't3', status: 'queued', queue_position: 0 }
		],
		slots: { in_flight: 1, max: 2 },
		elsewhere: { waiting: 1, in_flight: 0 }
	});
	assert.deepEqual(queue.positions, { t2: 2 });
	assert.deepEqual(queue.elsewhere, { waiting: 1, inFlight: 0 });
	assert.deepEqual(normalizeQueue({ takes: [] }).elsewhere, { waiting: 0, inFlight: 0 });
});

test('queue: the client moves a take to the head through its project route', async () => {
	const calls = [];
	const client = createClient({
		async request(method, path, data) {
			calls.push([method, path, data]);
			return { success: true, data: { take: { id: 't1', status: 'queued', priority: 4 } } };
		}
	});

	assert.equal((await client.prioritizeTake('p1', 't1')).data.priority, 4);
	assert.deepEqual(calls, [['POST', '/projects/p1/takes/t1/prioritize', {}]]);
});

test('engine: a shot keeps only the valid settings it sets for itself, a preset with its model and backend', () => {
	assert.deepEqual(shotEngineOf({ engine: { preset: LTX, model: '', backend: 'b-local', profile: 'Ref2VA', quality: 'final', seed: 0, variants: 3 } }), {
		preset: LTX,
		model: null,
		backend: 'b-local',
		profile: 'Ref2VA',
		quality: 'final',
		seed: 0
	});
	assert.deepEqual(shotEngineOf({ engine: { model: 'cm-veo', backend: 'b', profile: 'Painting', quality: 'Standard', seed: -1 } }), {});
	assert.deepEqual(shotEngineOf({ engine: { seed: SEED_MAX + 1 } }), {});
	assert.deepEqual(shotEngineOf({ engine: 'wan' }), {});
	assert.deepEqual(shotEngineOf({}), {});
	assert.deepEqual([validSeed(SEED_MAX), validSeed(1.5), validSeed(true)], [true, false, false]);
	assert.deepEqual([hasOwnEngine({ engine: { quality: 'final' } }), hasOwnEngine({ engine: {} }), hasOwnEngine({})], [true, false, false]);
});

test('engine: writing the settings of a shot drops the empty ones and the object when nothing is left', () => {
	const clip = { id: 's1' };
	setShotEngine(clip, { preset: WAN, model: null, quality: '', seed: 7 });
	assert.deepEqual(clip.engine, { preset: WAN, model: null, seed: 7 });
	setShotEngine(clip, {});
	assert.ok(!('engine' in clip));
});

test('engine: a shot without settings of its own follows the project, the Production bar quality and a random seed', () => {
	const doc = { engine: { preset: WAN, model: null, quality: 'final' }, direction: { mode: 'FL2VA' } };

	assert.deepEqual(effectiveEngine({}, doc, 'draft'), { preset: WAN, model: null, profile: 'FL2VA', quality: 'draft', seed: null });
	assert.deepEqual(effectiveEngine({}, doc), { preset: WAN, model: null, profile: 'FL2VA', quality: 'final', seed: null });
	assert.deepEqual(effectiveEngine({ engine: { preset: 'cloud', model: 'cm-veo', profile: 'Hybrid AV', quality: 'draft', seed: 42 } }, doc, 'final'), {
		preset: 'cloud',
		model: 'cm-veo',
		profile: 'Hybrid AV',
		quality: 'draft',
		seed: 42
	});
	assert.deepEqual([projectQuality({ quality: 'final' }), projectQuality({ quality: 'Standard' }), projectQuality(null)], ['final', 'draft', 'draft']);
});

test('engine: a random seed stays in the range the server accepts', () => {
	assert.deepEqual([randomSeed(() => 0), randomSeed(() => 0.999999999999)], [0, SEED_MAX]);
	for (let i = 0; i < 50; i++) assert.ok(validSeed(randomSeed()));
});

test('engine: the migration cleans the settings of a shot without creating any, and never adds hybrid weights or profiles', () => {
	assert.deepEqual(migrateShotEngine({ id: 's1', engine: { preset: '', seed: 3, variants: 2 } }), { id: 's1', engine: { seed: 3 } });
	assert.deepEqual(migrateShotEngine({ id: 's1', engine: { quality: 'best' } }), { id: 's1' });
	assert.deepEqual(migrateShotEngine({ id: 's1' }), { id: 's1' });
	const doc = emptyDoc((key) => key);
	doc.clips.push({ id: 's1', start: 0, dur: 4, engine: { profile: 'Ref2VA', bogus: true } }, { id: 's2', start: 4, dur: 4 });
	const next = migrate(doc);
	assert.deepEqual([next.clips[0].engine, 'engine' in next.clips[1]], [{ profile: 'Ref2VA' }, false]);
	assert.ok(!('hybrid' in next) && !('profiles' in next));
	const old = { ...emptyDoc((key) => key), hybrid: { continuite: 80, identite: 55, audio: 10, mouvement: 40, style: 50 }, profiles: [] };
	assert.deepEqual([migrate(old).hybrid, migrate(old).profiles], [old.hybrid, []]);
});

test('engine: the shot editor reads and writes the shot settings in one step, without marking the takes', () => {
	const doc = { engine: { variants: 2, preset: WAN, model: null }, direction: { mode: 'FL2VA' }, prompts: [{ id: 'p1', shotId: 's1', start: 0, dur: 4, text: 'A lighthouse.' }], frames: [], references: [] };
	const clip = { id: 's1', start: 0, dur: 4, engine: { quality: 'final' } };
	const before = shotDraft(doc, clip, doc.engine);
	assert.deepEqual(before.engine, { quality: 'final' });

	const result = applyShotDraft(doc, clip, before, { ...before, engine: { preset: LTX, model: null, backend: 'b-local', seed: 42 } }, { makeId: () => 'x', engine: doc.engine });

	assert.deepEqual(result, { changed: false, resized: false, released: null });
	assert.deepEqual(clip.engine, { preset: LTX, model: null, backend: 'b-local', seed: 42 });
	assert.equal(revisionOf(clip), 0);
	applyShotDraft(doc, clip, shotDraft(doc, clip, doc.engine), { ...shotDraft(doc, clip, doc.engine), engine: {} }, { makeId: () => 'x', engine: doc.engine });
	assert.ok(!('engine' in clip));
});

const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;
const STATUS_BAR = new URL('../components/shell/StatusBar.svelte', import.meta.url).href;
const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

function scene() {
	project.id = 'p1';
	project.version = 1;
	project.status = 'saved';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }, { id: LTX, name: 'LTX 2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	Object.assign(ui, { workspace: 'storyboard', storyView: 'grid', selection: null, picked: [], dirty: false, modal: null, menuOpen: null, toasts: [] });
	Object.assign(ui.production, { target: 'sequence', quality: 'draft', state: 'ready', progress: 0, running: 0, step: '', lastCount: 0, startedAt: null, lastSeconds: null, failed: 0, failedVariant: null, failedTake: null });
	doc.engine = { backend: 'native', preset: WAN, model: null, variants: 2 };
	doc.clips = [
		{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo', take: null, assetId: null },
		{ id: 's2', start: 4, dur: 4, label: 'Two', stage: 'todo', take: null, assetId: null }
	];
	doc.prompts = doc.clips.map((c, i) => ({ id: `p${i + 1}`, shotId: c.id, start: c.start, dur: 4, strength: 75, text: `Shot ${i + 1} at dawn.` }));
	setTakes('p1', []);
}

test('engine: the request keeps its shape, the shot settings travel in the saved document', async () => {
	scene();
	setShotEngine(doc.clips[1], { preset: LTX, model: null, seed: 7 });
	assert.deepEqual(shotEngineOf(doc.clips[1]), { preset: LTX, model: null, seed: 7 });

	const request = estimateRequest();
	assert.deepEqual(request.body, { shots: ['s1', 's2'], quality: 'draft', variants: 2, preset_id: WAN, model_id: null });
	assert.deepEqual(JSON.parse(request.key), ['p1', 1, request.body]);

	const saved = [];
	bindClient({
		async saveProject(id, next, version) {
			saved.push([id, next, version]);
			return { ok: true, data: { version: version + 1, updatedAt: '2026-10-29T10:00:00Z' } };
		}
	});
	ui.dirty = true;
	assert.equal(await flushSave(), true);
	assert.equal(saved.length, 1);
	assert.deepEqual([saved[0][0], saved[0][2], saved[0][1].clips[1].engine, saved[0][1].clips[0].engine], ['p1', 1, { preset: LTX, model: null, seed: 7 }, undefined]);
	assert.equal(project.version, 2);
	bindClient(null);
});

test('workshop: the advanced workshop, its commands, the local window queue and the Hybrid weights are gone', async () => {
	assert.equal(existsSync(new URL('../components/modals/AdvancedWorkshop.svelte', import.meta.url)), false);
	assert.equal(commandById('advanced'), null);
	assert.equal(commandById('hybrid'), null);
	scene();
	commandById('engine').run();
	assert.deepEqual(ui.modal, { type: 'engine', preset: null });
	assert.equal(commandById('queue').keys, 'alt+mod+g');
	ui.menuOpen = null;
	commandById('queue').run();
	assert.equal(ui.menuOpen, QUEUE_MENU);
	assert.ok(!('queue' in ui));
	const fresh = emptyDoc((key) => key);
	assert.ok(!('hybrid' in fresh) && !('profiles' in fresh));
	ui.modal = { type: 'advanced' };
	const html = clean(await renderComponent(MODALS));
	assert.equal(textOf(html), '');
	assert.doesNotMatch(html, /role="dialog"/);
	ui.modal = null;
});

test('queue: the queue opens as a list above the queue button of the production deck, from the deck, the status bar and the Production menu', async () => {
	scene();
	const waiting = (id, shotId, extra = {}) => ({ id, shotId, status: 'queued', label: 'draft', quality: 'draft', variant: 'A', url: null, generationId: null, priority: 0, progress: 0, createdAt: at(1), ...extra });
	setTakes('p1', [waiting('q1', 's1'), waiting('r1', 's2', { status: 'running', generationId: 'g1', progress: 40, step: 'Sampling', createdAt: at(0) }), waiting('q2', 's1', { variant: 'B', createdAt: at(2) })]);

	ui.workspace = 'timeline';
	openQueue();
	assert.deepEqual([ui.workspace, ui.menuOpen], ['director', QUEUE_MENU]);
	ui.workspace = 'storyboard';
	ui.menuOpen = null;
	openQueue();
	assert.deepEqual([ui.workspace, ui.menuOpen], ['storyboard', QUEUE_MENU]);
	assert.equal(commandById('queue').menu, t('shell.menu.production'));

	const deck = clean(await renderComponent(DECK));
	assert.match(deck, new RegExp(`<button type="button" class="vp-deck-icon-button" aria-label="${escaped(t('production.queueLabel'))}" aria-expanded="true" aria-haspopup="dialog">`));
	assert.match(deck, new RegExp(`<div class="vp-menu overflow-auto" role="dialog" aria-label="${escaped(t('panels.queue.title'))}"[^>]*><div class="flex flex-col gap-3 p-3">`));
	const ordered = queueOrder(takeStore.list);
	assert.deepEqual([...deck.matchAll(/data-take="([^"]*)"/g)].map((m) => m[1]), ordered.map((take) => take.id));
	assert.equal(ordered[0].id, 'r1');
	assert.ok(deck.includes(t('panels.queue.count', { count: 3 })));
	const buttons = hostUis(deck, 'IconButton');
	assert.deepEqual(buttons.filter((p) => p.label === t('panels.queue.cancel', { variant: 'A' })).length, 2);
	assert.deepEqual(ordered.map((take) => buttons.find((p) => p.label === t('panels.queue.prioritize', { variant: take.variant }) && p.disabled === !canPrioritize(take, ordered)) !== undefined), [true, true, true]);
	assert.match(deck, /role="progressbar"[^>]*aria-valuenow="40"/);

	ui.menuOpen = null;
	const closed = clean(await renderComponent(DECK));
	assert.match(closed, /aria-expanded="false" aria-haspopup="dialog"/);
	assert.doesNotMatch(closed, /data-take=/);

	const bar = clean(await renderComponent(STATUS_BAR));
	assert.match(bar, new RegExp(`<button type="button" class="flex h-6 items-center gap-1 hover:text-fg hover:underline" data-vp-menu="">.*?${escaped(t('shell.status.queue', { count: 3 }))}</button>`));
	setTakes('p1', []);
	assert.doesNotMatch(clean(await renderComponent(STATUS_BAR)), /data-vp-menu/);
});

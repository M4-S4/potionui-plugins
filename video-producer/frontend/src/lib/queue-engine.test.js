import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { createClient, normalizeQueue, normalizeTake } from './api.js';
import { SEED_MAX, effectiveEngine, hasOwnEngine, migrateShotEngine, projectQuality, randomSeed, setShotEngine, shotEngineOf, validSeed } from './engine.js';
import { canPrioritize, handedOver, isWaiting, prioritized, queueOrder } from './queue.js';
import { applyShotDraft, revisionOf, shotDraft } from './shots.js';
import { emptyDoc, migrate } from './starter.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const WAN = '01KX47WANVIDEO0000000000TV';
const LTX = '01KX47LTX25VIDEO00000000TV';
const at = (n) => `2026-10-23T10:00:0${n}+00:00`;
const take = (id, extra = {}) => ({ id, shotId: 's1', status: 'queued', generationId: null, priority: 0, createdAt: at(0), ...extra });

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

test('engine: the request keeps its shape, the shot settings travel in the saved document', () => {
	const production = source('./production.svelte.js');
	const body = production.slice(production.indexOf('function requestBody('), production.indexOf('export function estimateRequest('));

	assert.match(body, /shots: clips\.map\(\(c\) => c\.id\), quality, variants: counts\.variants, preset_id: option\.preset, model_id: option\.model/);
	assert.doesNotMatch(body, /engine/);
	assert.match(production, /const saved = await flushSave\(\);/);
});

test('workshop: the advanced workshop, its commands, the local window queue and the Hybrid weights are gone', () => {
	assert.equal(existsSync(new URL('../components/modals/AdvancedWorkshop.svelte', import.meta.url)), false);
	const commands = source('./commands.js');
	for (const id of ['advanced', 'hybrid']) assert.doesNotMatch(commands, new RegExp(`command\\('${id}'`));
	assert.match(commands, /command\('engine', openEngineSettings\)/);
	assert.match(commands, /command\('queue', openQueue, \{ keys: 'alt\+mod\+g' \}\)/);
	const production = source('./production.svelte.js');
	assert.doesNotMatch(production, /queueWindow|generateQueue|production\.queue/);
	assert.doesNotMatch(source('./state.svelte.js'), /queue: \[\]/);
	for (const path of ['../components/panels/DirectorDock.svelte', '../components/production/ProductionBar.svelte', '../components/modals/Modals.svelte']) {
		assert.doesNotMatch(source(path), /type: 'advanced'|AdvancedWorkshop|doc\.hybrid|doc\.profiles/, path);
	}
	assert.doesNotMatch(source('./starter.js'), /hybrid|profiles:/);
});

test('queue: the dock lists the queue in a tab next to Results, and the Production bar opens it', () => {
	const dock = source('../components/panels/DirectorDock.svelte');
	assert.match(dock, /\{ id: 'results', label: t\('panels\.dock\.tab\.results'\), badge: takeCount \|\| null \},\n\t\t\{ id: 'queue', label: t\('panels\.dock\.tab\.queue'\), badge: queued \|\| null \}/);
	assert.match(dock, /\{:else if ui\.dockTab === 'queue'\}\n\t\t<QueuePanel \/>/);
	assert.match(source('../components/production/ProductionBar.svelte'), /onclick: openQueue/);
	const panel = source('../components/panels/QueuePanel.svelte');
	assert.match(panel, /const ordered = \$derived\(queueOrder\(takeStore\.list\)\);/);
	assert.match(panel, /onclick: \(\) => prioritizeTake\(take\)/);
	assert.match(panel, /onclick: \(\) => cancelTake\(take\)/);
});

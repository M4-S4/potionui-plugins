import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent, textOf } from './svelte-harness.js';

const notes = [];
window.__potionui.notifications.toast = (level, message) => notes.push(message);
globalThis.document = { body: {}, querySelector: () => null };

const { ui, applyMe, dispose } = await import('./state.svelte.js');
const { bindClient, openProject } = await import('./project.svelte.js');
const { startProduction, startGeneration, readiness, refusal, refreshEstimate, scheduleEstimate, estimateRequest, tryAgain } = await import('./production.svelte.js');
const { takeStore } = await import('./takes.svelte.js');
const { normalizeTake } = await import('./api.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { t } = await import('../i18n/index.svelte.js');

const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;
const WAN = '01KX47WANVIDEO0000000000TV';
const UNRECORDED = { code: 'quota_unrecorded', message: 'The GPU minutes of this take could not be reserved: try again in a moment.', data: { shot_id: 's2' } };
const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const inlineActions = (html) => [...clean(html).matchAll(/<button type="button" class="vp-deck-inline-action[^"]*"[^>]*>(.*?)<\/button>/g)].map((m) => textOf(m[1]));
const server = { docs: new Map(), refuse: 0, blocks: [], sent: [], estimates: 0 };

bindClient({
	async getProject(id) {
		const { doc, version } = server.docs.get(id);
		return { ok: true, data: { id, name: 'Film', version, doc: copy(doc), createdAt: null, updatedAt: null, unchanged: false } };
	},
	async saveProject(id, next) {
		const stored = server.docs.get(id);
		stored.doc = copy(next);
		stored.version += 1;
		return { ok: true, data: { id, name: 'Film', version: stored.version, doc: null, createdAt: null, updatedAt: null, unchanged: false } };
	},
	async listTakes() {
		return { ok: true, data: [] };
	},
	async listRenditions() {
		return { ok: true, data: [] };
	},
	async queue() {
		return { ok: true, data: { takes: [], keyframes: [], slots: null, elsewhere: null, positions: {} } };
	},
	async estimate() {
		server.estimates += 1;
		return { ok: true, data: { shots: [], vram: null, time: { seconds: null, samples: 0 }, quota: null, cost: null, blocks: copy(server.blocks), warnings: [] } };
	},
	async generate(id, body) {
		server.sent.push(copy(body));
		if (server.refuse > 0) {
			server.refuse -= 1;
			return { ok: false, error: { status: 409, code: 'blocked', message: '', data: { blocks: [copy(UNRECORDED)] } } };
		}
		return { ok: true, data: body.shots.map((shotId) => normalizeTake({ id: `t-${server.sent.length}-${shotId}`, project_id: id, shot_id: shotId, generation_id: null, kind: 'render', quality: body.quality, status: 'queued', variant: 'A', label: 'draft', created_at: '2026-10-30T10:00:00Z' })) };
	},
	async cancelTake() {
		return { ok: false, error: { status: 404 } };
	},
	saveLastProject() {}
});
const stop = startProduction();
applyMe({
	engines: [{ id: 'native', name: 'Local Generation', kind: 'local' }],
	presets: [{ id: WAN, name: 'Wan', video: true, cloud: false, profiles: ['FL2VA'], limits: { maxDuration: 10 } }]
});

after(() => {
	stop();
	dispose();
	delete globalThis.document;
});

async function open(id) {
	const start = emptyDoc((key) => key);
	start.direction.univers = 'A harbour at dawn.';
	start.engine = { ...start.engine, preset: WAN, model: null, backend: 'native' };
	start.clips = ['s1', 's2'].map((shotId, i) => newClip({ id: shotId, label: `Shot ${i + 1}`, start: i * 4, dur: 4 }));
	start.prompts = start.clips.map((c, i) => ({ id: `p${i + 1}`, shotId: c.id, start: c.start, dur: 4, strength: 75, text: `Shot ${i + 1} at dawn.` }));
	server.docs.set(id, { doc: start, version: 1 });
	assert.equal((await openProject(id)).ok, true);
	while (!takeStore.loaded) await settle();
	await settle();
	Object.assign(ui, { workspace: 'storyboard', modal: null, paletteOpen: false, hostModal: false, menuOpen: null, deckDrawer: false });
	ui.production.target = 'clip';
	ui.production.quality = 'draft';
	ui.selection = { kind: 'clip', id: 's2' };
	Object.assign(server, { refuse: 0, blocks: [], sent: [] });
	notes.length = 0;
}

test('refusal flow: a generation refused because its GPU minutes could not be reserved stays in the deck, besides the toast, with Try again in place of Edit the shot, and Try again sends it again', async () => {
	await open('p-refused');
	server.refuse = 1;
	await startGeneration();
	assert.deepEqual(server.sent.map((body) => body.shots), [['s2']]);
	assert.deepEqual(notes, [t('generation.block.quotaUnrecorded')]);
	const ready = readiness();
	assert.deepEqual(ready.missing, []);
	assert.deepEqual(ready.refused, { text: t('generation.block.quotaUnrecorded'), reason: { code: 'quota_unrecorded', shotId: 's2' } });
	const html = await renderComponent(DECK);
	assert.match(html, /class="vp-deck" role="region"[^>]*data-state="blocked"/);
	assert.match(textOf(html), new RegExp(escaped(t('production.deck.blocked'))));
	assert.match(textOf(html), new RegExp(escaped(t('generation.block.quotaUnrecorded'))));
	assert.deepEqual(inlineActions(html), [t('production.deck.unblock.retry')]);
	assert.doesNotMatch(html, /class="vp-deck-generate"[^>]*disabled=""/);
	await tryAgain();
	assert.deepEqual(server.sent.map((body) => body.shots), [['s2'], ['s2']]);
	assert.equal(refusal.key, null);
	assert.equal(readiness().refused, null);
	assert.doesNotMatch(await renderComponent(DECK), /data-state="blocked"/);
});

test('refusal flow: the refusal leaves the deck as soon as the request changes and does not come back with it, and a new run clears it', async () => {
	await open('p-changed');
	server.refuse = 1;
	await startGeneration();
	scheduleEstimate(estimateRequest());
	assert.equal(readiness().refused?.reason.code, 'quota_unrecorded');
	ui.production.quality = 'final';
	assert.equal(readiness().refused, null);
	scheduleEstimate(estimateRequest());
	ui.production.quality = 'draft';
	assert.equal(readiness().refused, null);
	assert.equal(refusal.key, null);
	server.refuse = 1;
	await startGeneration();
	assert.ok(readiness().refused);
	ui.selection = { kind: 'clip', id: 's1' };
	assert.equal(readiness().refused, null);
	ui.selection = { kind: 'clip', id: 's2' };
	await startGeneration();
	assert.equal(readiness().refused, null);
});

test('refusal flow: the same block met in the estimate offers Try again too, which asks for the estimate again and generates nothing', async () => {
	await open('p-estimate');
	server.blocks = [UNRECORDED];
	refreshEstimate();
	await settle();
	assert.deepEqual(readiness().reasons.map((reason) => [reason.code, reason.shotId]), [['quota_unrecorded', 's2']]);
	const html = await renderComponent(DECK);
	assert.deepEqual(inlineActions(html), [t('production.deck.unblock.retry')]);
	assert.match(html, /class="vp-deck-generate"[^>]*disabled=""/);
	server.blocks = [];
	const asked = server.estimates;
	tryAgain();
	await settle();
	assert.equal(server.estimates, asked + 1);
	assert.deepEqual(readiness().missing, []);
	assert.deepEqual(server.sent, []);
});

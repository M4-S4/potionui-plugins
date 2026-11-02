import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

const hooks = `
import { readFile } from 'node:fs/promises';
import { compileModule } from ${JSON.stringify(import.meta.resolve('svelte/compiler'))};
export async function load(url, context, next) {
	if (url.endsWith('.svelte.js')) return { format: 'module', shortCircuit: true, source: compileModule(await readFile(new URL(url), 'utf8'), { generate: 'client', filename: url }).js.code };
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

const { doc, act, undo, dispose } = await import('./state.svelte.js');
const { bindClient, openProject } = await import('./project.svelte.js');
const { startProduction } = await import('./production.svelte.js');
const { takeStore } = await import('./takes.svelte.js');
const { retrieveImages, neighborsOf } = await import('./shotimages.svelte.js');
const { applyShotDraft, shotDraft } = await import('./shots.js');
const { chainState, setChain } = await import('./chain.js');
const { framesOf } = await import('./seam.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { ulid } = await import('./ulid.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const projects = new Map();
const calls = [];

bindClient({
	async getProject(id) {
		const p = projects.get(id);
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null, unchanged: false } };
	},
	async saveProject(id, next) {
		const p = projects.get(id);
		p.doc = copy(next);
		p.version += 1;
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: null, createdAt: null, updatedAt: null, unchanged: false } };
	},
	async listTakes(id) {
		return { ok: true, data: projects.get(id).takes.map((x) => copy(x)) };
	},
	async listRenditions() {
		return { ok: true, data: [] };
	},
	async queue() {
		return { ok: true, data: { takes: [], keyframes: [], slots: null, elsewhere: null, positions: {} } };
	},
	async endFrame(id, shotId) {
		calls.push(['end', shotId]);
		const clip = projects.get(id).doc.clips.find((c) => c.id === shotId);
		return { ok: true, data: { media: { itemId: 'item-end', url: '/api/media/uploads/end.png', filename: 'take-frame-4s.png', width: 832, height: 480 }, source: { shotId, takeId: 't1', assetId: clip.assetId, at: clip.srcIn + clip.dur } } };
	},
	async startFrame(id, shotId) {
		calls.push(['start', shotId]);
		const clip = projects.get(id).doc.clips.find((c) => c.id === shotId);
		return { ok: true, data: { media: { itemId: 'item-start', url: '/api/media/uploads/start.png', filename: 'take-frame-0.5s.png', width: 832, height: 480 }, source: { shotId, takeId: 't3', assetId: clip.assetId, at: clip.srcIn } } };
	},
	async labelTake() {
		return { ok: false, error: { code: 'x' } };
	},
	saveLastProject() {}
});
const stop = startProduction();
globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast() {} } } };

after(() => {
	stop();
	dispose();
	delete globalThis.window;
});

const video = (id, takeId) => ({ id, kind: 'video', name: id, src: `/m/${id}.mp4`, origin: { kind: 'history', generationId: `g-${takeId}`, fileId: '1' }, srcDur: 5, width: 832, height: 480, fps: 25, res: '832×480', generated: true, quality: 'draft', resultId: takeId, role: null, synth: null, transcript: null, character: null, lipSync: null });

async function open(id, { chain = true, middle = {}, takes = [] } = {}) {
	const start = emptyDoc((key) => key);
	start.assets.push(video('v1', 't1'), video('v3', 't3'));
	start.clips = [newClip({ id: 's1', start: 0, dur: 4, assetId: 'v1', stage: 'draft' }), newClip({ id: 's2', start: 4, dur: 4, ...middle }), newClip({ id: 's3', start: 8, dur: 4, srcIn: 0.5, assetId: 'v3', stage: 'draft' })];
	if (!chain) setChain(start, false);
	projects.set(id, { doc: start, version: 1, takes });
	assert.equal((await openProject(id)).ok, true);
	while (!takeStore.loaded) await settle();
	await settle();
}

function save(draft, baseline) {
	const clip = doc.clips.find((c) => c.id === 's2');
	act(() => applyShotDraft(doc, clip, baseline, copy(draft), { makeId: ulid, engine: doc.engine }));
}

test('retrieving both frames fills the draft, keeps the link of the shot and saving it is undone step by step', async () => {
	await open('p1');
	const clip = doc.clips.find((c) => c.id === 's2');
	const baseline = shotDraft(doc, clip, doc.engine);
	const draft = copy(baseline);

	await retrieveImages(clip, draft, 'neighbors');

	assert.deepEqual(calls.splice(0), [['end', 's1'], ['start', 's3']]);
	const first = doc.assets.find((a) => a.id === draft.first);
	const last = doc.assets.find((a) => a.id === draft.last);
	assert.deepEqual(first.frameOf, { shotId: 's1', takeId: 't1', assetId: 'v1', at: 4 });
	assert.deepEqual(last.frameOf, { shotId: 's3', takeId: 't3', assetId: 'v3', at: 0.5 });
	assert.equal(draft.firstFromPrevious, null);
	const sources = neighborsOf(clip, draft);
	assert.deepEqual([sources.previous.state, sources.next.state], ['current', 'current']);

	save(draft, baseline);
	assert.deepEqual([framesOf(doc, 's2', 'first')[0].assetId, framesOf(doc, 's2', 'last')[0].assetId], [first.id, last.id]);
	assert.equal(chainState(doc, 1).state, 'fresh');
	assert.equal('firstFromPrevious' in doc.clips[1], false);

	undo();
	assert.deepEqual([framesOf(doc, 's2', 'first').length, framesOf(doc, 's2', 'last').length], [0, 0]);
	undo();
	undo();
	assert.equal(doc.assets.some((a) => a.id === first.id || a.id === last.id), false);
});

test('with the project link off, retrieving the previous frame turns the link of the shot on, as its switch does', async () => {
	await open('p2', { chain: false });
	const clip = doc.clips.find((c) => c.id === 's2');
	const baseline = shotDraft(doc, clip, doc.engine);
	const draft = copy(baseline);

	await retrieveImages(clip, draft, 'previous');
	save(draft, baseline);

	assert.equal(doc.clips[1].firstFromPrevious, true);
	assert.equal(chainState(doc, 1).state, 'fresh');
	undo();
	assert.equal('firstFromPrevious' in doc.clips[1], false);
	calls.length = 0;
});

test('a previous shot still being generated is linked: the shot keeps no start image and waits for its take', async () => {
	const running = { id: 't9', projectId: 'p3', shotId: 's1', kind: 'render', status: 'running', quality: 'draft', variant: 'A', label: 'draft', url: null, createdAt: '2026-10-26T10:00:00Z', chain: null };
	await open('p3', { chain: false, takes: [running] });
	doc.clips[0].assetId = null;
	const clip = doc.clips.find((c) => c.id === 's2');
	const baseline = shotDraft(doc, clip, doc.engine);
	const draft = { ...copy(baseline), first: 'v3' };

	assert.equal(neighborsOf(clip, draft).previous.state, 'pending');
	await retrieveImages(clip, draft, 'previous');

	assert.deepEqual([draft.first, draft.firstFromPrevious], [null, true]);
	assert.equal(neighborsOf(clip, draft).previous.state, 'linked');
	assert.deepEqual(calls, []);
});

test('the first frame of a still is the still itself, copied once with where it was taken', async () => {
	await open('p4');
	doc.assets.push({ ...video('img', null), kind: 'image', src: '/m/img.png', generated: false, resultId: null, origin: { kind: 'library', itemId: 'it-img' } });
	doc.clips[2].assetId = 'img';
	const clip = doc.clips.find((c) => c.id === 's2');
	const draft = copy(shotDraft(doc, clip, doc.engine));

	await retrieveImages(clip, draft, 'next');
	const kept = draft.last;
	draft.last = null;
	await retrieveImages(clip, draft, 'next');

	assert.equal(draft.last, kept);
	assert.deepEqual(doc.assets.find((a) => a.id === kept).frameOf, { shotId: 's3', takeId: null, assetId: 'img', at: null });
	assert.equal(doc.assets.filter((a) => a.frameOf?.assetId === 'img').length, 1);
	assert.deepEqual(calls, []);
});

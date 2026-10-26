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

const { doc, undo, history, dispose } = await import('./state.svelte.js');
const { bindClient, openProject, flushSave } = await import('./project.svelte.js');
const { startProduction } = await import('./production.svelte.js');
const { takeStore, upsertTake } = await import('./takes.svelte.js');
const { setShotChaining, waitText } = await import('./chain.svelte.js');
const { chainState } = await import('./chain.js');
const { seamImage } = await import('./seam.js');
const { emptyDoc, newClip } = await import('./starter.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const projects = new Map();

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
	async queue(id) {
		const active = projects.get(id).takes.filter((x) => x.status === 'queued' || x.status === 'running');
		return { ok: true, data: { takes: active.map((x) => copy(x)), keyframes: [], slots: null, elsewhere: null, positions: {} } };
	},
	async labelTake(id, takeId, label) {
		const take = projects.get(id).takes.find((x) => x.id === takeId);
		return { ok: true, data: { ...copy(take), label } };
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

const FRAME = { itemId: 'item-1', url: '/api/media/uploads/wan-frame-4s.png', filename: 'wan-frame-4s.png', width: 832, height: 480 };

function take(id, shotId, extra = {}) {
	return { id, projectId: null, shotId, generationId: `g-${id}`, fileId: '1', kind: 'render', quality: 'draft', status: 'done', variant: 'A', label: 'draft', chosen: false, flag: null, url: `/media/${id}.mp4`, thumbUrl: null, durationS: 4, width: 832, height: 480, fps: 16, priority: 0, createdAt: '2026-10-26T10:00:00Z', chain: null, ...extra };
}

function chained(id, after, extra = {}) {
	const source = { shotId: 's1', takeId: after, assetId: `gen-${after}`, at: 4 };
	return take(id, 's2', { status: 'running', url: null, generationId: `g-${id}`, chain: { previous: 's1', after, state: 'taken', batch: 'b1', source, frame: { ...FRAME, itemId: `item-${id}` } }, ...extra });
}

async function open(id, shots, takes) {
	const start = emptyDoc((key) => key);
	start.clips = shots.map((shot, i) => newClip({ start: i * 4, dur: 4, ...shot }));
	projects.set(id, { doc: start, version: 1, takes: takes.map((x) => ({ ...x, projectId: id })) });
	const result = await openProject(id);
	assert.equal(result.ok, true);
	while (!takeStore.loaded) await settle();
	await settle();
	return projects.get(id);
}

const firstOf = (shotId) => seamImage(doc, shotId, 'first');

test('opening a project whose chained take got its image while the page was closed places it as the first frame, without an undo step', async () => {
	const stored = await open('p-closed', [{ id: 's1' }, { id: 's2' }], [take('t1', 's1'), chained('t2', 't1')]);

	assert.equal(firstOf('s2').id, 'chain-t2');
	assert.deepEqual(firstOf('s2').frameOf, { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4 });
	assert.equal(doc.clips[0].take, 't1');
	assert.equal(chainState(doc, 1).state, 'fresh');
	assert.equal(history.canUndo, false);
	assert.equal(await flushSave(), true);
	assert.ok(stored.doc.assets.some((a) => a.id === 'chain-t2'));
});

test('an image taken while the page is open is one undoable change, and a later poll does not put it back', async () => {
	await open('p-live', [{ id: 's1' }, { id: 's2' }], [take('t1', 's1')]);
	assert.equal(firstOf('s2'), null);

	upsertTake(chained('tl', 't1'));
	assert.equal(firstOf('s2').id, 'chain-tl');
	assert.equal(history.canUndo, true);

	undo();
	assert.equal(firstOf('s2'), null);
	upsertTake(chained('tl', 't1', { progress: 40 }));
	assert.equal(firstOf('s2'), null);
});

test('the second take of a batch keeps the image of the first, a later batch replaces it', async () => {
	await open('p-batch', [{ id: 's1' }, { id: 's2' }], [take('t1', 's1'), take('t9', 's1', { variant: 'B' })]);

	upsertTake(chained('ta', 't1'));
	upsertTake(chained('tb', 't9', { variant: 'B' }));
	assert.equal(firstOf('s2').id, 'chain-ta');

	upsertTake(chained('tc', 't9', { createdAt: '2026-10-26T11:00:00Z', chain: { ...chained('tc', 't9').chain, batch: 'b2' } }));
	assert.equal(firstOf('s2').id, 'chain-tc');
});

test('a waiting take says what it waits for, and turning the shot off drops its first frame in one undoable step', async () => {
	const waiting = take('tw', 's2', { status: 'queued', url: null, generationId: null, variant: 'B', chain: { previous: 's1', after: 't9', state: 'waiting', batch: 'b1', source: null, frame: null } });
	await open('p-off', [{ id: 's1', label: 'Harbour' }, { id: 's2' }], [take('t1', 's1'), chained('to', 't1'), take('t9', 's1', { status: 'running', url: null, variant: 'C' }), waiting]);
	assert.equal(waitText(takeStore.list.find((x) => x.id === 'tw')), 'Waiting for take C of “Harbour”');

	setShotChaining(doc.clips[1], false);
	assert.equal(doc.clips[1].firstFromPrevious, false);
	assert.equal(firstOf('s2'), null);
	assert.ok(doc.assets.some((a) => a.id === 'chain-to'));

	undo();
	assert.equal('firstFromPrevious' in doc.clips[1], false);
	assert.equal(firstOf('s2').id, 'chain-to');
});

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

const { doc, undo, redo, dispose } = await import('./state.svelte.js');
const { bindClient, openProject, flushSave } = await import('./project.svelte.js');
const { startProduction, useTake, insertResult, labelTake, assembleChosen, cancelTake } = await import('./production.svelte.js');
const { deleteAsset } = await import('./assets.svelte.js');
const { takeStore, upsertTake, takeById } = await import('./takes.svelte.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { marksOf } = await import('./labels.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function makeServer() {
	const projects = new Map();
	const labels = [];
	const client = {
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
			return { ok: true, data: projects.get(id).takes.map((x) => ({ ...x })) };
		},
		async listRenditions() {
			return { ok: true, data: [] };
		},
		async labelTake(id, takeId, label) {
			const take = projects.get(id).takes.find((x) => x.id === takeId);
			Object.assign(take, marksOf(label));
			labels.push([takeId, label]);
			return { ok: true, data: { ...take } };
		},
		async cancelTake() {
			return { ok: false, error: { status: 404, code: 'take_not_found', message: '', data: null } };
		},
		saveLastProject() {}
	};
	return { projects, labels, client };
}

const server = makeServer();
bindClient(server.client);
const stop = startProduction();
globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast() {} } } };

after(() => {
	stop();
	dispose();
	delete globalThis.window;
});

function take(id, shotId, extra = {}) {
	return { id, projectId: null, shotId, generationId: `g-${id}`, fileId: '1', kind: 'render', quality: 'draft', status: 'done', variant: 'A', label: 'draft', chosen: false, flag: null, url: `/media/${id}.mp4`, thumbUrl: null, durationS: 4, width: 832, height: 480, fps: 24, priority: 0, ...extra };
}

function project(id, shots, takes) {
	const start = emptyDoc((key) => key);
	start.clips = shots.map((shot, i) => newClip({ start: i * 4, dur: 4, ...shot }));
	server.projects.set(id, { doc: start, version: 1, takes: takes.map((x) => ({ ...x, projectId: id })) });
	return server.projects.get(id);
}

async function open(id) {
	const result = await openProject(id);
	assert.equal(result.ok, true);
	while (!takeStore.loaded) await settle();
	await settle();
}

async function reopen(id) {
	assert.equal(await flushSave(), true);
	await open(id);
}

const shot = (id) => doc.clips.find((c) => c.id === id);
const hasAsset = (id) => doc.assets.some((a) => a.id === id);
const assetCount = (id) => doc.assets.filter((a) => a.id === id).length;
const labelsOf = (takeId) => server.labels.filter(([id]) => id === takeId).map(([, label]) => label);

test('a removed take video stays out on reopen and on refresh, and its take is neither placed again nor labeled final', async () => {
	const stored = project('p-removed', [{ id: 's1', label: 'Harbour' }], [take('t1', 's1')]);
	await open('p-removed');
	assert.equal(hasAsset('gen-t1'), true);
	assert.deepEqual([shot('s1').take, shot('s1').stage], ['t1', 'draft']);
	assert.deepEqual(labelsOf('t1'), ['final']);

	assert.equal(await deleteAsset('gen-t1'), true);
	await settle();
	assert.equal(hasAsset('gen-t1'), false);
	assert.deepEqual([shot('s1').assetId, shot('s1').take, shot('s1').stage], [null, null, 'todo']);
	assert.deepEqual(doc.removedTakes, ['t1']);
	assert.deepEqual(labelsOf('t1'), ['final', 'draft']);

	await reopen('p-removed');
	assert.deepEqual(stored.doc.removedTakes, ['t1']);
	assert.equal(hasAsset('gen-t1'), false);
	assert.deepEqual([shot('s1').take, shot('s1').stage], [null, 'todo']);
	assert.deepEqual(doc.removedTakes, ['t1']);

	await cancelTake(takeById('t1'));
	assert.equal(hasAsset('gen-t1'), false);
	assert.equal(shot('s1').stage, 'todo');

	await reopen('p-removed');
	assert.equal(hasAsset('gen-t1'), false);
	assert.deepEqual(labelsOf('t1'), ['final', 'draft']);
});

test('a take that finishes after a removal still gets its video and lands in a shot to generate, page closed or open', async () => {
	const stored = project('p-new', [{ id: 's1' }, { id: 's2' }], [take('t1', 's1')]);
	await open('p-new');
	await deleteAsset('gen-t1');
	await flushSave();

	stored.takes.push(take('t2', 's1', { variant: 'B' }));
	await reopen('p-new');
	assert.equal(hasAsset('gen-t1'), false);
	assert.equal(hasAsset('gen-t2'), true);
	assert.deepEqual([shot('s1').take, shot('s1').stage], ['t2', 'draft']);
	assert.deepEqual(labelsOf('t2'), ['final']);

	stored.takes.push(take('t3', 's2'));
	await cancelTake(takeById('t2'));
	assert.equal(hasAsset('gen-t3'), true);
	assert.equal(shot('s2').take, 't3');
	assert.equal(hasAsset('gen-t1'), false);
	assert.deepEqual(doc.removedTakes, ['t1']);
});

test('choosing a removed take again puts its video back, forgets the removal, and Undo and Redo follow', async () => {
	project('p-choose', [{ id: 's1' }], [take('t1', 's1'), take('t2', 's1', { variant: 'B' })]);
	await open('p-choose');
	assert.equal(shot('s1').take, 't1');
	assert.equal(hasAsset('gen-t2'), true);
	await deleteAsset('gen-t1');
	await deleteAsset('gen-t2');
	assert.deepEqual(doc.removedTakes, ['t1', 't2']);
	await reopen('p-choose');
	assert.equal(shot('s1').stage, 'todo');

	useTake(shot('s1'), 't1');
	assert.equal(assetCount('gen-t1'), 1);
	assert.deepEqual([shot('s1').take, shot('s1').stage], ['t1', 'draft']);
	assert.deepEqual(doc.removedTakes, ['t2']);

	undo();
	assert.equal(hasAsset('gen-t1'), false);
	assert.equal(shot('s1').stage, 'todo');
	assert.deepEqual(doc.removedTakes, ['t1', 't2']);
	redo();
	assert.equal(shot('s1').take, 't1');
	assert.deepEqual(doc.removedTakes, ['t2']);

	insertResult('t2');
	assert.equal(shot('s1').take, 't2');
	assert.equal('removedTakes' in doc, false);
	await reopen('p-choose');
	assert.equal(assetCount('gen-t1'), 1);
	assert.equal(assetCount('gen-t2'), 1);
	assert.equal(shot('s1').take, 't2');
	assert.equal('removedTakes' in doc, false);

	await deleteAsset('gen-t1');
	await settle();
	labelTake(shot('s1'), takeById('t1'), 'final');
	assert.equal(shot('s1').take, 't1');
	assert.equal('removedTakes' in doc, false);
});

test('Assemble the chosen takes puts back a chosen take whose video was removed', async () => {
	project('p-assemble', [{ id: 's1' }], [take('t1', 's1')]);
	await open('p-assemble');
	await deleteAsset('gen-t1');
	await settle();
	upsertTake({ ...takeById('t1'), ...marksOf('final') });
	assembleChosen();
	assert.equal(assetCount('gen-t1'), 1);
	assert.equal(shot('s1').take, 't1');
	assert.equal('removedTakes' in doc, false);
});

test('Undo brings a removed take video back with no trace of the removal, and Redo removes it again for good', async () => {
	project('p-undo', [{ id: 's1' }], [take('t1', 's1')]);
	await open('p-undo');
	await deleteAsset('gen-t1');
	await settle();

	undo();
	await settle();
	assert.equal(assetCount('gen-t1'), 1);
	assert.deepEqual([shot('s1').take, shot('s1').stage], ['t1', 'draft']);
	assert.equal('removedTakes' in doc, false);
	assert.equal(labelsOf('t1').at(-1), 'final');

	redo();
	await settle();
	assert.equal(hasAsset('gen-t1'), false);
	assert.deepEqual(doc.removedTakes, ['t1']);
	await reopen('p-undo');
	assert.equal(hasAsset('gen-t1'), false);
	assert.equal(shot('s1').stage, 'todo');

	useTake(shot('s1'), 't1');
	await deleteAsset('gen-t1');
	undo();
	await reopen('p-undo');
	assert.equal(assetCount('gen-t1'), 1);
	assert.equal(shot('s1').take, 't1');
	assert.equal('removedTakes' in doc, false);
});

test('a final take whose video was removed is not placed again, even on a shot that is not to generate', async () => {
	const stored = project('p-final', [{ id: 's1' }], [take('t1', 's1'), take('t1f', 's1', { quality: 'final', parentTakeId: 't1' })]);
	await open('p-final');
	assert.equal(shot('s1').take, 't1f');
	await deleteAsset('gen-t1f');
	useTake(shot('s1'), 't1');
	await reopen('p-final');
	assert.deepEqual(stored.doc.removedTakes, ['t1f']);
	assert.equal(hasAsset('gen-t1f'), false);
	assert.deepEqual([shot('s1').take, shot('s1').stage], ['t1', 'draft']);
});

test('the takes of a deleted shot still bring their video once, and a removal of it holds', async () => {
	project('p-orphan', [], [take('t9', 'gone')]);
	await open('p-orphan');
	assert.equal(hasAsset('gen-t9'), true);
	await deleteAsset('gen-t9');
	await reopen('p-orphan');
	assert.equal(hasAsset('gen-t9'), false);
	assert.deepEqual(doc.removedTakes, ['t9']);
	assert.deepEqual(labelsOf('t9'), []);
});

test('a removed take the server no longer lists is forgotten when the takes are read again', async () => {
	const stored = project('p-prune', [{ id: 's1' }], [take('t1', 's1'), take('t2', 's1', { variant: 'B' })]);
	await open('p-prune');
	await deleteAsset('gen-t1');
	await deleteAsset('gen-t2');
	await reopen('p-prune');
	assert.deepEqual(doc.removedTakes, ['t1', 't2']);

	stored.takes = stored.takes.filter((x) => x.id !== 't1');
	await reopen('p-prune');
	assert.deepEqual(doc.removedTakes, ['t2']);
	assert.equal(hasAsset('gen-t2'), false);

	stored.takes = [];
	await cancelTake({ id: 'missing' });
	assert.equal('removedTakes' in doc, false);
	await flushSave();
	assert.equal('removedTakes' in stored.doc, false);
});

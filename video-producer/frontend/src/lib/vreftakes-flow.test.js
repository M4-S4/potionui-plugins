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

const toasts = [];
globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast: (level, message) => toasts.push(message) } } };

const { doc, ui, undo, redo, dispose } = await import('./state.svelte.js');
const { bindClient, openProject } = await import('./project.svelte.js');
const { startProduction } = await import('./production.svelte.js');
const { takeStore, takeById } = await import('./takes.svelte.js');
const { sendTakeToTrack, dropTakeOnTrack, takeChoices, addVideoTrack } = await import('./vreftracks.svelte.js');
const { takeTracks, vrefLabel } = await import('./vreftracks.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { marksOf, takeLabelOf } = await import('./labels.js');
const { t } = await import('../i18n/index.svelte.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

const projects = new Map();
const labels = [];
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
	saveLastProject() {}
});
const stop = startProduction();

after(() => {
	stop();
	dispose();
	delete globalThis.window;
});

function take(id, shotId, extra = {}) {
	return { id, projectId: null, shotId, generationId: `g-${id}`, fileId: '1', kind: 'render', quality: 'draft', status: 'done', variant: 'A', label: 'draft', chosen: false, flag: null, url: `/media/${id}.mp4`, thumbUrl: null, durationS: 3, width: 832, height: 480, fps: 24, priority: 0, ...extra };
}

async function open(id, takes) {
	const start = emptyDoc((key) => key);
	start.clips = [newClip({ id: 's1', start: 0, dur: 3 }), newClip({ id: 's2', start: 3, dur: 3 })];
	projects.set(id, { doc: start, version: 1, takes: takes.map((x) => ({ ...x, projectId: id })) });
	const result = await openProject(id);
	assert.equal(result.ok, true);
	while (!takeStore.loaded) await settle();
	await settle();
	labels.length = 0;
	toasts.length = 0;
	ui.vrefSound = false;
}

const shot = (id) => doc.clips.find((c) => c.id === id);
const undoable = () => ui.toasts.at(-1)?.message;
const labelsOf = (takeId) => labels.filter(([id]) => id === takeId).map(([, label]) => label);

test('vref takes: a placed take moves to a new track under its shot, freeing the shot, and Undo puts it back as the final take', async () => {
	await open('p-move', [take('t1', 's1')]);
	assert.deepEqual([shot('s1').take, takeLabelOf(takeById('t1'))], ['t1', 'final']);
	const choices = takeChoices(takeById('t1'));
	assert.deepEqual({ placed: choices.placed, span: choices.span, shot: choices.shot, targets: choices.targets, slot: choices.slot }, { placed: true, span: [0, 3], shot: '01', targets: [], slot: 1 });

	const done = sendTakeToTrack(takeById('t1'), { move: true });
	await settle();
	assert.equal(vrefLabel(done.track.slot), 'vref1');
	assert.deepEqual({ ...doc.vrefItems[0], id: undefined }, { id: undefined, track: done.track.id, assetId: 'gen-t1', start: 0, dur: 3, srcIn: 0, fromTake: 't1' });
	assert.deepEqual([shot('s1').assetId, shot('s1').take, shot('s1').stage], [null, null, 'todo']);
	assert.deepEqual(labelsOf('t1'), ['draft']);
	assert.deepEqual({ ...ui.selection }, { kind: 'vref', id: doc.vrefItems[0].id });
	assert.deepEqual(takeTracks(doc, 't1').map((track) => track.id), [done.track.id]);
	assert.equal(undoable(), t('lib.vref.take.moved', { variant: 'A', label: 'vref1', shot: '01' }));

	undo();
	await settle();
	assert.equal('vrefTracks' in doc, false);
	assert.equal('vrefItems' in doc, false);
	assert.deepEqual([shot('s1').take, shot('s1').stage], ['t1', 'draft']);
	assert.deepEqual(labelsOf('t1'), ['draft', 'final']);

	redo();
	await settle();
	assert.equal(doc.vrefItems.length, 1);
	assert.equal(shot('s1').take, null);
});

test('vref takes: Copy keeps the placed take on its shot, a take that is not placed is always copied, and a drop does what the menu does first', async () => {
	await open('p-copy', [take('t1', 's1'), take('t2', 's1', { variant: 'B' }), take('t3', 's2', { variant: 'C' })]);
	assert.deepEqual([shot('s1').take, shot('s2').take], ['t1', 't3']);
	const track = addVideoTrack();

	assert.equal(sendTakeToTrack(takeById('t1'), { trackId: track.id, move: false }).released, null);
	assert.equal(shot('s1').take, 't1');
	assert.deepEqual(labelsOf('t1'), []);
	assert.equal(undoable(), t('lib.vref.take.copied', { variant: 'A', label: 'vref1', shot: '01' }));

	const busy = takeChoices(takeById('t2'));
	assert.equal(busy.placed, false);
	assert.deepEqual(
		busy.targets.map((x) => [x.busy, x.reason]),
		[[true, t('lib.vref.take.busy', { label: 'vref1', shot: '01' })]]
	);
	assert.equal(sendTakeToTrack(takeById('t2'), { trackId: track.id, move: true }), null);
	assert.equal(toasts.at(-1), t('lib.vref.take.busy', { label: 'vref1', shot: '01' }));
	assert.equal(doc.vrefItems.length, 1);

	const second = sendTakeToTrack(takeById('t2'), { move: true });
	assert.equal(vrefLabel(second.track.slot), 'vref2');
	assert.equal(second.released, null);
	assert.equal(shot('s1').take, 't1');
	assert.equal(takeLabelOf(takeById('t2')), 'draft');

	const dropped = dropTakeOnTrack('t3', track.id);
	await settle();
	assert.deepEqual([dropped.item.start, dropped.item.fromTake], [3, 't3']);
	assert.deepEqual([shot('s2').take, shot('s2').stage], [null, 'todo']);
	assert.deepEqual(labelsOf('t3'), ['draft']);
	assert.equal(dropTakeOnTrack('missing', track.id), null);
});

test('vref takes: with its sound, a take also lays its sound on a reference sound track, reused while free and new where taken, in the same undo step', async () => {
	await open('p-sound', [take('t1', 's1'), take('t2', 's2', { variant: 'B' }), take('t3', 's1', { variant: 'C' })]);
	const lanes = doc.lanes.length;

	const first = sendTakeToTrack(takeById('t1'), { move: false, sound: true });
	assert.equal(doc.lanes.length, lanes + 1);
	assert.equal(first.lane.reference, true);
	assert.deepEqual({ ...doc.audio.at(-1), id: undefined }, { id: undefined, assetId: 'gen-t1', lane: first.lane.id, start: 0, dur: 3, srcIn: 0, fadeIn: 0, fadeOut: 0, gain: 0, fromTake: 't1' });

	ui.vrefSound = true;
	const second = dropTakeOnTrack('t2', first.track.id);
	assert.equal(second.lane.id, first.lane.id);
	assert.equal(doc.lanes.length, lanes + 1);
	assert.deepEqual([doc.audio.at(-1).start, doc.audio.at(-1).lane], [3, first.lane.id]);

	const third = sendTakeToTrack(takeById('t3'), { move: false, sound: true });
	assert.notEqual(third.lane.id, first.lane.id);
	assert.equal(doc.lanes.length, lanes + 2);
	assert.equal(undoable(), `${t('lib.vref.take.copied', { variant: 'C', label: 'vref2', shot: '01' })} ${t('lib.vref.take.withSound', { lane: 'A' + doc.lanes.length })}`);

	undo();
	assert.equal(doc.lanes.length, lanes + 1);
	assert.equal(doc.audio.filter((item) => item.fromTake).length, 2);
	assert.equal(doc.vrefTracks.length, 1);
});

test('vref takes: with three tracks the new track is offered greyed, and a take that is not finished goes nowhere', async () => {
	await open('p-full', [take('t1', 's1'), take('t2', 's2', { status: 'failed', url: null })]);
	addVideoTrack();
	addVideoTrack();
	addVideoTrack();
	assert.equal(takeChoices(takeById('t1')).slot, null);
	assert.equal(sendTakeToTrack(takeById('t1'), { move: true }), null);
	assert.equal(toasts.at(-1), t('timeline.vref.fullToast', { max: 3 }));
	assert.equal(shot('s1').take, 't1');
	assert.equal(takeChoices(takeById('t2')), null);
	assert.equal(sendTakeToTrack(takeById('t2'), { trackId: doc.vrefTracks[0].id }), null);
	assert.equal('vrefItems' in doc, false);
});

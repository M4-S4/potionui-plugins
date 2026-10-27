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

const asked = [];
let answer = true;
globalThis.window = { __potionui: { confirm: async (options) => (asked.push(options), answer), notifications: { toast() {} } } };
globalThis.document = { body: {}, querySelector: () => null };

const { doc, ui, replaceDoc, select, undo, history, deleteSelection, duplicateSelection, dispose } = await import('./state.svelte.js');
const { addTrackItem, addVideoTrack, placeOnTrack, setTrackRole, setTrackLength, toggleTrack, renameTrack, openTrackSettings } = await import('./vreftracks.svelte.js');
const { deleteAsset } = await import('./assets.svelte.js');
const { emptyDoc, newAsset, newClip } = await import('./starter.js');
const { t } = await import('../i18n/index.svelte.js');

after(() => {
	dispose();
	delete globalThis.window;
	delete globalThis.document;
});

function project() {
	const base = emptyDoc((key) => key);
	replaceDoc({
		...base,
		assets: [newAsset({ id: 'walk', kind: 'video', name: 'walk.mp4', src: '/media/walk.mp4', srcDur: 6 }), newAsset({ id: 'pic', kind: 'image', name: 'pic.png', src: '/media/pic.png' })],
		clips: [newClip({ id: 's1', start: 0, dur: 4 }), newClip({ id: 's2', start: 4, dur: 4 })],
		prompts: [{ id: 'p2', shotId: 's2', start: 4, dur: 4, strength: 75, text: 'She walks as in @vref1.' }]
	});
	asked.length = 0;
	answer = true;
}

test('vref flow: a track is added in the smallest free slot as one undo step, and the fourth one is offered greyed with its reason', () => {
	project();
	const first = addVideoTrack();
	assert.deepEqual({ slot: first.slot, role: first.role }, { slot: 1, role: 'motion' });
	assert.deepEqual({ ...ui.selection }, { kind: 'vtrack', id: first.id });
	undo();
	assert.equal('vrefTracks' in doc, false);
	addVideoTrack();
	addVideoTrack();
	assert.equal(addTrackItem().badge, 'vref3');
	addVideoTrack();
	const full = addTrackItem();
	assert.equal(full.disabled, true);
	assert.equal(full.hint, t('timeline.vref.full', { max: 3, first: 'vref1', second: 'vref2', third: 'vref3' }));
	assert.equal(addVideoTrack(), undefined);
	assert.equal(doc.vrefTracks.length, 3);
});

test('vref flow: a track takes a video at the drop point for the length of its source, and refuses an image', () => {
	project();
	const track = addVideoTrack();
	assert.equal(placeOnTrack(track.id, 'pic', 2), null);
	assert.equal('vrefItems' in doc, false);
	const end = placeOnTrack(track.id, 'walk', 3.013);
	assert.equal(end, 9);
	assert.deepEqual({ ...doc.vrefItems[0], id: undefined }, { id: undefined, track: track.id, assetId: 'walk', start: 3, dur: 6, srcIn: 0 });
	assert.deepEqual({ ...ui.selection }, { kind: 'vref', id: doc.vrefItems[0].id });
	assert.equal(duplicateSelection(), undefined);
	assert.equal(doc.vrefItems.length, 2);
	assert.equal(doc.vrefItems[1].start, 9);
	undo();
	select('vref', doc.vrefItems[0].id);
	deleteSelection();
	assert.equal('vrefItems' in doc, false);
	undo();
	assert.equal(doc.vrefItems.length, 1);
});

test('vref flow: the role, the length, the name and the switch of a track are each one undo step', () => {
	project();
	const track = addVideoTrack();
	const steps = () => history.canUndo;
	setTrackRole(track, 'continuation');
	assert.equal(doc.vrefTracks[0].role, 'continuation');
	setTrackLength(doc.vrefTracks[0], 73);
	assert.equal(doc.vrefTracks[0].seconds, 73 / 24);
	renameTrack(doc.vrefTracks[0], 'Walk');
	toggleTrack(doc.vrefTracks[0]);
	assert.equal(doc.vrefTracks[0].off, true);
	assert.ok(steps());
	undo();
	assert.equal('off' in doc.vrefTracks[0], false);
	undo();
	assert.equal(doc.vrefTracks[0].name, '');
	undo();
	assert.equal('seconds' in doc.vrefTracks[0], false);
	undo();
	assert.equal(doc.vrefTracks[0].role, 'motion');
	openTrackSettings(doc.vrefTracks[0], 'length');
	assert.deepEqual({ ...ui.vrefField }, { id: track.id, field: 'length' });
	assert.equal(ui.inspectorOpen, true);
});

test('vref flow: deleting a track asks first, names the shots that cite it, frees its slot and goes back with Undo', async () => {
	project();
	const track = addVideoTrack();
	placeOnTrack(track.id, 'walk', 0);
	doc.clips[0].referenceOverrides = { excludeVrefs: [track.id] };
	select('vtrack', track.id);
	answer = false;
	await deleteSelection();
	assert.equal(doc.vrefTracks.length, 1);
	answer = true;
	await deleteSelection();
	assert.equal(asked.length, 2);
	assert.equal(asked[1].title, t('lib.vref.deleteTitle', { label: 'vref1' }));
	assert.ok(asked[1].message.includes(t('lib.vref.deleteCited', { count: 1, label: 'vref1', shots: '02' })));
	assert.ok(asked[1].message.includes(t('lib.vref.deleteItems', { count: 1, track: 'vref1' })));
	assert.equal('vrefTracks' in doc, false);
	assert.equal('vrefItems' in doc, false);
	assert.equal('referenceOverrides' in doc.clips[0], false);
	assert.equal(ui.selection, null);
	undo();
	assert.equal(doc.vrefTracks[0].id, track.id);
	assert.equal(doc.vrefItems.length, 1);
	assert.deepEqual(doc.clips[0].referenceOverrides.excludeVrefs, [track.id]);
	assert.equal(addVideoTrack().slot, 2);
});

test('vref flow: removing a video from the Media lists the parts of tracks it feeds and removes them', async () => {
	project();
	const track = addVideoTrack();
	placeOnTrack(track.id, 'walk', 0);
	await deleteAsset('walk');
	assert.ok(asked.at(-1).message.includes(t('lib.media.use.vrefs', { count: 1 })));
	assert.equal('vrefItems' in doc, false);
	assert.equal(doc.vrefTracks.length, 1);
});

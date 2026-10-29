import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent } from './svelte-harness.js';
import { ADD_RANGE, RANGE, TOGGLE, inOrder, picking, pruned, ranged, toggled } from './picking.js';
import { pickMode } from './keyboard.js';

const ORDER = ['s1', 's2', 's3', 's4', 's5', 's6'];

globalThis.document = { body: {}, querySelector: () => null };

const { doc, ui, select, pickClip, pickedClips, deleteSelection, undo, act, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { handleKeydown } = await import('./commands.js');
const { t } = await import('../i18n/index.svelte.js');

after(() => {
	dispose();
	delete globalThis.document;
});

test('picking: Ctrl+click starts the set from the chosen shot, adds the clicked one and makes it the active shot', () => {
	assert.deepEqual(toggled(ORDER, [], 's2', 's5'), { picked: ['s2', 's5'], active: 's5' });
	assert.deepEqual(toggled(ORDER, ['s2', 's5'], 's5', 's1'), { picked: ['s1', 's2', 's5'], active: 's1' });
	assert.deepEqual(toggled(ORDER, [], null, 's3'), { picked: [], active: 's3' });
});

test('picking: Ctrl+click on a picked shot takes it out, one shot left is a plain selection, none left selects nothing', () => {
	assert.deepEqual(toggled(ORDER, ['s1', 's2', 's5'], 's5', 's2'), { picked: ['s1', 's5'], active: 's5' });
	assert.deepEqual(toggled(ORDER, ['s1', 's2', 's5'], 's5', 's5'), { picked: ['s1', 's2'], active: 's2' });
	assert.deepEqual(toggled(ORDER, ['s1', 's5'], 's5', 's1'), { picked: [], active: 's5' });
	assert.deepEqual(toggled(ORDER, [], 's3', 's3'), { picked: [], active: null });
});

test('picking: Shift+click picks every shot from the chosen one to the clicked one, in the order of the edit, and keeps the chosen one as anchor', () => {
	assert.deepEqual(ranged(ORDER, [], 's2', 's5'), { picked: ['s2', 's3', 's4', 's5'], active: 's2' });
	assert.deepEqual(ranged(ORDER, [], 's5', 's2'), { picked: ['s2', 's3', 's4', 's5'], active: 's5' });
	assert.deepEqual(ranged(ORDER, ['s2', 's3', 's4', 's5'], 's2', 's3'), { picked: ['s2', 's3'], active: 's2' });
	assert.deepEqual(ranged(ORDER, [], null, 's4'), { picked: [], active: 's4' });
	assert.deepEqual(ranged(ORDER, [], 's4', 's4'), { picked: [], active: 's4' });
});

test('picking: Ctrl+Shift+click adds the range to the shots already picked', () => {
	assert.deepEqual(ranged(ORDER, ['s1', 's6'], 's1', 's3', true), { picked: ['s1', 's2', 's3', 's6'], active: 's1' });
	assert.deepEqual(picking(ORDER, [], 's5', 's6', ADD_RANGE), { picked: ['s5', 's6'], active: 's5' });
	assert.deepEqual(picking(ORDER, [], 's5', 's6', RANGE), picking(ORDER, [], 's5', 's6', ADD_RANGE));
	assert.deepEqual(picking(ORDER, [], 's5', 's6', TOGGLE), { picked: ['s5', 's6'], active: 's6' });
});

test('picking: a shot that is gone is ignored, the set follows the edit after an undo, a redo or a move', () => {
	assert.deepEqual(toggled(ORDER, ['s1', 's2'], 's2', 'gone'), { picked: ['s1', 's2'], active: 's2' });
	assert.deepEqual(inOrder(['s3', 's1', 's2'], ['s1', 's2', 's3']), ['s3', 's1', 's2']);
	assert.deepEqual(pruned(['s1', 's3'], ['s1', 's2', 's3']), ['s1', 's3']);
	assert.deepEqual(pruned(['s1', 's3'], ['s1', 's2']), []);
});

test('picking: Ctrl (⌘ on a Mac) toggles, Shift picks a range, both add the range, Ctrl on a Mac is not a pick', () => {
	const e = (mods) => ({ ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...mods });
	assert.equal(pickMode(e({ ctrlKey: true }), false), 'toggle');
	assert.equal(pickMode(e({ metaKey: true }), true), 'toggle');
	assert.equal(pickMode(e({ ctrlKey: true }), true), null);
	assert.equal(pickMode(e({ shiftKey: true }), false), 'range');
	assert.equal(pickMode(e({ ctrlKey: true, shiftKey: true }), false), 'add');
	assert.equal(pickMode(e({}), false), null);
});

const GRID = new URL('../components/storyboard/StoryboardView.svelte', import.meta.url).href;
const BAND_LANES = new URL('../components/storyboard/BandLanes.svelte', import.meta.url).href;
const BAND_VIEW = new URL('../components/storyboard/BandView.svelte', import.meta.url).href;
const TIMELINE = new URL('../components/timeline/Timeline.svelte', import.meta.url).href;
const INSPECTOR = new URL('../components/inspector/Inspector.svelte', import.meta.url).href;

function shots() {
	project.id = 'p1';
	doc.clips = ORDER.map((id, i) => ({ id, start: i * 4, dur: 4, label: `Shot ${id.slice(1)}`, stage: 'todo', take: null, assetId: null }));
	doc.prompts = [];
	doc.frames = [];
	Object.assign(ui, { workspace: 'storyboard', storyView: 'grid', selection: null, picked: [], modal: null, paletteOpen: false, toasts: [] });
}

const key = (name) => ({ key: name, code: name, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, target: null, preventDefault() {} });

test('picking: the state keeps ui.selection as the active shot and the picked shots apart, any plain selection clears them', () => {
	shots();
	select('clip', 's1');
	assert.deepEqual([ui.selection, ui.picked], [{ kind: 'clip', id: 's1' }, []]);

	pickClip('s3', TOGGLE);
	let expected = picking(ORDER, [], 's1', 's3', TOGGLE);
	assert.deepEqual([ui.selection, ui.picked], [{ kind: 'clip', id: expected.active }, expected.picked]);
	assert.deepEqual(pickedClips().map((c) => c.id), expected.picked);
	pickClip('s5', RANGE);
	expected = picking(ORDER, expected.picked, expected.active, 's5', RANGE);
	assert.deepEqual([ui.selection.id, ui.picked], [expected.active, expected.picked]);

	select('clip', 's2');
	assert.deepEqual([ui.selection, ui.picked, pickedClips()], [{ kind: 'clip', id: 's2' }, [], []]);

	pickClip('s4', TOGGLE);
	assert.ok(ui.picked.includes('s4'));
	act(() => doc.clips.splice(3, 1));
	const stale = [...ui.picked];
	const order = doc.clips.map((c) => c.id);
	pickClip('s6', TOGGLE);
	expected = picking(order, pruned(order, stale), 's4', 's6', TOGGLE);
	assert.deepEqual([ui.selection.id, ui.picked], [expected.active, expected.picked]);
	assert.ok(!ui.picked.includes('s4'));
	undo();
	assert.deepEqual(doc.clips.map((c) => c.id), ORDER);
	assert.ok(!ui.picked.includes('s4'));

	select('clip', 's1');
	pickClip('s2', TOGGLE);
	assert.deepEqual(pickedClips().map((c) => c.id), ['s1', 's2']);
	deleteSelection();
	assert.deepEqual([doc.clips.map((c) => c.id), ui.selection, ui.picked], [['s3', 's4', 's5', 's6'], null, []]);
});

test('picking: the grid, the band and the V1 track pick with the same modifiers and show the picked shots', async () => {
	for (const mac of [false, true]) {
		const mod = mac ? { metaKey: true } : { ctrlKey: true };
		assert.equal(pickMode({ ctrlKey: false, metaKey: false, shiftKey: false, ...mod }, mac), TOGGLE);
		assert.equal(pickMode({ ctrlKey: false, metaKey: false, shiftKey: true }, mac), RANGE);
		assert.equal(pickMode({ ctrlKey: false, metaKey: false, shiftKey: true, ...mod }, mac), ADD_RANGE);
		assert.equal(pickMode({ ctrlKey: false, metaKey: false, shiftKey: false }, mac), null);
		assert.equal(pickMode({ ctrlKey: mac, metaKey: !mac, shiftKey: false }, mac), null);
	}

	shots();
	ui.selection = { kind: 'clip', id: 's1' };
	ui.picked = ['s1', 's3'];
	const grid = clean(await renderComponent(GRID));
	assert.deepEqual([...grid.matchAll(/data-story-shot="([^"]*)" data-picked=""/g)].map((m) => m[1]), ['s1', 's3']);
	ui.storyView = 'band';
	const lanes = clean(await renderComponent(BAND_LANES));
	assert.deepEqual([...lanes.matchAll(/data-picked=""[^>]*data-band-shot="([^"]*)"/g)].map((m) => m[1]), ['s1', 's3']);
	const timeline = clean(await renderComponent(TIMELINE));
	assert.deepEqual([...timeline.matchAll(/data-picked=""[^>]*aria-label="([^"]*)"/g)].map((m) => m[1]), [t('timeline.clip.label', { name: 'Shot 1', stage: t('lib.stage.todo'), dur: '4.0 s' }), t('timeline.clip.label', { name: 'Shot 3', stage: t('lib.stage.todo'), dur: '4.0 s' })]);
	assert.match(clean(await renderComponent(BAND_VIEW)), /data-picked-summary="2"/);
	assert.match(clean(await renderComponent(INSPECTOR)), /data-picked-summary="2"/);
	ui.picked = [];
	assert.doesNotMatch(clean(await renderComponent(BAND_VIEW)), /data-picked-summary/);
	assert.doesNotMatch(clean(await renderComponent(INSPECTOR)), /data-picked-summary/);
	assert.doesNotMatch(clean(await renderComponent(GRID)), /data-picked=""/);
});

test('scrolling: the grid of the Storyboard is bounded by its cell, so its list scrolls, and the arrows walk its rows or the takes of the band', async () => {
	shots();
	const grid = clean(await renderComponent(GRID));
	assert.match(grid, new RegExp(`^<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas" aria-label="${t('storyboard.title')}">`));
	assert.match(grid, /<div class="min-h-0 flex-1 overflow-auto p-5" role="list"><div class="grid [^"]*" data-story-grid="">/);
	ui.storyView = 'band';
	assert.match(clean(await renderComponent(BAND_VIEW)), new RegExp(`^<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas" aria-label="${t('storyboard.title')}">`));

	ui.storyView = 'grid';
	select('clip', 's1');
	handleKeydown(key('ArrowDown'), null);
	assert.deepEqual([ui.selection.id, ui.playhead], ['s2', 4.01]);
	handleKeydown(key('ArrowDown'), null);
	handleKeydown(key('ArrowUp'), null);
	assert.equal(ui.selection.id, 's2');
	handleKeydown(key('ArrowUp'), null);
	handleKeydown(key('ArrowUp'), null);
	assert.equal(ui.selection.id, 's1');
	ui.storyView = 'band';
	handleKeydown(key('ArrowDown'), null);
	assert.equal(ui.selection.id, 's1');
	ui.workspace = 'timeline';
	ui.playhead = 0;
	handleKeydown(key('ArrowDown'), null);
	assert.deepEqual([ui.selection.id, ui.playhead], ['s1', 0]);
});

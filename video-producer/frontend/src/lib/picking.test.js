import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ADD_RANGE, RANGE, TOGGLE, inOrder, picking, pruned, ranged, toggled } from './picking.js';
import { pickMode } from './keyboard.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const ORDER = ['s1', 's2', 's3', 's4', 's5', 's6'];

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

test('picking: the state keeps ui.selection as the active shot and the picked shots apart, any plain selection clears them', () => {
	const state = source('state.svelte.js');
	assert.match(state, /\tselection: null,\n\tpicked: \[\],/);
	assert.match(state, /ui\.selection = kind \? \{ kind, id \} : null;\n\tif \(ui\.picked\.length\) ui\.picked = \[\];/);
	assert.match(state, /const next = picking\(order, pruned\(order, ui\.picked\), active, id, mode\);\n\tui\.selection = next\.active \? \{ kind: 'clip', id: next\.active \} : null;\n\tui\.picked = next\.picked;/);
	assert.match(state, /if \(ui\.picked\.length\) ui\.picked = pruned\(doc\.clips\.map\(\(c\) => c\.id\), ui\.picked\);/);
	assert.match(state, /selection: null, picked: \[\], preview: null/);
	assert.match(state, /const picked = pickedClips\(\);\n\tif \(picked\.length\) return deleteShots\(picked\);/);
});

test('picking: the grid, the band and the V1 track pick with the same modifiers and show the picked shots', () => {
	const grid = source('../components/storyboard/StoryboardView.svelte');
	assert.match(grid, /onclick=\{\(e\) => pick\(c, e\)\}/);
	assert.match(grid, /const mode = e \? pickMode\(e\) : null;\n\t\tif \(mode\) return pickClip\(c\.id, mode\);/);
	assert.match(grid, /data-picked=\{picked \? '' : null\}/);
	const band = source('../components/storyboard/BandLanes.svelte');
	assert.match(band, /const mode = e\.button === 0 \? pickMode\(e\) : null;\n\t\tif \(mode\) \{\n\t\t\te\.preventDefault\(\);\n\t\t\te\.stopPropagation\(\);\n\t\t\treturn pickClip\(c\.id, mode\);/);
	const timeline = source('../components/timeline/Timeline.svelte');
	assert.match(timeline, /const mode = e\.button === 0 && ui\.tool !== 'blade' \? pickMode\(e\) : null;/);
	for (const view of [grid, band, timeline]) assert.match(view, /data-picked=\{picked \? '' : null\}/);
	assert.match(source('../components/storyboard/BandView.svelte'), /\{#if multi\}\n\t\t\t\t\t<PickedSummary \/>/);
	assert.match(source('../components/inspector/Inspector.svelte'), /\{#if multi\}\n\t\t\t<PickedSummary \/>/);
});

test('scrolling: the grid of the Storyboard is bounded by its cell, so its list scrolls, and brings the chosen shot into view', () => {
	const grid = source('../components/storyboard/StoryboardView.svelte');
	assert.match(grid, /<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas" aria-label=\{t\('storyboard\.title'\)\}>/);
	assert.match(grid, /<div bind:this=\{listEl\} class="min-h-0 flex-1 overflow-auto p-5" role="list"/);
	assert.match(grid, /if \(id && listEl\) queueMicrotask\(\(\) => reveal\(id\)\);/);
	assert.match(source('../components/storyboard/BandView.svelte'), /<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas"/);
	const commands = source('commands.js');
	assert.match(commands, /\{ spec: 'arrowup', run: vertical\(-1\), repeat: true, when: \(\) => ui\.workspace === 'storyboard' \},/);
	assert.match(commands, /return \(\) => \(bandView\(\) \? cycleTake\(delta\) : stepShot\(delta \* gridColumns\(\)\)\);/);
});

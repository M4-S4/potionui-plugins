import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import './svelte-harness.js';
import { advance } from './player.js';

const { doc, ui, seqDuration, dispose } = await import('./state.svelte.js');
const { handleKeydown } = await import('./commands.js');

globalThis.document = { body: {}, querySelector: () => null };

after(() => {
	dispose();
	delete globalThis.document;
});

test('advance: playback moves on and stops at the end of the cut when the loop is off', () => {
	assert.deepEqual(advance(2, 0.5, { end: 10 }), { t: 2.5, stop: false });
	assert.deepEqual(advance(9.8, 0.5, { end: 10 }), { t: 10, stop: true });
	assert.deepEqual(advance(3.9, 0.2, { range: { in: 2, out: 4 }, end: 10 }), { t: 4.1, stop: false });
});

test('advance: the loop goes back to the In point at the end of the range, and to the start at the end of the cut without a range', () => {
	assert.deepEqual(advance(3.9, 0.2, { loop: true, range: { in: 2, out: 4 }, end: 10 }), { t: 2, stop: false });
	assert.deepEqual(advance(9.8, 0.5, { loop: true, end: 10 }), { t: 0, stop: false });
	assert.deepEqual(advance(9.8, 0.5, { loop: true, range: { in: 2, out: 12 }, end: 10 }), { t: 10, stop: true });
});

test('playback: End seeks to the end of the cut and Home to its start outside the Storyboard, and go to the last or the first shot inside it', () => {
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo' }, { id: 's2', start: 4, dur: 4, label: 'Two', stage: 'todo' }, { id: 's3', start: 8, dur: 4, label: 'Three', stage: 'todo' }];
	Object.assign(ui, { workspace: 'mixer', modal: null, paletteOpen: false, hostModal: false, playhead: 2, selection: null, storyView: 'grid' });
	const press = (key) => handleKeydown({ key, target: null, preventDefault() {} }, null);
	press('End');
	assert.equal(ui.playhead, seqDuration());
	press('Home');
	assert.equal(ui.playhead, 0);
	ui.workspace = 'storyboard';
	ui.playhead = 2;
	press('End');
	assert.deepEqual([ui.selection, ui.playhead], [{ kind: 'clip', id: 's3' }, 8.01]);
	press('Home');
	assert.deepEqual([ui.selection, ui.playhead], [{ kind: 'clip', id: 's1' }, 0.01]);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { advance } from './player.js';

const here = dirname(fileURLToPath(import.meta.url));
const source = (file) => readFileSync(join(here, file), 'utf-8');

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

test('playback: every frame of the clock goes through advance, and End seeks to the end of the cut outside the Storyboard', () => {
	const playback = source('playback.svelte.js');
	assert.match(playback, /const next = advance\(ui\.playhead, dt, \{ loop: ui\.loop, range: ui\.range, end: seqDuration\(\) \}\);\n\tui\.playhead = next\.t;\n\tif \(next\.stop\) return pause\(\);/);
	const commands = source('commands.js');
	assert.match(commands, /\{ spec: 'home', run: edge\(false\) \},\n\t\{ spec: 'end', run: edge\(true\) \},/);
	assert.match(commands, /if \(ui\.workspace !== 'storyboard'\) return seek\(last \? seqDuration\(\) : 0\);/);
});

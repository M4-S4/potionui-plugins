import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { advance, fractionOf, shotMarks, timeAt } from './player.js';

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

test('fractionOf: the share of the cut stays between 0 and 1, and an empty cut reads 0', () => {
	assert.equal(fractionOf(5, 10), 0.5);
	assert.equal(fractionOf(-1, 10), 0);
	assert.equal(fractionOf(12, 10), 1);
	assert.equal(fractionOf(3, 0), 0);
});

test('timeAt: a point of the bar gives its time, clamped to the cut, and a bar with no width gives the start', () => {
	const rect = { left: 100, width: 400 };
	assert.equal(timeAt(300, rect, 20), 10);
	assert.equal(timeAt(50, rect, 20), 0);
	assert.equal(timeAt(900, rect, 20), 20);
	assert.equal(timeAt(300, { left: 100, width: 0 }, 20), 0);
	assert.equal(timeAt(300, null, 20), 0);
});

test('shotMarks: one block per shot, placed and sized in percent of the cut', () => {
	const clips = [
		{ id: 'a', start: 0, dur: 4 },
		{ id: 'b', start: 4, dur: 2 },
		{ id: 'c', start: 6, dur: 6 }
	];
	assert.deepEqual(shotMarks(clips, 16), [
		{ id: 'a', index: 0, left: 0, width: 25 },
		{ id: 'b', index: 1, left: 25, width: 12.5 },
		{ id: 'c', index: 2, left: 37.5, width: 37.5 }
	]);
	assert.deepEqual(shotMarks([{ id: 'x', start: 8, dur: 4 }], 10), [{ id: 'x', index: 0, left: 80, width: 20 }]);
	assert.deepEqual(shotMarks([], 10), []);
});

test('playback: every frame of the clock goes through advance, and End seeks to the end of the cut', () => {
	const playback = source('playback.svelte.js');
	assert.match(playback, /const next = advance\(ui\.playhead, dt, \{ loop: ui\.loop, range: ui\.range, end: seqDuration\(\) \}\);\n\tui\.playhead = next\.t;\n\tif \(next\.stop\) return pause\(\);/);
	const commands = source('commands.js');
	assert.match(commands, /\{ spec: 'home', run: \(\) => seek\(0\) \},\n\t\{ spec: 'end', run: \(\) => seek\(seqDuration\(\)\) \},/);
});

test('position bar: a slider that seeks on click and drag, names the shot under the playhead and leaves the keys to the page', () => {
	const bar = source('../components/viewer/PlayBar.svelte');
	assert.match(bar, /role="slider"/);
	assert.match(bar, /tabindex="0"/);
	assert.match(bar, /aria-valuetext=\{t\('viewer\.bar\.value', \{ tc: now, shot: shotText \}\)\}/);
	assert.match(bar, /drag\(e, \{ undoable: false, onMove: \(dx, dy, ev\) => seekTo\(ev\.clientX\) \}\);/);
	assert.match(bar, /\$effect\(\(\) => cancelDrag\);/);
	assert.doesNotMatch(bar, /onkeydown/);
	assert.match(source('keyboard.js'), /const ACTIVATION = '[^']*'/);
	assert.doesNotMatch(/const ACTIVATION = '([^']*)'/.exec(source('keyboard.js'))[1], /slider/);
	for (const locale of ['en', 'fr']) {
		const viewer = JSON.parse(source(`../i18n/${locale}/viewer.json`));
		for (const key of ['bar.label', 'bar.shot', 'bar.noShot', 'bar.value']) assert.ok(viewer[key], `${locale}: viewer.${key} is missing`);
	}
	assert.equal(JSON.parse(source('../i18n/fr/viewer.json'))['bar.shot'], 'Plan {index}/{count} · {name}');
});

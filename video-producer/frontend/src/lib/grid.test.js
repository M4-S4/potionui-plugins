import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { GRID_STEP, onGrid, onStep } from './grid.js';
import { frameTime } from './seam.js';
import { mergeDocs } from './merge.js';
import { applyShotDraft, setSpeed, shotDraft } from './shots.js';
import { headTrim } from './dissolve.js';

const here = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(readFileSync(join(here, '..', '..', '..', 'tests', 'fixtures', 'snap_cases.json'), 'utf-8'));

function shotDoc(dur) {
	return { clips: [{ id: 'c', assetId: null, start: 0, dur, srcIn: 0 }], prompts: [], frames: [], references: [], assets: [], lanes: [], audio: [], titles: [] };
}

test('grid: every time the page puts on the 0.04 s grid is rounded as the server rounds it', () => {
	for (const [value, snapped] of cases) {
		assert.equal(onGrid(value), snapped, String(value));
		assert.equal(onStep(value, GRID_STEP), snapped, String(value));
		assert.equal(frameTime({ start: value, dur: 1 }, 'first'), snapped, String(value));
		if (value >= 0.4 && value <= 60) {
			const doc = shotDoc(5);
			const clip = doc.clips[0];
			applyShotDraft(doc, clip, shotDraft(doc, clip), { ...shotDraft(doc, clip), dur: value }, { makeId: () => 'id' });
			assert.equal(clip.dur, snapped, String(value));
		}
	}
});

test('grid: the last frame of a shot, a length asked in Edit shot and a merge that lays the shots out again fall where the server puts them', () => {
	assert.equal(frameTime({ start: 1.48, dur: 0.42 }, 'last'), 1.88);
	const doc = shotDoc(5);
	const clip = doc.clips[0];
	applyShotDraft(doc, clip, shotDraft(doc, clip), { ...shotDraft(doc, clip), dur: 0.58 }, { makeId: () => 'id' });
	assert.equal(clip.dur, 0.6);
	const clips = [{ id: 'a', dur: 1 }, { id: 'b', dur: 0.84 }, { id: 'c', dur: 1.56 }].map((c) => ({ ...c, start: 0 }));
	const mine = { clips: clips.map((c) => (c.id === 'a' ? { ...c, dur: 1.02 } : c)) };
	const theirs = { clips: clips.map((c) => (c.id === 'c' ? { ...c, dur: 1.6 } : c)) };
	assert.deepEqual(mergeDocs({ clips }, mine, theirs).value.clips.map((c) => c.start), [0, 1.04, 1.88]);
	const slowed = { clips: [{ id: 's', assetId: null, start: 0, dur: 1.17, srcIn: 0 }], assets: [] };
	setSpeed(slowed, slowed.clips[0], 0.5);
	assert.equal(slowed.clips[0].dur, 2.36);
	assert.equal(headTrim(0, 3, 1, 0.06).dur, 2.92);
});

test('grid: a value that is not a number rounds as before, through its number', () => {
	assert.ok(Number.isNaN(onStep(undefined, 0.04)));
	assert.equal(onStep(null, 0.04), 0);
	assert.equal(onStep('', 0.04), 0);
	assert.equal(onStep('1.23'), 1.2);
	assert.equal(onStep(true), 1);
	assert.ok(Number.isNaN(onStep('x')));
	assert.equal(onStep(Infinity), Infinity);
	assert.equal(onStep(-Infinity), -Infinity);
});

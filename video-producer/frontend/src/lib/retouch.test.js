import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { REFINE, REMIX, blockReason, canRetouch, initialRange, moveEdge, overLimit, rangeProblem, retouchBody, retouchPair, shareOf, snap, touchesEnd } from './retouch.js';
import { normalizeRetouch, normalizeRetouchOffers, normalizeTake } from './api.js';

const take = { id: 't1', kind: 'render', status: 'done', url: '/v.mp4', fps: 24, durationS: 5 };
const refine = { task: REFINE, engines: [{ presetId: 'p', name: 'H3' }], minS: 0.5, maxS: null, ready: true, reason: null, missing: [] };
const remix = { task: REMIX, engines: [{ presetId: 'p', name: 'H3' }], minS: 1, maxS: 3, ready: true, reason: null, missing: [] };

test('a range snaps to whole frames and stays inside the take', () => {
	assert.deepEqual(snap(take, 2.01, 3.26), { first: 48, last: 78, frames: 30, start: 2, end: 3.25, seconds: 1.25, total: 120 });
	assert.deepEqual([snap(take, -1, 9).first, snap(take, -1, 9).last], [0, 120]);
	assert.equal(snap(take, 3, 3).frames, 1);
});

test('the first range is one second around the playhead, inside the take', () => {
	assert.deepEqual([initialRange(take).start, initialRange(take).end], [2, 3]);
	assert.deepEqual([initialRange(take, 0.1).start, initialRange(take, 0.1).end], [0, 1]);
	assert.deepEqual([initialRange(take, 4.9).start, initialRange(take, 4.9).end], [4, 5]);
	assert.equal(initialRange({ ...take, durationS: 0.5 }).seconds, 0.5);
});

test('an edge never passes the other one', () => {
	const range = snap(take, 2, 3);
	assert.deepEqual([moveEdge(take, range, 'in', 4).start, moveEdge(take, range, 'in', 4).end], [3 - 1 / 24, 3]);
	assert.deepEqual([moveEdge(take, range, 'out', 1).start, moveEdge(take, range, 'out', 1).end], [2, 2 + 1 / 24]);
	assert.equal(moveEdge(take, range, 'out', 4.5).end, 4.5);
});

test('the limits of the offer are read with half a frame of slack', () => {
	assert.deepEqual(rangeProblem(remix, snap(take, 1, 4.5), 24), { code: 'tooLong', limit: 3 });
	assert.deepEqual(overLimit(remix, snap(take, 1, 4.5)), { start: 4, end: 4.5 });
	assert.equal(rangeProblem(remix, snap(take, 1, 4), 24), null);
	assert.equal(rangeProblem(remix, snap(take, 1, 4 + 1 / 24), 24).code, 'tooLong');
	assert.deepEqual(rangeProblem(remix, snap(take, 1, 1.5), 24), { code: 'tooShort', limit: 1 });
	assert.equal(rangeProblem(refine, snap(take, 0, 5), 24), null);
	assert.equal(overLimit(refine, snap(take, 0, 5)), null);
});

test('only a finished video take with a known length can be retouched', () => {
	assert.equal(canRetouch(take), true);
	assert.equal(canRetouch({ ...take, status: 'running' }), false);
	assert.equal(canRetouch({ ...take, kind: 'keyframe' }), false);
	assert.equal(canRetouch({ ...take, durationS: null }), false);
	assert.equal(canRetouch({ ...take, url: null }), false);
});

test('the start button says why it waits', () => {
	const state = { task: REFINE, faces: true, hands: true, prompt: '', range: snap(take, 2, 3) };
	assert.equal(blockReason(state, take, refine), null);
	assert.equal(blockReason(state, take, null), 'loading');
	assert.equal(blockReason(state, take, { ...refine, engines: [] }), 'engineMissing');
	assert.equal(blockReason(state, take, { ...refine, missing: ['face_landmarker.task'] }), 'detectorMissing');
	assert.equal(blockReason({ ...state, faces: false, hands: false }, take, refine), 'nothingToRefine');
	assert.equal(blockReason({ ...state, task: REMIX }, take, remix), 'promptRequired');
	assert.equal(blockReason({ ...state, task: REMIX, prompt: 'snow', range: snap(take, 0, 4) }, take, remix), 'tooLong');
	assert.equal(blockReason(state, { ...take, status: 'failed' }, refine), 'takeNotDone');
});

test('the request carries only what its task takes', () => {
	const range = snap(take, 2, 3.25);
	assert.deepEqual(retouchBody({ task: REFINE, presetId: 'p', range, strength: 'light', faces: true, hands: false, prompt: 'ignored' }), {
		task: REFINE, start_s: 2, end_s: 3.25, preset_id: 'p', strength: 'light', faces: true, hands: false
	});
	assert.deepEqual(retouchBody({ task: REMIX, presetId: null, range, prompt: '  make it snow ' }), { task: REMIX, start_s: 2, end_s: 3.25, prompt: 'make it snow' });
});

test('a range is drawn as shares of the take and the end of the take is noticed', () => {
	assert.deepEqual(shareOf(snap(take, 1, 2), 5), { left: 20, width: 20 });
	assert.deepEqual(shareOf(null, 5), { left: 0, width: 0 });
	assert.equal(touchesEnd(snap(take, 4, 5)), true);
	assert.equal(touchesEnd(snap(take, 3, 4)), false);
});

test('a comparison of a retouched take and its source is recognised in either order', () => {
	const source = { id: 'a', kind: 'render' };
	const retouched = { id: 'b', kind: 'retouch', parentTakeId: 'a' };
	assert.deepEqual(retouchPair([source, retouched]), { source, retouched });
	assert.deepEqual(retouchPair([retouched, source]), { source, retouched });
	assert.equal(retouchPair([source, { id: 'c', kind: 'render' }]), null);
	assert.equal(retouchPair([source]), null);
});

test('a retouched take keeps its range, task and origin from the API', () => {
	const shaped = normalizeTake({
		id: 't2', kind: 'retouch', status: 'done', parent_take_id: 't1',
		origin: { kind: 'library', itemId: 'item-2' },
		retouch: { task: 'remix', start_s: 1, end_s: 2.5, source_take_id: 't1', preset_id: 'p', prompt: 'rain' }
	});
	assert.equal(shaped.kind, 'retouch');
	assert.deepEqual(shaped.origin, { kind: 'library', itemId: 'item-2' });
	assert.deepEqual(shaped.retouch, { task: 'remix', start: 1, end: 2.5, sourceTakeId: 't1', presetId: 'p', prompt: 'rain', strength: null, faces: true, hands: true });
	assert.equal(normalizeRetouch({ task: 'extend', start_s: 1, end_s: 2 }), null);
	assert.equal(normalizeRetouch({ task: 'remix', start_s: 2, end_s: 1 }), null);
	assert.equal(normalizeTake({ id: 't3', kind: 'render' }).retouch, null);
});

test('the offers keep their engines, limits and missing files', () => {
	assert.deepEqual(
		normalizeRetouchOffers({ offers: [{ task: 'refine_faces', engines: [{ preset_id: 'p', name: 'H3' }, { name: 'nameless' }], min_s: 0.5, max_s: null, ready: false, reason: 'detector_missing', missing: ['face_landmarker.task', 3] }] }),
		[{ task: 'refine_faces', engines: [{ presetId: 'p', name: 'H3' }], minS: 0.5, maxS: null, ready: false, reason: 'detector_missing', missing: ['face_landmarker.task'] }]
	);
	assert.deepEqual(normalizeRetouchOffers(null), []);
});

test('the missing detection models ask for a scan of the models first, in both languages', () => {
	const en = JSON.parse(readFileSync(new URL('../i18n/en/generation.json', import.meta.url), 'utf-8'))['retouch.detectorMissing'];
	const fr = JSON.parse(readFileSync(new URL('../i18n/fr/generation.json', import.meta.url), 'utf-8'))['retouch.detectorMissing'];
	assert.match(en, /scan the models \(Admin › Models\), then to install them/);
	assert.match(fr, /lancer un scan des modèles \(Admin › Models\), puis de les installer/);
	assert.ok(en.includes('{files}') && fr.includes('{files}'));
});

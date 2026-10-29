import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CADENCES, DEFAULT_CADENCE, INTERPOLATORS, SLOWER, SLOW_SPEEDS, SPEEDS, exportCadence, finalCadence, neededFps, shotCadence, sourceSeconds, speedOf, interpolatorChoice, interpolatorsReady, isActiveRendition, nearlyAsFast, needsConform, pickInterpolator, placedTakes, renditionFor, takeCadence, targetOf } from './cadence.js';
import { createClient, normalizePassEstimate, normalizeRendition, normalizeRenditionEstimate } from './api.js';

const table = JSON.parse(readFileSync(new URL('../../../backend/formats.json', import.meta.url), 'utf-8'));

const take = (id, fps, extra = {}) => ({ id, fps, status: 'done', kind: 'render', url: `/x/${id}.mp4`, ...extra });
const rendition = (takeId, status, extra = {}) => ({ id: `r-${takeId}-${status}`, takeId, fps: 25, status, ...extra });
const me = (rife, rtx, rtxChecked = true) => ({ features: { interpolators: { rife, rtx, rtxChecked } } });

test('the cadences rule is the one of the formats table the server reads', () => {
	assert.deepEqual(CADENCES, table.cadence.values);
	assert.equal(DEFAULT_CADENCE, table.cadence.default);
	assert.equal(SLOWER, table.cadence.slower);
	assert.deepEqual(CADENCES, [24, 25, 30, 48, 50, 60]);
	assert.deepEqual(INTERPOLATORS, ['auto', 'rife', 'rtx']);
});

test('a take is conformed when it is slower than the film by the table share or more, as the server says', () => {
	const cases = [
		[16, 24, true],
		[16, 25, true],
		[16, 30, true],
		[24, 25, false],
		[25, 24, false],
		[24, 48, true],
		[25, 50, true],
		[30, 60, true],
		[null, 25, false],
		[0, 25, false],
		[16, null, false]
	];
	for (const [from, to, needed] of cases) assert.equal(needsConform(from, to), needed, `${from} in ${to}`);
	assert.equal(nearlyAsFast(24, 25), true);
	assert.equal(nearlyAsFast(16, 25), false);
	assert.equal(nearlyAsFast(25, 25), false);
});

test('only a cadence of the table is a frame rate takes are conformed to', () => {
	assert.equal(targetOf({ fps: 25 }), 25);
	assert.equal(targetOf({ fps: 60 }), 60);
	assert.equal(targetOf({}), 25);
	assert.equal(targetOf({ fps: 23.976 }), null);
	assert.equal(targetOf({ fps: 12 }), null);
});

test('the film asks for auto unless its final pass choices name an interpolator', () => {
	assert.equal(interpolatorChoice({}), 'auto');
	assert.equal(interpolatorChoice({ finalPass: { interpolator: 'rife' } }), 'rife');
	assert.equal(interpolatorChoice({ finalPass: { interpolator: 'high' } }), 'auto');
});

test('auto takes frame generation when it is ready and rife otherwise; a named one only when it is ready', () => {
	assert.deepEqual(interpolatorsReady(null), { rife: false, rtx: false, rtxChecked: true });
	assert.equal(pickInterpolator('auto', me(true, true)), 'rtx');
	assert.equal(pickInterpolator('auto', me(true, false)), 'rife');
	assert.equal(pickInterpolator('auto', me(false, false)), null);
	assert.equal(pickInterpolator('rife', me(true, true)), 'rife');
	assert.equal(pickInterpolator('rtx', me(true, false)), null);
});

test('frame generation the server could not check on its remote worker is offered by name, and auto prefers rife to it', () => {
	assert.deepEqual(interpolatorsReady(me(true, true, false)), { rife: true, rtx: true, rtxChecked: false });
	assert.deepEqual(interpolatorsReady({ features: { interpolators: { rife: false, rtx: true, rtx_checked: false } } }), { rife: false, rtx: true, rtxChecked: false });
	assert.equal(pickInterpolator('auto', me(true, true, false)), 'rife');
	assert.equal(pickInterpolator('auto', me(false, true, false)), 'rtx');
	assert.equal(pickInterpolator('rtx', me(true, true, false)), 'rtx');
	assert.equal(pickInterpolator('rife', me(false, true, false)), null);
});

test('a take card shows the version of the take at the film rate, on its way, failed, or still to make', () => {
	const doc = { fps: 25 };
	assert.equal(takeCadence(take('t', 25), [], doc).state, 'none');
	assert.equal(takeCadence(take('t', 24), [], doc).state, 'near');
	assert.equal(takeCadence(take('t', 16, { status: 'running' }), [], doc).state, 'none');
	assert.equal(takeCadence(take('t', 16, { kind: 'keyframe' }), [], doc).state, 'none');
	assert.deepEqual(takeCadence(take('t', 16), [], doc), { state: 'slow', from: 16, to: 25, speed: 1, rendition: null });
	assert.equal(takeCadence(take('t', 16), [rendition('t', 'queued')], doc).state, 'conforming');
	assert.equal(takeCadence(take('t', 16), [rendition('t', 'waiting')], doc).state, 'conforming');
	assert.equal(takeCadence(take('t', 16), [rendition('t', 'done')], doc).state, 'conformed');
	assert.equal(takeCadence(take('t', 16), [rendition('t', 'failed')], doc).state, 'failed');
	assert.equal(takeCadence(take('t', 16), [rendition('t', 'cancelled')], doc).state, 'slow');
	assert.equal(takeCadence(take('t', 16), [rendition('t', 'done', { fps: 30 })], doc).state, 'slow');
	assert.equal(takeCadence(take('t', 16), [rendition('t', 'done')], { fps: 23.976 }).state, 'none');
	assert.equal(isActiveRendition({ status: 'running' }), true);
	assert.equal(isActiveRendition({ status: 'done' }), false);
	assert.equal(renditionFor([rendition('t', 'failed'), rendition('t', 'done')], 't', 25).status, 'done');
});

test('the export counts the placed takes that will stutter, the versions on their way and the nearly as fast ones', () => {
	const takes = [take('a', 16), take('b', 16), take('c', 24), take('d', 25), take('e', 16), take('f', 16)];
	const doc = {
		fps: 25,
		assets: ['a', 'b', 'c', 'd', 'e', 'f'].map((id) => ({ id: `gen-${id}`, resultId: id })),
		clips: [
			{ id: 's1', assetId: 'gen-a' },
			{ id: 's2', assetId: 'gen-b' },
			{ id: 's3', assetId: 'gen-c' },
			{ id: 's4', assetId: 'gen-d' },
			{ id: 's5', assetId: 'gen-e' },
			{ id: 's6', assetId: 'gen-a' },
			{ id: 's7', assetId: null }
		]
	};
	const found = exportCadence(doc, takes, [rendition('b', 'running'), rendition('e', 'done')]);
	assert.deepEqual(found.slow.map((x) => x.id), ['a', 'a']);
	assert.deepEqual(found.slowed, []);
	assert.deepEqual(found.rates, [16]);
	assert.deepEqual(found.conforming.map((x) => x.id), ['b']);
	assert.deepEqual(found.conformed.map((x) => x.id), ['e']);
	assert.deepEqual(found.near, [{ fps: 24, count: 1 }]);
	assert.equal(found.fps, 25);
	assert.deepEqual(placedTakes(doc, takes).map((item) => item.take.id), ['a', 'b', 'c', 'd', 'e', 'a']);
});

test('the versions at a frame rate and their estimate are read from the API', () => {
	assert.deepEqual(
		normalizeRendition({ id: 'r1', take_id: 't1', shot_id: 's1', fps: 25, source_fps: 16, interpolator: 'rife', status: 'running', progress: 40, step: 'RIFE', width: 832, height: 480, duration_s: 4, url: '/u.mp4', created_at: 'c' }),
		{ id: 'r1', takeId: 't1', shotId: 's1', fps: 25, sourceFps: 16, interpolator: 'rife', factor: null, sourceRenditionId: null, status: 'running', progress: 40, step: 'RIFE', width: 832, height: 480, durationS: 4, errorCode: null, errorMessage: null, url: '/u.mp4', createdAt: 'c', finishedAt: null }
	);
	assert.equal(normalizeRendition({ id: 'r1' }), null);
	assert.equal(normalizeRendition({ id: 'r1', take_id: 't1', status: 'odd', interpolator: 'high' }).status, 'queued');
	assert.deepEqual(normalizeRenditionEstimate({ fps: 25, choice: 'auto', interpolator: 'rtx', ready: { rife: true, rtx: true }, takes: ['t1', 3], seconds: 12.5 }), {
		fps: 25,
		choice: 'auto',
		interpolator: 'rtx',
		ready: { rife: true, rtx: true, rtxChecked: true },
		takes: ['t1'],
		seconds: 12.5
	});
	assert.deepEqual(normalizeRenditionEstimate({ fps: 25, choice: 'auto', interpolator: 'rife', ready: { rife: true, rtx: true, rtx_checked: false }, takes: [], seconds: null }).ready, { rife: true, rtx: true, rtxChecked: false });
	const pass = normalizePassEstimate({ shots: [], vram: null, time: {}, quota: null, blocks: [], warnings: [], cadence: { fps: 25, choice: 'rife', interpolator: null, ready: {}, shots: ['s1'], near: ['s2'], seconds: null } });
	assert.deepEqual(pass.cadence, { fps: 25, choice: 'rife', interpolator: null, ready: { rife: false, rtx: false, rtxChecked: true }, shots: ['s1'], slowed: [], near: ['s2'], seconds: null });
});

test('the client orders, estimates, lists and cancels versions, and asks a final take to conform', async () => {
	const calls = [];
	const responses = [
		{ success: true, data: { renditions: [{ id: 'r1', take_id: 't1', fps: 25, status: 'queued' }], refused: [{ take_id: 't2', code: 'not_slower', message: 'x' }] } },
		{ success: true, data: { fps: 25, choice: 'auto', interpolator: 'rife', ready: { rife: true }, takes: ['t1'], seconds: null } },
		{ success: true, data: { renditions: [{ id: 'r1', take_id: 't1', fps: 25, status: 'queued' }] } },
		{ success: true, data: { rendition: { id: 'r1', take_id: 't1', fps: 25, status: 'cancelled' } } },
		{ success: true, data: { take: { id: 't3', parent_take_id: 't1', status: 'queued' } } }
	];
	const client = createClient({
		async request(method, path, data) {
			calls.push([method, path, data]);
			return responses.shift();
		}
	});
	const ordered = await client.orderRenditions('p1', ['t1', 't2'], 'rife');
	assert.deepEqual(ordered.data.refused, [{ takeId: 't2', code: 'not_slower', message: 'x' }]);
	assert.equal(ordered.data.renditions[0].id, 'r1');
	assert.equal((await client.renditionsEstimate('p1', ['t1'])).data.interpolator, 'rife');
	assert.equal((await client.listRenditions('p1')).data[0].status, 'queued');
	assert.equal((await client.cancelRendition('r1')).data.status, 'cancelled');
	assert.equal((await client.finalTake('p1', 't1', 'upscale', 'fhd1080', 'auto', 'compressed', true)).data.parentTakeId, 't1');
	assert.deepEqual(calls, [
		['POST', '/projects/p1/renditions', { takes: ['t1', 't2'], interpolator: 'rife' }],
		['POST', '/projects/p1/renditions/estimate', { takes: ['t1'] }],
		['GET', '/projects/p1/renditions', undefined],
		['POST', '/renditions/r1/cancel', {}],
		['POST', '/projects/p1/takes/t1/final', { method: 'upscale', target: 'fhd1080', conform: true }]
	]);
});

test('a slowed shot plays its take at a speed of the table and needs the film rate divided by it', () => {
	assert.deepEqual(SPEEDS, table.cadence.speeds);
	assert.deepEqual(SLOW_SPEEDS, [0.5, 0.25]);
	assert.deepEqual([{}, { speed: 0.5 }, { speed: 0.25 }, { speed: 0.75 }, null].map(speedOf), [1, 0.5, 0.25, 1, 1]);
	assert.equal(sourceSeconds({ dur: 4, speed: 0.5 }), 2);
	assert.equal(neededFps({ fps: 25 }, { speed: 0.5 }, take('t', 16)), 50);
	assert.equal(neededFps({ fps: 25 }, { speed: 0.25 }, take('t', 25)), 100);
	assert.equal(neededFps({ fps: 25 }, { speed: 0.5 }, take('t', 50)), null);
	assert.equal(neededFps({ fps: 25 }, {}, take('t', 25)), null);
});

test('a slowed shot shows the version at its rate, and the export counts the slowed shots apart', () => {
	const doc = { fps: 25, assets: [{ id: 'gen-a', resultId: 'a' }, { id: 'gen-b', resultId: 'b' }], clips: [{ id: 's1', assetId: 'gen-a', speed: 0.5 }, { id: 's2', assetId: 'gen-b' }] };
	const takes = [take('a', 25, { shotId: 's1' }), take('b', 16, { shotId: 's2' })];
	assert.deepEqual(shotCadence(takes[0], doc.clips[0], [], doc), { state: 'slow', from: 25, to: 50, speed: 0.5, rendition: null });
	assert.equal(shotCadence(takes[0], doc.clips[0], [{ id: 'r', takeId: 'a', fps: 50, status: 'done' }], doc).state, 'conformed');
	assert.equal(takeCadence(takes[0], [], doc).to, 50);
	const found = exportCadence(doc, takes, []);
	assert.deepEqual(found.slowed.map((x) => x.id), ['a']);
	assert.deepEqual(found.slow.map((x) => x.id), ['b']);
});

test('finalCadence: a final take is brought to the rate its shot needs, the film rate divided by the speed of the shot', () => {
	const doc = { fps: 25, clips: [{ id: 's1', dur: 4 }, { id: 's2', dur: 4, speed: 0.5 }, { id: 's3', dur: 4, speed: 0.25 }] };
	assert.deepEqual(finalCadence(doc, { shotId: 's1', fps: 16 }), { slow: true, from: 16, fps: 25 });
	assert.deepEqual(finalCadence(doc, { shotId: 's2', fps: 16 }), { slow: true, from: 16, fps: 50 });
	assert.deepEqual(finalCadence(doc, { shotId: 's2', fps: 25 }), { slow: true, from: 25, fps: 50 });
	assert.deepEqual(finalCadence(doc, { shotId: 's3', fps: 25 }), { slow: true, from: 25, fps: 100 });
	assert.deepEqual(finalCadence(doc, { shotId: 's1', fps: 25 }), { slow: false, from: 25, fps: null });
	assert.deepEqual(finalCadence(doc, { shotId: 'gone', fps: 16 }), { slow: true, from: 16, fps: 25 });
	assert.deepEqual(finalCadence(doc, null), { slow: false, from: null, fps: null });
	const single = readFileSync(new URL('../components/modals/MakeFinal.svelte', import.meta.url), 'utf8');
	assert.match(single, /finalCadence\(doc, take\)/);
	assert.doesNotMatch(single, /needsConform\(take\?\.fps, filmFps\)/);
});

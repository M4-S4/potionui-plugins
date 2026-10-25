import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	deviation,
	deviationLevel,
	distance,
	dollyCamera,
	focalToFov,
	fovToFocal,
	fromSpherical,
	holesMatter,
	horizontalFov,
	orbitCamera,
	panCamera,
	projectSize,
	sourceView,
	spherical
} from './scene3d/camera.js';
import { plyHeader, plyView } from './scene3d/files.js';
import { createPoller, jobScene, lostScene, orphanJobs } from './scene3d/jobs.js';

const near = (actual, expected, eps = 1e-6) => assert.ok(Math.abs(actual - expected) <= eps, `${actual} is not ${expected}`);
const nearVec = (actual, expected, eps = 1e-6) => expected.forEach((v, i) => near(actual[i], v, eps));
const source = { pos: [0, 0, 0], target: [0, 0, -4], focal: 30, roll: 0 };

test('focal length and field of view: 36 mm wide sensor, horizontal fov 2·atan(18/focal), vertical from the aspect', () => {
	near(horizontalFov(36), (2 * Math.atan(0.5) * 180) / Math.PI);
	near(horizontalFov(18), 90);
	near(focalToFov(18, 1), 90);
	near(focalToFov(fovToFocal(60, 16 / 9), 16 / 9), 60);
	near(fovToFocal(focalToFov(35, 2.39), 2.39), 35);
	assert.ok(focalToFov(35, 16 / 9) < horizontalFov(35));
});

test('the holes warning only matters for a scene with a source view', () => {
	assert.equal(holesMatter({ kind: 'splat', view: { fov: 50, aspect: 1.5, depth: 4 } }), true);
	assert.equal(holesMatter({ kind: 'splatfile', view: null }), false);
	assert.equal(holesMatter(null), false);
});

test('free camera: orbit keeps the distance and stops short of the poles, pan moves pos and target together, dolly keeps a minimum distance', () => {
	const turned = orbitCamera(source, 30, 0);
	near(distance(turned.pos, turned.target), 4);
	near(spherical(turned).az, 30);
	near(spherical(orbitCamera(source, 0, 200)).el, 85);
	const panned = panCamera(source, 0.5, 0);
	nearVec(panned.pos, [2, 0, 0]);
	nearVec(panned.target, [2, 0, -4]);
	nearVec(panCamera(source, 0, 0.25).pos, [0, 1, 0]);
	const rolled = panCamera({ ...source, roll: 90 }, 0.5, 0);
	nearVec(rolled.pos, [0, 2, 0]);
	nearVec(dollyCamera(source, 0.5).pos, [0, 0, -2]);
	nearVec(dollyCamera(source, 0, 0.5).pos, [0, 0, -3.5]);
});

test('deviation from the source view: the angle seen from the pivot and the push along the source axis, holes past 15° or 25 %', () => {
	const { az, el, dist } = spherical(source);
	const side = deviation({ ...source, pos: fromSpherical(source.target, az + 15, el, dist) }, source);
	near(side.angle, 15, 1e-4);
	assert.ok(side.shift < 0.05);
	assert.equal(deviationLevel(side), 'near');
	const pushed = deviation({ ...source, pos: fromSpherical(source.target, az, el, dist * 0.75) }, source);
	near(pushed.angle, 0);
	near(pushed.shift, 0.25);
	assert.equal(deviationLevel({ angle: 2, shift: 0.05 }), 'ok');
	assert.equal(deviationLevel({ angle: 16, shift: 0 }), 'holes');
	assert.equal(deviationLevel({ angle: 0, shift: 0.3 }), 'holes');
});

test('source view: the source camera at the origin looks at (0, 0, −depth) with the fov of VIEW; a scene without a view frames its bounds', () => {
	const view = sourceView({ kind: 'splat', view: { fov: 60, aspect: 16 / 9, depth: 4 } }, null);
	assert.deepEqual([view.pos, view.target, view.roll], [[0, 0, 0], [0, 0, -4], 0]);
	near(focalToFov(view.focal, 16 / 9), 60, 1e-3);
	const framed = sourceView({ kind: 'splatfile', view: null }, { bounds: { center: [0, 1, -5], radius: 2 } });
	assert.deepEqual(framed.target, [0, 1, -5]);
	nearVec(framed.pos, [0, 1.5, -0.6]);
	assert.deepEqual(sourceView(null, null).target, [0, 0, -4]);
});

test('capture size: the project frame, short side from the resolution and long side from the aspect, even sides', () => {
	assert.deepEqual(projectSize('1080p', 16 / 9), { width: 1920, height: 1080 });
	assert.deepEqual(projectSize('720p', 16 / 9), { width: 1280, height: 720 });
	assert.deepEqual(projectSize('1080p', 9 / 16), { width: 1080, height: 1920 });
	assert.deepEqual(projectSize('4K', 16 / 9), { width: 3840, height: 2160 });
	assert.deepEqual(projectSize('1080p', 2.39), { width: 2580, height: 1080 });
	assert.deepEqual(projectSize('1080p', 9), { width: 1920, height: 1080 });
	assert.deepEqual(projectSize('weird', 1), { width: 1080, height: 1080 });
});

function plyBytes(comment) {
	const header = `ply\nformat binary_little_endian 1.0\n${comment}element vertex 1\nproperty float x\nend_header\n`;
	const head = new TextEncoder().encode(header);
	const out = new Uint8Array(head.length + 4);
	out.set(head);
	return out;
}

test('PLY header: the potionui_view comment gives the source view; anything else gives none', () => {
	const bytes = plyBytes('comment potionui_view fov_y=52.5 aspect=1.7778 depth=4 width=1024 height=576 convention=opencv\n');
	assert.match(plyHeader(bytes), /^ply\n/);
	assert.deepEqual(plyView(bytes), { fov: 52.5, aspect: 1.7778, depth: 4, width: 1024, height: 576 });
	assert.deepEqual(plyView(bytes.buffer), plyView(bytes));
	assert.deepEqual(plyView('ply\ncomment potionui_view fov_y=40 aspect=1 depth=2\nend_header\n'), { fov: 40, aspect: 1, depth: 2 });
	assert.equal(plyView(plyBytes('comment made by hand\n')), null);
	assert.equal(plyView(plyBytes('comment potionui_view fov_y=0 aspect=1 depth=4\n')), null);
	assert.equal(plyView(plyBytes('comment potionui_view fov_y=40 aspect=1 depth=4 convention=opengl\n')), null);
	assert.equal(plyView(new Uint8Array([1, 2, 3])), null);
	assert.equal(plyHeader(new TextEncoder().encode('ply\nno end')), null);
});

const gltf = {
	asset: { version: '2.0' },
	cameras: [
		{ type: 'perspective', name: 'Lens', perspective: { yfov: 0.7, znear: 0.1 } },
		{ type: 'orthographic', orthographic: { xmag: 1, ymag: 1, znear: 0.1, zfar: 10 } }
	],
	nodes: [{ name: 'Set' }, { name: 'Camera', camera: 0 }, { camera: 0 }, { name: 'Camera', camera: 0 }, { name: 'Top', camera: 1 }],
	accessors: [{ count: 49, type: 'SCALAR', componentType: 5126, min: [0], max: [2.0416667] }],
	animations: [{ samplers: [{ input: 0, output: 0 }], channels: [{ sampler: 0, target: { node: 1, path: 'translation' } }] }]
};

function glb(json) {
	const text = new TextEncoder().encode(JSON.stringify(json));
	const size = Math.ceil(text.length / 4) * 4;
	const out = new Uint8Array(20 + size).fill(0x20, 20);
	const view = new DataView(out.buffer);
	view.setUint32(0, 0x46546c67, true);
	view.setUint32(4, 2, true);
	view.setUint32(8, out.length, true);
	view.setUint32(12, size, true);
	view.setUint32(16, 0x4e4f534a, true);
	out.set(text, 20);
	return out;
}

test('scene jobs: a scene follows only its own job, a job still being submitted is not overwritten by an older one, lost and orphan jobs are found', () => {
	const scenes = [
		{ id: 's1', kind: 'splat', status: 'running', jobId: 'j2' },
		{ id: 's2', kind: 'splat', status: 'queued', jobId: null },
		{ id: 's3', kind: 'glb' }
	];
	assert.equal(jobScene(scenes, { id: 'j2', sceneId: 's1' }), scenes[0]);
	assert.equal(jobScene(scenes, { id: 'j1', sceneId: 's1', status: 'failed' }), null, 'an earlier failed attempt no longer overwrites the retry');
	assert.equal(jobScene(scenes, { id: 'j3', sceneId: 's2' }), scenes[1]);
	assert.equal(jobScene(scenes, { id: 'j3', sceneId: 's2' }, new Set(['s2'])), null);
	assert.equal(jobScene(scenes, { id: 'j3', sceneId: 's2' }, new Set(['s1'])), scenes[1]);
	assert.equal(jobScene(scenes, { id: 'j9', sceneId: 's3' }), null);
	assert.equal(jobScene(scenes, { id: 'j9', sceneId: 'gone' }), null);
	assert.equal(lostScene(scenes[0], [{ id: 'j1', sceneId: 's1' }]), true);
	assert.equal(lostScene(scenes[0], [{ id: 'j2', sceneId: 's1' }]), false);
	assert.equal(lostScene(scenes[1], [{ id: 'j3', sceneId: 's2' }]), false);
	assert.equal(lostScene(scenes[1], []), true);
	const live = new Map([
		['s1', 'j2'],
		['s2', 'j3'],
		['gone', 'j4'],
		['s4', 'j5'],
		['s5', 'j6']
	]);
	const now = [...scenes, { id: 's4', kind: 'splat', status: 'failed', jobId: 'j5' }, { id: 's5', kind: 'splat', status: 'running', jobId: 'j0' }];
	assert.deepEqual(orphanJobs(live, now), [
		['gone', 'j4'],
		['s4', 'j5'],
		['s5', 'j6']
	]);
});

function fakeTimers() {
	const pending = new Map();
	let next = 1;
	return {
		pending,
		setTimeout: (fn) => (pending.set(next, fn), next++),
		clearTimeout: (id) => pending.delete(id),
		async fire() {
			const [[id, fn]] = pending;
			pending.delete(id);
			await fn();
		}
	};
}

test('polling: one chain at a time, however often it is armed, stopped for good until armed again', async () => {
	const timers = fakeTimers();
	let busy = true;
	let release;
	let runs = 0;
	const poller = createPoller({ every: 2000, active: () => busy, timers, run: () => ((runs += 1), new Promise((resolve) => (release = resolve))) });
	poller.arm();
	poller.arm();
	assert.equal(timers.pending.size, 1);
	const first = timers.fire();
	assert.equal(poller.running, true);
	poller.arm();
	assert.equal(timers.pending.size, 0, 'arming while a request runs does not start a second chain');
	release();
	await first;
	assert.equal(timers.pending.size, 1);
	assert.equal(runs, 1);
	const second = timers.fire();
	poller.stop();
	poller.arm();
	release();
	await second;
	assert.equal(timers.pending.size, 1, 'stopped then armed during a request: one chain goes on');
	const third = timers.fire();
	poller.stop();
	release();
	await third;
	assert.equal(timers.pending.size, 0, 'stopped during a request: nothing is armed again');
	poller.arm();
	assert.equal(timers.pending.size, 1);
	busy = false;
	const fourth = timers.fire();
	release();
	await fourth;
	assert.equal(timers.pending.size, 0);
	poller.arm();
	assert.equal(timers.pending.size, 0);
	const quiet = createPoller({ every: 10, active: () => true, timers, run: async () => false });
	quiet.arm();
	await timers.fire();
	assert.equal(timers.pending.size, 0, 'a run that returns false ends the chain');
	assert.equal(quiet.armed, false);
});

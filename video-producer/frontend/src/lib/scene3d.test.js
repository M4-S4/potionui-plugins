import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
	FOCAL_RANGE,
	atSource,
	boundCamera,
	deviation,
	deviationLevel,
	distance,
	dollyCamera,
	focalToFov,
	fovToFocal,
	fitsFrame,
	fromSpherical,
	holesMatter,
	horizontalFov,
	lowestFocal,
	orbitCamera,
	panCamera,
	projectSize,
	reach,
	sourceView,
	spherical
} from './scene3d/camera.js';
import { plyHeader, plyView } from './scene3d/files.js';
import { createPoller, jobScene, lostScene, orphanJobs, reusableScene } from './scene3d/jobs.js';

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

test('reliable zone: the camera stops on its border, 15° around the source view or 25 % of its distance, and comes back from outside only toward it', () => {
	const { az, el, dist } = spherical(source);
	const far = { ...source, pos: fromSpherical(source.target, az + 40, el, dist) };
	const held = boundCamera(far, source, source);
	near(reach(held, source), 1, 1e-4);
	near(deviation(held, source).angle, 15, 1e-3);
	const inside = orbitCamera(source, 5, 0);
	assert.deepEqual(boundCamera(inside, source, source), inside);
	const pushed = boundCamera(dollyCamera(source, 0.5), source, source);
	near(deviation(pushed, source).shift, 0.25, 1e-4);
	const outside = { ...source, pos: fromSpherical(source.target, az + 30, el, dist) };
	const closer = { ...source, pos: fromSpherical(source.target, az + 20, el, dist) };
	assert.deepEqual(boundCamera(closer, outside, source), closer);
	assert.deepEqual(boundCamera(far, outside, source), outside);
});

test('reliable zone: no focal length wider than the source picture for a scene that has one, the whole range otherwise', () => {
	const view = sourceView({ kind: 'splat', view: { fov: 60, aspect: 16 / 9, depth: 4 } }, null);
	assert.equal(lowestFocal({ kind: 'splat', view: { fov: 60, aspect: 16 / 9, depth: 4 } }, view), view.focal);
	assert.equal(lowestFocal({ kind: 'splat', view: { fov: 170, aspect: 1, depth: 4 } }, { focal: 2 }), FOCAL_RANGE[0]);
	assert.equal(lowestFocal({ kind: 'splatfile', view: null }, view), FOCAL_RANGE[0]);
	assert.equal(lowestFocal(null, null), FOCAL_RANGE[0]);
});

test('reusable scene: a picture already lifted is not built again, a finished scene first, then one in progress, then a failed one to retry', () => {
	const scenes = [
		{ id: 'a', kind: 'splat', sourceAssetId: 'img', sourceTime: null, status: 'failed' },
		{ id: 'b', kind: 'splat', sourceAssetId: 'img', sourceTime: null, status: 'running' },
		{ id: 'c', kind: 'splat', sourceAssetId: 'img', sourceTime: null, status: 'done', fileId: 'f1' },
		{ id: 'd', kind: 'splat', sourceAssetId: 'clip', sourceTime: 1.5, status: 'done', fileId: 'f2' },
		{ id: 'e', kind: 'splatfile', fileId: 'f3' }
	];
	assert.equal(reusableScene(scenes, 'img').id, 'c');
	assert.equal(reusableScene(scenes.slice(0, 2), 'img').id, 'b');
	assert.equal(reusableScene(scenes.slice(0, 1), 'img').id, 'a');
	assert.equal(reusableScene(scenes, 'clip'), null, 'a frame of a video is another picture');
	assert.equal(reusableScene(scenes, 'other'), null);
	assert.equal(reusableScene(scenes, null), null);
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

test('scene jobs: a scene follows only its own job, a job still being submitted is not overwritten by an older one, lost and orphan jobs are found', () => {
	const scenes = [
		{ id: 's1', kind: 'splat', status: 'running', jobId: 'j2' },
		{ id: 's2', kind: 'splat', status: 'queued', jobId: null },
		{ id: 's3', kind: 'splatfile' }
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

test('reframing tool: the shot editor, the Director and the Shot menu open it, and only its viewer loads the 3D engine', () => {
	const read = (file) => readFileSync(new URL(file, import.meta.url), 'utf-8');
	assert.match(read('../components/modals/ShotEditor.svelte'), /ui\.modal = \{ type: 'reframe', id, returnTo: \{ type: 'shot', id, draft: \$state\.snapshot\(draft\), baseline \} \};/);
	assert.match(read('../components/modals/Modals.svelte'), /<ReframeTool id=\{m\.id\} returnTo=\{m\.returnTo \?\? null\} \/>/);
	assert.match(read('../components/panels/DirectorDock.svelte'), /onclick: openReframe \}\}>\{t\('panels\.dock\.refs\.reframe'\)\}/);
	assert.match(read('./commands.js'), /command\('reframe', openReframe\)/);
	assert.match(read('../components/modals/ReframeTool.svelte'), /<SceneViewer \{scene\} \/>/);
	assert.doesNotMatch(read('../VideoProducerPage.svelte'), /SceneViewer|workspace === 'scene'/);
	assert.match(read('./scene.svelte.js'), /import\('\.\/scene3d\/engine\.js'\)/);
	assert.doesNotMatch(read('./scene.svelte.js'), /ui\.workspace/);
});

test('source view: only the exact source camera counts, and the source picture stands in for it only when it has the frame of the project', () => {
	const source = { pos: [0, 0, 0], target: [0, 0, -4], focal: 26, roll: 0 };
	assert.equal(atSource({ ...source, pos: [...source.pos], target: [...source.target] }, source), true);
	assert.equal(atSource(orbitCamera(source, 0.5, 0), source), false);
	assert.equal(atSource({ ...source, focal: 27 }, source), false);
	assert.equal(atSource({ ...source, roll: 1 }, source), false);
	assert.equal(atSource(dollyCamera(source, 0.99), source), false);
	assert.equal(atSource(null, source), false);
	assert.equal(fitsFrame({ width: 1280, height: 720 }, 16 / 9), true);
	assert.equal(fitsFrame({ width: 1500, height: 1000 }, 16 / 9), false);
	assert.equal(fitsFrame({ width: 0, height: 720 }, 16 / 9), false);
	assert.equal(fitsFrame(null, 16 / 9), false);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	FPS,
	MAX_REFERENCE_SIDE,
	PRESETS,
	cameraAt,
	cameraKeys,
	deviation,
	deviationLevel,
	distance,
	dollyCamera,
	focalToFov,
	fovToFocal,
	frameCount,
	FRAME_STEP,
	holesMatter,
	horizontalFov,
	interpolate,
	migrateKeyframe,
	orbitCamera,
	panCamera,
	presetAmount,
	presetBase,
	presetWarns,
	projectSize,
	renderPoses,
	renderSize,
	renderTimes,
	retime,
	rollOf,
	sampleTimes,
	smoothstep,
	sourceView,
	spherical,
	trajectory
} from './scene3d/camera.js';
import { GLTF_READ_LIMIT, cameraNode, gltfCameras, gltfExternal, gltfJson, packGltf, plyHeader, plyView, readSceneHead, sceneFileKind, sceneName } from './scene3d/files.js';
import { assetInUse, controlFor, dropPlanControls, movePlan, planSignature, pruneAsset } from './scene3d/doc.js';
import { createPoller, jobScene, lostScene, orphanJobs } from './scene3d/jobs.js';

const near = (actual, expected, eps = 1e-6) => assert.ok(Math.abs(actual - expected) <= eps, `${actual} is not ${expected}`);
const nearVec = (actual, expected, eps = 1e-6) => expected.forEach((v, i) => near(actual[i], v, eps));
let n = 0;
const makeId = () => `k${++n}`;
const source = { pos: [0, 0, 0], target: [0, 0, -4], focal: 30, roll: 0 };

test('smoothstep eases in and out between 0 and 1 and clamps outside', () => {
	assert.deepEqual([smoothstep(-1), smoothstep(0), smoothstep(0.5), smoothstep(1), smoothstep(2)], [0, 0, 0.5, 1, 1]);
	near(smoothstep(0.25), 0.15625);
});

test('focal length and field of view: 36 mm wide sensor, horizontal fov 2·atan(18/focal), vertical from the aspect', () => {
	near(horizontalFov(36), (2 * Math.atan(0.5) * 180) / Math.PI);
	near(horizontalFov(18), 90);
	near(focalToFov(18, 1), 90);
	near(focalToFov(fovToFocal(60, 16 / 9), 16 / 9), 60);
	near(fovToFocal(focalToFov(35, 2.39), 2.39), 35);
	assert.ok(focalToFov(35, 16 / 9) < horizontalFov(35));
});

test('trajectories: orbit ±10°, push in 15 % of the depth, rise +10° by default, around the target, bounded by the contract', () => {
	assert.deepEqual(PRESETS, {
		orbit: { value: 10, min: 3, max: 45, warn: 15, unit: 'deg' },
		dolly: { value: 15, min: 5, max: 60, warn: 25, unit: 'pct' },
		crane: { value: 10, min: 3, max: 45, warn: 15, unit: 'deg' }
	});
	assert.deepEqual([presetAmount('orbit', undefined), presetAmount('orbit', 1), presetAmount('dolly', 90), presetAmount('crane', 20), presetAmount('spin', 5)], [10, 3, 60, 20, null]);
	const orbit = trajectory('orbit', 10, source, 5, makeId);
	assert.deepEqual(orbit.map((k) => k.t), [0, 5]);
	for (const k of orbit) {
		near(distance(k.pos, k.target), 4, 1e-5);
		assert.deepEqual(k.target, [0, 0, -4]);
		assert.equal(k.focal, 30);
	}
	near(spherical(orbit[0]).az, -10, 1e-4);
	near(spherical(orbit[1]).az, 10, 1e-4);
	const dolly = trajectory('dolly', undefined, source, 4, makeId);
	assert.deepEqual(dolly[0].pos, [0, 0, 0]);
	nearVec(dolly[1].pos, [0, 0, -0.6]);
	const crane = trajectory('crane', 10, source, 4, makeId);
	near(spherical(crane[1]).el, 10, 1e-4);
	near(distance(crane[1].pos, crane[1].target), 4, 1e-5);
	assert.ok(crane[1].pos[1] > 0);
	assert.deepEqual(trajectory('spin', 10, source, 4, makeId), []);
	assert.equal(new Set([...orbit, ...dolly, ...crane].map((k) => k.id)).size, 6);
});

test('the holes warning starts past 15° or 25 %, and only matters for a scene with a source view', () => {
	assert.deepEqual([presetWarns('orbit', 15), presetWarns('orbit', 16), presetWarns('dolly', 25), presetWarns('dolly', 30), presetWarns('crane', 45)], [false, true, false, true, true]);
	assert.equal(holesMatter({ kind: 'splat', view: { fov: 50, aspect: 1.5, depth: 4 } }), true);
	assert.equal(holesMatter({ kind: 'splatfile', view: null }), false);
	assert.equal(holesMatter({ kind: 'glb', cameras: [] }), false);
});

test('cameraAt: pos and target eased by smoothstep along an arc around the target, focal linear, clamped at both ends', () => {
	const keys = [
		{ id: 'a', t: 0, pos: [0, 0, 0], target: [0, 0, -4], focal: 20, roll: 0 },
		{ id: 'b', t: 2, pos: [4 * Math.sin(Math.PI / 4), 0, -4 + 4 * Math.cos(Math.PI / 4)], target: [0, 0, -4], focal: 40, roll: 10 }
	];
	const plan = { keyframes: keys };
	assert.equal(cameraAt({ keyframes: [] }, 1), null);
	assert.deepEqual(cameraAt(plan, -1).pos, keys[0].pos);
	assert.deepEqual(cameraAt(plan, 5).pos, keys[1].pos);
	const mid = cameraAt(plan, 1);
	near(distance(mid.pos, mid.target), 4);
	near(spherical(mid).az, 22.5);
	near(mid.focal, 30);
	near(mid.roll, 5);
	const quarter = cameraAt(plan, 0.5);
	near(spherical(quarter).az, 45 * smoothstep(0.25));
	near(quarter.focal, 25);
	const push = interpolate({ pos: [0, 0, 0], target: [0, 0, -4], focal: 30 }, { pos: [0, 0, -2], target: [0, 0, -4], focal: 30 }, 0.5);
	nearVec(push.pos, [0, 0, -1]);
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

test('deviation from the source view: the angle seen from the pivot and the push along the source axis', () => {
	const orbit = trajectory('orbit', 15, source, 1, makeId);
	const side = deviation(orbit[1], source);
	near(side.angle, 15, 1e-4);
	assert.ok(side.shift < 0.05);
	assert.equal(deviationLevel(side), 'near');
	const pushed = deviation(trajectory('dolly', 25, source, 1, makeId)[1], source);
	near(pushed.angle, 0);
	near(pushed.shift, 0.25);
	assert.equal(deviationLevel({ angle: 2, shift: 0.05 }), 'ok');
	assert.equal(deviationLevel({ angle: 16, shift: 0 }), 'holes');
	assert.equal(deviationLevel({ angle: 0, shift: 0.3 }), 'holes');
});

test('source view: the source camera at the origin looks at (0, 0, −depth) with the fov of VIEW; a Blender scene starts from its first camera or frames its bounds', () => {
	const view = sourceView({ kind: 'splat', view: { fov: 60, aspect: 16 / 9, depth: 4 } }, null);
	assert.deepEqual([view.pos, view.target, view.roll], [[0, 0, 0], [0, 0, -4], 0]);
	near(focalToFov(view.focal, 16 / 9), 60, 1e-3);
	const camera = { pos: [1, 2, 3], target: [1, 2, 2], focal: 50, roll: 0 };
	assert.deepEqual(sourceView({ kind: 'glb', cameras: [] }, { camera, bounds: { center: [0, 0, 0], radius: 2 } }), camera);
	const framed = sourceView({ kind: 'splatfile', view: null }, { bounds: { center: [0, 1, -5], radius: 2 } });
	assert.deepEqual(framed.target, [0, 1, -5]);
	nearVec(framed.pos, [0, 1.5, -0.6]);
	assert.deepEqual(sourceView(null, null).target, [0, 0, -4]);
	const base = presetBase({ kind: 'glb', cameras: [] }, { pos: [0, 0, 10], target: [0, 0, 9], focal: 35, roll: 0 }, { bounds: { center: [0, 0, 0], radius: 1 } });
	assert.deepEqual([base.pos, base.target], [[0, 0, 10], [0, 0, 0]]);
});

test('Blender camera: samples at 24 fps, target 1 m along local −z, focal from yfov and the aspect, roll from the quaternion', () => {
	assert.equal(FPS, 24);
	assert.equal(sampleTimes(1).length, 25);
	assert.deepEqual(sampleTimes(0.1), [0, 0.041667, 0.083333]);
	assert.deepEqual(sampleTimes(0), [0]);
	const half = Math.SQRT1_2;
	const [still, turned, rolled] = cameraKeys(
		[
			{ t: 0, pos: [0, 1, 5], quat: [0, 0, 0, 1], yfov: 40, aspect: null },
			{ t: 1 / 24, pos: [0, 1, 5], quat: [0, half, 0, half], yfov: 40, aspect: 2 },
			{ t: 2 / 24, pos: [0, 1, 5], quat: [0, 0, Math.sin(Math.PI / 12), Math.cos(Math.PI / 12)], yfov: 40, aspect: null }
		],
		16 / 9,
		makeId
	);
	assert.deepEqual(still.target, [0, 1, 4]);
	near(still.focal, fovToFocal(40, 16 / 9), 1e-3);
	near(still.roll, 0);
	nearVec(turned.target, [-1, 1, 5]);
	near(turned.focal, fovToFocal(40, 2), 1e-3);
	near(rolled.roll, 30, 1e-3);
	near(rollOf([0, 0, -1], [0, 1, 0]), 0);
	near(turned.t, 0.0417, 1e-4);
});

test('render size: captures at the project frame (short side from the resolution, long side from the aspect); the reference video capped at 1280 on its long side with the same aspect ratio, even sides', () => {
	assert.equal(MAX_REFERENCE_SIDE, 1280);
	assert.deepEqual(projectSize('1080p', 16 / 9), { width: 1920, height: 1080 });
	assert.deepEqual(renderSize(projectSize('1080p', 16 / 9)), { width: 1280, height: 720 });
	assert.deepEqual(projectSize('720p', 16 / 9), { width: 1280, height: 720 });
	assert.deepEqual(renderSize(projectSize('720p', 16 / 9)), { width: 1280, height: 720 });
	assert.deepEqual(projectSize('1080p', 9 / 16), { width: 1080, height: 1920 });
	assert.deepEqual(renderSize(projectSize('1080p', 9 / 16)), { width: 720, height: 1280 });
	assert.deepEqual(projectSize('4K', 16 / 9), { width: 3840, height: 2160 });
	assert.deepEqual(renderSize(projectSize('4K', 16 / 9)), { width: 1280, height: 720 });
	assert.deepEqual(renderSize(projectSize('480p', 16 / 9)), { width: 852, height: 480 });
	assert.deepEqual(renderSize(projectSize('1080p', 16 / 9), 1920), { width: 1920, height: 1080 });
	assert.deepEqual(renderSize(projectSize('1080p', 2.39)), { width: 1280, height: 536 });
	for (const size of [projectSize('1080p', 16 / 9), projectSize('1080p', 1), projectSize('4K', 2.39), projectSize('720p', 4 / 5)]) {
		const video = renderSize(size);
		assert.ok(Math.max(video.width, video.height) <= MAX_REFERENCE_SIDE);
		assert.equal(video.width % 2, 0);
		assert.equal(video.height % 2, 0);
		assert.ok(Math.abs(video.width / video.height / (size.width / size.height) - 1) < 0.005);
	}
	assert.deepEqual(projectSize('1080p', 2.39), { width: 2580, height: 1080 });
	assert.deepEqual(projectSize('1080p', 9), { width: 1920, height: 1080 });
	assert.deepEqual(projectSize('weird', 1), { width: 1080, height: 1080 });
});

test('frames: 1 + 8k frames at 24 fps, at least the length of the 3D shot, one every 1/24 s from the start key, the last one on the end key and the extra ones holding it, the pose a pure function of the frame index', () => {
	assert.equal(FRAME_STEP, 8);
	assert.equal(frameCount(5.17), 129);
	assert.equal(frameCount(3), 73);
	assert.equal(frameCount(2), 49);
	assert.equal(frameCount(0.01), 9);
	const times = renderTimes(2);
	assert.equal(times.length, 49);
	assert.deepEqual([times[0], times[48]], [0, 2]);
	near(times[1], 1 / 24);
	assert.ok(times.every((t, i) => i === 0 || t > times[i - 1]));
	const three = renderTimes(3);
	assert.equal(three.length, 73);
	assert.ok(three.every((t, i) => Math.abs(t - i / 24) < 1e-9));
	assert.equal(renderTimes(3.02).at(-1), 3.02);
	assert.deepEqual(renderTimes(0.01), [0, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]);
	const long = renderTimes(5.17);
	assert.equal(long.at(-1), 5.17);
	assert.deepEqual(long.slice(125), [5.17, 5.17, 5.17, 5.17]);
	assert.ok(long.every((t, i) => i === 0 || t >= long[i - 1]));
	const plan = { dur: 2, keyframes: trajectory('orbit', 10, source, 2, makeId) };
	const poses = renderPoses(plan);
	assert.equal(poses.length, 49);
	assert.deepEqual(poses[0], cameraAt(plan, 0));
	assert.deepEqual(poses[0].pos, plan.keyframes[0].pos);
	assert.deepEqual(poses[48].pos, plan.keyframes[1].pos);
	assert.deepEqual(poses[48], cameraAt(plan, 2));
	assert.deepEqual(renderPoses(plan), poses);
	assert.deepEqual(retime(plan.keyframes, 2, 4).map((k) => k.t), [0, 4]);
	assert.equal(retime(plan.keyframes, 0, 4), plan.keyframes);
});

test('migrateKeyframe: the old {az, el, dist, focal, height} keys become pos/target with the formula of the old eye()', () => {
	const k = migrateKeyframe({ id: 'k', t: 1.5, az: 90, el: 0, dist: 10, focal: 28, height: 1.4 });
	assert.deepEqual(Object.keys(k), ['id', 't', 'pos', 'target', 'focal', 'roll']);
	nearVec(k.pos, [10, 1.4, 0]);
	assert.deepEqual([k.target, k.focal, k.roll, k.t], [[0, 1.4, 0], 28, 0, 1.5]);
	const up = migrateKeyframe({ id: 'u', t: 0, az: 0, el: 30, dist: 2, focal: 35, height: 0 });
	nearVec(up.pos, [0, 1, Math.sqrt(3)]);
	const current = { id: 'c', t: 0, pos: [1, 2, 3], target: [0, 0, 0], focal: 35, roll: 0 };
	assert.equal(migrateKeyframe(current), current);
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

test('glTF cameras: the perspective camera nodes, named and made unique, animated with the length of their animation', () => {
	const expected = [
		{ name: 'Camera', animated: true, duration: 2.0417 },
		{ name: 'Lens', animated: false, duration: null },
		{ name: 'Camera 2', animated: false, duration: null }
	];
	assert.deepEqual(gltfCameras(gltf), expected);
	assert.deepEqual(gltfCameras(glb(gltf)), expected);
	assert.deepEqual(gltfCameras(JSON.stringify(gltf)), expected);
	assert.deepEqual(gltfJson(glb(gltf)).nodes.length, 5);
	assert.deepEqual([cameraNode(gltf, 'Camera'), cameraNode(gltf, 'Lens'), cameraNode(gltf, 'Camera 2'), cameraNode(gltf, 'Top'), cameraNode(gltf, 'nope')], [1, 2, 3, -1, -1]);
	assert.deepEqual(gltfCameras({ asset: {} }), []);
	assert.deepEqual(gltfCameras(new Uint8Array([1, 2, 3])), []);
	assert.equal(gltfJson('not json'), null);
});

test('scene files: splats and Blender files by extension, the name without it', () => {
	assert.deepEqual(['a.PLY', 'b.spz', 'c.splat', 'd.glb', 'e.gltf', 'f.obj', 'noext'].map(sceneFileKind), [
		{ kind: 'splat', format: 'ply' },
		{ kind: 'splat', format: 'spz' },
		{ kind: 'splat', format: 'splat' },
		{ kind: 'glb', format: 'glb' },
		{ kind: 'glb', format: 'gltf' },
		null,
		null
	]);
	assert.equal(sceneName('C:\\scans\\harbour.v2.ply'), 'harbour.v2');
	assert.equal(sceneName('set.glb'), 'set');
});

const dataUri = 'data:application/octet-stream;base64,AAAA';

test('a .gltf is accepted only when its buffers and images are data: URIs, and is packed into a .glb that keeps them', () => {
	assert.deepEqual(gltfExternal({ buffers: [{ uri: dataUri, byteLength: 3 }], images: [{ uri: 'data:image/png;base64,AA' }] }), []);
	assert.deepEqual(gltfExternal({ buffers: [{ uri: 'scene.bin', byteLength: 3 }], images: [{ uri: 'wood.png' }, { bufferView: 0, mimeType: 'image/png' }] }), ['scene.bin', 'wood.png']);
	assert.deepEqual(gltfExternal({ buffers: [{ byteLength: 3 }] }), ['']);
	assert.deepEqual(gltfExternal({ asset: {} }), []);
	const json = { ...gltf, buffers: [{ uri: dataUri, byteLength: 3 }] };
	const text = JSON.stringify(json);
	const packed = packGltf(new Uint8Array([0xef, 0xbb, 0xbf, ...new TextEncoder().encode(text)]));
	const view = new DataView(packed.buffer);
	assert.deepEqual([view.getUint32(0, true), view.getUint32(4, true), view.getUint32(8, true), view.getUint32(16, true)], [0x46546c67, 2, packed.length, 0x4e4f534a]);
	assert.equal(packed.length % 4, 0);
	assert.equal(view.getUint32(12, true), packed.length - 20);
	assert.deepEqual(gltfJson(packed), json);
	assert.deepEqual(gltfCameras(packed), gltfCameras(json));
});

test('reading a Blender file before the upload: the JSON chunk of a .glb only, a self-contained .gltf packed, and a clear refusal for the others', async () => {
	const ok = new Blob([JSON.stringify({ ...gltf, buffers: [{ uri: dataUri, byteLength: 3 }] })]);
	const packed = await readSceneHead(ok, 'gltf');
	assert.equal(packed.error, undefined);
	assert.equal(packed.json.nodes.length, 5);
	assert.deepEqual(gltfCameras(packed.packed).map((c) => c.name), ['Camera', 'Lens', 'Camera 2']);
	assert.deepEqual(await readSceneHead(new Blob([JSON.stringify({ ...gltf, buffers: [{ uri: 'set.bin', byteLength: 3 }] })]), 'gltf'), { error: 'gltf_external' });
	assert.deepEqual(await readSceneHead(new Blob(['{ not json']), 'gltf'), { error: 'gltf_invalid' });
	assert.deepEqual(await readSceneHead(ok, 'gltf', 16), { error: 'gltf_large' });
	assert.equal(GLTF_READ_LIMIT, 64 * 1024 * 1024);
	const binary = glb(gltf);
	const big = new Blob([binary, new Uint8Array(1 << 20)]);
	let read = 0;
	const spy = { size: big.size, slice: (a, b) => ((read += Math.min(b, big.size) - a), big.slice(a, b)) };
	const head = await readSceneHead(spy, 'glb');
	assert.equal(head.json.nodes.length, 5);
	assert.equal(head.rename, false);
	assert.equal(read, 20 + binary.length, 'only the header and the JSON chunk are read');
	assert.equal((await readSceneHead(new Blob([binary]), 'gltf')).rename, true);
	assert.equal((await readSceneHead(new Blob([binary]), 'glb', 8)).json, null);
	assert.equal((await readSceneHead(new Blob([new Uint8Array(4)]), 'glb')).json, null);
});

test('plan signature: changes with the keys, the length, the start, the scene, the amount, the preset and the camera, not with the name', () => {
	const plan = { id: 'p', name: 'A', shotId: 'c1', sceneId: 's1', start: 0, dur: 4, source: 'trajectory', preset: 'orbit', amount: 10, camera: null, keyframes: trajectory('orbit', 10, source, 4, makeId) };
	const base = planSignature(plan);
	assert.equal(planSignature({ ...plan, name: 'B' }), base);
	assert.equal(planSignature(JSON.parse(JSON.stringify(plan))), base);
	for (const change of [{ dur: 5 }, { start: 1 }, { sceneId: 's2' }, { amount: 12 }, { preset: 'dolly' }, { camera: 'Cam' }, { keyframes: plan.keyframes.slice(1) }]) assert.notEqual(planSignature({ ...plan, ...change }), base);
	assert.equal(planSignature(null), '');
});

test('3D shot and its reference video: found by planId or by the old shot rule, moved and made stale with the shot, dropped with the 3D shot', () => {
	const plan = { id: 'p1', shotId: 'c1', start: 2 };
	const own = { id: 'g1', source: 'scene3d', planId: 'p1', shotId: 'c1', start: 2, stale: false };
	const legacy = { id: 'g2', source: 'scene3d', planId: null, shotId: 'c1', start: 2, stale: false };
	const other = { id: 'g3', source: 'import', shotId: 'c1', start: 2 };
	assert.equal(controlFor([legacy, own], plan), own);
	assert.equal(controlFor([other, legacy], plan), legacy);
	assert.equal(controlFor([other], plan), null);
	assert.equal(controlFor([{ ...legacy, shotId: null, start: 2 }], { id: 'p9', shotId: null, start: 2 }).id, 'g2');
	assert.equal(controlFor([own], null), null);
	const controls = [{ ...own }, { ...other }];
	const moved = { ...plan };
	assert.equal(movePlan(controls, moved, 'c1'), null);
	assert.equal(controls[0].stale, false);
	const control = movePlan(controls, moved, 'c2');
	assert.equal(control, controls[0]);
	assert.deepEqual([moved.shotId, control.shotId, control.stale, control.planId], ['c2', 'c2', true, 'p1']);
	assert.equal(controls[1].shotId, 'c1');
	const adopted = [{ ...legacy }];
	movePlan(adopted, { ...plan }, null);
	assert.deepEqual([adopted[0].shotId, adopted[0].planId, adopted[0].stale], [null, 'p1', true]);
	assert.equal(movePlan([], { ...plan }, 'c3'), null);
	const list = [{ id: 'a', planId: 'p1' }, { id: 'b', planId: 'p2' }, { id: 'c', planId: 'p1' }, { id: 'd' }];
	assert.equal(dropPlanControls(list, 'p1'), 2);
	assert.deepEqual(list.map((c) => c.id), ['b', 'd']);
});

test('an old reference video leaves the project only when nothing else uses its asset', () => {
	const doc = {
		assets: [{ id: 'v1' }, { id: 'v2' }, { id: 'v3' }, { id: 'img' }, { id: 'src' }],
		clips: [{ id: 'c1', assetId: 'v2' }],
		audio: [],
		frames: [{ id: 'f1', assetId: 'img' }],
		references: [{ id: 'r1', assetId: 'v3' }],
		controls: [{ id: 'g1', assetId: 'new' }],
		scenes: [{ id: 's1', kind: 'splat', sourceAssetId: 'src' }]
	};
	assert.deepEqual(['v1', 'v2', 'v3', 'img', 'src', 'new', null].map((id) => assetInUse(doc, id)), [false, true, true, true, true, true, false]);
	assert.equal(pruneAsset(doc, 'v2'), false);
	assert.equal(pruneAsset(doc, 'v3'), false);
	assert.equal(pruneAsset(doc, 'v1'), true);
	assert.equal(pruneAsset(doc, 'v1'), false);
	assert.equal(pruneAsset(doc, null), false);
	assert.deepEqual(doc.assets.map((a) => a.id), ['v2', 'v3', 'img', 'src']);
	assert.equal(assetInUse({ assets: [] }, 'x'), false);
});

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

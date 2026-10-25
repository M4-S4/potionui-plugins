import { test } from 'node:test';
import assert from 'node:assert/strict';
import { orbitCamera, dollyCamera, focalToFov } from './scene3d/camera.js';
import { STREAK_WARN, streakLevel, streakShare, streakTable } from './scene3d/streaks.js';

const SOURCE = { pos: [0, 0, 0], target: [0, 0, -4], focal: 26, roll: 0 };
const ASPECT = 16 / 9;
const posed = (cam) => ({ ...cam, fov: focalToFov(cam.focal, ASPECT) });

function quatBetween(from, to) {
	const [ax, ay, az] = from;
	const [bx, by, bz] = to;
	const cx = ay * bz - az * by;
	const cy = az * bx - ax * bz;
	const cz = ax * by - ay * bx;
	const w = 1 + ax * bx + ay * by + az * bz;
	const n = Math.hypot(cx, cy, cz, w);
	return { x: cx / n, y: cy / n, z: cz / n, w: w / n };
}

function splats({ ribbon = true } = {}) {
	const list = [];
	const step = 0.04;
	for (let x = -3; x <= 3; x += step) {
		for (let y = -1.8; y <= 1.8; y += step) list.push({ c: { x, y, z: -4 }, s: { x: step, y: step, z: 0.002 }, q: { x: 0, y: 0, z: 0, w: 1 }, o: 1 });
	}
	if (ribbon) {
		for (let y = -0.6; y <= 0.4; y += 0.01) {
			for (let x = -0.9; x <= -0.6; x += 0.01) {
				const c = { x, y, z: -1.5 };
				const len = Math.hypot(c.x, c.y, c.z);
				list.push({ c, s: { x: 0.004, y: 0.004, z: 0.35 }, q: quatBetween([0, 0, 1], [c.x / len, c.y / len, c.z / len]), o: 1 });
			}
		}
	}
	return (cb) => list.forEach((g, i) => cb(i, g.c, g.s, g.q, g.o));
}

test('streaks: none at the source view, ribbons along the source rays stretch once the camera turns or moves in, a zoom alone stretches nothing', () => {
	const table = streakTable(splats(), SOURCE);
	assert.ok(table.count > 10000);
	const at = (cam) => streakShare(table, posed(cam), 640, 360, 8);
	assert.ok(at(SOURCE) < 0.002, `source ${at(SOURCE)}`);
	const turned = at(orbitCamera(SOURCE, 12, 0));
	assert.ok(turned > STREAK_WARN, `turned ${turned}`);
	assert.equal(streakLevel(turned), 'streaks');
	assert.ok(at({ ...SOURCE, focal: 70 }) < 0.002, 'zoom');
	assert.ok(at(dollyCamera(SOURCE, 0.9)) > STREAK_WARN, 'push');
	const flat = streakTable(splats({ ribbon: false }), SOURCE);
	assert.ok(streakShare(flat, posed(orbitCamera(SOURCE, 12, 0)), 640, 360, 8) < 0.002, 'flat wall');
	assert.equal(streakLevel(null), 'ok');
	const sampled = streakShare(table, posed(orbitCamera(SOURCE, 12, 0)), 640, 360, 16, 4);
	assert.ok(Math.abs(sampled - turned) < 0.02, `sampled ${sampled} against ${turned}`);
});

test('streaks: a splat file stored upside down, as the stage turns it, measures the same as its upright twin', () => {
	const upright = streakTable(splats(), SOURCE);
	const turned = (cb) =>
		splats()((i, c, s, q, o) => cb(i, { x: c.x, y: -c.y, z: -c.z }, s, { x: q.x, y: -q.y, z: -q.z, w: q.w }, o));
	const flipped = streakTable(turned, SOURCE, true);
	const cam = posed(orbitCamera(SOURCE, 12, 0));
	assert.ok(Math.abs(streakShare(upright, cam, 640, 360, 8) - streakShare(flipped, cam, 640, 360, 8)) < 1e-9);
});

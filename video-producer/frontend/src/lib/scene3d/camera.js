export const FPS = 24;
export const MIN_REFERENCE_SECONDS = 2;
export const SENSOR_HALF_WIDTH = 18;
export const WARN_ANGLE = 15;
export const WARN_SHIFT = 0.25;
export const DEFAULT_FOCAL = 35;
export const FOCAL_RANGE = [12, 135];
export const ROLL_RANGE = [-45, 45];
const MAX_ELEVATION = 85;
const EPS = 1e-9;

export const PRESETS = {
	orbit: { value: 10, min: 3, max: 45, warn: WARN_ANGLE, unit: 'deg' },
	dolly: { value: 15, min: 5, max: 60, warn: WARN_SHIFT * 100, unit: 'pct' },
	crane: { value: 10, min: 3, max: 45, warn: WARN_ANGLE, unit: 'deg' }
};
export const PRESET_IDS = Object.keys(PRESETS);

const SHORT_SIDES = { '4K': 2160 };
export const MAX_REFERENCE_SIDE = 1280;

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const rad = (d) => (d * Math.PI) / 180;
const deg = (r) => (r * 180) / Math.PI;
const fixed = (v, digits = 6) => +v.toFixed(digits);

export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const length = (a) => Math.hypot(a[0], a[1], a[2]);
export const distance = (a, b) => length(sub(a, b));
const lerp = (a, b, s) => a + (b - a) * s;
const lerp3 = (a, b, s) => [lerp(a[0], b[0], s), lerp(a[1], b[1], s), lerp(a[2], b[2], s)];
const round3 = (a) => a.map((v) => fixed(v));

export function normalize(a) {
	const l = length(a);
	return l < EPS ? [0, 0, 0] : scale(a, 1 / l);
}

export function smoothstep(u) {
	const x = clamp(u, 0, 1);
	return x * x * (3 - 2 * x);
}

export function focalToFov(focal, aspect) {
	return deg(2 * Math.atan(SENSOR_HALF_WIDTH / (focal * aspect)));
}

export function fovToFocal(fov, aspect) {
	return SENSOR_HALF_WIDTH / (Math.tan(rad(fov) / 2) * aspect);
}

export function horizontalFov(focal) {
	return deg(2 * Math.atan(SENSOR_HALF_WIDTH / focal));
}

export function pose(k) {
	return { pos: [...k.pos], target: [...k.target], focal: k.focal, roll: k.roll ?? 0 };
}

function slerpDirection(a, b, s) {
	const cos = clamp(dot(a, b), -1, 1);
	if (cos > 0.9999 || cos < -0.9999) return normalize(lerp3(a, b, s));
	const angle = Math.acos(cos);
	const sin = Math.sin(angle);
	return add(scale(a, Math.sin((1 - s) * angle) / sin), scale(b, Math.sin(s * angle) / sin));
}

export function interpolate(a, b, s, u = s) {
	const target = lerp3(a.target, b.target, s);
	const offA = sub(a.pos, a.target);
	const offB = sub(b.pos, b.target);
	const lenA = length(offA);
	const lenB = length(offB);
	const offset = lenA < EPS || lenB < EPS ? lerp3(offA, offB, s) : scale(slerpDirection(scale(offA, 1 / lenA), scale(offB, 1 / lenB), s), lerp(lenA, lenB, s));
	return { pos: add(target, offset), target, focal: lerp(a.focal, b.focal, u), roll: lerp(a.roll ?? 0, b.roll ?? 0, s) };
}

export function cameraAt(plan, time) {
	const keys = plan?.keyframes ?? [];
	if (!keys.length) return null;
	if (time <= keys[0].t) return pose(keys[0]);
	const last = keys[keys.length - 1];
	if (time >= last.t) return pose(last);
	const i = keys.findIndex((k) => k.t > time);
	const a = keys[i - 1];
	const b = keys[i];
	const u = (time - a.t) / (b.t - a.t);
	return interpolate(a, b, smoothstep(u), u);
}

export function spherical(cam) {
	const offset = sub(cam.pos, cam.target);
	const dist = length(offset);
	if (dist < EPS) return { az: 0, el: 0, dist: 0 };
	return { az: deg(Math.atan2(offset[0], offset[2])), el: deg(Math.asin(clamp(offset[1] / dist, -1, 1))), dist };
}

export function fromSpherical(target, az, el, dist) {
	const a = rad(az);
	const e = rad(el);
	return add(target, [Math.sin(a) * Math.cos(e) * dist, Math.sin(e) * dist, Math.cos(a) * Math.cos(e) * dist]);
}

export function basis(cam) {
	const forward = normalize(sub(cam.target, cam.pos));
	let right = cross(forward, [0, 1, 0]);
	right = length(right) < 1e-6 ? [1, 0, 0] : normalize(right);
	const up = cross(right, forward);
	const r = rad(cam.roll ?? 0);
	return { forward, right: add(scale(right, Math.cos(r)), scale(up, Math.sin(r))), up: add(scale(up, Math.cos(r)), scale(right, -Math.sin(r))) };
}

export function orbitCamera(cam, dAz, dEl) {
	const { az, el, dist } = spherical(cam);
	return { ...cam, pos: fromSpherical(cam.target, az + dAz, clamp(el + dEl, -MAX_ELEVATION, MAX_ELEVATION), dist) };
}

export function panCamera(cam, dx, dy) {
	const { right, up } = basis(cam);
	const dist = distance(cam.pos, cam.target);
	const move = add(scale(right, dx * dist), scale(up, dy * dist));
	return { ...cam, pos: add(cam.pos, move), target: add(cam.target, move) };
}

export function dollyCamera(cam, factor, minDist = 0.01) {
	const offset = sub(cam.pos, cam.target);
	const dist = length(offset);
	if (dist < EPS) return cam;
	const next = Math.max(minDist, dist * factor);
	return { ...cam, pos: add(cam.target, scale(offset, next / dist)) };
}

export function presetAmount(preset, amount) {
	const spec = PRESETS[preset];
	if (!spec) return null;
	return clamp(Number.isFinite(amount) ? amount : spec.value, spec.min, spec.max);
}

export function presetWarns(preset, amount) {
	const spec = PRESETS[preset];
	return Boolean(spec) && presetAmount(preset, amount) > spec.warn;
}

export function trajectory(preset, amount, base, dur, makeId) {
	const value = presetAmount(preset, amount);
	if (value === null) return [];
	const { az, el, dist } = spherical(base);
	const key = (t, pos) => ({ id: makeId(), t: fixed(t, 4), pos: round3(pos), target: round3(base.target), focal: fixed(base.focal, 3), roll: fixed(base.roll ?? 0, 3) });
	if (preset === 'orbit') return [key(0, fromSpherical(base.target, az - value, el, dist)), key(dur, fromSpherical(base.target, az + value, el, dist))];
	if (preset === 'dolly') return [key(0, base.pos), key(dur, fromSpherical(base.target, az, el, dist * (1 - value / 100)))];
	return [key(0, base.pos), key(dur, fromSpherical(base.target, az, clamp(el + value, -MAX_ELEVATION, MAX_ELEVATION), dist))];
}

export function retime(keyframes, from, to) {
	if (!(from > 0) || !(to > 0)) return keyframes;
	return keyframes.map((k) => ({ ...k, t: fixed((k.t * to) / from, 4) }));
}

export function deviation(cam, source) {
	const depth = distance(source.pos, source.target);
	if (depth < EPS) return { angle: 0, shift: 0 };
	const a = sub(source.pos, source.target);
	const b = sub(cam.pos, source.target);
	const lb = length(b);
	const angle = lb < EPS ? 0 : deg(Math.acos(clamp(dot(a, b) / (depth * lb), -1, 1)));
	const forward = scale(a, -1 / depth);
	return { angle, shift: Math.abs(dot(sub(cam.pos, source.pos), forward)) / depth };
}

export function deviationLevel({ angle, shift }) {
	const ratio = Math.max(angle / WARN_ANGLE, shift / WARN_SHIFT);
	if (ratio > 1) return 'holes';
	if (ratio > 2 / 3) return 'near';
	return 'ok';
}

export function holesMatter(scene) {
	return Boolean(scene && scene.kind !== 'glb' && scene.view);
}

export function sourceView(scene, info) {
	if (scene && scene.kind !== 'glb' && scene.view?.depth > 0 && scene.view.fov > 0) {
		const { fov, aspect, depth } = scene.view;
		return { pos: [0, 0, 0], target: [0, 0, -depth], focal: fixed(fovToFocal(fov, aspect > 0 ? aspect : 1), 3), roll: 0 };
	}
	if (info?.camera) return pose(info.camera);
	if (info?.bounds) {
		const { center, radius } = info.bounds;
		const r = radius > EPS ? radius : 1;
		return { pos: add(center, [0, r * 0.25, r * 2.2]), target: [...center], focal: DEFAULT_FOCAL, roll: 0 };
	}
	return { pos: [0, 0, 0], target: [0, 0, -4], focal: DEFAULT_FOCAL, roll: 0 };
}

export function presetBase(scene, cam, info) {
	if (scene?.kind === 'glb' && info?.bounds) return { pos: [...cam.pos], target: [...info.bounds.center], focal: cam.focal, roll: cam.roll ?? 0 };
	return sourceView(scene, info);
}

export function sampleTimes(duration, fps = FPS) {
	if (!(duration > 0)) return [0];
	const n = Math.floor(duration * fps + 1e-6) + 1;
	return Array.from({ length: n }, (_, i) => fixed(i / fps));
}

export function rotate(q, v) {
	const [x, y, z, w] = q;
	const u = [x, y, z];
	const c1 = cross(u, v);
	const c2 = cross(u, c1);
	return add(v, add(scale(c1, 2 * w), scale(c2, 2)));
}

export function rollOf(forward, up) {
	let right = cross(forward, [0, 1, 0]);
	right = length(right) < 1e-6 ? [1, 0, 0] : normalize(right);
	const level = cross(right, forward);
	return deg(Math.atan2(-dot(up, right), dot(up, level)));
}

export function cameraKeys(samples, aspect, makeId) {
	return samples.map(({ t, pos, quat, yfov, aspect: own }) => {
		const forward = normalize(rotate(quat, [0, 0, -1]));
		const up = normalize(rotate(quat, [0, 1, 0]));
		return { id: makeId(), t: fixed(t, 4), pos: round3(pos), target: round3(add(pos, forward)), focal: fixed(fovToFocal(yfov, own > 0 ? own : aspect), 3), roll: fixed(rollOf(forward, up), 3) };
	});
}

function shortSide(resolution) {
	if (SHORT_SIDES[resolution]) return SHORT_SIDES[resolution];
	const match = /^(\d{3,4})p$/i.exec(String(resolution ?? '').trim());
	return match ? Number(match[1]) : 1080;
}

const even = (v) => {
	const whole = Math.round(v);
	return Math.max(2, whole - (whole % 2));
};

export function projectSize(resolution, aspect) {
	const base = shortSide(resolution);
	const ratio = aspect >= 0.25 && aspect <= 4 ? aspect : 16 / 9;
	return ratio >= 1 ? { width: even(base * ratio), height: base } : { width: base, height: even(base / ratio) };
}

export function renderSize(size, maxSide = MAX_REFERENCE_SIDE) {
	const k = Math.min(1, maxSide / Math.max(size.width, size.height));
	const floor32 = (v) => Math.max(32, Math.floor((v * k) / 32 + 1e-6) * 32);
	return { width: floor32(size.width), height: floor32(size.height) };
}

export function frameCount(dur, fps = FPS) {
	return Math.max(2, Math.round(dur * fps));
}

export function renderTimes(dur, fps = FPS) {
	const n = frameCount(dur, fps);
	const span = Math.max(0, dur);
	return Array.from({ length: n }, (_, i) => (i === n - 1 ? span : (i * span) / (n - 1)));
}

export function renderPoses(plan, fps = FPS) {
	return renderTimes(plan.dur, fps).map((time) => cameraAt(plan, time));
}

export function migrateKeyframe(k) {
	if (!k || typeof k !== 'object' || Array.isArray(k.pos)) return k;
	const az = rad(Number(k.az) || 0);
	const el = rad(Number(k.el) || 0);
	const dist = Number(k.dist) || 0;
	const height = Number(k.height) || 0;
	return {
		id: k.id,
		t: Number(k.t) || 0,
		pos: round3([Math.sin(az) * Math.cos(el) * dist, height + Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist]),
		target: [0, height, 0],
		focal: Number(k.focal) || DEFAULT_FOCAL,
		roll: 0
	};
}

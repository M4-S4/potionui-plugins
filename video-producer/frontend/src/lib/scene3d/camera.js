export const SENSOR_HALF_WIDTH = 18;
export const WARN_ANGLE = 15;
export const WARN_SHIFT = 0.25;
export const DEFAULT_FOCAL = 35;
export const FOCAL_RANGE = [12, 135];
export const ROLL_RANGE = [-45, 45];
const MAX_ELEVATION = 85;
const EPS = 1e-9;

const SHORT_SIDES = { '4K': 2160 };

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

export function normalize(a) {
	const l = length(a);
	return l < EPS ? [0, 0, 0] : scale(a, 1 / l);
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

export function reach(cam, source) {
	const { angle, shift } = deviation(cam, source);
	return Math.max(angle / WARN_ANGLE, shift / WARN_SHIFT);
}

const blend = (from, to, k) => ({ ...to, pos: from.pos.map((v, i) => v + (to.pos[i] - v) * k), target: from.target.map((v, i) => v + (to.target[i] - v) * k) });

export function boundCamera(next, prev, source) {
	const ahead = reach(next, source);
	if (ahead <= 1) return next;
	const behind = reach(prev, source);
	if (behind > 1) return ahead < behind ? next : prev;
	let lo = 0;
	let hi = 1;
	for (let i = 0; i < 24; i++) {
		const mid = (lo + hi) / 2;
		if (reach(blend(prev, next, mid), source) <= 1) lo = mid;
		else hi = mid;
	}
	return blend(prev, next, lo);
}

export const lowestFocal = (scene, source) => (holesMatter(scene) && source ? clamp(source.focal, FOCAL_RANGE[0], FOCAL_RANGE[1]) : FOCAL_RANGE[0]);

export function holesMatter(scene) {
	return Boolean(scene?.view);
}

export function sourceView(scene, info) {
	if (scene?.view?.depth > 0 && scene.view.fov > 0) {
		const { fov, aspect, depth } = scene.view;
		return { pos: [0, 0, 0], target: [0, 0, -depth], focal: fixed(fovToFocal(fov, aspect > 0 ? aspect : 1), 3), roll: 0 };
	}
	if (info?.bounds) {
		const { center, radius } = info.bounds;
		const r = radius > EPS ? radius : 1;
		return { pos: add(center, [0, r * 0.25, r * 2.2]), target: [...center], focal: DEFAULT_FOCAL, roll: 0 };
	}
	return { pos: [0, 0, 0], target: [0, 0, -4], focal: DEFAULT_FOCAL, roll: 0 };
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

import { basis } from './camera.js';

export const STREAK_FACTOR = 2.5;
export const STREAK_WARN = 0.03;
export const STREAK_SHOWN = 0.005;
export const LIVE_CELL = 16;
export const CAPTURE_CELL = 8;
export const LIVE_STRIDE = 4;
const OCCLUDER = 0.5;
const ROW = 10;
const LOW_PASS = 0.3;
const MAX_RADIUS = 48;
const NEAR = 1e-4;

function view(pose) {
	const { forward, right, up } = basis(pose);
	return [...pose.pos, ...right, ...up, ...forward];
}

function project(data, row, v, f, out) {
	const dx = data[row] - v[0];
	const dy = data[row + 1] - v[1];
	const dz = data[row + 2] - v[2];
	const z = dx * v[9] + dy * v[10] + dz * v[11];
	if (z <= NEAR) return false;
	const x = dx * v[3] + dy * v[4] + dz * v[5];
	const y = dx * v[6] + dy * v[7] + dz * v[8];
	const k = f / z;
	const t00 = k * (v[3] - (x * v[9]) / z);
	const t01 = k * (v[4] - (x * v[10]) / z);
	const t02 = k * (v[5] - (x * v[11]) / z);
	const t10 = -k * (v[6] - (y * v[9]) / z);
	const t11 = -k * (v[7] - (y * v[10]) / z);
	const t12 = -k * (v[8] - (y * v[11]) / z);
	const s00 = data[row + 3];
	const s01 = data[row + 4];
	const s02 = data[row + 5];
	const s11 = data[row + 6];
	const s12 = data[row + 7];
	const s22 = data[row + 8];
	const m00 = t00 * s00 + t01 * s01 + t02 * s02;
	const m01 = t00 * s01 + t01 * s11 + t02 * s12;
	const m02 = t00 * s02 + t01 * s12 + t02 * s22;
	const m10 = t10 * s00 + t11 * s01 + t12 * s02;
	const m11 = t10 * s01 + t11 * s11 + t12 * s12;
	const m12 = t10 * s02 + t11 * s12 + t12 * s22;
	out[0] = k * x;
	out[1] = -k * y;
	out[2] = z;
	out[3] = m00 * t00 + m01 * t01 + m02 * t02;
	out[4] = m00 * t10 + m01 * t11 + m02 * t12;
	out[5] = m10 * t10 + m11 * t11 + m12 * t12;
	return true;
}

const widest = (a, b, c) => Math.sqrt(Math.max(0, (a + c) / 2 + Math.sqrt(((a - c) / 2) ** 2 + b * b)));

export function streakTable(forEachSplat, source, upsideDown = false) {
	let data = new Float32Array(ROW * 4096);
	let n = 0;
	const v = view(source);
	const p = new Float64Array(6);
	const flip = upsideDown ? -1 : 1;
	forEachSplat((_, center, scales, q, opacity) => {
		if (!(opacity >= OCCLUDER)) return;
		if ((n + 1) * ROW > data.length) {
			const grown = new Float32Array(data.length * 2);
			grown.set(data);
			data = grown;
		}
		const { x, y, z, w } = q;
		const r00 = 1 - 2 * (y * y + z * z), r01 = 2 * (x * y - w * z), r02 = 2 * (x * z + w * y);
		const r10 = 2 * (x * y + w * z), r11 = 1 - 2 * (x * x + z * z), r12 = 2 * (y * z - w * x);
		const r20 = 2 * (x * z - w * y), r21 = 2 * (y * z + w * x), r22 = 1 - 2 * (x * x + y * y);
		const d0 = scales.x * scales.x, d1 = scales.y * scales.y, d2 = scales.z * scales.z;
		const row = n * ROW;
		data[row] = center.x;
		data[row + 1] = flip * center.y;
		data[row + 2] = flip * center.z;
		data[row + 3] = r00 * r00 * d0 + r01 * r01 * d1 + r02 * r02 * d2;
		data[row + 4] = flip * (r00 * r10 * d0 + r01 * r11 * d1 + r02 * r12 * d2);
		data[row + 5] = flip * (r00 * r20 * d0 + r01 * r21 * d1 + r02 * r22 * d2);
		data[row + 6] = r10 * r10 * d0 + r11 * r11 * d1 + r12 * r12 * d2;
		data[row + 7] = r10 * r20 * d0 + r11 * r21 * d1 + r12 * r22 * d2;
		data[row + 8] = r20 * r20 * d0 + r21 * r21 * d1 + r22 * r22 * d2;
		data[row + 9] = project(data, row, v, 1, p) ? widest(p[3], p[4], p[5]) * p[2] : Infinity;
		n += 1;
	});
	return { data: data.subarray(0, n * ROW), count: n };
}

export function streakShare(table, pose, width, height, cell = CAPTURE_CELL, stride = 1) {
	const f = height / 2 / Math.tan(((pose.fov ?? 50) * Math.PI) / 360);
	const v = view(pose);
	const gw = Math.ceil(width / cell);
	const gh = Math.ceil(height / cell);
	const depth = new Float32Array(gw * gh).fill(Infinity);
	const streak = new Uint8Array(gw * gh);
	const p = new Float64Array(6);
	const { data, count } = table;
	const mark = (k, z, stretched) => {
		if (z < depth[k]) {
			depth[k] = z;
			streak[k] = stretched;
		}
	};
	for (let i = 0; i < count; i += stride) {
		const row = i * ROW;
		if (!project(data, row, v, f, p)) continue;
		const [u, w, z, a0, b, c0] = p;
		const stretched = (widest(a0, b, c0) * z) / f > STREAK_FACTOR * data[row + 9] ? 1 : 0;
		const a = a0 + LOW_PASS;
		const c = c0 + LOW_PASS;
		const cx = (u + width / 2) / cell;
		const cy = (w + height / 2) / cell;
		const reach = Math.min(MAX_RADIUS, widest(a, b, c) / cell);
		if (reach < 0.5) {
			const gx = Math.floor(cx);
			const gy = Math.floor(cy);
			if (gx >= 0 && gy >= 0 && gx < gw && gy < gh) mark(gy * gw + gx, z, stretched);
			continue;
		}
		const det = a * c - b * b;
		if (!(det > 0)) continue;
		const i0 = c / det;
		const i1 = -b / det;
		const i2 = a / det;
		const x0 = Math.max(0, Math.floor(cx - reach));
		const x1 = Math.min(gw - 1, Math.floor(cx + reach));
		const y0 = Math.max(0, Math.floor(cy - reach));
		const y1 = Math.min(gh - 1, Math.floor(cy + reach));
		for (let gy = y0; gy <= y1; gy++) {
			const dy = (gy + 0.5 - cy) * cell;
			for (let gx = x0; gx <= x1; gx++) {
				const dx = (gx + 0.5 - cx) * cell;
				if (i0 * dx * dx + 2 * i1 * dx * dy + i2 * dy * dy <= 1) mark(gy * gw + gx, z, stretched);
			}
		}
	}
	let total = 0;
	for (let k = 0; k < streak.length; k++) total += streak[k];
	return total / streak.length;
}

export const streakLevel = (share) => (share != null && share > STREAK_WARN ? 'streaks' : 'ok');

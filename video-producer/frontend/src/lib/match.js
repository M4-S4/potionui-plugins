export const LUT_SIZE = 33;
export const MAX_SCALE = 1.5;
export const DEFAULT_STRENGTH = 80;
export const STATS = 6;
export const ANCHORS = ['keyframe', 'reference', 'previous'];

const MIN_SPREAD = 1e-3;
const IDENTITY = 1e-4;
const WHITE = [0.95047, 1, 1.08883];
const TO_XYZ = [0.4124564, 0.3575761, 0.1804375, 0.2126729, 0.7151522, 0.072175, 0.0193339, 0.119192, 0.9503041];
const TO_RGB = [3.2404542, -1.5371385, -0.4985314, -0.969266, 1.8760108, 0.041556, 0.0556434, -0.2040259, 1.0572252];
const EDGE = 6 / 29;

const linear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const encoded = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const f = (t) => (t > EDGE ** 3 ? Math.cbrt(t) : t / (3 * EDGE ** 2) + 4 / 29);
const fInverse = (t) => (t > EDGE ? t ** 3 : 3 * EDGE ** 2 * (t - 4 / 29));
const unit = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
const BYTE_LINEAR = Float64Array.from({ length: 256 }, (_, i) => linear(i / 255));

function labOfLinear(r, g, b) {
	const fx = f((TO_XYZ[0] * r + TO_XYZ[1] * g + TO_XYZ[2] * b) / WHITE[0]);
	const fy = f((TO_XYZ[3] * r + TO_XYZ[4] * g + TO_XYZ[5] * b) / WHITE[1]);
	const fz = f((TO_XYZ[6] * r + TO_XYZ[7] * g + TO_XYZ[8] * b) / WHITE[2]);
	return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

export function toLab([r, g, b]) {
	return labOfLinear(linear(r), linear(g), linear(b));
}

export function fromLab([l, a, b]) {
	const fy = (l + 16) / 116;
	const x = WHITE[0] * fInverse(fy + a / 500);
	const y = WHITE[1] * fInverse(fy);
	const z = WHITE[2] * fInverse(fy - b / 200);
	return [0, 3, 6].map((k) => unit(encoded(Math.max(TO_RGB[k] * x + TO_RGB[k + 1] * y + TO_RGB[k + 2] * z, 0))));
}

export function labStats(images) {
	const sum = [0, 0, 0];
	const square = [0, 0, 0];
	let count = 0;
	for (const data of images) {
		for (let i = 0; i < data.length; i += 4) {
			if (data[i + 3] === 0) continue;
			const lab = labOfLinear(BYTE_LINEAR[data[i]], BYTE_LINEAR[data[i + 1]], BYTE_LINEAR[data[i + 2]]);
			for (let k = 0; k < 3; k++) {
				sum[k] += lab[k];
				square[k] += lab[k] * lab[k];
			}
			count++;
		}
	}
	if (!count) return null;
	const means = sum.map((s) => s / count);
	const spreads = square.map((s, k) => Math.sqrt(Math.max(s / count - means[k] ** 2, 0)));
	return [...means, ...spreads].map((v) => +v.toFixed(4) || 0);
}

const statsOf = (value) => (Array.isArray(value) && value.length === STATS && value.every((v) => typeof v === 'number' && Number.isFinite(v)) ? value : null);

export function transferOf(match) {
	const source = statsOf(match?.source);
	const target = statsOf(match?.target);
	if (!source || !target || typeof match.strength !== 'number' || !Number.isFinite(match.strength)) return null;
	const amount = unit(match.strength / 100);
	const gains = [];
	const offsets = [];
	for (let k = 0; k < 3; k++) {
		const spreadSource = source[k + 3];
		const spreadTarget = target[k + 3];
		let scale = spreadSource > MIN_SPREAD && spreadTarget > MIN_SPREAD ? spreadTarget / spreadSource : 1;
		scale = Math.min(Math.max(scale, 1 / MAX_SCALE), MAX_SCALE);
		gains.push(1 + amount * (scale - 1));
		offsets.push(amount * (target[k] - scale * source[k]));
	}
	return { gains, offsets };
}

export const isIdentity = (moves) => moves.gains.every((g) => Math.abs(g - 1) < IDENTITY) && moves.offsets.every((o) => Math.abs(o) < IDENTITY * 100);

export function matchStale(clip) {
	return Boolean(clip?.match) && (clip.assetId == null || clip.match.assetId !== clip.assetId);
}

export function activeTransfer(clip) {
	if (!clip?.match || matchStale(clip)) return null;
	const moves = transferOf(clip.match);
	return moves && !isIdentity(moves) ? moves : null;
}

export function applyTransfer(moves, rgb) {
	const lab = toLab(rgb);
	return fromLab(lab.map((v, k) => v * moves.gains[k] + moves.offsets[k]));
}

export function bakeLut(moves, size = LUT_SIZE) {
	const levels = Array.from({ length: size }, (_, i) => linear(i / (size - 1)));
	const table = new Float32Array(size * size * size * 3);
	let n = 0;
	for (const b of levels) {
		for (const g of levels) {
			for (const r of levels) {
				const lab = labOfLinear(r, g, b);
				const out = fromLab([lab[0] * moves.gains[0] + moves.offsets[0], lab[1] * moves.gains[1] + moves.offsets[1], lab[2] * moves.gains[2] + moves.offsets[2]]);
				table[n++] = out[0];
				table[n++] = out[1];
				table[n++] = out[2];
			}
		}
	}
	return { size, table };
}

export function applyLut(data, lut) {
	const { size, table } = lut;
	const top = size - 1;
	const plane = size * size;
	const scale = top / 255;
	for (let i = 0; i < data.length; i += 4) {
		const x = data[i] * scale;
		const y = data[i + 1] * scale;
		const z = data[i + 2] * scale;
		const r0 = Math.min(Math.floor(x), top - 1);
		const g0 = Math.min(Math.floor(y), top - 1);
		const b0 = Math.min(Math.floor(z), top - 1);
		const fr = x - r0;
		const fg = y - g0;
		const fb = z - b0;
		const base = (b0 * plane + g0 * size + r0) * 3;
		for (let k = 0; k < 3; k++) {
			const at = (offset) => table[base + offset * 3 + k];
			const c00 = at(0) + (at(1) - at(0)) * fr;
			const c10 = at(size) + (at(size + 1) - at(size)) * fr;
			const c01 = at(plane) + (at(plane + 1) - at(plane)) * fr;
			const c11 = at(plane + size) + (at(plane + size + 1) - at(plane + size)) * fr;
			const c0 = c00 + (c10 - c00) * fg;
			const c1 = c01 + (c11 - c01) * fg;
			data[i + k] = Math.round(unit(c0 + (c1 - c0) * fb) * 255);
		}
	}
	return data;
}

export function lutBytes(lut) {
	const bytes = new Uint8Array((lut.table.length / 3) * 4);
	for (let i = 0, j = 0; i < lut.table.length; i += 3, j += 4) {
		bytes[j] = Math.round(lut.table[i] * 255);
		bytes[j + 1] = Math.round(lut.table[i + 1] * 255);
		bytes[j + 2] = Math.round(lut.table[i + 2] * 255);
		bytes[j + 3] = 255;
	}
	return bytes;
}

export function gapOf(source, target) {
	if (!statsOf(source) || !statsOf(target)) return null;
	const dl = target[0] - source[0];
	const da = target[1] - source[1];
	const db = target[2] - source[2];
	return { delta: Math.hypot(dl, da, db), light: -dl, warm: -db, tint: -da };
}

export function movedStats(stats, moves) {
	if (!statsOf(stats) || !moves) return stats;
	return [0, 1, 2].map((k) => stats[k] * moves.gains[k] + moves.offsets[k]).concat([0, 1, 2].map((k) => stats[k + 3] * Math.abs(moves.gains[k])));
}

const lutCache = new Map();

export function lutOf(clip) {
	const moves = activeTransfer(clip);
	if (!moves) return null;
	const key = [...moves.gains, ...moves.offsets].map((v) => v.toFixed(6)).join(',');
	let lut = lutCache.get(key);
	if (!lut) {
		lut = { ...bakeLut(moves), key };
		lutCache.set(key, lut);
		if (lutCache.size > 24) lutCache.delete(lutCache.keys().next().value);
	}
	return lut;
}

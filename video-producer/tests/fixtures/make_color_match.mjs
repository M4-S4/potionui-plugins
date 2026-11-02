import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { LUT_SIZE, MAX_SCALE, applyLut, bakeLut, transferOf } from '../../frontend/src/lib/match.js';

const here = dirname(fileURLToPath(import.meta.url));

function random(seed) {
	let state = seed >>> 0;
	return () => {
		state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
		return state / 2 ** 32;
	};
}

const LEVELS = [0, 36, 73, 109, 146, 182, 219, 255];
const RANDOM_COLORS = 64;
const LUT_STEP = 97;

export const CASES = [
	{ name: 'warm_dark_take', match: { anchor: 'keyframe', anchorId: 'f1', assetId: 'a1', strength: 80, source: [45, 4, 18, 20, 7, 10], target: [52, 1, 6, 23, 8, 11] } },
	{ name: 'cool_flat_take', match: { anchor: 'reference', anchorId: 'r1', assetId: 'a1', strength: 100, source: [58, -3, -14, 14, 5, 8], target: [55, 2, 4, 21, 9, 12] } }
];

export function colors() {
	const next = random(20261024);
	const grid = LEVELS.flatMap((b) => LEVELS.flatMap((g) => LEVELS.map((r) => [r, g, b])));
	const loose = Array.from({ length: RANDOM_COLORS }, () => [0, 1, 2].map(() => Math.floor(next() * 256)));
	return [...grid, ...loose];
}

export function preview(match, list) {
	const lut = bakeLut(transferOf(match));
	const data = new Uint8ClampedArray(list.flatMap(([r, g, b]) => [r, g, b, 255]));
	applyLut(data, lut);
	return list.map((_, i) => [data[i * 4], data[i * 4 + 1], data[i * 4 + 2]]);
}

export function fixture() {
	const list = colors();
	return {
		lutSize: LUT_SIZE,
		maxScale: MAX_SCALE,
		colors: list,
		cases: CASES.map(({ name, match }) => {
			const { table } = bakeLut(transferOf(match));
			const samples = [];
			for (let i = 0; i < table.length / 3; i += LUT_STEP) samples.push([i, ...[0, 1, 2].map((k) => +table[i * 3 + k].toFixed(6))]);
			return { name, match, preview: preview(match, list), lut: samples };
		})
	};
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
	const out = fixture();
	writeFileSync(join(here, 'color_match.json'), JSON.stringify(out) + '\n');
	console.log(`${out.colors.length} colors, ${out.cases.length} cases`);
}

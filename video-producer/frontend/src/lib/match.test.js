import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { drawGraded, gradePixels } from './grade.js';
import {
	LUT_SIZE,
	MAX_SCALE,
	activeTransfer,
	applyLut,
	applyTransfer,
	bakeLut,
	fromLab,
	gapOf,
	isIdentity,
	labStats,
	lutBytes,
	lutOf,
	matchStale,
	movedStats,
	toLab,
	transferOf
} from './match.js';

const fixture = JSON.parse(readFileSync(new URL('../../../tests/fixtures/color_match.json', import.meta.url), 'utf8'));
const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const close = (actual, expected, tolerance) => actual.every((v, i) => Math.abs(v - expected[i]) <= tolerance);
const match = (fields = {}) => ({ anchor: 'keyframe', anchorId: 'f1', assetId: 'a1', strength: 100, source: [50, 0, 0, 20, 8, 8], target: [50, 0, 0, 20, 8, 8], ...fields });
const image = (colors) => new Uint8ClampedArray(colors.flatMap(([r, g, b, a = 255]) => [r, g, b, a]));

test('toLab and fromLab: CIELAB D65 of sRGB, white at L 100, red at its textbook value, and back to the same color', () => {
	assert.ok(close(toLab([1, 1, 1]), [100, 0, 0], 0.01));
	assert.ok(close(toLab([1, 0, 0]), [53.24, 80.09, 67.2], 0.02));
	assert.ok(close(toLab([0, 0, 0]), [0, 0, 0], 1e-9));
	for (const rgb of [[0.2, 0.5, 0.8], [1, 0.4, 0], [0.01, 0.02, 0.03], [0.5, 0.5, 0.5]]) assert.ok(close(fromLab(toLab(rgb)), rgb, 1e-6));
	assert.deepEqual(fromLab([120, 300, -300]).map((v) => v >= 0 && v <= 1), [true, true, true]);
});

test('labStats: the means and spreads of L, a and b over every opaque pixel of every image, null when nothing is opaque', () => {
	assert.deepEqual(labStats([image([[255, 255, 255], [255, 255, 255]])]), [100, 0, 0, 0, 0, 0]);
	const [l, , , spread] = labStats([image([[0, 0, 0]]), image([[255, 255, 255], [9, 9, 9, 0]])]);
	assert.equal(l, 50);
	assert.equal(spread, 50);
	assert.equal(labStats([image([[1, 2, 3, 0]])]), null);
	assert.equal(labStats([]), null);
});

test('transferOf: the Reinhard move of means and spreads scaled by the strength, the spread ratio held between 2/3 and 3/2', () => {
	assert.ok(isIdentity(transferOf(match())));
	assert.ok(isIdentity(transferOf(match({ strength: 0, target: [70, 10, 10, 30, 12, 12] }))));
	const full = transferOf(match({ target: [60, 4, -6, 25, 4, 16] }));
	assert.ok(close(full.gains, [1.25, 2 / 3, 1.5], 1e-12));
	assert.ok(close(full.offsets, [60 - 1.25 * 50, 4, -6], 1e-12));
	const half = transferOf(match({ strength: 50, target: [60, 4, -6, 25, 4, 16] }));
	assert.ok(close(half.gains, [1.125, 5 / 6, 1.25], 1e-12));
	assert.ok(close(half.offsets, [0.5 * (60 - 1.25 * 50), 2, -3], 1e-12));
	assert.equal(MAX_SCALE, 1.5);
	assert.ok(close(transferOf(match({ source: [50, 0, 0, 0, 8, 8], target: [55, 0, 0, 20, 8, 8] })).gains, [1, 1, 1], 0));
	assert.equal(transferOf(match({ source: [1, 2, 3] })), null);
	assert.equal(transferOf(match({ strength: '80' })), null);
	assert.equal(transferOf(match({ target: [1, 2, 3, 4, 5, NaN] })), null);
	assert.equal(transferOf(null), null);
});

test('activeTransfer: only a match measured on the asset the shot shows now and that moves colors applies', () => {
	const moving = match({ target: [60, 2, 2, 20, 8, 8] });
	assert.ok(activeTransfer({ assetId: 'a1', match: moving }));
	assert.equal(activeTransfer({ assetId: 'a2', match: moving }), null);
	assert.equal(activeTransfer({ assetId: null, match: moving }), null);
	assert.equal(activeTransfer({ assetId: 'a1', match: match() }), null);
	assert.equal(activeTransfer({ assetId: 'a1' }), null);
	assert.equal(matchStale({ assetId: 'a2', match: moving }), true);
	assert.equal(matchStale({ assetId: 'a1', match: moving }), false);
	assert.equal(matchStale({ assetId: 'a2' }), false);
	assert.equal(lutOf({ assetId: 'a2', match: moving }), null);
	assert.equal(lutOf({ assetId: 'a1', match: moving }), lutOf({ assetId: 'a1', match: { ...moving } }));
});

test('bakeLut: a size³ table, red fastest, whose trilinear reading stays within a level of the exact transfer on most colors', () => {
	const moves = transferOf(match({ strength: 80, source: [45, 4, 18, 20, 7, 10], target: [52, 1, 6, 23, 8, 11] }));
	const lut = bakeLut(moves);
	assert.equal(lut.size, LUT_SIZE);
	assert.equal(lut.table.length, LUT_SIZE ** 3 * 3);
	const red = applyTransfer(moves, [1, 0, 0]);
	assert.ok(close([...lut.table.slice((LUT_SIZE - 1) * 3, LUT_SIZE * 3)], red, 1e-6));
	const errors = fixture.colors.map((rgb) => {
		const [out] = [applyLut(image([rgb]), lut)];
		const exact = applyTransfer(moves, rgb.map((c) => c / 255)).map((c) => c * 255);
		return Math.max(...[0, 1, 2].map((k) => Math.abs(out[k] - exact[k])));
	});
	const mean = errors.reduce((a, b) => a + b, 0) / errors.length;
	assert.ok(mean < 0.75, `mean ${mean}`);
	assert.ok(errors.filter((e) => e > 1).length / errors.length < 0.1);
});

test('applyLut: an identity table keeps every pixel and the alpha', () => {
	const lut = bakeLut({ gains: [1, 1, 1], offsets: [0, 0, 0] });
	const data = image(fixture.colors.slice(0, 200));
	const before = [...data];
	applyLut(data, lut);
	assert.ok(close([...data], before, 1));
	assert.deepEqual([...applyLut(image([[10, 20, 30, 7]]), lut)].slice(3), [7]);
});

test('the fixture the export tests read is the preview of this code: same colors, same LUT samples, same pixels', () => {
	assert.equal(fixture.lutSize, LUT_SIZE);
	assert.equal(fixture.maxScale, MAX_SCALE);
	for (const item of fixture.cases) {
		const lut = bakeLut(transferOf(item.match));
		for (const [index, r, g, b] of item.lut) assert.ok(close([...lut.table.slice(index * 3, index * 3 + 3)], [r, g, b], 1e-6), `${item.name} ${index}`);
		const data = gradePixels(image(fixture.colors), [], lut);
		assert.deepEqual(
			fixture.colors.map((_, i) => [data[i * 4], data[i * 4 + 1], data[i * 4 + 2]]),
			item.preview,
			`${item.name}: regenerate tests/fixtures/color_match.json with make_color_match.mjs`
		);
	}
});

test('a take with a warm cast matched at full strength to a neutral anchor comes out neutral', () => {
	const take = image(Array.from({ length: 64 }, (_, i) => [90 + i * 2, 70 + i * 2, 40 + i]));
	const anchor = image(Array.from({ length: 64 }, (_, i) => [70 + i * 2, 72 + i * 2, 74 + i * 2]));
	const stats = { source: labStats([take]), target: labStats([anchor]) };
	const before = gapOf(stats.source, stats.target);
	const after = labStats([applyLut(take, bakeLut(transferOf(match({ ...stats }))))]);
	assert.ok(before.delta > 15 && before.warm > 10);
	assert.ok(gapOf(after, stats.target).delta < before.delta * 0.2);
});

test('gapOf and movedStats: the ΔE of the means with the take lighter, warmer or more magenta than its anchor, and the stats a transfer leads to', () => {
	const gap = gapOf([60, 5, 20, 1, 1, 1], [50, 2, 8, 1, 1, 1]);
	assert.ok(Math.abs(gap.delta - Math.hypot(10, 3, 12)) < 1e-12);
	assert.deepEqual([gap.light, gap.tint, gap.warm], [10, 3, 12]);
	assert.equal(gapOf([1, 2], [1, 2]), null);
	const moves = transferOf(match({ source: [60, 5, 20, 20, 8, 8], target: [50, 2, 8, 20, 8, 8] }));
	assert.ok(close(movedStats([60, 5, 20, 20, 8, 8], moves), [50, 2, 8, 20, 8, 8], 1e-9));
});

test('lutBytes: four bytes a point for the 3D texture, alpha opaque', () => {
	const bytes = lutBytes(bakeLut({ gains: [1, 1, 1], offsets: [0, 0, 0] }, 2));
	assert.deepEqual([...bytes], [0, 0, 0, 255, 255, 0, 0, 255, 0, 255, 0, 255, 255, 255, 0, 255, 0, 0, 255, 255, 255, 0, 255, 255, 0, 255, 255, 255, 255, 255, 255, 255]);
});

test('drawGraded with a LUT: drawn without the canvas filter, the LUT first and the look after, on the pixels', () => {
	const calls = [];
	const context = {
		drawImage: () => calls.push('draw'),
		getImageData: () => ({ data: image([[100, 100, 100]]) })
	};
	Object.defineProperty(context, 'filter', { set: (value) => calls.push(['filter', value]), get: () => 'none' });
	const lut = bakeLut({ gains: [1, 1, 1], offsets: [20, 0, 0] });
	const graded = drawGraded(context, {}, 1, 1, [['brightness', 2]], lut);
	assert.deepEqual(calls, [['filter', 'none'], 'draw']);
	const lifted = applyLut(image([[100, 100, 100]]), lut);
	assert.deepEqual([...graded].slice(0, 3), [...lifted].slice(0, 3).map((v) => Math.min(255, v * 2)));
});

test('the viewer and the inspector preview a matched shot through its LUT, never through a CSS filter alone', () => {
	const viewer = source('../components/viewer/Viewer.svelte');
	assert.match(viewer, /const lut = \$derived\(mode === 'sequence' && clip \? lutOf\(clip\) : null\);/);
	assert.match(viewer, /<MatchCanvas source=\{video\} \{lut\}/);
	assert.match(viewer, /<MatchCanvas source=\{picture\} \{lut\}/);
	assert.match(source('../components/viewer/MatchCanvas.svelte'), /renderer\.draw\(source, lut\)/);
	assert.match(source('../components/inspector/MatchSection.svelte'), /drawGraded\(g, img, canvas\.width, canvas\.height, \[\], current\)/);
	assert.match(source('./lutgl.js'), /texImage3D\(gl\.TEXTURE_3D, 0, gl\.RGBA8, lut\.size, lut\.size, lut\.size/);
});

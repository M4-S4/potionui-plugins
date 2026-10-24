import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { drawGraded, filterOf, gradePixels, lookSteps, lumaHistogram } from './grade.js';

const pixel = (r, g, b) => new Uint8ClampedArray([r, g, b, 255]);

test('lookSteps and filterOf: the CSS filter of a clip, none when the look is neutral', () => {
	assert.equal(filterOf(lookSteps({ exposure: 0, contrast: 100, saturation: 100, temperature: 0 })), 'none');
	assert.equal(filterOf(lookSteps(null)), 'none');
	assert.equal(
		filterOf(lookSteps({ exposure: 0.2, contrast: 105, saturation: 112, temperature: 35 })),
		'brightness(1.05) contrast(1.05) saturate(1.12) sepia(0.14)'
	);
	assert.equal(filterOf(lookSteps({ exposure: 0, contrast: 100, saturation: 100, temperature: -40 })), 'hue-rotate(-8deg) saturate(0.9)');
});

test('gradePixels: brightness and contrast are the linear transfers of the CSS filters, clamped', () => {
	assert.deepEqual([...gradePixels(pixel(100, 200, 250), [['brightness', 1.25]])], [125, 250, 255, 255]);
	assert.deepEqual([...gradePixels(pixel(0, 128, 255), [['contrast', 2]])], [0, 129, 255, 255]);
	assert.deepEqual([...gradePixels(pixel(64, 128, 192), [['contrast', 0.5]])], [96, 128, 160, 255]);
});

test('gradePixels: saturate 0 gives the grey of the luma weights, sepia 0 and hue-rotate 0 change nothing', () => {
	const [r, g, b] = gradePixels(pixel(255, 0, 0), [['saturate', 0]]);
	assert.deepEqual([r, g, b], [54, 54, 54]);
	assert.deepEqual([...gradePixels(pixel(10, 120, 230), [['sepia', 0]])], [10, 120, 230, 255]);
	assert.deepEqual([...gradePixels(pixel(10, 120, 230), [['hue-rotate', 0]])], [10, 120, 230, 255]);
});

test('gradePixels: full sepia of white is the sepia tone, hue-rotate 180 turns red towards cyan', () => {
	assert.deepEqual([...gradePixels(pixel(255, 255, 255), [['sepia', 1]])], [255, 255, 239, 255]);
	const [r, g, b] = gradePixels(pixel(255, 0, 0), [['hue-rotate', 180]]);
	assert.ok(r === 0 && g > 100 && b > 100);
});

test('gradePixels: steps apply in order, alpha untouched, an invalid value leaves the pixels as the browser would', () => {
	const data = new Uint8ClampedArray([200, 100, 50, 7]);
	gradePixels(data, [['brightness', 0.5], ['contrast', 2]]);
	assert.deepEqual([...data], [73, 0, 0, 7]);
	assert.deepEqual([...gradePixels(pixel(1, 2, 3), [['contrast', NaN]])], [1, 2, 3, 255]);
});

function fakeContext(native) {
	const calls = [];
	const context = {
		drawImage: (...args) => calls.push(['drawImage', ...args.slice(1)]),
		getImageData: () => ({ data: pixel(100, 100, 100) })
	};
	if (native) {
		Object.defineProperty(context, 'filter', { set: (value) => calls.push(['filter', value]), get: () => 'none', enumerable: true });
	}
	return { context, calls };
}

test('drawGraded: the canvas filter when the browser has it, else the same grade on the pixels', () => {
	const steps = [['brightness', 1.5]];
	const native = fakeContext(true);
	assert.deepEqual([...drawGraded(native.context, {}, 48, 27, steps)], [100, 100, 100, 255]);
	assert.deepEqual(native.calls, [['filter', 'brightness(1.5)'], ['drawImage', 0, 0, 48, 27]]);
	const older = fakeContext(false);
	assert.deepEqual([...drawGraded(older.context, {}, 48, 27, steps)], [150, 150, 150, 255]);
	assert.deepEqual(older.calls, [['drawImage', 0, 0, 48, 27]]);
});

test('lumaHistogram: 64 bins of the Rec. 709 luma, scaled to the fullest bin', () => {
	const data = new Uint8ClampedArray([0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255, 255, 255, 0, 0, 255]);
	const bins = lumaHistogram(data);
	assert.equal(bins.length, 64);
	assert.equal(bins[0], 1);
	assert.equal(bins[63], 0.5);
	assert.equal(bins[13], 0.5);
	assert.equal(bins.reduce((sum, v) => sum + v, 0), 2);
	assert.deepEqual(lumaHistogram(new Uint8ClampedArray(0)), new Array(64).fill(0));
});

test('color preview: presets and histogram take a picture of the shot, its frame at the in point first, never the video file', () => {
	const section = readFileSync(new URL('../components/inspector/ColorSection.svelte', import.meta.url), 'utf8');
	const media = readFileSync(new URL('./media.js', import.meta.url), 'utf8');
	assert.match(section, /const picture = \$derived\(shotFrame\(clip\)\);/);
	assert.match(section, /img\.src = picture;/);
	assert.match(section, /<img src=\{picture\}/);
	assert.doesNotMatch(section, /src=\{a\.src\}|img\.src = a\.src/);
	assert.match(section, /bins = lumaHistogram\(drawGraded\(g, img, 160, 90, steps, lut\)\);/);
	assert.match(media, /return videoFrame\(a, c\.srcIn \?\? 0\) \?\? assetThumb\(a\);/);
});

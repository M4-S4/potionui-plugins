import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { renderComponent } from './svelte-harness.js';
import { drawGraded, filterOf, gradePixels, lookSteps, lumaHistogram } from './grade.js';

const pixel = (r, g, b) => new Uint8ClampedArray([r, g, b, 255]);

const { doc, dispose } = await import('./state.svelte.js');
const { shotFrame } = await import('./media.js');
const { colorPresets } = await import('./look.js');
const CONTROLS = new URL('../components/inspector/ColorControls.svelte', import.meta.url).href;

after(() => dispose());

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

test('color preview: presets and histogram take a picture of the shot, its frame at the in point first, never the video file', async () => {
	const look = { exposure: 0, contrast: 100, saturation: 100, temperature: 0, preset: 'Original' };
	doc.assets = [{ id: 'v', kind: 'video', name: 'Clip', src: '/m/v.mp4', srcDur: 5 }, { id: 'p', kind: 'image', name: 'Still', src: '/m/still.png' }, { id: 's', kind: 'audio', name: 'Voice', src: '/m/voice.mp3' }];
	doc.clips = [{ id: 's1', start: 0, dur: 4, srcIn: 1.2, assetId: 'v', label: 'One', stage: 'draft', ...look }, { id: 's2', start: 4, dur: 4, srcIn: 0, assetId: 'p', label: 'Two', stage: 'draft', ...look }, { id: 's3', start: 8, dur: 4, srcIn: 0, assetId: 's', label: 'Three', stage: 'draft', ...look }];
	assert.equal(shotFrame(doc.clips[0]), null);
	assert.equal(shotFrame(doc.clips[1]), '/m/still.png');
	assert.equal(shotFrame(doc.clips[2]), null);
	assert.equal(shotFrame({ assetId: 'gone' }), null);
	const presets = Object.keys(colorPresets).length;
	const video = await renderComponent(CONTROLS, { clip: doc.clips[0] });
	assert.doesNotMatch(video, /src="\/m\/v\.mp4"/);
	assert.equal((video.match(/<span class="block aspect-video w-full bg-surface-3">/g) ?? []).length, presets);
	const still = await renderComponent(CONTROLS, { clip: doc.clips[1] });
	assert.equal((still.match(/<img src="\/m\/still\.png"/g) ?? []).length, presets);
});

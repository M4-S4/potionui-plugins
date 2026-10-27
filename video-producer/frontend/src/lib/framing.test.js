import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { changedRatio, costOf, customFormat, customSize, engineSize, exportFrame, fitClass, formatChange, formatSections, framed, glyph, largestTake, measuredFor, percent, sameSizes, sizeOf, sizeSections, tierOf, upscaled } from './framing.js';

const WAN = '01KX47WANVIDEO0000000000TV';
const LTX = '01KX47LTXVIDEO0000000000TV';
const H3 = '01KX47H3MINIMAX000000000VA';
const options = (values) => values.map((value) => ({ value, label: value }));
const wan = { id: WAN, resolutions: options(['1280x720', '720x1280', '832x480', '480x832', '1024x1024', '720x720']) };
const ltx = { id: LTX, resolutions: options(['1280x720', '832x480', '960x544']) };
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-3, `${actual} != ${expected}`);
const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');

test('framing: a take is cropped like the export up to 30 % of loss, then put between bars, as the project says', () => {
	assert.deepEqual(sizeOf({ width: 1280, height: 720 }), [1280, 720]);
	assert.deepEqual(sizeOf({ resolution: '832x480' }), [832, 480]);
	assert.equal(sizeOf({}), null);
	const scope = framed([1280, 720], { aspect: '2.39:1' });
	assert.equal(scope.mode, 'crop');
	close(scope.loss, 1 - 16 / 9 / 2.39);
	assert.equal(percent(scope.loss), 26);
	assert.equal(framed([832, 480], { aspect: '16:9' }).mode, 'exact');
	assert.equal(framed([1280, 720], { aspect: '1:1' }).mode, 'bars');
	assert.equal(framed([1280, 720], { aspect: '1:1', framing: 'crop' }).mode, 'crop');
	assert.equal(framed([1280, 720], { aspect: '2.39:1', framing: 'bars' }).mode, 'bars');
	assert.equal(framed(null, { aspect: '16:9' }), null);
	assert.equal(fitClass('bars'), 'object-contain');
	assert.equal(fitClass('crop'), 'object-cover');
	assert.equal(fitClass('exact'), 'object-cover');
});

test('framing: the glyph of a ratio fills the long side of its box', () => {
	assert.deepEqual(glyph(16 / 9), { x: 5, y: 8.0625, width: 14, height: 7.875 });
	assert.deepEqual(glyph(0.5), { x: 8.5, y: 5, width: 7, height: 14 });
});

test('framing: the formats come grouped as cinema, screen and social with their delivery frame, and a custom format of the project gets its own group', () => {
	const sections = formatSections({ aspect: '16:9', resolution: '1080p' });
	assert.deepEqual(sections.map((s) => s.id), ['cinema', 'screen', 'social']);
	assert.deepEqual(sections.map((s) => s.rows.map((r) => r.value)), [['2.39:1', '2:1', '1.85:1'], ['16:9', '4:3'], ['1:1', '4:5', '9:16']]);
	const frames = Object.fromEntries(sections.flatMap((s) => s.rows).map((r) => [r.value, r.size.join('x')]));
	assert.deepEqual(frames, { '2.39:1': '1920x804', '2:1': '1920x960', '1.85:1': '1920x1038', '16:9': '1920x1080', '4:3': '1440x1080', '1:1': '1080x1080', '4:5': '1080x1350', '9:16': '1080x1920' });
	const custom = formatSections({ aspect: '21:9', resolution: '1080p' });
	assert.deepEqual(custom.at(-1), { id: 'custom', rows: [{ value: '21:9', ratio: 21 / 9, size: [1920, 822] }] });
	assert.deepEqual(formatSections({ aspect: '2.39:1', resolution: '1440p' })[0].rows[0].size, [2560, 1072]);
});

test('framing: a custom format takes two numbers with two decimals at most, from 1:4 to 4:1', () => {
	assert.deepEqual(customFormat('21', '9'), { ok: true, value: '21:9' });
	assert.deepEqual(customFormat(' 2.40 ', '1'), { ok: true, value: '2.40:1' });
	assert.deepEqual(customFormat('5', '1'), { ok: false, error: 'range' });
	assert.deepEqual(customFormat('1', '4.5'), { ok: false, error: 'range' });
	assert.deepEqual(customFormat('x', '1'), { ok: false, error: 'invalid' });
	assert.deepEqual(customFormat('2.555', '1'), { ok: false, error: 'invalid' });
	assert.deepEqual(customFormat('0', '1'), { ok: false, error: 'invalid' });
});

test('framing: sizes fall in tiers by area, and cost the time of 832x480 raised to the measured exponent', () => {
	assert.equal(tierOf([1280, 720]), 'high');
	assert.equal(tierOf([1040, 832]), 'high');
	assert.equal(tierOf([960, 544]), 'mid');
	assert.equal(tierOf([832, 480]), 'low');
	assert.equal(tierOf([640, 480]), 'low');
	assert.equal(tierOf([640, 352]), 'small');
	close(costOf([832, 480]), 1);
	close(costOf([1280, 720]), (921600 / 399360) ** 1.2);
});

test('framing: the size picker lists the working family of the engine for the format, with Auto, the measures of the backend and the framing of each size', () => {
	const measured = measuredFor({ measured: { [WAN]: { gpu: ['832x480'] } } }, WAN, 'gpu');
	assert.deepEqual(measured, ['832x480']);
	assert.deepEqual(measuredFor({}, WAN, 'gpu'), []);
	const draft = sizeSections({ preset: wan, ratio: 16 / 9, quality: 'draft', setting: '832x480', measured });
	assert.equal(draft.auto, '832x480');
	assert.deepEqual(draft.sections.map((s) => [s.id, s.rows.map((r) => r.value)]), [['high', ['1280x720']], ['low', ['832x480']]]);
	assert.deepEqual(draft.rows.map((r) => [r.value, r.measured, r.fit, r.own]), [['1280x720', false, 'exact', false], ['832x480', true, 'exact', false]]);
	assert.equal(sizeSections({ preset: wan, ratio: 16 / 9, quality: 'final', setting: '832x480' }).auto, '1280x720');
	const scope = sizeSections({ preset: wan, ratio: 2.39, quality: 'final', measured: null });
	assert.deepEqual(scope.rows.map((r) => [r.value, r.fit, percent(r.loss), r.measured]), [['1280x720', 'crop', 26, null], ['832x480', 'crop', 27, null]]);
	assert.deepEqual(sizeSections({ preset: wan, ratio: 2.39, quality: 'final', framing: 'bars' }).rows.map((r) => r.fit), ['bars', 'bars']);
	const square = sizeSections({ preset: wan, ratio: 1, quality: 'final' });
	assert.deepEqual(square.rows.map((r) => r.value), ['1024x1024', '720x720']);
});

test('framing: a size the project chose off the list is shown on the grid of the engine, and one on the list is not repeated', () => {
	const snapped = sizeSections({ preset: ltx, ratio: 16 / 9, quality: 'final', chosen: '1280x720' });
	assert.deepEqual(snapped.rows.map((r) => [r.value, r.own]), [['1280x704', false], ['960x544', false], ['832x480', false]]);
	const own = sizeSections({ preset: ltx, ratio: 2.39, quality: 'final', chosen: '1536x640' });
	assert.deepEqual(own.rows.map((r) => [r.value, r.own, r.fit]), [['1536x640', true, 'exact'], ['1280x704', false, 'crop'], ['960x544', false, 'crop'], ['832x480', false, 'crop']]);
});

test('framing: a custom size is put on the grid of the engine, and one the engine refuses says why', () => {
	assert.deepEqual(customSize('1280', '720', LTX), { ok: true, value: '1280x704', snapped: true });
	assert.deepEqual(customSize('1280', '720', WAN), { ok: true, value: '1280x720', snapped: false });
	assert.deepEqual(customSize('12a', '720', WAN), { ok: false, error: 'invalid' });
	assert.deepEqual(customSize('32', '720', WAN), { ok: false, error: 'bounds' });
	assert.deepEqual(customSize('9000', '720', WAN), { ok: false, error: 'bounds' });
	assert.deepEqual(customSize('2048', '400', H3), { ok: false, error: 'ratio', value: '2048x384' });
	assert.deepEqual(customSize('1344', '1344', H3), { ok: false, error: 'area', value: '1344x1344' });
	assert.deepEqual(customSize('1536', '640', H3), { ok: true, value: '1536x640', snapped: false });
});

test('framing: the project keeps a chosen size per preset and quality, and Auto removes it', () => {
	const engine = { preset: WAN };
	engineSize(engine, WAN, 'draft', '832x480');
	engineSize(engine, WAN, 'final', '1040x832');
	assert.deepEqual(engine, { preset: WAN, sizes: { [WAN]: { draft: '832x480', final: '1040x832' } } });
	engineSize(engine, WAN, 'draft', null);
	assert.deepEqual(engine.sizes, { [WAN]: { final: '1040x832' } });
	engineSize(engine, WAN, 'final', null);
	assert.deepEqual(engine, { preset: WAN });
	assert.ok(sameSizes({ a: { draft: '1x1', final: '2x2' }, b: { final: '3x3' } }, { b: { final: '3x3' }, a: { final: '2x2', draft: '1x1' } }));
	assert.ok(!sameSizes({ a: { draft: '1x1' } }, { a: { final: '1x1' } }));
	assert.ok(sameSizes(undefined, {}));
});

test('framing: a change of format counts the shots whose placed take is cropped or put between bars', () => {
	const takes = { a: { width: 1280, height: 720 }, b: { resolution: '720x1280' }, c: { resolution: '832x480' } };
	const clips = [{ take: 'a' }, { take: 'b' }, { take: null }, { take: 'c' }, { take: 'gone' }];
	assert.deepEqual(formatChange(clips, (id) => takes[id] ?? null, { aspect: '2.39:1' }), { crop: 2, bars: 1 });
	assert.deepEqual(formatChange(clips, (id) => takes[id] ?? null, { aspect: '16:9' }), { crop: 0, bars: 1 });
	assert.deepEqual(formatChange(clips, (id) => takes[id] ?? null, { aspect: '16:9', framing: 'crop' }), { crop: 1, bars: 0 });
});

test('framing: a take is in an old ratio when it differs from the size its engine makes now, past the 3 % a crop hides', () => {
	assert.ok(changedRatio({ resolution: '1280x720' }, '720x1280'));
	assert.ok(changedRatio({ width: 1280, height: 720 }, '1024x1024'));
	assert.ok(!changedRatio({ resolution: '832x480' }, '1280x720'));
	assert.ok(!changedRatio({ resolution: '1280x704' }, '1280x720'));
	assert.ok(!changedRatio({}, '1280x720'));
	assert.ok(!changedRatio({ resolution: '1280x720' }, null));
});

test('framing: the export frame follows the film or the social ratio, and a note says when the largest take is enlarged', () => {
	assert.deepEqual(exportFrame({ aspect: '2.39:1' }, 'web', '1080p', '9:16'), [1920, 804]);
	assert.deepEqual(exportFrame({ aspect: '2.39:1' }, 'social', '1080p', '4:5'), [1080, 1350]);
	assert.deepEqual(exportFrame({ aspect: '16:9' }, 'social', '4K', '1:1'), [2160, 2160]);
	const takes = { a: { resolution: '832x480' }, b: { width: 1280, height: 720 } };
	const largest = largestTake([{ take: 'a' }, { take: 'b' }, { take: null }], (id) => takes[id]);
	assert.deepEqual(largest, [1280, 720]);
	assert.equal(largestTake([], () => null), null);
	assert.ok(upscaled([1280, 720], [1920, 804]));
	assert.ok(!upscaled([1920, 1080], [1920, 804]));
	assert.ok(!upscaled([1280, 720], [1280, 536]));
	assert.ok(!upscaled([1080, 1920], [1920, 1080], 'bars'));
	assert.ok(upscaled([1080, 1920], [1920, 1080], 'crop'));
	assert.ok(!upscaled(null, [1920, 1080]));
});

test('framing: the viewer crops or puts bars like the export, on the shot and on a previewed take, and the menus list every format and resolution', () => {
	const viewer = source('../components/viewer/Viewer.svelte');
	assert.match(viewer, /const liveFit = \$derived\(liveVideo \|\| liveImage \? fitFor\(liveVideo \?\? liveImage, a\) : BARS\);/);
	assert.match(viewer, /src=\{liveVideo\}\n\t+class="h-full w-full \{fitClass\(liveFit\)\}"/);
	assert.match(viewer, /src=\{previewResult\.url\}\n\t+class="h-full w-full \{fitClass\(resultFit\)\}"/);
	assert.match(viewer, /class="h-full w-full \{fitClass\(liveFit\)\}" style:opacity/);
	assert.match(viewer, /\{#each formats as section \(section\.id\)\}<optgroup label=\{formatGroupText\(section\.id\)\}>/);
	assert.match(viewer, /\{#each RESOLUTION_NAMES as r \(r\)\}/);
	assert.doesNotMatch(viewer, /bind:value=\{doc\.(aspect|resolution)\}/);
});

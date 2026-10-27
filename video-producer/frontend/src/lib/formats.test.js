import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import table from './formatstable.js';
import {
	FORMATS,
	SOCIAL_FORMATS,
	chosenSize,
	closestFormat,
	deliverySize,
	draftSize,
	finalSize,
	fit,
	formatValue,
	migrateFormats,
	nearestMeasured,
	pickSize,
	ratioOf,
	ratioText,
	resolutionValue,
	sizesValue,
	timeScale
} from './formats.js';
import { emptyDoc, migrate } from './starter.js';
import { draftResolution, finalResolution } from './generation.js';
import { RESOLUTIONS, videoFile } from './exports.js';
import { fcpxml, sequenceFrame } from './exchange.js';

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const shared = read('../../../backend/formats.json');
const cases = read('../../../tests/fixtures/format_cases.json');
const { cases: migrations } = read('../../../tests/fixtures/format_migration.json');
const pick = (doc) => Object.fromEntries(['aspect', 'resolution', 'framing', 'engine'].filter((key) => key in doc).map((key) => [key, doc[key]]));
const round9 = (value) => Math.round(value * 1e9) / 1e9;

test('the page copy of the formats table is identical to the backend one', () => {
	assert.deepEqual(table, shared);
	assert.deepEqual(RESOLUTIONS, Object.keys(shared.resolutions));
	assert.ok(FORMATS.every((name) => formatValue(name) === name));
	assert.ok(SOCIAL_FORMATS.includes(shared.social.default));
});

test('shared cases: formats read, kept and delivered as the server does', () => {
	for (const [text, ratio] of cases.ratios) assert.equal(ratioOf(text), ratio, text);
	for (const [text, kept] of cases.values) assert.equal(formatValue(text), kept, String(text));
	for (const [text, kept] of cases.resolutions) assert.equal(resolutionValue(text), kept, String(text));
	for (const [name, resolution, size] of cases.delivery) assert.deepEqual(deliverySize(ratioOf(name), resolution), size, `${name} ${resolution}`);
});

test('shared cases: draft and final sizes of each engine for each format', () => {
	for (const c of cases.plans) {
		const options = cases.options[c.options];
		const preset = cases.presets[c.preset];
		const ratio = ratioOf(c.format);
		assert.equal(draftSize(options, c.setting, ratio, preset), c.draft, `${c.preset} ${c.format} ${c.setting} draft`);
		assert.equal(finalSize(options, ratio, preset), c.final, `${c.preset} ${c.format} final`);
	}
});

test('shared cases: a chosen size is taken or left out', () => {
	for (const c of cases.picks) {
		const choice = pickSize(cases.options[c.options], ratioOf(c.format), c.quality, c.setting, c.chosen, cases.presets[c.preset]);
		assert.deepEqual([choice.size, choice.refused, choice.problem], [c.size, c.refused, c.problem], `${c.preset} ${c.chosen}`);
	}
});

test('shared cases: framing, closest format, ratio text, time scale, nearest size and chosen sizes', () => {
	for (const [take, frame, framing, shown] of cases.fits) assert.equal(fit(ratioOf(take), ratioOf(frame), framing), shown, `${take} in ${frame} ${framing}`);
	for (const [values, name, closest] of cases.closest) assert.equal(closestFormat(values, ratioOf(name)), closest, `${values} ${name}`);
	for (const [size, text] of cases.texts) assert.equal(ratioText(ratioOf(size)), text, size);
	for (const [measured, wanted, scale] of cases.scales) assert.equal(round9(timeScale(measured, wanted)), scale, `${measured} ${wanted}`);
	for (const [measured, wanted, nearest] of cases.nearest) assert.equal(nearestMeasured(measured, wanted), nearest, `${measured} ${wanted}`);
	for (const [value, kept] of cases.sizes) assert.deepEqual(sizesValue(value), kept);
});

for (const c of migrations) {
	test(`shared migration: ${c.name}`, () => {
		const doc = structuredClone(c.doc);
		const before = structuredClone(doc);
		assert.deepEqual(pick(migrateFormats(doc)), c.expected);
		assert.deepEqual(doc, before);
	});
}

test('migrate reads the format of a whole document as the server does', () => {
	const doc = { ...emptyDoc((key) => key), ...structuredClone(migrations[4].doc) };
	assert.deepEqual(pick(migrate(doc)), migrations[4].expected);
	const plain = emptyDoc((key) => key);
	assert.deepEqual(pick(migrate(plain)), pick(plain));
});

test('the size helpers of the page follow the shared rule and the size the project chose', () => {
	const wan = { id: cases.presets.wan, resolutions: cases.options.wan.map((value) => ({ value, label: value })) };
	const ltx = { id: cases.presets.ltx, resolutions: cases.options.wan.map((value) => ({ value, label: value })) };
	const h3 = { id: cases.presets.h3, resolutions: cases.options.h3.map((value) => ({ value, label: value })) };
	const doc = { engine: { sizes: { [wan.id]: { final: '1488x624' }, [h3.id]: { final: '1920x1080' } } } };
	assert.equal(draftResolution(wan, '832x480', 2.39), '832x480');
	assert.equal(finalResolution(wan, 2.39, chosenSize(doc, wan.id, 'final')), '1488x624');
	assert.equal(finalResolution(h3, 16 / 9, chosenSize(doc, h3.id, 'final')), '1344x768');
	assert.equal(finalResolution(ltx, 16 / 9), '1280x704');
	assert.equal(draftResolution(h3, '832x480', 0.8), '480x640');
	assert.equal(chosenSize(doc, 'other', 'final'), null);
});

test('the export of a social video of another ratio names it, and the FCPXML frame follows the project', () => {
	assert.equal(videoFile('Aube', '1080p', 'social', false, '4:5'), 'Aube_1080p_4x5.mp4');
	assert.equal(videoFile('Aube', '1080p', 'social', false, '9:16'), 'Aube_1080p.mp4');
	assert.equal(videoFile('Aube', '1440p', 'social', true, '1:1'), 'Aube_1440p_1x1_social_stems.zip');
	assert.equal(videoFile('Aube', '1080p', 'web', false, '4:5'), 'Aube_1080p.mp4');
	const scope = { ...emptyDoc((key) => key), aspect: '2.39:1', name: 'Scope' };
	assert.deepEqual(sequenceFrame(scope), [1920, 804]);
	assert.deepEqual(sequenceFrame({ ...scope, aspect: '16:9', resolution: '1440p' }), [2560, 1440]);
	const xml = fcpxml(scope, { label: () => '' });
	assert.ok(xml.includes('<format id="r1" frameDuration="1/25s" width="1920" height="804"/>'));
	assert.ok(fcpxml({ ...scope, aspect: '16:9' }, { label: () => '' }).includes('name="FFVideoFormat1080p25"'));
});

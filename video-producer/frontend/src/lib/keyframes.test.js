import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	DEFAULT_CANDIDATES,
	acceptedRoles,
	choiceOf,
	chosenOption,
	clampCount,
	draftPictures,
	keyframeAsset,
	keyframeOptions,
	normalizeKeyframeEstimate,
	normalizeKeyframePreset,
	ordered,
	presetAbsent,
	requestBody,
	storedChoice,
	usable
} from './keyframes.js';
import { normalizeMe, normalizeTake } from './api.js';

const QWEN = '01M31Y6WNM07EHAXXCDV1QVJVX';
const GEMINI = '01M48T0Q8PFET5JD9Z2FDP8E11';

const presets = [
	normalizeKeyframePreset({ id: QWEN, name: 'Qwen-Image-2.1', engine: 'native', requires: { recommended_vram_gb: 24 }, max_images: 10, models: [] }),
	normalizeKeyframePreset({ id: GEMINI, name: 'Gemini Images', engine: 'cloud', driver: 'cloud.google', backend_id: 'b-google', max_images: 10, models: [{ id: 'cm-nano', name: 'Nano Banana 2.1', max_images: 10 }, { id: 'cm-pro', name: 'Nano Banana Pro', max_images: 5 }] })
];

const image = (id, extra = {}) => ({ id, kind: 'image', name: id, src: `/m/${id}.png`, ...extra });

function scene() {
	return {
		aspect: '16:9',
		assets: [image('lea'), image('cafe'), image('hat'), image('capture'), image('street'), image('source'), { id: 'voice', kind: 'audio', name: 'voice', src: '/m/v.wav' }, { id: 'clip', kind: 'video', name: 'clip', src: '/m/c.mp4' }],
		references: [
			{ id: 'r-lea', name: 'Léa', space: 'identite', type: 'Personnage', assetId: 'lea', scope: null },
			{ id: 'r-cafe', name: 'Café', space: 'decors3d', type: 'Capture 3D', assetId: 'cafe', scope: { type: 'global' } },
			{ id: 'r-street', name: 'Street', space: 'decors3d', type: 'Capture 3D', assetId: 'street', scope: null },
			{ id: 'r-voice', name: 'Voice', space: 'son', type: 'Voix', assetId: 'voice', scope: null },
			{ id: 'r-move', name: 'Move', space: 'mouvement', type: 'Mouvement', assetId: 'clip', scope: null },
			{ id: 'r-own', name: 'Red hat', space: 'identite', type: 'Objet', assetId: 'hat', scope: { type: 'shot', shotId: 's1' } }
		],
		frames: [],
		scenes: [],
		clips: [{ id: 's1', start: 0, dur: 4 }]
	};
}

const draftOf = (doc, extra = {}) => ({ text: 'Léa sits down.', first: null, last: null, exclude: ['r-street'], own: [{ id: 'r-own', name: 'Red hat', space: 'identite', type: 'Objet', assetId: 'hat', role: 'Identité' }], ...extra });

test('the edit presets of GET /me become one option per local preset and per cloud edit model', () => {
	const options = keyframeOptions(presets);

	assert.deepEqual(
		options.map((o) => [o.key, o.label, o.group, o.cloud, o.maxImages]),
		[
			[`${QWEN}|`, 'Qwen-Image-2.1', null, false, 10],
			[`${GEMINI}|cm-nano`, 'Nano Banana 2.1', 'Gemini Images', true, 10],
			[`${GEMINI}|cm-pro`, 'Nano Banana Pro', 'Gemini Images', true, 5]
		]
	);
	assert.equal(presets[0].recommendedVram, 24);
	assert.equal(normalizeKeyframePreset({ name: 'no id' }), null);
	assert.deepEqual(normalizeMe({ keyframe_presets: [{ id: QWEN, name: 'Qwen-Image-2.1', engine: 'native', max_images: 10 }, 'x'] }).keyframePresets.map((p) => p.id), [QWEN]);
	assert.deepEqual(normalizeMe({}).keyframePresets, []);
});

test('the project keeps its choice, the first option stands in for none, and a vanished one is absent', () => {
	const options = keyframeOptions(presets);

	assert.deepEqual(storedChoice({ keyframes: { preset: GEMINI, model: 'cm-pro' } }), { preset: GEMINI, model: 'cm-pro' });
	assert.deepEqual(storedChoice({ keyframes: { model: 'cm-pro' } }), { preset: null, model: null });
	assert.deepEqual(storedChoice({}), { preset: null, model: null });
	assert.equal(chosenOption(options, { preset: GEMINI, model: 'cm-pro' }).label, 'Nano Banana Pro');
	assert.equal(chosenOption(options, { preset: null }).preset, QWEN);
	assert.equal(chosenOption(options, { preset: 'gone', model: null }), null);
	assert.equal(presetAbsent(options, { preset: 'gone', model: null }), true);
	assert.equal(presetAbsent(options, { preset: QWEN, model: null }), false);
	assert.equal(presetAbsent(options, { preset: null }), false);
	assert.deepEqual(choiceOf(options[0]), { preset: QWEN });
	assert.deepEqual(choiceOf(options[1]), { preset: GEMINI, model: 'cm-nano' });
});

test('the pictures sent are the Identité and Décors 3D images of the editor, settings first, excluded ones left out', () => {
	const doc = scene();

	const pictures = draftPictures(doc, doc.clips[0], draftOf(doc));

	assert.deepEqual(
		pictures.map((p) => [p.assetId, p.role, p.name, p.origin]),
		[
			['cafe', 'setting', 'Café', 'reference'],
			['lea', 'character', 'Léa', 'reference'],
			['hat', 'object', 'Red hat', 'reference']
		]
	);
});

test('the start image is the framing of the end image, and of a new start image only when it is a saved 3D capture', () => {
	const doc = scene();
	doc.frames = [{ id: 'f1', shotId: 's1', time: 0, assetId: 'capture', role: 'first', strength: 100, sceneId: 'sc1' }];
	const draft = draftOf(doc, { first: 'capture' });

	assert.deepEqual(draftPictures(doc, doc.clips[0], draft, 'first')[0], { assetId: 'capture', role: 'frame', name: '', origin: 'frame' });
	assert.equal(draftPictures(doc, doc.clips[0], draftOf(doc, { first: 'street' }), 'first')[0].assetId, 'cafe');
	assert.equal(draftPictures(doc, doc.clips[0], draftOf(doc, { first: 'street' }), 'last')[0].assetId, 'street');
	delete doc.frames[0].sceneId;
	assert.equal(draftPictures(doc, doc.clips[0], draft, 'first')[0].assetId, 'cafe');
	assert.equal(draftPictures(doc, doc.clips[0], draft, 'last')[0].role, 'frame');
});

test('the picture the scene of a captured start image was built from is sent as a set, right after the capture', () => {
	const doc = scene();
	doc.scenes = [{ id: 'sc1', kind: 'splat', status: 'done', sourceAssetId: 'source' }];
	doc.frames = [{ id: 'f1', shotId: 's1', time: 0, assetId: 'capture', role: 'first', strength: 100, sceneId: 'sc1' }];
	const scenePicture = (draft) => draftPictures(doc, doc.clips[0], draft).find((p) => p.origin === 'scene') ?? null;

	const pictures = draftPictures(doc, doc.clips[0], draftOf(doc, { first: 'capture' }));
	assert.deepEqual(pictures.slice(0, 2), [
		{ assetId: 'capture', role: 'frame', name: '', origin: 'frame' },
		{ assetId: 'source', role: 'setting', name: '', origin: 'scene' }
	]);
	assert.equal(scenePicture(draftOf(doc, { first: 'street' })), null);
	doc.scenes[0].status = 'running';
	assert.equal(scenePicture(draftOf(doc, { first: 'capture' })), null);
	doc.scenes[0].status = 'done';
	delete doc.frames[0].sceneId;
	assert.equal(scenePicture(draftOf(doc, { first: 'capture' })), null);
});

test('the body names the preset, model, role, count, prompt and pictures, the count kept from 2 to 4', () => {
	const option = keyframeOptions(presets)[1];
	const pictures = [{ assetId: 'cafe', role: 'setting', name: 'Café', origin: 'reference' }];

	assert.deepEqual(requestBody({ option, role: 'last', count: 3, prompt: 'Léa sits down.', pictures }), {
		preset_id: GEMINI,
		model_id: 'cm-nano',
		role: 'last',
		count: 3,
		prompt: 'Léa sits down.',
		references: [{ asset_id: 'cafe', role: 'setting', name: 'Café' }]
	});
	assert.equal(requestBody({ option, role: 'middle', count: 9, prompt: null, pictures: [] }).role, 'first');
	assert.equal(clampCount(9), 4);
	assert.equal(clampCount(1), 2);
	assert.equal(clampCount('3'), DEFAULT_CANDIDATES);
});

test('the estimate is read with its pictures, time, memory, quota, cost, blocks and warnings', () => {
	const estimate = normalizeKeyframeEstimate({
		role: 'first',
		count: 3,
		resolution: '1360x768',
		prompt: 'The opening frame…',
		references: [{ rank: 1, asset_id: 'cafe', role: 'setting', name: 'Café', origin: 'reference' }, { rank: 2, asset_id: null, role: 'hero', name: '', origin: 'scene' }],
		vram: { estimate_gb: 18.5, free_gb: 11.2, streams: true, unknown: false },
		time: { seconds: 270, per_candidate: 90, samples: 2 },
		quota: { applies: true, needed_minutes: 4.5, remaining: 30, limit: 60, exempt: false },
		cost: null,
		blocks: [{ code: 'missing_models', message: 'Install…', data: { fields: ['vae'] } }],
		warnings: [{ code: 'aspect_mismatch', message: '', data: { size: '1024x1024' } }, { message: 'no code' }]
	});

	assert.deepEqual(estimate.references.map((r) => [r.rank, r.assetId, r.role]), [[1, 'cafe', 'setting'], [2, null, 'setting']]);
	assert.deepEqual(estimate.time, { seconds: 270, perCandidate: 90, samples: 2 });
	assert.deepEqual(estimate.vram, { estimateGb: 18.5, freeGb: 11.2, streams: true, unknown: false });
	assert.equal(estimate.quota.neededMinutes, 4.5);
	assert.deepEqual(estimate.blocks, [{ code: 'missing_models', message: 'Install…', data: { fields: ['vae'] } }]);
	assert.equal(estimate.warnings.length, 1);
	assert.deepEqual(normalizeKeyframeEstimate({ cost: { total_usd: 0.12, known: true } }).cost, { totalUsd: '0.12', known: true });
	assert.equal(normalizeKeyframeEstimate('x'), null);
});

test('a candidate take keeps its kind, the gallery runs in letter order, and an accepted one is a project image', () => {
	const take = normalizeTake({ id: 't1', kind: 'keyframe', status: 'done', variant: 'B', generation_id: 'g1', file_id: 'f1', url: '/api/media/generations/g1/0.png', width: 1360, height: 768 });
	const list = ['AA', 'C', 'A', 'B'].map((variant, i) => ({ id: `k${i}`, kind: 'keyframe', variant }));

	assert.equal(take.kind, 'keyframe');
	assert.equal(normalizeTake({ id: 't2', kind: 'other' }).kind, 'render');
	assert.deepEqual(ordered([...list, { id: 'v', kind: 'render', variant: 'A' }]).map((x) => x.variant), ['A', 'B', 'C', 'AA']);
	assert.equal(usable(take), true);
	assert.equal(usable({ ...take, status: 'running' }), false);
	assert.deepEqual(acceptedRoles(take, { first: 'gen-t1', last: 'gen-t1' }), ['first', 'last']);
	assert.deepEqual(acceptedRoles(take, { first: 'other', last: null }), []);
	const made = keyframeAsset(take, 'Shot 1 · candidate B');
	assert.deepEqual(
		{ id: made.id, kind: made.kind, src: made.src, origin: made.origin, res: made.res, generated: made.generated, resultId: made.resultId },
		{ id: 'gen-t1', kind: 'image', src: '/api/media/generations/g1/0.png', origin: { kind: 'history', generationId: 'g1', fileId: 'f1' }, res: '1360×768', generated: true, resultId: 't1' }
	);
});

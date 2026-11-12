import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LIBRARY_FILE, MEDIA_TOOLS, createClient, normalizeTool } from './api.js';
import { FINISH_EFFECTS, availability, choicesOf, cleanFinishing, effectByKey, fieldBounds, finishFailure, finishFormat, finishRequest, finishSteps, finishable, finishedName, finishingOf, settingOf, toolsById } from './finishing.js';

const CATALOG = [
	{ id: 'film_grain', label: 'Film grain', params: [{ name: 'amount', type: 'float', default: 30, min: 0, max: 100, step: 1 }, { name: 'size', type: 'float', default: 1.5, min: 1, max: 3, step: 0.1 }, { name: 'color', type: 'checkbox', default: false }] },
	{ id: 'vignette', label: 'Vignette', params: [{ name: 'amount', type: 'float', default: 40, min: 0, max: 100, step: 1 }, { name: 'radius', type: 'float', default: 50, min: 0, max: 100, step: 1 }] },
	{ id: 'fix_colors', label: 'Fix colours', params: [{ name: 'strength', type: 'float', default: 100, min: 0, max: 100, step: 5 }] },
	{ id: 'lut', label: 'LUT', params: [{ name: 'lut', type: 'lut', default: '', options: [{ label: 'None', value: '' }, { label: 'warm', value: 'warm.cube' }, { label: 'teal orange', value: 'teal_orange.cube' }] }, { name: 'strength', type: 'float', default: 1, min: 0, max: 1, step: 0.05 }] },
	{ id: 'look', label: 'Look', params: [{ name: 'look', type: 'look', default: '', options: [{ label: 'None', value: '' }] }, { name: 'strength', type: 'float', default: 1, min: 0, max: 1, step: 0.05 }] },
	{ id: 'trim', label: 'Trim', params: [] }
].map(normalizeTool);

const tools = toolsById(CATALOG);
const job = (extra = {}) => ({ id: 'j1', status: 'done', format: 'web', media: { kind: 'library', itemId: 'item-9', url: '/api/media/uploads/e.mp4' }, ...extra });

test('finishing: nothing is on by default, and a project without settings sends no step', () => {
	assert.deepEqual(finishingOf({ master: { vol: 0 } }), {});
	for (const effect of FINISH_EFFECTS) assert.equal(settingOf({}, effect, tools.get(effect.tool)).on, false);
	assert.deepEqual(finishSteps({}, tools), []);
});

test('finishing: the steps follow the correct, grade, then texture order, with the values the user chose', () => {
	const finishing = {
		grain: { on: true, amount: 45, size: 2 },
		vignette: { on: true, amount: 60, radius: 35 },
		fixColors: { on: true, strength: 80 },
		lut: { on: true, ref: 'teal_orange.cube', strength: 0.5 }
	};
	assert.deepEqual(finishSteps(finishing, tools), [
		{ tool: 'fix_colors', params: { white_balance: true, contrast: true, strength: 80 } },
		{ tool: 'lut', params: { strength: 0.5, lut: 'teal_orange.cube' } },
		{ tool: 'vignette', params: { amount: 60, radius: 35 } },
		{ tool: 'film_grain', params: { amount: 45, size: 2 } }
	]);
});

test('finishing: an effect switched off keeps its values but sends nothing', () => {
	const finishing = { grain: { on: false, amount: 80, size: 2.5 } };
	assert.deepEqual(finishSteps(finishing, tools), []);
	assert.deepEqual(settingOf(finishing, effectByKey('grain'), tools.get('film_grain')), { on: false, amount: 80, size: 2.5 });
});

test('finishing: values out of the core bounds are brought back, and missing ones take the core default', () => {
	const grain = effectByKey('grain');
	assert.deepEqual(settingOf({ grain: { on: true, amount: 400 } }, grain, tools.get('film_grain')), { on: true, amount: 100, size: 1.5 });
	assert.deepEqual(fieldBounds(grain.fields[1], tools.get('film_grain')), { min: 1, max: 3, step: 0.1, value: 1.5 });
	assert.deepEqual(fieldBounds(grain.fields[0], undefined), { min: 0, max: 100, step: 1, value: 30 });
});

test('finishing: a LUT or a look comes from the core list; a fresh one starts on the first, none means unavailable', () => {
	const lut = effectByKey('lut');
	assert.deepEqual(choicesOf(lut, tools.get('lut')).map((x) => x.value), ['warm.cube', 'teal_orange.cube']);
	assert.deepEqual(settingOf({ lut: { on: true } }, lut, tools.get('lut')), { on: true, strength: 1, ref: 'warm.cube', missing: false });
	assert.equal(availability(lut, tools), 'ready');
	assert.equal(availability(effectByKey('look'), tools), 'empty');
	assert.deepEqual(finishSteps({ look: { on: true, ref: 'mine:1' } }, tools), []);
	assert.equal(availability(effectByKey('grain'), toolsById([])), 'missing');
	assert.deepEqual(finishSteps({ grain: { on: true } }, toolsById([])), []);
});

test('finishing: a saved LUT or look that the core no longer offers is kept as chosen, marked missing, and left out of the run', () => {
	const lut = effectByKey('lut');
	assert.deepEqual(settingOf({ lut: { on: true, ref: 'gone.cube', strength: 0.5 } }, lut, tools.get('lut')), { on: true, strength: 0.5, ref: 'gone.cube', missing: true });
	assert.deepEqual(finishSteps({ lut: { on: true, ref: 'gone.cube' }, grain: { on: true } }, tools), [{ tool: 'film_grain', params: { amount: 30, size: 1.5 } }]);
	assert.deepEqual(finishSteps({ lut: { on: true, ref: 'teal_orange.cube' } }, tools), [{ tool: 'lut', params: { strength: 1, lut: 'teal_orange.cube' } }]);
	assert.deepEqual(cleanFinishing({ lut: settingOf({ lut: { on: true, ref: 'gone.cube' } }, lut, tools.get('lut')) }), { lut: { on: true, strength: 1, ref: 'gone.cube' } });
});

test('finishing: only a finished web or social export with its library item can be finished', () => {
	assert.equal(finishFormat('web'), true);
	assert.equal(finishFormat('social'), true);
	assert.equal(finishFormat('master'), false);
	assert.equal(finishFormat('archive'), false);
	assert.equal(finishable(job()), true);
	assert.equal(finishable(job({ format: 'social' })), true);
	assert.equal(finishable(job({ format: 'master', media: null })), false);
	assert.equal(finishable(job({ status: 'failed' })), false);
	assert.equal(finishable(job({ media: null })), false);
});

test('finishing: the request is one run on the library item of the export, making a new item', () => {
	const steps = finishSteps({ vignette: { on: true }, grain: { on: true } }, tools);
	assert.deepEqual(finishRequest('item-9', steps), {
		steps: [
			{ tool: 'vignette', params: { amount: 40, radius: 50 } },
			{ tool: 'film_grain', params: { amount: 30, size: 1.5 } }
		],
		inputs: [{ item_id: 'item-9' }],
		output: { mode: 'new' }
	});
	assert.equal(finishedName('Lumi_s_potion_1080p.mp4'), 'Lumi_s_potion_1080p_finished.mp4');
	assert.equal(finishedName(''), 'video-producer_finished.mp4');
});

test('finishing: failures read as a full queue, a missing file or another failure, a refused limit keeping its own words', () => {
	assert.equal(finishFailure({ code: 'too_many_queued' }), 'busy');
	assert.equal(finishFailure({ code: 'limit_exceeded', message: 'Your plan allows 2 GB of uploads' }), 'failed');
	assert.equal(finishFailure({ code: 'not_found' }), 'gone');
	assert.equal(finishFailure({ code: 'tool_failed', message: 'x' }), 'failed');
	assert.equal(finishFailure(null), null);
});

test('finishing: the saved settings keep only known effects, fields and bounds', () => {
	assert.deepEqual(cleanFinishing({ grain: { on: true, amount: 300, size: 2, color: true }, blur: { on: true }, lut: { on: false, ref: 'warm.cube', strength: 0.4 } }), {
		lut: { on: false, strength: 0.4, ref: 'warm.cube' },
		grain: { on: true, amount: 100, size: 2 }
	});
	assert.equal(cleanFinishing({}), null);
	assert.equal(cleanFinishing(null), null);
});

test('finishing: a download only goes to a library upload path; any other path from a response is refused before any request', async () => {
	const calls = [];
	const client = createClient({ fetchRawFromApp: async (path) => (calls.push(path), { ok: true, status: 200, blob: async () => 'B' }) }, () => {});
	for (const path of ['https://evil.example/x.mp4', '//evil.example/x.mp4', '/api/plugins/video-producer/exports/1/file', '/api/media/uploads/../db.sqlite', '/api/media/uploads/a/b.mp4', '/api/media/uploads/x.mp4?redirect=1', '/api/media/uploads/%2e%2e', 'javascript:alert(1)', '/api/media/uploads/', null]) {
		const result = await client.downloadCore(path, 'x.mp4');
		assert.equal(result.ok, false, String(path));
		assert.equal(result.error.code, 'invalid_path', String(path));
	}
	assert.deepEqual(calls, []);
	assert.equal(LIBRARY_FILE.test('/api/media/uploads/cb08f73b-1d1f-454c-a9d6-75a39f8e1d91.mp4'), true);
});

test('finishing: the page reads the core catalog of video tools and downloads a library file, through the host client', async () => {
	const calls = [];
	const saved = [];
	const api = {
		async fetchRawFromApp(path, init) {
			calls.push([init.method, path]);
			if (path.startsWith(MEDIA_TOOLS)) return { ok: true, status: 200, json: async () => ({ success: true, data: { tools: [{ id: 'vignette', label: 'Vignette', params: [{ name: 'amount', min: 0, max: 100 }] }, { id: 'x' }] } }) };
			if (path.endsWith('/gone.mp4')) return { ok: false, status: 404, json: async () => ({ detail: { success: false, error: 'not_found', message: 'Upload not found' } }) };
			return { ok: true, status: 200, blob: async () => 'BLOB' };
		}
	};
	const client = createClient(api, (name, blob) => saved.push([name, blob]));
	const listed = await client.mediaTools('video');
	assert.deepEqual(listed.data.map((tool) => tool.id), ['vignette', 'x']);
	assert.deepEqual(listed.data[0].params[0], { name: 'amount', type: '', default: null, min: 0, max: 100, step: null, options: null });
	assert.deepEqual(await client.downloadCore('/api/media/uploads/f.mp4', 'film_finished.mp4'), { ok: true, data: { filename: 'film_finished.mp4' } });
	assert.deepEqual(saved, [['film_finished.mp4', 'BLOB']]);
	assert.deepEqual((await client.downloadCore('/api/media/uploads/gone.mp4', 'x.mp4')).error, { status: 404, code: 'not_found', message: 'Upload not found', data: null });
	assert.deepEqual(calls, [
		['GET', '/api/media-tools?kind=video'],
		['GET', '/api/media/uploads/f.mp4'],
		['GET', '/api/media/uploads/gone.mp4']
	]);
});

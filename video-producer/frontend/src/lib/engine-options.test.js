import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { compileModule } from 'svelte/compiler';
import { MODEL_LIST_LIMIT, coreModels, createClient, normalizeField, normalizePreset } from './api.js';
import { fitInline } from './barfit.js';
import {
	clampNumber,
	cleanOptions,
	fieldTitle,
	groupsOf,
	loraName,
	mainMode,
	matches,
	migrateOptions,
	modelTypeOf,
	optionCount,
	optionsOf,
	presetFields,
	resolveFields,
	resolvedValues,
	sameOptions,
	setPresetOptions,
	stepCounts,
	validOption
} from './options.js';
import { emptyDoc, migrate } from './starter.js';
import { chainState } from './chain.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

async function reactive() {
	const code = compileModule('export function live(value) { const state = $state(value); return state; }', { generate: 'client', filename: 'live.svelte.js' }).js.code;
	const module = code.replace(`'svelte/internal/client'`, JSON.stringify(import.meta.resolve('svelte/internal/client')));
	return (await import(`data:text/javascript,${encodeURIComponent(module)}`)).live;
}
const H3 = '01KX47H3MINIMAX000000000VA';
const LTX = '01KX47LTX25VIDEO00000000TV';
const recipe = (index) =>
	Object.entries({ balanced: [24, 4], distilled: [8, 1], quality: [30, 3] }).map(([profile, values]) => ({ when: { field: 'speed_profile', equals: profile }, then: { set_value: values[index], set_disabled: false } }));

function wire(name, type, extra = {}) {
	return { name, type, label: null, group: [], audience: 'simple', gate: null, default: null, required: false, limits: {}, reactions: [], ...extra };
}

const LTX_OPTIONS = [
	wire('speed_profile', 'select', { label: 'Speed', default: 'balanced', options: ['balanced', 'distilled', 'quality', 'custom'].map((value) => ({ value, label: value })) }),
	wire('seed', 'seed', { default: -1 }),
	wire('steps', 'slider', { label: 'Steps', default: 24, group: ['Advanced', 'Sampling'], audience: 'advanced', limits: { min: 1, max: 100, step: 1 }, reactions: recipe(0) }),
	wire('cfg', 'slider', { default: 4, group: ['Advanced', 'Sampling'], limits: { min: 1, max: 20, step: 0.5 }, reactions: [...recipe(1), { when: { field: 'speed_profile', equals: 'distilled' }, then: { set_disabled: true } }] }),
	wire('upscale', 'select', { default: 'off', group: ['Enhance'], options: ['off', '2.0x'].map((value) => ({ value, label: value })) }),
	wire('refine_strength', 'select', {
		default: 'strong',
		group: ['Enhance'],
		options: [{ value: 'strong', label: 'Strong' }],
		reactions: [
			{ when: { field: 'upscale', equals: 'off' }, then: { set_visibility: false } },
			{ when: { field: 'upscale', not_equals: 'off' }, then: { set_visibility: true } }
		]
	}),
	wire('detailer', 'gate', { default: false, group: ['Enhance'] }),
	wire('detail_strength', 'slider', { default: 0.5, group: ['Enhance'], gate: 'detailer', limits: { min: 0, max: 1, step: 0.05 } }),
	wire('model', 'model', { required: true, limits: { model_type: 'diffusion_model' }, recommended: ['dit.safetensors'] }),
	wire('loras', 'lora_picker', { default: [{ model: 'models/loras/style.safetensors', strength: 1 }], group: ['LoRA'], limits: { model_type: 'lora', strength_min: -2, strength_max: 2, max_items: 2 } })
];

function ltxPreset() {
	return normalizePreset({
		id: LTX,
		name: 'LTX-2.5',
		engine: 'native',
		video_director: { preset_modes: ['video'] },
		modes: { video: { default_form: 'custom', fields: {}, options: LTX_OPTIONS }, upscale: { default_form: 'custom', fields: {} } }
	});
}

function h3Preset() {
	return normalizePreset({
		id: H3,
		name: 'MiniMax-H3',
		engine: 'native',
		video_director: { preset_modes: ['video', 'refs'] },
		modes: {
			refs: { fields: {}, options: [wire('steps', 'slider', { default: 20 }), wire('reference_strength', 'slider', { default: 1 })] },
			video: { fields: {}, options: [wire('speed_profile', 'select', { default: 'quality', options: [{ value: 'quality', label: 'Quality' }] }), wire('steps', 'slider', { default: 24 })] }
		}
	});
}

const fieldsOf = (preset) => presetFields(preset);

test('options: a preset brings the options of each mode the director runs, its main mode first', () => {
	const ltx = ltxPreset();
	assert.deepEqual(ltx.presetModes, ['video']);
	assert.deepEqual(Object.keys(ltx.options), ['video']);
	assert.equal(ltx.options.video.length, LTX_OPTIONS.length);
	assert.deepEqual(ltx.options.video[2], {
		name: 'steps',
		type: 'slider',
		label: 'Steps',
		group: ['Advanced', 'Sampling'],
		audience: 'advanced',
		gate: null,
		default: 24,
		required: false,
		limits: { min: 1, max: 100, step: 1 },
		reactions: recipe(0),
		options: [],
		recommended: []
	});
	assert.deepEqual(ltx.options.video.at(-2).recommended, ['dit.safetensors']);
	assert.deepEqual(ltx.options.video.at(-1).limits, { strength_min: -2, strength_max: 2, max_items: 2, model_type: 'lora' });

	const h3 = h3Preset();
	assert.equal(mainMode(h3), 'video');
	assert.deepEqual(
		fieldsOf(h3).map((f) => [f.name, f.modes]),
		[
			['speed_profile', ['video']],
			['steps', ['video', 'refs']],
			['reference_strength', ['refs']]
		]
	);
	assert.equal(normalizeField({ name: 'x' }), null);
	assert.deepEqual(normalizeField({ name: 'x', type: 'checkbox', limits: { min: 'a', model_type: 3 }, reactions: [{ when: {} }, 'bad'] }).limits, {});
	assert.deepEqual(normalizePreset({ id: 'p', modes: { video: { fields: {} } } }).options, {});
});

test('options: each value is checked against the limits of its field, like the server does', () => {
	const f = Object.fromEntries(fieldsOf(ltxPreset()).map((field) => [field.name, field]));

	assert.ok(validOption(f.steps, 8) && validOption(f.steps, 100));
	assert.ok(!validOption(f.steps, 0) && !validOption(f.steps, 101) && !validOption(f.steps, 8.5) && !validOption(f.steps, '8'));
	assert.ok(validOption(f.cfg, 1.5) && !validOption(f.cfg, 0.5));
	assert.ok(validOption(f.seed, -1) && validOption(f.seed, 2 ** 31 - 1) && !validOption(f.seed, 2 ** 31) && !validOption(f.seed, 1.5));
	assert.ok(validOption(f.detailer, true) && !validOption(f.detailer, 1));
	assert.ok(validOption(f.speed_profile, 'distilled') && !validOption(f.speed_profile, 'turbo'));
	assert.ok(validOption(f.model, 'model:01ABC') && !validOption(f.model, 'model:') && !validOption(f.model, 'dit.safetensors'));
	assert.ok(validOption(f.loras, [{ model: 'model:l1', strength: 1.5 }]));
	assert.ok(!validOption(f.loras, [{ model: 'model:l1', strength: 2.5 }]));
	assert.ok(!validOption(f.loras, [{ model: 'model:l1', strength: 1, enabled: true }]));
	assert.ok(!validOption(f.loras, Array(3).fill({ model: 'model:l1', strength: 1 })));
	assert.ok(validOption({ type: 'textbox', limits: {} }, '1.0, 0.5') && !validOption({ type: 'textbox', limits: { max_length: 3 } }, 'abcd'));
	assert.ok(!validOption({ type: 'cloud_options', limits: {} }, {}));
});

test('options: the conditions of the reactions read like the core reads them', () => {
	const values = { speed_profile: 'distilled', cfg: 4, upscale: 'off', loras: [] };

	assert.ok(matches({ field: 'speed_profile', equals: 'distilled' }, values));
	assert.ok(matches({ field: 'speed_profile', operator: 'not_equals', value: 'balanced' }, values));
	assert.ok(matches({ field: 'cfg', greater_than: 1 }, values) && !matches({ field: 'cfg', less_than: 'x' }, values));
	assert.ok(matches({ field: 'upscale', in: ['off', '1.5x'] }, values) && matches({ field: 'loras', is_empty: true }, values));
	assert.ok(matches({ logic: 'OR', conditions: [{ field: 'cfg', less_than: 1 }, { field: 'upscale', equals: 'off' }] }, values));
	assert.ok(!matches({ logic: 'AND', conditions: [{ field: 'cfg', less_than: 1 }, { field: 'upscale', equals: 'off' }] }, values));
	assert.ok(matches([{ field: 'cfg', equals: 4 }, { field: 'upscale', not_in: ['2.0x'] }], values));
	assert.ok(!matches({ field: 'cfg', equals: true }, { cfg: 1 }));
	assert.ok(!matches({ field: 'cfg', unknown: 1 }, values) && !matches('cfg > 1', values));
});

test('options: the defaults follow the speed profile, the fields hide, disable and sit under their gate', () => {
	const fields = fieldsOf(ltxPreset());
	const rows = (given) => Object.fromEntries(resolveFields(fields, given).map((row) => [row.field.name, row]));

	const plain = rows({});
	assert.equal(plain.steps.value, 24);
	assert.equal(plain.refine_strength.visible, false);
	assert.equal(plain.detail_strength.visible, false);
	assert.equal(plain.cfg.disabled, false);

	const distilled = rows({ speed_profile: 'distilled', upscale: '2.0x', detailer: true, steps: 12 });
	assert.deepEqual([distilled.steps.value, distilled.steps.base, distilled.steps.set], [12, 8, true]);
	assert.deepEqual([distilled.cfg.value, distilled.cfg.set, distilled.cfg.disabled], [1, false, true]);
	assert.equal(distilled.refine_strength.visible, true);
	assert.equal(distilled.detail_strength.visible, true);
	assert.equal(resolvedValues(fields, { speed_profile: 'quality' }).cfg, 3);
	assert.deepEqual(stepCounts(fields, { speed_profile: 'distilled' }), { asked: 8, base: 24, scale: 8 / 24 });
	assert.equal(stepCounts(fields.filter((f) => f.name !== 'steps'), {}), null);
});

test('options: only the valid values that differ from what the field would take are kept', () => {
	const fields = fieldsOf(ltxPreset());

	assert.deepEqual(cleanOptions(fields, { speed_profile: 'distilled', steps: 8, cfg: 1.5, upscale: 'off', unknown: 3, seed: 2 ** 31 }), { speed_profile: 'distilled', cfg: 1.5 });
	assert.deepEqual(cleanOptions(fields, { steps: 24, seed: -1, loras: [{ model: 'models/loras/style.safetensors', strength: 1 }] }), {});
	assert.deepEqual(cleanOptions(fields, { loras: [] }), { loras: [] });
	assert.ok(sameOptions({ a: 1, b: [1] }, { b: [1], a: 1 }) && !sameOptions({ a: 1 }, { a: 1, b: 2 }) && !sameOptions({ a: 1 }, { a: '1' }));
});

test('options: the window groups the fields by their tab and section and names them', () => {
	const groups = groupsOf(resolveFields(fieldsOf(ltxPreset()), {}).filter((row) => row.visible));

	assert.deepEqual(
		groups.map((g) => [g.key, g.rows.map((row) => row.field.name)]),
		[
			['', ['speed_profile', 'seed', 'model']],
			['Advanced › Sampling', ['steps', 'cfg']],
			['Enhance', ['upscale', 'detailer']],
			['LoRA', ['loras']]
		]
	);
	assert.equal(fieldTitle({ name: 'step_cache_threshold' }), 'Step cache threshold');
	assert.equal(fieldTitle({ name: 'cfg', label: 'CFG Scale' }), 'CFG Scale');
	assert.equal(modelTypeOf({ type: 'lora_picker', limits: {} }), 'lora');
	assert.equal(modelTypeOf({ type: 'model', limits: { model_type: 'vae' } }), 'vae');
	const list = [{ id: 'l1', ref: 'model:l1', name: 'Style', file: 'style.safetensors' }];
	assert.equal(loraName('models\\loras\\style.safetensors', list).entry.ref, 'model:l1');
	assert.deepEqual(loraName('models/loras/other.safetensors', list), { entry: null, name: 'other.safetensors' });
});

test('options: the project keeps the options of each preset apart, and a preset with none leaves no trace', () => {
	const engine = { quality: 'draft', variants: 2, backend: '' };

	setPresetOptions(engine, LTX, { steps: 12 });
	setPresetOptions(engine, H3, { speed_profile: 'turbo' });
	assert.deepEqual(optionsOf(engine, LTX), { steps: 12 });
	assert.deepEqual(optionsOf(engine, H3), { speed_profile: 'turbo' });
	assert.equal(optionCount(engine, LTX), 1);
	const copy = optionsOf(engine, LTX);
	copy.steps = 99;
	assert.equal(engine.options[LTX].steps, 12);

	setPresetOptions(engine, LTX, {});
	assert.deepEqual(Object.keys(engine.options), [H3]);
	setPresetOptions(engine, H3, {});
	assert.ok(!('options' in engine));
	assert.deepEqual(optionsOf(engine, null), {});
	assert.equal(optionCount({}, LTX), 0);
});

test('options: the options of the open project read, count and save through its $state document', async () => {
	const live = await reactive();
	const engine = live({ quality: 'draft', preset: H3, options: { [H3]: { speed_profile: 'quality', loras: [{ model: 'model:l1', strength: 0.5 }] } } });

	assert.deepEqual(optionsOf(engine, H3), { speed_profile: 'quality', loras: [{ model: 'model:l1', strength: 0.5 }] });
	assert.equal(optionCount(engine, H3), 2);
	const copy = optionsOf(engine, H3);
	copy.loras[0].strength = 2;
	assert.equal(engine.options[H3].loras[0].strength, 0.5);

	setPresetOptions(engine, LTX, live({ steps: 12 }));
	assert.deepEqual(optionsOf(engine, LTX), { steps: 12 });
	assert.deepEqual(Object.keys(engine.options).sort(), [H3, LTX].sort());
});

test('options: deleting a shot of a project whose engine keeps options leaves the Production bar and the cut readable', async () => {
	const live = await reactive();
	const doc = live({
		fps: 25,
		engine: { preset: H3, quality: 'draft', options: { [H3]: { speed_profile: 'quality' } } },
		clips: [
			{ id: 'a', start: 0, dur: 5, stage: 'todo' },
			{ id: 'b', start: 5, dur: 5, stage: 'todo' },
			{ id: 'c', start: 10, dur: 5, stage: 'todo' }
		],
		prompts: [{ id: 'p', shotId: 'b', start: 5, dur: 5, text: 'Street flare' }],
		frames: [],
		assets: []
	});

	doc.clips.splice(1, 1);
	doc.prompts.splice(0, 1);

	assert.equal(optionCount(doc.engine, doc.engine.preset), 1);
	assert.deepEqual(doc.clips.map((c) => [c.id, c.start, c.dur]), [['a', 0, 5], ['c', 10, 5]]);
	assert.equal(chainState(doc, 1), null);
});

test('options: opening a project drops malformed options and keeps the rest', () => {
	const engine = {
		quality: 'draft',
		variants: 2,
		backend: '',
		options: {
			[LTX]: { steps: 12, bad: { x: 1 }, nothing: null, loras: [{ model: 'model:l1', strength: 1 }] },
			[H3]: { loras: [{ model: 'model:l1' }] },
			'': { steps: 1 },
			broken: 3
		}
	};

	assert.deepEqual(migrateOptions(engine).options, { [LTX]: { steps: 12, loras: [{ model: 'model:l1', strength: 1 }] } });
	assert.ok(!('options' in migrateOptions({ ...engine, options: [] })));
	assert.equal(migrateOptions({ quality: 'draft' }).options, undefined);
	const doc = emptyDoc((key) => key);
	doc.engine.options = { [LTX]: { steps: 12, bad: null } };
	assert.deepEqual(migrate(doc).engine.options, { [LTX]: { steps: 12 } });
	assert.ok(!('options' in emptyDoc((key) => key).engine));
});

test('options: a typed number lands inside its limits and on its step', () => {
	const fields = Object.fromEntries(fieldsOf(ltxPreset()).map((field) => [field.name, field]));

	assert.equal(clampNumber(fields.steps, '250'), 100);
	assert.equal(clampNumber(fields.steps, '7.6'), 8);
	assert.equal(clampNumber(fields.cfg, '3.3'), 3.5);
	assert.equal(clampNumber(fields.cfg, '0'), 1);
	assert.equal(clampNumber(fields.detail_strength, '0.33'), 0.35);
	assert.equal(clampNumber(fields.steps, 'abc'), null);
});

test('production bar: what does not fit goes to the More menu, by rank, the Edit Engine button always stays', () => {
	const items = [
		{ id: 'engine', width: 180, rank: 1 },
		{ id: 'profile', width: 200, rank: 2 },
		{ id: 'margin', width: 120, rank: 3, show: false },
		{ id: 'own', width: 60, rank: 4 },
		{ id: 'edit', width: 28, rank: 0, pinned: true },
		{ id: 'label', width: 80, rank: 5, folds: false }
	];
	const at = (room) => {
		const fit = fitInline(room, items);
		return [[...fit.inline].sort(), fit.overflow];
	};

	assert.deepEqual(at(600), [['edit', 'engine', 'label', 'own', 'profile'], []]);
	assert.deepEqual(at(500), [['edit', 'engine', 'own', 'profile'], []]);
	assert.deepEqual(at(400), [['edit', 'engine', 'own'], ['profile']]);
	assert.deepEqual(at(150), [['edit', 'own'], ['engine', 'profile']]);
	assert.deepEqual(at(0), [['edit'], ['engine', 'profile', 'own']]);
});

test('production bar: the engine and the profile never leave the bar, the generate label, the range and the notice give way first', () => {
	const items = [
		{ id: 'engine', width: 192, min: 112, rank: 3, keep: true },
		{ id: 'profile', width: 220, min: 96, rank: 4, keep: true },
		{ id: 'margin', width: 128, rank: 6 },
		{ id: 'own', width: 64, rank: 7, show: false },
		{ id: 'edit', width: 28, rank: 0, pinned: true },
		{ id: 'label', width: 88, rank: 8, folds: false },
		{ id: 'go', width: 120, rank: 1, outside: true },
		{ id: 'scope', width: 104, rank: 2, outside: true },
		{ id: 'notice', width: 200, rank: 5, outside: true }
	];
	const at = (budget) => {
		const fit = fitInline(budget, items);
		return [[...fit.inline].sort(), [...fit.wide].sort(), fit.overflow];
	};

	assert.deepEqual(at(1112), [['edit', 'engine', 'go', 'label', 'margin', 'notice', 'profile', 'scope'], ['engine', 'profile'], []]);
	assert.deepEqual(at(1111), [['edit', 'engine', 'go', 'margin', 'notice', 'profile', 'scope'], ['engine', 'profile'], []]);
	assert.deepEqual(at(700), [['edit', 'engine', 'go', 'label', 'profile', 'scope'], ['engine'], ['margin']]);
	assert.deepEqual(at(500), [['edit', 'engine', 'go', 'profile'], ['engine'], ['margin']]);
	assert.deepEqual(at(400), [['edit', 'engine', 'profile', 'scope'], [], ['margin']]);
	assert.deepEqual(at(0), [['edit', 'engine', 'profile'], [], ['margin']]);
	for (const budget of [0, 200, 400, 800, 1600]) assert.ok(['engine', 'profile'].every((id) => fitInline(budget, items).inline.has(id)), String(budget));
});

test('client: the models a field can take come from the PotionUI preset model list', async () => {
	const seen = [];
	const api = {
		async fetchRawFromApp(path, init) {
			seen.push([path, init.method]);
			return new Response(JSON.stringify({ success: true, data: { models: [{ id: 'm1', filename: 'loras/style_v2.safetensors', name: 'Style v2', custom_name: null }, { id: 'm2', filename: null, name: '' }, { name: 'no id' }] } }), { status: 200 });
		}
	};

	const result = await createClient(api).presetModels(LTX, 'lora');

	assert.deepEqual(seen, [[`/api/presets/${LTX}/models?limit=${MODEL_LIST_LIMIT}&model_type=lora`, 'GET']]);
	assert.deepEqual(result.data, [
		{ id: 'm1', ref: 'model:m1', name: 'Style v2', file: 'style_v2.safetensors' },
		{ id: 'm2', ref: 'model:m2', name: 'm2', file: null }
	]);
	assert.equal((await coreModels({}, LTX, 'lora')).error.code, 'no_api');
	const refused = await coreModels({ fetchRawFromApp: async () => new Response(JSON.stringify({ detail: 'nope' }), { status: 404 }) }, LTX, 'lora');
	assert.equal(refused.ok, false);
});

test('pages: the engine settings live in the Production bar and the Edit Engine window, the dock only points there', () => {
	const bar = source('../components/production/ProductionBar.svelte');
	assert.match(bar, /const profileItems = \$derived\(supportedProfiles\(\)\.map\(\(m\) => \(\{ id: m, label: m \}\)\)\);/);
	assert.doesNotMatch(bar, /disabled: !supported/);
	assert.match(bar, /\{ id: 'margin', width: widths\.margin, rank: 6, show: guided \}/);
	assert.match(bar, /\{ id: 'engine', width: ENGINE_WIDE, min: ENGINE_MIN, rank: 3, keep: true \}/);
	assert.match(bar, /\{ id: 'profile', width: widths\.profile, min: widths\.compact, rank: 4, keep: true, show: showProfile \}/);
	assert.doesNotMatch(bar, /fit\.overflow\.includes\('(engine|profile)'\)/);
	assert.doesNotMatch(bar, /hostIconName\('dots'\)/);
	assert.match(bar, /onSelect: setProjectQuality/);
	assert.match(bar, /onclick: \(\) => openEngineSettings\(engine\?\.preset\)/);
	assert.match(bar, /use:watch=\{'room'\} data-vp-engine/);
	assert.match(bar, /observer \?\?= new ResizeObserver\(measure\);/);
	assert.doesNotMatch(bar, /min-\[1400px\]/);

	const dock = source('../components/panels/DirectorDock.svelte');
	for (const gone of ['selectEngine', 'setProjectQuality', 'DraftsField', 'setReferenceMargin', 'SegmentedControl', 'dockFocus']) assert.doesNotMatch(dock, new RegExp(gone), gone);
	assert.match(dock, /t\('panels\.dock\.engine\.moved'\)/);
	assert.match(dock, /onclick: \(\) => openEngineSettings\(\)/);

	const production = source('./production.svelte.js');
	assert.match(production, /ui\.modal = \{ type: 'engine', preset: typeof preset === 'string' && preset \? preset : null \};/);
	assert.match(production, /code === 'engine_option_invalid'/);
	assert.match(source('../components/modals/Modals.svelte'), /\{:else if m\?\.type === 'engine'\}\n\t\t<EngineEditor preset=\{m\.preset \?\? null\} \/>/);
	assert.doesNotMatch(source('./state.svelte.js'), /dockFocus/);

	const editor = source('../components/modals/EngineEditor.svelte');
	assert.match(editor, /drafts\[chosen\] = cleanOptions\(fields, next\);/);
	assert.match(editor, /for \(const \[id, kept\] of updates\) setPresetOptions\(doc\.engine, id, kept\);/);
});

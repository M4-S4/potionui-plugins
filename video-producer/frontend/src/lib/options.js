import { isObject } from './values.js';

export const NUMBER_TYPES = ['slider', 'number', 'stepper', 'integer'];
export const FLAG_TYPES = ['checkbox', 'boolean', 'gate'];
export const CHOICE_TYPES = ['select', 'sampler', 'schedule'];
export const TEXT_TYPES = ['textbox', 'string'];
export const SEED_TYPE = 'seed';
export const MODEL_TYPE = 'model';
export const LORA_TYPE = 'lora_picker';
export const MODEL_REF = 'model:';
export const SEED_MAX = 2 ** 31 - 1;

const TEXT_LIMIT = 2000;
const LORA_LIMIT = 32;
const PASSES = 8;

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value);
const whole = (value) => isNumber(value) && Number.isInteger(value);
const within = (value, low, high) => (!isNumber(low) || value >= low) && (!isNumber(high) || value <= high);
const modelRef = (value) => typeof value === 'string' && value.startsWith(MODEL_REF) && value.length > MODEL_REF.length;
const copy = (value) => JSON.parse(JSON.stringify(value));

export function integral(field) {
	const { step, min } = field?.limits ?? {};
	return field?.type === 'integer' || (whole(step) && step >= 1 && (min === undefined || min === null || whole(min)));
}

function loraRow(row, limits) {
	if (!isObject(row) || Object.keys(row).sort().join() !== 'model,strength') return false;
	return modelRef(row.model) && isNumber(row.strength) && within(row.strength, limits.strength_min, limits.strength_max);
}

export function validOption(field, value) {
	const kind = field?.type;
	const limits = field?.limits ?? {};
	if (NUMBER_TYPES.includes(kind)) return isNumber(value) && within(value, limits.min, limits.max) && (!integral(field) || Number.isInteger(value));
	if (kind === SEED_TYPE) return Number.isInteger(value) && value >= -1 && value <= SEED_MAX;
	if (FLAG_TYPES.includes(kind)) return typeof value === 'boolean';
	if (CHOICE_TYPES.includes(kind)) {
		const options = (field.options ?? []).map((o) => o.value);
		return typeof value === 'string' && (options.length ? options.includes(value) : value.length > 0 && value.length <= TEXT_LIMIT);
	}
	if (TEXT_TYPES.includes(kind)) return typeof value === 'string' && value.length <= (whole(limits.max_length) ? limits.max_length : TEXT_LIMIT);
	if (kind === MODEL_TYPE) return modelRef(value);
	if (kind === LORA_TYPE) return Array.isArray(value) && value.length <= (whole(limits.max_items) ? limits.max_items : LORA_LIMIT) && value.every((row) => loraRow(row, limits));
	return false;
}

export function mainMode(preset) {
	const modes = preset?.modes ?? [];
	return (preset?.presetModes ?? []).find((m) => modes.includes(m)) ?? modes[0] ?? null;
}

export function presetFields(preset) {
	const byMode = isObject(preset?.options) ? preset.options : {};
	const main = mainMode(preset);
	const order = [...(main && byMode[main] ? [main] : []), ...Object.keys(byMode).filter((m) => m !== main)];
	const fields = [];
	for (const mode of order) {
		for (const field of byMode[mode] ?? []) {
			const known = fields.find((f) => f.name === field.name);
			if (known) known.modes.push(mode);
			else fields.push({ ...field, modes: [mode] });
		}
	}
	return fields;
}

const same = (a, b) => (isNumber(a) && isNumber(b) ? a === b : typeof a === typeof b && JSON.stringify(a) === JSON.stringify(b));
const compare = (a, b, test) => {
	const x = parseFloat(a);
	const y = parseFloat(b);
	return Number.isFinite(x) && Number.isFinite(y) && test(x, y);
};
const empty = (value) => value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length) || (isObject(value) && !Object.keys(value).length);

const OPERATORS = {
	equals: same,
	not_equals: (a, b) => !same(a, b),
	in: (a, b) => Array.isArray(b) && b.some((item) => same(a, item)),
	not_in: (a, b) => Array.isArray(b) && !b.some((item) => same(a, item)),
	greater_than: (a, b) => compare(a, b, (x, y) => x > y),
	less_than: (a, b) => compare(a, b, (x, y) => x < y),
	greater_than_or_equals: (a, b) => compare(a, b, (x, y) => x >= y),
	less_than_or_equals: (a, b) => compare(a, b, (x, y) => x <= y),
	contains: (a, b) => String(a ?? '').includes(String(b)),
	not_contains: (a, b) => !String(a ?? '').includes(String(b)),
	is_empty: (a) => empty(a),
	is_not_empty: (a) => !empty(a)
};

export function matches(when, values) {
	if (Array.isArray(when)) return when.every((item) => matches(item, values));
	if (!isObject(when)) return false;
	if ('logic' in when) {
		const conditions = Array.isArray(when.conditions) ? when.conditions : [];
		if (when.logic === 'OR') return conditions.length ? conditions.some((item) => matches(item, values)) : true;
		return when.logic === 'AND' && conditions.every((item) => matches(item, values));
	}
	const operator = when.operator ?? Object.keys(OPERATORS).find((key) => key in when);
	const test = OPERATORS[operator];
	if (!test || typeof when.field !== 'string') return false;
	return Boolean(test(values[when.field], 'operator' in when ? when.value : when[operator]));
}

export function resolvedValues(fields, given) {
	const current = Object.fromEntries(fields.map((f) => [f.name, f.default ?? null]));
	const set = Object.fromEntries(Object.entries(given ?? {}).filter(([name]) => name in current));
	Object.assign(current, set);
	for (let pass = 0; pass < PASSES; pass++) {
		const snapshot = { ...current };
		for (const field of fields) {
			if (field.name in set) continue;
			for (const reaction of field.reactions ?? []) {
				if (reaction.then && 'set_value' in reaction.then && matches(reaction.when, snapshot)) current[field.name] = reaction.then.set_value;
			}
		}
		if (fields.every((f) => same(current[f.name], snapshot[f.name]))) break;
	}
	return current;
}

function lastAction(field, values, key) {
	let found;
	for (const reaction of field.reactions ?? []) {
		if (reaction.then && key in reaction.then && matches(reaction.when, values)) found = reaction.then[key];
	}
	return found;
}

export function resolveFields(fields, given = {}) {
	const values = resolvedValues(fields, given);
	return fields.map((field) => {
		const set = Object.hasOwn(given, field.name);
		const others = { ...given };
		delete others[field.name];
		const base = set ? resolvedValues(fields, others)[field.name] : values[field.name];
		const gated = field.gate ? values[field.gate] === true : true;
		return { field, value: values[field.name], base, set, visible: gated && lastAction(field, values, 'set_visibility') !== false, disabled: lastAction(field, values, 'set_disabled') === true };
	});
}

export function cleanOptions(fields, given) {
	const kept = {};
	for (const field of fields) {
		if (Object.hasOwn(given ?? {}, field.name) && validOption(field, given[field.name])) kept[field.name] = given[field.name];
	}
	for (const field of fields) {
		if (!(field.name in kept)) continue;
		const others = { ...kept };
		delete others[field.name];
		if (same(resolvedValues(fields, others)[field.name], kept[field.name])) delete kept[field.name];
	}
	return kept;
}

export function groupsOf(rows) {
	const groups = [];
	for (const row of rows) {
		const path = row.field.group ?? [];
		const key = path.join(' › ');
		let group = groups.find((g) => g.key === key);
		if (!group) {
			group = { key, path, rows: [] };
			groups.push(group);
		}
		group.rows.push(row);
	}
	return groups;
}

export function fieldTitle(field) {
	if (field?.label) return field.label;
	const words = String(field?.name ?? '').replace(/_/g, ' ').trim();
	return words ? words[0].toUpperCase() + words.slice(1) : '';
}

export function optionsOf(engine, presetId) {
	const chosen = isObject(engine?.options) && presetId ? engine.options[presetId] : null;
	return isObject(chosen) ? copy(chosen) : {};
}

export function setPresetOptions(engine, presetId, values) {
	if (!engine || !presetId) return;
	const kept = isObject(values) ? values : {};
	const options = isObject(engine.options) ? { ...engine.options } : {};
	if (Object.keys(kept).length) options[presetId] = copy(kept);
	else delete options[presetId];
	if (Object.keys(options).length) engine.options = options;
	else delete engine.options;
}

export const optionCount = (engine, presetId) => Object.keys(optionsOf(engine, presetId)).length;

const storable = (value) =>
	typeof value === 'string' || typeof value === 'boolean' || isNumber(value) || (Array.isArray(value) && value.every((row) => isObject(row) && Object.keys(row).sort().join() === 'model,strength' && typeof row.model === 'string' && row.model && isNumber(row.strength)));

export function migrateOptions(engine) {
	if (!isObject(engine) || !('options' in engine)) return engine;
	const options = {};
	for (const [presetId, values] of Object.entries(isObject(engine.options) ? engine.options : {})) {
		if (!presetId || !isObject(values)) continue;
		const kept = Object.fromEntries(Object.entries(values).filter(([name, value]) => name && storable(value)));
		if (Object.keys(kept).length) options[presetId] = kept;
	}
	const next = { ...engine };
	if (Object.keys(options).length) next.options = options;
	else delete next.options;
	return next;
}

export function stepCounts(fields, given) {
	if (!fields.some((f) => f.name === 'steps' && NUMBER_TYPES.includes(f.type))) return null;
	const asked = resolvedValues(fields, given).steps;
	const base = resolvedValues(fields, {}).steps;
	return isNumber(asked) && isNumber(base) && asked > 0 && base > 0 ? { asked, base, scale: asked / base } : null;
}

export function sameOptions(a, b) {
	const keys = (value) => Object.keys(isObject(value) ? value : {}).sort();
	return JSON.stringify(keys(a)) === JSON.stringify(keys(b)) && keys(a).every((key) => same(a[key], b[key]));
}

export const modelTypeOf = (field) => field?.limits?.model_type ?? (field?.type === LORA_TYPE ? 'lora' : null);

export async function loadModels(models, presetId, type, client) {
	const key = `${presetId}|${type}`;
	if (!presetId || (models[key] && !models[key].failed)) return;
	models[key] = { loading: true, list: [], failed: false };
	const result = await client?.presetModels?.(presetId, type);
	models[key] = result?.ok ? { loading: false, list: result.data, failed: false } : { loading: false, list: [], failed: true };
}

export function loraName(model, list) {
	const file = String(model ?? '').replaceAll('\\', '/').split('/').pop();
	const found = (list ?? []).find((entry) => entry.ref === model || (entry.file && entry.file === file));
	return { entry: found ?? null, name: found?.name ?? file };
}

export function clampNumber(field, value) {
	const { min, max, step } = field?.limits ?? {};
	let next = Number(value);
	if (!Number.isFinite(next)) return null;
	if (isNumber(min)) next = Math.max(min, next);
	if (isNumber(max)) next = Math.min(max, next);
	if (integral(field)) next = Math.round(next);
	else if (isNumber(step) && step > 0) next = Math.round(next / step) * step;
	return Number(next.toFixed(6));
}

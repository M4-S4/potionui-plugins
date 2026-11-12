import { LIBRARY_FORMATS } from './exports.js';
import { isObject } from './values.js';

export const FINISH_EFFECTS = [
	{ key: 'fixColors', tool: 'fix_colors', fields: [{ name: 'strength', min: 0, max: 100, step: 5, value: 100 }], fixed: { white_balance: true, contrast: true } },
	{ key: 'lut', tool: 'lut', choice: 'lut', fields: [{ name: 'strength', min: 0, max: 1, step: 0.05, value: 1 }] },
	{ key: 'look', tool: 'look', choice: 'look', fields: [{ name: 'strength', min: 0, max: 1, step: 0.05, value: 1 }] },
	{
		key: 'vignette',
		tool: 'vignette',
		fields: [
			{ name: 'amount', min: 0, max: 100, step: 1, value: 40 },
			{ name: 'radius', min: 0, max: 100, step: 1, value: 50 }
		]
	},
	{
		key: 'grain',
		tool: 'film_grain',
		fields: [
			{ name: 'amount', min: 0, max: 100, step: 1, value: 30 },
			{ name: 'size', min: 1, max: 3, step: 0.1, value: 1.5 }
		]
	}
];

export const FINISH_KEYS = FINISH_EFFECTS.map((effect) => effect.key);
export const FINISHED_SUFFIX = '_finished';
export const FINISH_POLL_MS = 1000;
export const FINISH_READ_TRIES = 5;
export const MAX_FINISH_RUNS = 8;

const finite = (value) => typeof value === 'number' && Number.isFinite(value);

export const effectByKey = (key) => FINISH_EFFECTS.find((effect) => effect.key === key) ?? null;

export function toolsById(tools) {
	return new Map((tools ?? []).filter((tool) => tool?.id && tool.runnable !== false).map((tool) => [tool.id, tool]));
}

const paramOf = (tool, name) => tool?.params?.find((param) => param.name === name) ?? null;

export function fieldBounds(field, tool) {
	const param = paramOf(tool, field.name);
	const min = finite(param?.min) ? param.min : field.min;
	const max = finite(param?.max) ? param.max : field.max;
	const step = finite(param?.step) ? param.step : field.step;
	const value = finite(param?.default) && param.default >= min && param.default <= max ? param.default : field.value;
	return { min, max, step, value };
}

export function choicesOf(effect, tool) {
	if (!effect.choice) return [];
	return (paramOf(tool, effect.choice)?.options ?? []).filter((option) => option.value !== '');
}

export const finishingOf = (doc) => (isObject(doc?.master?.finishing) ? doc.master.finishing : {});

function bounded(value, { min, max, value: fallback }) {
	return finite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

export function settingOf(finishing, effect, tool) {
	const saved = isObject(finishing?.[effect.key]) ? finishing[effect.key] : {};
	const values = Object.fromEntries(effect.fields.map((field) => [field.name, bounded(saved[field.name], fieldBounds(field, tool))]));
	const setting = { on: saved.on === true, ...values };
	if (effect.choice) {
		const choices = choicesOf(effect, tool);
		const chosen = typeof saved.ref === 'string' && saved.ref ? saved.ref : null;
		const offered = chosen !== null && choices.some((option) => option.value === chosen);
		setting.ref = chosen ?? choices[0]?.value ?? '';
		setting.missing = chosen !== null && !offered;
	}
	return setting;
}

export function availability(effect, tools) {
	const tool = tools.get(effect.tool);
	if (!tool) return 'missing';
	if (effect.choice && !choicesOf(effect, tool).length) return 'empty';
	return 'ready';
}

export function finishSteps(finishing, tools) {
	const steps = [];
	for (const effect of FINISH_EFFECTS) {
		const tool = tools.get(effect.tool);
		if (!tool || availability(effect, tools) !== 'ready') continue;
		const setting = settingOf(finishing, effect, tool);
		if (!setting.on || setting.missing) continue;
		const params = { ...(effect.fixed ?? {}), ...Object.fromEntries(effect.fields.map((field) => [field.name, setting[field.name]])) };
		if (effect.choice) params[effect.choice] = setting.ref;
		steps.push({ tool: effect.tool, params });
	}
	return steps;
}

export const finishFormat = (format) => LIBRARY_FORMATS.includes(format);

export const finishable = (job) => Boolean(job && job.status === 'done' && finishFormat(job.format) && job.media?.itemId);

export function finishRequest(itemId, steps) {
	return { steps: steps.map((step) => ({ tool: step.tool, params: { ...step.params } })), inputs: [{ item_id: itemId }], output: { mode: 'new' } };
}

export function finishedName(fileName) {
	const name = String(fileName ?? '').replace(/\.[A-Za-z0-9]{2,4}$/, '') || 'video-producer';
	return `${name}${FINISHED_SUFFIX}.mp4`;
}

export function finishFailure(error) {
	if (!error) return null;
	if (error.code === 'too_many_queued') return 'busy';
	if (error.code === 'not_found') return 'gone';
	return 'failed';
}

export function cleanFinishing(value) {
	if (!isObject(value)) return null;
	const kept = {};
	for (const effect of FINISH_EFFECTS) {
		const saved = value[effect.key];
		if (!isObject(saved)) continue;
		const entry = { on: saved.on === true };
		for (const field of effect.fields) if (finite(saved[field.name])) entry[field.name] = bounded(saved[field.name], field);
		if (effect.choice && typeof saved.ref === 'string') entry.ref = saved.ref;
		kept[effect.key] = entry;
	}
	return Object.keys(kept).length ? kept : null;
}

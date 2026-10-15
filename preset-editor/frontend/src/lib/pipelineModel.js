import { SNIPPETS } from './files.js';
import { dumpYaml, parseYaml } from './yaml.js';

export const PIPE_KEYS = ['name', 'id', 'enabled', 'input', 'cache', 'configuration'];
export const CHAINS = { native: 'native-chain', cloud: 'cloud-chain' };

let counter = 0;

export function nextId() {
	counter += 1;
	return `p${counter}`;
}

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function clone(value) {
	return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

export function toPipe(data) {
	return { id: nextId(), attrs: clone(data) };
}

export function fromPipe(pipe) {
	const out = {};
	for (const [key, value] of Object.entries(pipe.attrs)) if (value !== undefined) out[key] = clone(value);
	return out;
}

export function parsePipelineDocument(text) {
	const parsed = parseYaml(text);
	if (!parsed.ok) return { ok: false, error: parsed.error };
	const data = parsed.data === null ? {} : parsed.data;
	if (!isObject(data)) return { ok: false, error: { message: 'pipeline.yml is a mapping with a pipeline: list', line: null, column: null } };
	const raw = data.pipeline === undefined || data.pipeline === null ? [] : data.pipeline;
	if (!Array.isArray(raw)) return { ok: false, error: { message: 'pipeline: is a list', line: null, column: null } };
	if (raw.some((item) => !isObject(item))) return { ok: false, error: { message: 'every entry of pipeline: is a mapping', line: null, column: null } };
	const unknown = {};
	for (const [key, value] of Object.entries(data)) if (key !== 'pipeline') unknown[key] = clone(value);
	return { ok: true, keyOrder: Object.keys(data), unknown, pipes: raw.map(toPipe) };
}

export function serializePipelineDocument(doc) {
	const out = {};
	const order = [...(doc.keyOrder ?? [])];
	for (const key of ['pipeline', ...Object.keys(doc.unknown ?? {})]) if (!order.includes(key)) order.push(key);
	for (const key of order) {
		if (key === 'pipeline') out.pipeline = doc.pipes.map(fromPipe);
		else if (key in (doc.unknown ?? {})) out[key] = clone(doc.unknown[key]);
	}
	return dumpYaml(out, { lineWidth: -1 });
}

export function pipeRef(pipe) {
	return typeof pipe.attrs.id === 'string' && pipe.attrs.id ? pipe.attrs.id : String(pipe.attrs.name ?? '');
}

export function pipeTitle(pipe) {
	const name = String(pipe.attrs.name ?? '?');
	const id = typeof pipe.attrs.id === 'string' && pipe.attrs.id && pipe.attrs.id !== name ? ` (${pipe.attrs.id})` : '';
	return `${name}${id}`;
}

export function referenceMap(reference) {
	const list = Array.isArray(reference) ? reference : Array.isArray(reference?.pipes) ? reference.pipes : [];
	return new Map(list.filter((item) => item && typeof item.name === 'string').map((item) => [item.name, item]));
}

export function isTemplated(value) {
	return typeof value === 'string' && (value.includes('{{') || value.includes('{%'));
}

function compatible(expected, actual) {
	return !expected || !actual || expected === actual || expected === 'ANY' || actual === 'ANY';
}

export function pipelineProblems(doc, reference = null) {
	const refs = referenceMap(reference);
	const byPipe = new Map();
	const add = (id, problem) => {
		if (!byPipe.has(id)) byPipe.set(id, []);
		byPipe.get(id).push(problem);
	};
	const declared = new Map();
	const names = new Map();
	for (const pipe of doc.pipes) {
		const attrs = pipe.attrs;
		const name = typeof attrs.name === 'string' ? attrs.name : '';
		if (!name) add(pipe.id, { key: 'name', message: 'required' });
		const known = refs.size && name ? refs.get(name) ?? null : null;
		if (refs.size && name && !known) add(pipe.id, { key: 'name', message: 'no pipe of this name on this instance', level: 'warning' });
		if ('id' in attrs && attrs.id !== null && (typeof attrs.id !== 'string' || !attrs.id)) add(pipe.id, { key: 'id', message: 'a non-empty string' });
		if ('enabled' in attrs && typeof attrs.enabled !== 'boolean' && typeof attrs.enabled !== 'string') add(pipe.id, { key: 'enabled', message: 'true, false or an expression' });
		const input = attrs.input;
		if (input !== undefined && input !== null) {
			if (!Array.isArray(input)) add(pipe.id, { key: 'input', message: 'a list of [input, pipe, output] triples' });
			else {
				input.forEach((entry, index) => {
					if (!Array.isArray(entry) || entry.length !== 3 || entry.some((part) => typeof part !== 'string' || !part)) {
						add(pipe.id, { key: 'input', message: `input[${index}] is [input, pipe, output]` });
						return;
					}
					const [target, source, output] = entry;
					const expected = known ? known.inputs.find((item) => item.name === target) ?? null : null;
					if (known && !expected) add(pipe.id, { key: 'input', message: `input[${index}]: ${name} has no input ${target}`, level: 'warning' });
					if (isTemplated(source) || isTemplated(output)) return;
					const sourcePipe = declared.get(source);
					if (!sourcePipe) {
						add(pipe.id, { key: 'input', message: `input[${index}]: ${source} is not declared before this pipe` });
						return;
					}
					const sourceKnown = refs.size ? refs.get(String(sourcePipe.attrs.name ?? '')) ?? null : null;
					if (!sourceKnown) return;
					const produced = sourceKnown.outputs.find((item) => item.name === output) ?? null;
					if (!produced) add(pipe.id, { key: 'input', message: `input[${index}]: ${sourcePipe.attrs.name} has no output ${output}`, level: 'warning' });
					else if (expected && !compatible(expected.io_type, produced.io_type)) {
						add(pipe.id, { key: 'input', message: `input[${index}]: ${output} is ${produced.io_type}, ${target} expects ${expected.io_type}`, level: 'warning' });
					}
				});
			}
		}
		const config = attrs.configuration;
		if (config !== undefined && config !== null && !isObject(config)) add(pipe.id, { key: 'configuration', message: 'a mapping' });
		else if (known) {
			const specs = Array.isArray(known.configuration) ? known.configuration : [];
			const declaredKeys = new Set(specs.map((spec) => spec.name));
			for (const key of Object.keys(config ?? {})) {
				if (!declaredKeys.has(key)) add(pipe.id, { key: 'configuration', message: `configuration.${key} is not declared for ${name}`, level: 'warning' });
			}
			for (const spec of specs) {
				if (spec.required && !(spec.name in (config ?? {})) && (spec.default === null || spec.default === undefined)) {
					add(pipe.id, { key: 'configuration', message: `configuration.${spec.name} is required`, level: 'warning' });
				}
			}
		}
		for (const key of Object.keys(attrs)) {
			if (!PIPE_KEYS.includes(key)) add(pipe.id, { key, message: 'unknown key (the core refuses it)' });
		}
		if (name) {
			const count = (names.get(name) ?? 0) + 1;
			names.set(name, count);
			if (typeof attrs.id === 'string' && attrs.id) {
				if (declared.has(attrs.id)) add(pipe.id, { key: 'id', message: `${attrs.id} is already used by an earlier pipe` });
				declared.set(attrs.id, pipe);
			} else if (count > 1) add(pipe.id, { key: 'id', message: `${name} appears more than once: give each instance an id` });
			if (!declared.has(name)) declared.set(name, pipe);
		}
	}
	const count = [...byPipe.values()].reduce((sum, list) => sum + list.filter((item) => item.level !== 'warning').length, 0);
	return { byPipe, count };
}

export function newPipe(name, reference = null) {
	const known = referenceMap(reference).get(name) ?? null;
	const attrs = { name, enabled: true };
	if (known) {
		const required = (known.configuration ?? []).filter((spec) => spec.required);
		if (required.length) attrs.configuration = Object.fromEntries(required.map((spec) => [spec.name, spec.default ?? '']));
	}
	return { id: nextId(), attrs };
}

export function insertPipe(doc, pipe, index = null) {
	const at = index === null || index === undefined ? doc.pipes.length : Math.max(0, Math.min(index, doc.pipes.length));
	doc.pipes.splice(at, 0, pipe);
	return pipe;
}

export function removePipe(doc, id) {
	const index = doc.pipes.findIndex((pipe) => pipe.id === id);
	if (index < 0) return null;
	return doc.pipes.splice(index, 1)[0];
}

export function movePipe(doc, id, delta) {
	const index = doc.pipes.findIndex((pipe) => pipe.id === id);
	const target = index + delta;
	if (index < 0 || target < 0 || target >= doc.pipes.length) return false;
	const [pipe] = doc.pipes.splice(index, 1);
	doc.pipes.splice(target, 0, pipe);
	return true;
}

export function startChain(kind, { family = 'sdxl' } = {}) {
	const snippet = SNIPPETS.find((item) => item.id === CHAINS[kind]);
	if (!snippet) return [];
	const parsed = parsePipelineDocument(snippet.build().replaceAll('<family>', family));
	return parsed.ok ? parsed.pipes : [];
}

export function sourcesBefore(doc, id) {
	const options = [];
	for (const pipe of doc.pipes) {
		if (pipe.id === id) break;
		options.push({ ref: pipeRef(pipe), name: String(pipe.attrs.name ?? ''), pipe });
	}
	return options;
}

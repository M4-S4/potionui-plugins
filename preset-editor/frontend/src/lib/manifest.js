import { CATEGORIES, DRIVER_RE, ENGINE_RE, MAX_NAME_LENGTH } from './drafts.js';
import { commentLines, dumpYaml, parseYaml, replaceTopLevelBlock, topLevelBlockSpan } from './yaml.js';

export const READ_ONLY_KEYS = ['schema', 'id'];
export const FIELD_KEYS = ['name', 'version', 'category', 'engine', 'driver', 'tags'];
export const MANAGED_KEYS = ['modes', 'media'];
export const SECTION_KEYS = ['vars', 'configuration', 'llm', 'speed_profiles', 'formulas', 'requires', 'requirements', 'prompt_resources', 'prompt_syntax', 'negative_prompt'];
export const LIST_SECTIONS = ['requirements'];
export const SEMVER_RE = /^\d+\.\d+\.\d+(?:[-+].+)?$/;
export const SECTION_HINTS = {
	vars: 'Values every pipeline.yml of the preset can read as {{ vars.<name> }}',
	configuration: 'Admin-set knobs (model tags, …) edited in Admin → Presets → Configuration',
	llm: 'Prompting guide and chat-workspace context',
	speed_profiles: 'Named generation profiles (draft, standard, max, …)',
	formulas: 'Formula groups',
	requires: 'Hardware guidance shown before the model download',
	requirements: 'Checkable requirements evaluated live on this instance (a list)',
	prompt_resources: 'Prompt resources (LoRAs, embeddings, …) by kind',
	prompt_syntax: 'Prompt syntax highlights',
	negative_prompt: 'When the negative prompt applies'
};

const KNOWN = new Set([...READ_ONLY_KEYS, ...FIELD_KEYS, ...MANAGED_KEYS, ...SECTION_KEYS]);

function text(value) {
	return value === null || value === undefined ? '' : String(value);
}

function present(value) {
	return value !== null && value !== undefined;
}

function same(a, b) {
	return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

export function manifestForm(source) {
	const parsed = parseYaml(source);
	if (!parsed.ok) return { ok: false, error: parsed.error };
	const data = parsed.data;
	if (!data || typeof data !== 'object' || Array.isArray(data)) {
		return { ok: false, error: { message: 'preset.yml is not a mapping of keys', line: null, column: null } };
	}
	const fields = {
		name: text(data.name),
		version: text(data.version),
		category: text(data.category),
		engine: text(data.engine),
		driver: text(data.driver),
		tags: Array.isArray(data.tags) ? data.tags.map(text).join(', ') : ''
	};
	const sections = {};
	for (const key of SECTION_KEYS) sections[key] = present(data[key]) ? dumpYaml(data[key]).trimEnd() : '';
	return {
		ok: true,
		fields,
		sections,
		readOnly: { schema: text(data.schema), id: text(data.id) },
		modes: Array.isArray(data.modes) ? data.modes.map(text) : [],
		unknownKeys: Object.keys(data).filter((key) => !KNOWN.has(key)),
		data
	};
}

export function fieldValues(fields) {
	const engine = text(fields.engine).trim();
	const driver = text(fields.driver).trim();
	const tags = [...new Set(text(fields.tags).split(',').map((tag) => tag.trim()).filter(Boolean))];
	return { name: text(fields.name).trim(), version: text(fields.version).trim(), category: text(fields.category).trim(), engine, driver: driver || null, tags };
}

export function fieldProblems(fields) {
	const values = fieldValues(fields);
	const problems = {};
	if (!values.name) problems.name = 'required';
	else if (values.name.length > MAX_NAME_LENGTH) problems.name = `at most ${MAX_NAME_LENGTH} characters`;
	if (!SEMVER_RE.test(values.version)) problems.version = 'a semver string such as 1.0.0';
	if (!CATEGORIES.includes(values.category)) problems.category = `one of ${CATEGORIES.join(', ')}`;
	if (!ENGINE_RE.test(values.engine)) problems.engine = 'lowercase letters, digits and _';
	if (values.driver && (!DRIVER_RE.test(values.driver) || !values.driver.startsWith(`${values.engine}.`))) {
		problems.driver = `<engine>.<name>, starting with ${values.engine || '<engine>'}.`;
	} else if (!values.driver && values.engine === 'cloud') problems.driver = 'required when the engine is cloud (e.g. cloud.openrouter)';
	return problems;
}

export function sectionValue(key, source) {
	const trimmed = text(source).trim();
	if (!trimmed) return { ok: true, value: null };
	const parsed = parseYaml(trimmed);
	if (!parsed.ok) return { ok: false, problem: `line ${parsed.error.line ?? '?'}: ${parsed.error.message}` };
	if (parsed.data === null) return { ok: true, value: null };
	const wantsList = LIST_SECTIONS.includes(key);
	if (wantsList && !Array.isArray(parsed.data)) return { ok: false, problem: 'a YAML list' };
	if (!wantsList && (typeof parsed.data !== 'object' || Array.isArray(parsed.data))) return { ok: false, problem: 'a YAML mapping' };
	return { ok: true, value: parsed.data };
}

export function sectionProblems(sections) {
	const problems = {};
	for (const key of SECTION_KEYS) {
		const checked = sectionValue(key, sections?.[key]);
		if (!checked.ok) problems[key] = checked.problem;
	}
	return problems;
}

function currentField(data, key) {
	if (key === 'tags') return Array.isArray(data.tags) ? data.tags.map(text) : [];
	return present(data[key]) ? text(data[key]) : null;
}

export function applyManifestForm(source, { fields, sections }, original) {
	const problems = { ...fieldProblems(fields) };
	for (const [key, problem] of Object.entries(sectionProblems(sections))) problems[key] = problem;
	if (Object.keys(problems).length) return { ok: false, problems };
	const values = fieldValues(fields);
	const replacements = [];
	for (const key of FIELD_KEYS) {
		const next = values[key];
		if (same(currentField(original.data, key), next)) continue;
		const absent = next === null || (key === 'tags' && next.length === 0 && !('tags' in original.data));
		replacements.push({ key, block: absent ? null : dumpYaml({ [key]: next }, { forceQuotes: true }).trimEnd() });
	}
	for (const key of SECTION_KEYS) {
		if ((original.sections[key] ?? '') === text(sections[key]).trimEnd()) continue;
		const { value } = sectionValue(key, sections[key]);
		replacements.push({ key, block: value === null ? null : dumpYaml({ [key]: value }).trimEnd() });
	}
	const lostComments = [];
	for (const { key } of replacements) {
		const span = topLevelBlockSpan(source, key);
		if (!span) continue;
		const offset = source.slice(0, span.start).split('\n').length - 1;
		for (const line of commentLines(source.slice(span.start, span.end))) lostComments.push(offset + line);
	}
	let result = source;
	for (const { key, block } of replacements) result = replaceTopLevelBlock(result, key, block);
	return { ok: true, text: result, changed: replacements.map((item) => item.key), lostComments: lostComments.sort((a, b) => a - b) };
}

export function formSnapshot(form) {
	return JSON.stringify({ fields: form.fields, sections: form.sections });
}

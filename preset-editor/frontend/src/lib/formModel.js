import { dumpYaml, parseYaml } from './yaml.js';

export const FORM_META_KEYS = ['name', 'label', 'description', 'short_description', 'mode_label', 'mode_icon', 'prompt', 'prompt_label', 'prompt_placeholder', 'llm_guide', 'examples', 'default', 'order'];
export const FORM_RAW_KEYS = ['negative_prompt', 'requirements', 'segment_templates'];
export const PROMPT_REQUIREMENTS = ['required', 'optional', 'none'];
export const FIELD_FORM_KEYS = ['type', 'name', 'label', 'description', 'ai_hint', 'formula', 'default', 'required', 'audience', 'width', 'full_width', 'visible', 'interactive', 'save_into', 'configuration'];
export const FIELD_RAW_KEYS = ['when', 'reactions', 'listeners', 'capability', 'merge_from', 'input', 'container', 'hidden_when_video_director'];
export const FIELD_KEYS = [...FIELD_FORM_KEYS, ...FIELD_RAW_KEYS, 'children'];
export const CONTAINER_TYPES = ['tabs', 'tab', 'row', 'group', 'accordion', 'section'];
export const PRESET_PATH_PREFIX = '{{ paths.preset }}/';
export const SHARED_PATH_PREFIX = '{{ paths._shared }}/';

let counter = 0;

export function nextId() {
	counter += 1;
	return `f${counter}`;
}

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function clone(value) {
	return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

export function toNode(data) {
	const attrs = {};
	let children = null;
	for (const [key, value] of Object.entries(data)) {
		if (key === 'children') children = Array.isArray(value) ? value.map((child) => toNode(isObject(child) ? child : { type: 'invalid', value: child })) : clone(value);
		else attrs[key] = clone(value);
	}
	return { id: nextId(), attrs, children };
}

export function fromNode(node) {
	const out = {};
	for (const [key, value] of Object.entries(node.attrs)) {
		if (key !== 'children' && value !== undefined) out[key] = clone(value);
	}
	if (node.children !== null && node.children !== undefined) {
		out.children = Array.isArray(node.children) ? node.children.map(fromNode) : clone(node.children);
	}
	return out;
}

export function parseFormDocument(text, { kind = 'form' } = {}) {
	const parsed = parseYaml(text);
	if (!parsed.ok) return { ok: false, error: parsed.error };
	const data = parsed.data === null ? {} : parsed.data;
	if (Array.isArray(data)) return { ok: false, error: { message: 'this file is an option list, not a fields: tree: edit it in the YAML view', line: null, column: null } };
	if (!isObject(data)) return { ok: false, error: { message: `${kind === 'tab' ? 'a fields fragment' : 'form.yml'} is a mapping with a fields: list`, line: null, column: null } };
	const rawFields = data.fields === undefined || data.fields === null ? [] : data.fields;
	if (!Array.isArray(rawFields)) return { ok: false, error: { message: 'fields: is a list', line: null, column: null } };
	if (rawFields.some((item) => !isObject(item))) return { ok: false, error: { message: 'every entry of fields: is a mapping', line: null, column: null } };
	const meta = {};
	const raw = {};
	const unknown = {};
	for (const [key, value] of Object.entries(data)) {
		if (key === 'fields') continue;
		if (FORM_META_KEYS.includes(key)) meta[key] = clone(value);
		else if (FORM_RAW_KEYS.includes(key)) raw[key] = value === null || value === undefined ? '' : dumpYaml(value, { lineWidth: -1 }).trimEnd();
		else unknown[key] = clone(value);
	}
	return { ok: true, kind, keyOrder: Object.keys(data), hasFields: 'fields' in data, meta, raw, unknown, fields: rawFields.map(toNode) };
}

export function serializeFormDocument(doc) {
	const out = {};
	const place = (key) => {
		if (key === 'fields') {
			out.fields = doc.fields.map(fromNode);
			return;
		}
		if (FORM_META_KEYS.includes(key)) {
			const value = doc.meta[key];
			if (value !== undefined && value !== null && value !== '') out[key] = clone(value);
			return;
		}
		if (FORM_RAW_KEYS.includes(key)) {
			const parsed = parseYaml(doc.raw[key] ?? '');
			if (parsed.ok && parsed.data !== null) out[key] = parsed.data;
			return;
		}
		if (key in doc.unknown) out[key] = clone(doc.unknown[key]);
	};
	const order = [...(doc.keyOrder ?? [])];
	for (const key of [...FORM_META_KEYS, 'fields', ...FORM_RAW_KEYS, ...Object.keys(doc.unknown ?? {})]) {
		if (!order.includes(key)) order.push(key);
	}
	for (const key of order) place(key);
	return dumpYaml(out, { lineWidth: -1 });
}

export function metaProblems(meta) {
	const problems = {};
	if (meta.name !== undefined && meta.name !== null && meta.name !== '' && !/^[A-Za-z0-9_-]+$/.test(String(meta.name))) problems.name = 'letters, digits, _ and -';
	if (meta.order !== undefined && meta.order !== null && meta.order !== '' && !Number.isInteger(Number(meta.order))) problems.order = 'an integer';
	if (meta.prompt !== undefined && meta.prompt !== null && meta.prompt !== '' && !PROMPT_REQUIREMENTS.includes(meta.prompt)) problems.prompt = 'required, optional or none';
	for (const key of ['prompt_label', 'prompt_placeholder']) {
		if (meta[key] !== undefined && meta[key] !== null && (typeof meta[key] !== 'string' || !meta[key].trim())) problems[key] = 'a text, or nothing';
	}
	if (meta.examples !== undefined && meta.examples !== null) {
		const examples = Array.isArray(meta.examples) ? meta.examples : [meta.examples];
		if (examples.some((item) => typeof item !== 'string' || !item.startsWith('public/'))) problems.examples = 'paths under public/';
	}
	return problems;
}

export function walk(nodes, visit, parent = null) {
	for (let index = 0; index < nodes.length; index += 1) {
		const node = nodes[index];
		if (visit(node, parent, index) === false) return false;
		if (Array.isArray(node.children) && walk(node.children, visit, node) === false) return false;
	}
	return true;
}

export function findNode(nodes, id) {
	let found = null;
	walk(nodes, (node, parent, index) => {
		if (node.id === id) {
			found = { node, parent, index, siblings: parent ? parent.children : nodes };
			return false;
		}
		return true;
	});
	return found;
}

export function removeNode(nodes, id) {
	const found = findNode(nodes, id);
	if (!found) return null;
	found.siblings.splice(found.index, 1);
	return found.node;
}

export function insertNode(nodes, node, { parentId = null, index = null } = {}) {
	let siblings = nodes;
	if (parentId) {
		const found = findNode(nodes, parentId);
		if (!found) return false;
		if (!Array.isArray(found.node.children)) found.node.children = [];
		siblings = found.node.children;
	}
	const at = index === null || index === undefined ? siblings.length : Math.max(0, Math.min(index, siblings.length));
	siblings.splice(at, 0, node);
	return true;
}

export function moveNode(nodes, id, { parentId = null, index = 0 } = {}) {
	const found = findNode(nodes, id);
	if (!found) return false;
	if (parentId) {
		const target = findNode(nodes, parentId);
		if (!target || target.node === found.node) return false;
		let cursor = target.parent;
		while (cursor) {
			if (cursor === found.node) return false;
			cursor = findNode(nodes, cursor.id)?.parent ?? null;
		}
	}
	const node = removeNode(nodes, id);
	return insertNode(nodes, node, { parentId, index });
}

export function fieldNames(nodes) {
	const names = [];
	walk(nodes, (node) => {
		if (typeof node.attrs.name === 'string' && node.attrs.name) names.push(node.attrs.name);
	});
	return names;
}

export function duplicateNames(nodes) {
	const seen = new Map();
	for (const name of fieldNames(nodes)) seen.set(name, (seen.get(name) ?? 0) + 1);
	return [...seen.entries()].filter(([, count]) => count > 1).map(([name]) => name);
}

export function nodeTitle(node) {
	const type = String(node.attrs.type ?? '?');
	const name = typeof node.attrs.name === 'string' && node.attrs.name ? node.attrs.name : '';
	const label = typeof node.attrs.label === 'string' && node.attrs.label ? node.attrs.label : '';
	return name ? `${name} · ${type}` : label ? `${label} · ${type}` : type;
}

export function isContainerType(type) {
	return CONTAINER_TYPES.includes(type);
}

export function isChildrenInclude(children) {
	return typeof children === 'string' || (isObject(children) && typeof children.file === 'string');
}

export function externalChildrenPath(node) {
	if (!isChildrenInclude(node.children)) return null;
	const file = typeof node.children === 'string' ? node.children : node.children.file;
	const vars = isObject(node.children) && isObject(node.children.vars) ? node.children.vars : null;
	const value = file.trim();
	if (value.startsWith(PRESET_PATH_PREFIX)) return { scope: 'preset', path: value.slice(PRESET_PATH_PREFIX.length), file, vars };
	if (value.startsWith(SHARED_PATH_PREFIX)) return { scope: 'shared', path: value.slice(SHARED_PATH_PREFIX.length), file, vars };
	return { scope: 'other', path: value, file, vars };
}

export function withIncludeVars(children, vars) {
	const file = typeof children === 'string' ? children : children.file;
	return vars && Object.keys(vars).length ? { file, vars } : file;
}

export function newField(type, { name = '', label = '' } = {}) {
	const attrs = {};
	if (name) attrs.name = name;
	attrs.type = type;
	if (label) attrs.label = label;
	return { id: nextId(), attrs, children: isContainerType(type) ? [] : null };
}

export function newTabReference(mode, tab, label) {
	const node = newField('tab', { label });
	node.children = `${PRESET_PATH_PREFIX}modes/${mode}/tabs/${tab}.yml`;
	return node;
}

export function cloneNode(node) {
	return toNode(fromNode(node));
}

export function orderedAttrs(attrs) {
	const keys = Object.keys(attrs);
	const known = FIELD_KEYS.filter((key) => keys.includes(key));
	const unknown = keys.filter((key) => !FIELD_KEYS.includes(key));
	return [...known, ...unknown];
}

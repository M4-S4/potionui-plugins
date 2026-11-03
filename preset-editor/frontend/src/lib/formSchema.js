import * as z from 'zod/mini';
import { CONTAINER_TYPES, FIELD_KEYS, duplicateNames, walk } from './formModel.js';

export const AUDIENCES = ['simple', 'advanced'];
export const SAVE_INTO = ['session', 'settings'];
export const BOOL_TYPES = ['checkbox', 'boolean'];
export const NUMERIC_TYPES = ['slider', 'number', 'seed', 'stepper'];
export const INTEGER_TYPES = ['integer'];
export const SCALAR_TYPES = ['select'];
export const STRING_TYPES = ['string', 'textbox'];
export const WIDTH_RE = /^\d+(?:\.\d+)?\/\d+(?:\.\d+)?$/;
export const INCLUDE_VAR_RE = /\{\{\s*vars\.\w+\s*\}\}/g;

const maybe = (schema) => z.optional(z.nullable(schema));
const optionalString = maybe(z.string());
const optionalBoolean = maybe(z.boolean());
const fraction = z.string().check(
	z.regex(WIDTH_RE, "a positive number or an 'a/b' fraction"),
	z.refine((value) => value.split('/').every((part) => Number(part) > 0), 'a and b are positive')
);
const widthSchema = maybe(z.union([z.number().check(z.positive()), fraction]));

export const fieldSchema = z.strictObject({
	type: z.string().check(z.minLength(1, 'required')),
	name: optionalString,
	label: optionalString,
	description: optionalString,
	ai_hint: optionalString,
	formula: maybe(z.union([z.string(), z.literal(false)])),
	default: z.optional(z.unknown()),
	required: optionalBoolean,
	audience: z.optional(z.enum(AUDIENCES)),
	width: widthSchema,
	full_width: z.optional(z.boolean()),
	visible: optionalBoolean,
	interactive: optionalBoolean,
	save_into: maybe(z.enum(SAVE_INTO)),
	configuration: maybe(z.record(z.string(), z.unknown())),
	when: z.optional(z.unknown()),
	reactions: maybe(z.array(z.unknown())),
	listeners: z.optional(z.unknown()),
	capability: maybe(z.record(z.string(), z.unknown())),
	merge_from: maybe(z.array(z.string().check(z.minLength(1)))),
	input: maybe(z.array(z.array(z.unknown()))),
	container: optionalBoolean,
	hidden_when_video_director: optionalBoolean,
	children: maybe(z.union([z.array(z.unknown()), z.string(), z.strictObject({ file: z.string().check(z.minLength(1)), vars: z.optional(z.nullable(z.record(z.string(), z.union([z.string(), z.number(), z.boolean()])))) })]))
});

export function isIncludeVar(value) {
	return typeof value === 'string' && value.includes('{{') && !value.replace(INCLUDE_VAR_RE, '').includes('{{');
}

export function defaultProblem(type, value, { allowVars = false } = {}) {
	if (value === null || value === undefined) return null;
	if (allowVars && isIncludeVar(value)) return null;
	if (typeof value === 'string' && value.includes('{{')) return 'default is never rendered: use a plain value, and reactions for dynamic behaviour';
	if (BOOL_TYPES.includes(type) && typeof value !== 'boolean') return `default of a ${type} field is true or false`;
	if (NUMERIC_TYPES.includes(type) && (typeof value !== 'number' || Number.isNaN(value))) return `default of a ${type} field is a number`;
	if (INTEGER_TYPES.includes(type) && !Number.isInteger(value)) return 'default of an integer field is an integer';
	if (SCALAR_TYPES.includes(type) && (Array.isArray(value) || (typeof value === 'object' && value !== null))) return `default of a ${type} field is a scalar`;
	if (STRING_TYPES.includes(type) && typeof value !== 'string') return `default of a ${type} field is a string`;
	return null;
}

export function fieldProblems(attrs, { types = null, allowVars = false, formulaGroups = null } = {}) {
	const problems = [];
	const checked = fieldSchema.safeParse(attrs);
	if (!checked.success) {
		for (const issue of checked.error.issues) {
			const key = issue.path.length ? String(issue.path[0]) : '';
			if (issue.code === 'unrecognized_keys' && !issue.path.length) {
				for (const unknown of issue.keys) problems.push({ key: unknown, message: 'unknown attribute (the core refuses it)' });
			} else if (issue.code === 'unrecognized_keys') problems.push({ key, message: `unknown key ${issue.keys.join(', ')} (the core refuses it)` });
			else problems.push({ key, message: issue.message });
		}
	}
	const type = typeof attrs.type === 'string' ? attrs.type : '';
	if (type && Array.isArray(types) && types.length && !types.includes(type)) problems.push({ key: 'type', message: 'no field type of this name on this instance' });
	const defaultIssue = defaultProblem(type, attrs.default, { allowVars });
	if (defaultIssue) problems.push({ key: 'default', message: defaultIssue });
	if (Array.isArray(formulaGroups) && typeof attrs.formula === 'string' && attrs.formula && !formulaGroups.includes(attrs.formula)) {
		problems.push({ key: 'formula', message: `${attrs.formula} is not declared in preset.yml formulas.groups: the lint refuses it`, level: 'warning' });
	}
	if (Array.isArray(attrs.merge_from)) {
		if (attrs.merge_from.includes(attrs.name)) problems.push({ key: 'merge_from', message: 'cannot list the field itself' });
		if (new Set(attrs.merge_from).size !== attrs.merge_from.length) problems.push({ key: 'merge_from', message: 'lists a key twice' });
	}
	return problems;
}

export function treeProblems(fields, { types = null, kind = 'form', configKeys = null, formulaGroups = null } = {}) {
	const byNode = new Map();
	const general = [];
	const add = (id, problem) => {
		if (!byNode.has(id)) byNode.set(id, []);
		byNode.get(id).push(problem);
	};
	walk(fields, (node, parent, index) => {
		for (const problem of fieldProblems(node.attrs, { types, allowVars: kind !== 'form', formulaGroups })) add(node.id, problem);
		const type = node.attrs.type;
		if (kind === 'form' && !parent && !node.attrs.name && type !== 'tabs') {
			add(node.id, { key: 'name', message: `fields[${index}] will not appear in the form: give it a name or put it inside a tab` });
		}
		if (configKeys && typeof type === 'string' && configKeys[type] && node.attrs.configuration && typeof node.attrs.configuration === 'object') {
			for (const key of Object.keys(node.attrs.configuration)) {
				if (!configKeys[type].includes(key)) add(node.id, { key: 'configuration', message: `configuration.${key} is not declared for ${type} (lint warning)`, level: 'warning' });
			}
		}
		if (Array.isArray(node.children) && node.children.length === 0 && CONTAINER_TYPES.includes(type)) {
			add(node.id, { key: 'children', message: 'empty container', level: 'warning' });
		}
	});
	for (const name of duplicateNames(fields)) general.push({ key: 'name', message: `the name ${name} is used more than once` });
	return { byNode, general, count: [...byNode.values()].reduce((sum, list) => sum + list.filter((item) => item.level !== 'warning').length, 0) + general.length };
}

export function knownKeys() {
	return [...FIELD_KEYS];
}

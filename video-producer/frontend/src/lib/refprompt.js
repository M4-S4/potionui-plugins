import { isObject } from './values.js';

export const LAYOUTS = {
	refs: ['subject_definitions', 'retention_analysis', 'citations'],
	subjects: ['subject_definitions'],
	cast: ['cast'],
	sheet: ['sheet', 'cast']
};

const isLayout = (value) => typeof value === 'string' && Object.hasOwn(LAYOUTS, value);

function picked(layout, parts) {
	const source = isObject(parts) ? parts : {};
	return Object.fromEntries(LAYOUTS[layout].filter((name) => typeof source[name] === 'string').map((name) => [name, source[name]]));
}

export function migrateReferencePrompt(value) {
	if (!isObject(value) || !isLayout(value.layout) || !isObject(value.parts)) return null;
	return { layout: value.layout, parts: picked(value.layout, value.parts), base: picked(value.layout, value.base) };
}

export const referencePromptOf = (clip) => migrateReferencePrompt(clip?.referencePrompt);

export function setReferencePrompt(clip, value) {
	const next = migrateReferencePrompt(value);
	if (next) clip.referencePrompt = next;
	else delete clip.referencePrompt;
}

export function sameReferencePrompt(a, b) {
	const x = migrateReferencePrompt(a);
	const y = migrateReferencePrompt(b);
	if (!x || !y) return !x && !y;
	return x.layout === y.layout && LAYOUTS[x.layout].every((name) => (x.parts[name] ?? '') === (y.parts[name] ?? ''));
}

export function replacement(reference) {
	if (!reference || !isLayout(reference.layout)) return null;
	const composed = picked(reference.layout, reference.composed);
	return { layout: reference.layout, parts: { ...composed }, base: { ...composed } };
}

export function acknowledged(value, reference) {
	const current = migrateReferencePrompt(value);
	return current && reference?.layout === current.layout ? { ...current, base: picked(current.layout, reference.composed) } : current;
}

export function withPart(value, name, text) {
	const current = migrateReferencePrompt(value);
	return current ? { ...current, parts: { ...current.parts, [name]: text } } : null;
}

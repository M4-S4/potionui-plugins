import { isObject } from './values.js';

export const LANGUAGES = ['English', 'French', 'Spanish', 'German', 'Italian', 'Portuguese', 'Russian', 'Arabic', 'Chinese', 'Japanese', 'Korean'];
export const DEFAULT_LANGUAGE = 'English';
export const WORDS_PER_SECOND = 3;

const isId = (value) => typeof value === 'string' && value.length > 0;

export function migrateLine(line) {
	if (!isObject(line) || !isId(line.id)) return null;
	const next = { id: line.id, speaker: isId(line.speaker) ? line.speaker : null, text: typeof line.text === 'string' ? line.text : '' };
	if (line.offscreen === true) next.offscreen = true;
	return next;
}

export function migrateDialogue(lines) {
	if (!Array.isArray(lines)) return null;
	const seen = new Set();
	const next = [];
	for (const line of lines) {
		const kept = migrateLine(line);
		if (kept && !seen.has(kept.id)) {
			seen.add(kept.id);
			next.push(kept);
		}
	}
	return next.length ? next : null;
}

export const linesOf = (clip) => migrateDialogue(clip?.dialogue) ?? [];

export function setDialogue(clip, lines) {
	const next = migrateDialogue(lines);
	if (next) clip.dialogue = next;
	else delete clip.dialogue;
}

const spokenKey = (lines) => JSON.stringify((migrateDialogue(lines) ?? []).map((l) => [l.speaker, l.text.trim(), Boolean(l.offscreen)]));

export const sameDialogue = (a, b) => spokenKey(a) === spokenKey(b);

export const newLine = (id, speaker = null) => ({ id, speaker, text: '' });

export const spokenWords = (lines) => (Array.isArray(lines) ? lines : []).reduce((sum, l) => sum + (typeof l?.text === 'string' ? l.text.split(/\s+/).filter(Boolean).length : 0), 0);

export const wordLimit = (seconds) => Math.floor((Number(seconds) || 0) * WORDS_PER_SECOND);

export function nextSpeaker(lines, cast) {
	const last = lines.at(-1)?.speaker ?? null;
	return cast.find((id) => id !== last) ?? cast[0] ?? null;
}

export const spokenLanguage = (doc, card) => (isId(card?.language) ? card.language : isId(doc?.dialogueLanguage) ? doc.dialogueLanguage : DEFAULT_LANGUAGE);

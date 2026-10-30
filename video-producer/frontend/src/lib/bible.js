import { isObject } from './values.js';

export const CHARACTERS = 'characters';
export const PLACES = 'places';
export const KINDS = [CHARACTERS, PLACES];
export const SPACES = { [CHARACTERS]: 'identite', [PLACES]: 'decors3d' };
export const LABEL_MAX = 60;
export const VOICE_SPACE = 'son';

const isId = (value) => typeof value === 'string' && value.length > 0;
const words = (value) => (typeof value === 'string' ? value : '');
const idList = (list) => [...new Set((Array.isArray(list) ? list : []).filter(isId))];
const clean = (value) => words(value).split(/\s+/).filter(Boolean).join(' ');

export const emptyBible = () => ({ [CHARACTERS]: [], [PLACES]: [] });

export function newCard(kind, id, extra = {}) {
	const card = { id, label: '', text: '', references: [], ...extra };
	return kind === CHARACTERS ? { props: '', ...card } : card;
}

function migrateCard(card, kind) {
	if (!isObject(card) || !isId(card.id)) return null;
	const next = { id: card.id, label: words(card.label), text: words(card.text), references: idList(card.references) };
	if (kind !== CHARACTERS) return next;
	const character = { ...next, props: words(card.props) };
	if (typeof card.voice === 'string' && card.voice) character.voice = card.voice;
	if (isId(card.language)) character.language = card.language;
	if (isId(card.voiceRef)) character.voiceRef = card.voiceRef;
	return character;
}

export function setVoice(card, field, value) {
	if (typeof value === 'string' && value) card[field] = value;
	else delete card[field];
}

export const voiceReferences = (doc) => new Set(cardsOf(doc, CHARACTERS).map((card) => card.voiceRef).filter(isId));

export const voiceChoices = (doc) => (doc?.references ?? []).filter((r) => r.space === VOICE_SPACE);

export function migrateBible(bible) {
	const source = isObject(bible) ? bible : {};
	const next = emptyBible();
	for (const kind of KINDS) {
		const seen = new Set();
		for (const card of Array.isArray(source[kind]) ? source[kind] : []) {
			const kept = migrateCard(card, kind);
			if (kept && !seen.has(kept.id)) {
				seen.add(kept.id);
				next[kind].push(kept);
			}
		}
	}
	return next;
}

export function migrateCast(cast) {
	if (!isObject(cast)) return null;
	const next = {};
	const characters = idList(cast.characters);
	if (characters.length) next.characters = characters;
	if (isId(cast.place)) next.place = cast.place;
	return Object.keys(next).length ? next : null;
}

export function castOf(clip) {
	const cast = migrateCast(clip?.cast);
	return { characters: cast?.characters ?? [], place: cast?.place ?? null };
}

export function setCast(clip, cast) {
	const next = migrateCast(cast);
	if (next) clip.cast = next;
	else delete clip.cast;
}

const castKey = (cast) => {
	const { characters, place } = castOf({ cast });
	return `${place ?? ''}|${[...characters].sort().join(',')}`;
};

export const sameCast = (a, b) => castKey(a) === castKey(b);

export const cardsOf = (doc, kind) => (Array.isArray(doc?.bible?.[kind]) ? doc.bible[kind] : []);
export const cardLabel = (card) => clean(card?.label);
export const usable = (card) => cardLabel(card).length > 0;

export function castCards(doc, cast) {
	const { characters, place } = castOf({ cast });
	return {
		characters: cardsOf(doc, CHARACTERS).filter((card) => usable(card) && characters.includes(card.id)),
		place: cardsOf(doc, PLACES).find((card) => usable(card) && card.id === place) ?? null
	};
}

export function castLabels(doc, clip) {
	const { characters, place } = castCards(doc, clip?.cast);
	return [...characters, ...(place ? [place] : [])].map(cardLabel);
}

export function shotsCasting(doc, kind, id) {
	return (doc?.clips ?? []).filter((clip) => {
		const cast = castOf(clip);
		return kind === CHARACTERS ? cast.characters.includes(id) : cast.place === id;
	});
}

export function addCard(doc, kind, card) {
	if (!isObject(doc.bible)) doc.bible = emptyBible();
	doc.bible[kind].push(card);
	return card;
}

export function removeCard(doc, kind, id) {
	const list = cardsOf(doc, kind);
	const i = list.findIndex((card) => card.id === id);
	if (i < 0) return false;
	list.splice(i, 1);
	for (const clip of doc.clips ?? []) {
		if (kind === CHARACTERS) for (const line of Array.isArray(clip.dialogue) ? clip.dialogue : []) if (line?.speaker === id) line.speaker = null;
		const cast = castOf(clip);
		if (kind === CHARACTERS) cast.characters = cast.characters.filter((x) => x !== id);
		else if (cast.place === id) cast.place = null;
		if ('cast' in clip) setCast(clip, cast);
	}
	return true;
}

export function linkable(doc, kind) {
	return (doc?.references ?? []).filter((r) => r.space === SPACES[kind]);
}

export function folded(value) {
	return clean(words(value).toLowerCase().normalize('NFKD').replace(/\p{M}/gu, ''));
}

export function names(value, label) {
	const wanted = folded(label);
	if (!wanted) return false;
	const escaped = wanted.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
	return new RegExp(`(?<![\\p{L}\\p{N}_])${escaped}(?![\\p{L}\\p{N}_])`, 'u').test(folded(value));
}

export function missingLabels(instruction, characters) {
	return characters.filter((card) => !names(instruction, card.label)).map(cardLabel);
}

export function instructionPromptOf(doc, clip) {
	const prompts = Array.isArray(doc?.prompts) ? doc.prompts : [];
	const own = prompts.find((p) => p.shotId === clip?.id);
	if (own) return own;
	const start = Number(clip?.start) || 0;
	const end = start + (Number(clip?.dur) || 0);
	let best = null;
	let most = 0;
	for (const p of prompts) {
		const overlap = Math.min(end, (Number(p.start) || 0) + (Number(p.dur) || 0)) - Math.max(start, Number(p.start) || 0);
		if (!p.shotId && overlap > most) {
			best = p;
			most = overlap;
		}
	}
	return best;
}

export function instructionOf(doc, clip) {
	return words(instructionPromptOf(doc, clip)?.text).trim();
}

export function suggestedLabel(value) {
	const head = clean(value).split(/[.,;:!?\n]/)[0].trim();
	return head.length > LABEL_MAX ? `${head.slice(0, LABEL_MAX - 1).trim()}…` : head;
}

export function convertDirection(doc, id) {
	const free = words(doc?.direction?.personnages).trim();
	if (!free) return null;
	const card = addCard(doc, CHARACTERS, newCard(CHARACTERS, id, { label: suggestedLabel(free), text: free }));
	for (const clip of doc.clips ?? []) {
		const cast = castOf(clip);
		setCast(clip, { ...cast, characters: [...cast.characters, id] });
	}
	doc.direction.personnages = '';
	return card;
}

export function bibleContext(doc) {
	const brief = (card) => ({ label: cardLabel(card), text: clean(card.text) });
	return { [CHARACTERS]: cardsOf(doc, CHARACTERS).filter(usable).map(brief), [PLACES]: cardsOf(doc, PLACES).filter(usable).map(brief) };
}

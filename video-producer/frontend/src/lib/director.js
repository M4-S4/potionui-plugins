import { isInFlight } from './generation.js';
import { labelOf } from './labels.js';
import { CHARACTERS, castOf, instructionOf, names, setCast, shotsCasting, usable } from './bible.js';
import { touch } from './shots.js';

export const VIEWS = ['review', 'direction', 'bible', 'references'];
export const VIEW_ICONS = { review: 'layers', direction: 'palette', bible: 'book', references: 'bookmark' };
export const REVIEW_FILTERS = ['review', 'running', 'final', 'all'];

const finished = (take) => take?.status === 'done' && Boolean(take.url);

export function defaultView(takes) {
	return (takes ?? []).length ? 'review' : 'direction';
}

export function viewOf(chosen, takes) {
	return VIEWS.includes(chosen) ? chosen : defaultView(takes);
}

export function reviewState(takes) {
	const list = takes ?? [];
	const latest = [...list].sort((a, b) => String(a.createdAt ?? '').localeCompare(String(b.createdAt ?? ''))).at(-1);
	const final = list.some((x) => finished(x) && labelOf(x) === 'final');
	const failed = latest?.status === 'failed';
	const open = !final && list.some((x) => finished(x) && labelOf(x) !== 'rejected');
	return { running: list.some(isInFlight), final, failed, review: failed || open };
}

export function reviewShots(clips, takes, filter) {
	return (clips ?? []).filter((clip) => {
		if (filter === 'all') return true;
		const state = reviewState((takes ?? []).filter((x) => x.shotId === clip.id));
		if (filter === 'running') return state.running;
		if (filter === 'final') return state.final;
		return state.review;
	});
}

export function reviewCounts(clips, takes) {
	return Object.fromEntries(REVIEW_FILTERS.map((filter) => [filter, reviewShots(clips, takes, filter).length]));
}

export function citedWithout(doc, kind, card) {
	if (!usable(card)) return [];
	const cast = new Set(shotsCasting(doc, kind, card.id));
	return (doc?.clips ?? []).filter((clip) => !cast.has(clip) && names(instructionOf(doc, clip), card.label));
}

export function unnamedIn(doc, kind, card) {
	if (kind !== CHARACTERS || !usable(card)) return [];
	return shotsCasting(doc, kind, card.id).filter((clip) => !names(instructionOf(doc, clip), card.label));
}

export function toggledCast(clip, kind, id) {
	const cast = castOf(clip);
	if (kind === CHARACTERS) cast.characters = cast.characters.includes(id) ? cast.characters.filter((x) => x !== id) : [...cast.characters, id];
	else cast.place = cast.place === id ? null : id;
	return cast;
}

export function isCast(clip, kind, id) {
	const cast = castOf(clip);
	return kind === CHARACTERS ? cast.characters.includes(id) : cast.place === id;
}

export function recast(clip, kind, id) {
	setCast(clip, toggledCast(clip, kind, id));
	touch(clip);
}

export function castWhereCited(doc, kind, card) {
	const shots = citedWithout(doc, kind, card);
	for (const clip of shots) recast(clip, kind, card.id);
	return shots;
}

export function cardImages(doc, card) {
	const ids = new Set(card?.references ?? []);
	return (doc?.references ?? []).filter((r) => ids.has(r.id));
}

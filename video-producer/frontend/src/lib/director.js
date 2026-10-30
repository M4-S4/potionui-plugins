import { isInFlight } from './generation.js';
import { takeLabelOf } from './labels.js';
import { CHARACTERS, castOf, instructionOf, names, setCast, shotsCasting, usable } from './bible.js';
import { shotNumberAt, touch } from './shots.js';

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
	const final = list.some((x) => finished(x) && takeLabelOf(x) === 'final');
	const failed = latest?.status === 'failed';
	const open = !final && list.some((x) => finished(x) && takeLabelOf(x) !== 'rejected');
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

export const reviewFilterOf = (chosen, counts) => (REVIEW_FILTERS.includes(chosen) ? chosen : counts.review ? 'review' : 'all');

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

export const PANEL_KINDS = { review: ['clip'], direction: ['clip'], bible: [], references: ['reference', 'clip', 'vtrack'] };

export function panelSelection(view, selection) {
	if (!selection) return { shown: null, elsewhere: null };
	return (PANEL_KINDS[view] ?? []).includes(selection.kind) ? { shown: selection, elsewhere: null } : { shown: null, elsewhere: selection };
}

export function witnessOf(doc, selection, pinned) {
	const clips = doc?.clips ?? [];
	const fixed = pinned ? clips.find((c) => c.id === pinned) : null;
	if (fixed) return { clip: fixed, source: 'pinned' };
	const picked = selection?.kind === 'clip' ? clips.find((c) => c.id === selection.id) : null;
	if (picked) return { clip: picked, source: 'selection' };
	const first = clips.find((c) => instructionOf(doc, c)) ?? clips[0] ?? null;
	return { clip: first, source: first ? 'first' : null };
}

export function viewShot(view, doc, selection, pinned) {
	if (view === 'direction') return witnessOf(doc, selection, pinned).clip;
	const shown = panelSelection(view, selection).shown;
	return shown?.kind === 'clip' ? ((doc?.clips ?? []).find((c) => c.id === shown.id) ?? null) : null;
}

export function promptShot(doc, prompt) {
	const clips = doc?.clips ?? [];
	if (!prompt) return null;
	const own = clips.find((c) => c.id === prompt.shotId);
	if (own) return own;
	const start = Number(prompt.start) || 0;
	const end = start + (Number(prompt.dur) || 0);
	let best = null;
	let most = 0;
	for (const c of clips) {
		const overlap = Math.min(end, c.start + c.dur) - Math.max(start, c.start);
		if (overlap > most) {
			best = c;
			most = overlap;
		}
	}
	return best;
}

export function marked(text, patterns) {
	const list = (patterns ?? []).filter(Boolean);
	return String(text ?? '')
		.split(/(?<=[.!?;\n])/)
		.filter(Boolean)
		.flatMap((part) => {
			const [, lead, body] = part.match(/^(\s*)([\s\S]*)$/);
			const mark = Boolean(body) && list.some((re) => re.test(body));
			return [...(lead ? [{ text: lead, mark: false }] : []), ...(body ? [{ text: body, mark }] : [])];
		});
}

export const markedPhrases = (text, patterns) => marked(text, patterns).filter((part) => part.mark).map((part) => part.text.trim());

export function shotNumbers(doc, clips, max = 3) {
	const list = (clips ?? []).map((c) => shotNumberAt((doc?.clips ?? []).indexOf(c)));
	return { list: list.slice(0, max).join(' · '), more: Math.max(0, list.length - max) };
}

const reviewable = (take) => finished(take) || take?.status === 'failed';

export const reviewChoice = (take, clip) => (reviewable(take) ? { kind: 'take', id: take.id } : { kind: 'shot', id: clip.id });

export function reviewPickOf(doc, takes, pick, selection) {
	const clips = doc?.clips ?? [];
	const chosen = selection?.kind === 'clip' ? (clips.find((c) => c.id === selection.id) ?? null) : null;
	if (!chosen) return null;
	if (pick?.kind === 'take') {
		const take = (takes ?? []).find((x) => x.id === pick.id);
		if (take?.shotId === chosen.id && reviewable(take)) return { kind: take.status === 'failed' ? 'failed' : 'take', clip: chosen, take };
	}
	const index = clips.indexOf(chosen);
	if (pick?.kind === 'seam' && pick.id === chosen.id && index > 0) return { kind: 'seam', clip: chosen, previous: clips[index - 1] };
	return { kind: 'shot', clip: chosen };
}

export function nextToReview(clips, takes) {
	for (const clip of reviewShots(clips, takes, 'review')) {
		const open = (takes ?? []).filter((x) => x.shotId === clip.id && finished(x) && takeLabelOf(x) !== 'rejected');
		const take = open.sort((a, b) => String(b.createdAt ?? '').localeCompare(String(a.createdAt ?? '')))[0];
		if (take) return { clip, take };
	}
	return null;
}

const WORD = /^[\p{L}\p{N}]/u;

export function missingWords(text, sent) {
	const known = new Set(String(sent ?? '').toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []);
	const parts = String(text ?? '')
		.split(/([\p{L}\p{N}]+)/u)
		.filter(Boolean)
		.map((part) => ({ text: part, mark: WORD.test(part) && !known.has(part.toLowerCase()) }));
	return parts
		.map((part, i) => ({ ...part, mark: part.mark || (/^\s+$/.test(part.text) && Boolean(parts[i - 1]?.mark) && Boolean(parts[i + 1]?.mark)) }))
		.reduce((out, part) => {
			const last = out.at(-1);
			if (last && last.mark === part.mark) last.text += part.text;
			else out.push({ ...part });
			return out;
		}, []);
}

const AFTER_PREVIOUS = ['previous_take_failed', 'previous_take_cancelled', 'previous_take_gone', 'chain_frame_failed'];
const REFUSED = ['banned_prompt', 'content_blocked'];

export function failureFixes(take) {
	const code = take?.errorCode;
	if (AFTER_PREVIOUS.includes(code)) return ['previous', 'retry'];
	if (REFUSED.includes(code)) return ['instruction', 'retry'];
	if (code === 'cuda_oom') return ['retry', 'engine', 'shorter'];
	return ['retry'];
}

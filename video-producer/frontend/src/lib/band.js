import { CHARACTERS, PLACES, names } from './bible.js';
import { GROUP_ORDER, takeLabelOf } from './labels.js';

export const BAND_MIN_SHOT = 1;
export const BAND_STEP = 0.5;
export const MUSIC_ROLE = 'Musique';
export const METHODS = ['phrases', 'music', 'assistant'];
export const AVG_MIN = 2;
export const AVG_MAX = 8;

const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const snapTo = (v, step) => Math.round(v / step) * step;
const fixed = (v) => +v.toFixed(3);

export function musicEnd(doc) {
	const lanes = new Set((doc?.lanes ?? []).filter((l) => l.role === MUSIC_ROLE).map((l) => l.id));
	return (doc?.audio ?? []).filter((a) => lanes.has(a.lane)).reduce((end, a) => Math.max(end, a.start + a.dur), 0);
}

export function sections(markers, end = 0) {
	const list = (markers ?? []).filter((m) => m?.kind === 'marker' && finite(m.time)).sort((a, b) => a.time - b.time);
	return list.map((m, i) => ({ id: m.id, label: m.label, start: m.time, end: i < list.length - 1 ? list[i + 1].time : Math.max(end, m.time) })).filter((s) => s.end > s.start);
}

export function sentencesOf(text) {
	return String(text ?? '')
		.split(/(?<=[.!?])\s+/)
		.map((x) => x.trim())
		.filter(Boolean);
}

export function headOf(text) {
	const head = String(text).replace(/[.!?]$/, '').split(/[:,]/)[0].trim();
	return head.length > 34 ? head.slice(0, 32) + '…' : head;
}

export const phraseDuration = (text) => Math.max(3, Math.min(7, Math.round(String(text).length / 14)));

export function castFor(text, bible) {
	const characters = (bible?.[CHARACTERS] ?? []).filter((card) => names(text, card.label)).map((card) => card.id);
	const place = (bible?.[PLACES] ?? []).find((card) => names(text, card.label))?.id ?? null;
	return characters.length || place ? { ...(characters.length ? { characters } : {}), ...(place ? { place } : {}) } : null;
}

export function byPhrases(text, bible, makeId) {
	return sentencesOf(text).map((sentence, i) => ({ id: makeId(), keep: true, n: i + 1, label: headOf(sentence), prompt: sentence, dur: phraseDuration(sentence), cast: castFor(sentence, bible) }));
}

export function musicParts(doc) {
	const end = musicEnd(doc);
	const marked = sections(doc?.markers, end);
	if (marked.length) return marked;
	return end > 0 ? [{ id: null, label: '', start: 0, end }] : [];
}

export function onMusic(text, parts, { avg = 4, step = BAND_STEP } = {}, bible, makeId) {
	const sentences = sentencesOf(text);
	if (!sentences.length || !parts?.length) return [];
	const slots = [];
	for (const part of parts) {
		const len = part.end - part.start;
		const count = Math.max(1, Math.round(len / avg));
		let prev = part.start;
		for (let k = 1; k <= count; k++) {
			const edge = k === count ? part.end : Math.max(prev + step, snapTo(part.start + (k * len) / count, step));
			if (edge - prev >= BAND_MIN_SHOT - 1e-6 || k === count) slots.push({ start: prev, dur: fixed(edge - prev), part: part.label });
			prev = edge;
		}
	}
	const first = parts[0].start;
	const span = parts[parts.length - 1].end - first;
	const seen = {};
	return slots.map((slot, i) => {
		const index = Math.min(sentences.length - 1, Math.floor(((slot.start + slot.dur / 2 - first) / span) * sentences.length));
		const sentence = sentences[index];
		seen[index] = (seen[index] ?? 0) + 1;
		const label = seen[index] > 1 ? `${headOf(sentence)} (${seen[index]})` : headOf(sentence);
		return { id: makeId(), keep: true, n: i + 1, label, prompt: sentence, dur: Math.max(BAND_MIN_SHOT, slot.dur), cast: castFor(sentence, bible), part: slot.part };
	});
}

export function renumber(items) {
	items.forEach((x, i) => (x.n = i + 1));
	return items;
}

export function splitItem(items, index, makeId) {
	const item = items[index];
	if (!item) return items;
	const first = Math.max(BAND_MIN_SHOT, snapTo(item.dur / 2, BAND_STEP));
	const second = Math.max(BAND_MIN_SHOT, fixed(item.dur - first));
	items.splice(index, 1, { ...item, dur: first }, { ...item, id: makeId(), label: item.label, dur: second });
	return renumber(items);
}

export function mergeItem(items, index) {
	const a = items[index];
	const b = items[index + 1];
	if (!a || !b) return items;
	const prompt = a.prompt === b.prompt ? a.prompt : `${a.prompt} ${b.prompt}`.trim();
	const characters = [...new Set([...(a.cast?.characters ?? []), ...(b.cast?.characters ?? [])])];
	const place = a.cast?.place ?? b.cast?.place ?? null;
	const cast = characters.length || place ? { ...(characters.length ? { characters } : {}), ...(place ? { place } : {}) } : null;
	items.splice(index, 2, { ...a, prompt, dur: fixed(a.dur + b.dur), cast });
	return renumber(items);
}

export function removeItem(items, index) {
	if (index >= 0 && index < items.length) items.splice(index, 1);
	return renumber(items);
}

export function moveItem(items, index, delta) {
	const j = index + delta;
	if (index < 0 || j < 0 || j >= items.length) return items;
	[items[index], items[j]] = [items[j], items[index]];
	return renumber(items);
}

export function insertIndex(clips, at, selectedId) {
	if (at === 'after') {
		const i = (clips ?? []).findIndex((c) => c.id === selectedId);
		if (i >= 0) return i + 1;
	}
	return (clips ?? []).length;
}

export function ghostLayout(clips, items, index) {
	const kept = (items ?? []).filter((x) => x.keep);
	let at = (clips ?? []).slice(0, index).reduce((sum, c) => sum + c.dur, 0);
	const ghosts = kept.map((item, j) => {
		const out = { ...item, n: index + j + 1, start: fixed(at) };
		at += item.dur;
		return out;
	});
	return { index, ghosts, shift: fixed(kept.reduce((sum, x) => sum + x.dur, 0)) };
}

export function displayStart(clip, i, layout) {
	return clip.start + (layout && layout.shift && i >= layout.index ? layout.shift : 0);
}

const flightRank = { running: 0, queued: 1, failed: 2 };

export function stackOrder(takes, hideRejected = false) {
	const done = (takes ?? []).filter((t) => t.status === 'done' && !(hideRejected && takeLabelOf(t) === 'rejected'));
	done.sort((a, b) => GROUP_ORDER.indexOf(takeLabelOf(a)) - GROUP_ORDER.indexOf(takeLabelOf(b)) || String(a.variant ?? '').localeCompare(String(b.variant ?? '')));
	const rest = (takes ?? []).filter((t) => t.status in flightRank).sort((a, b) => flightRank[a.status] - flightRank[b.status]);
	return [...done, ...rest];
}

export function previewable(takes, hideRejected = false) {
	return stackOrder(takes, hideRejected).filter((t) => t.status === 'done' && t.url);
}

export function lastFailure(takes) {
	const list = [...(takes ?? [])].sort((a, b) => String(a.createdAt ?? '').localeCompare(String(b.createdAt ?? '')));
	const last = list[list.length - 1];
	return last?.status === 'failed' ? last : null;
}

export function seamStatus(seam) {
	if (!seam) return null;
	if (seam.issues?.length) return 'issue';
	return seam.measured && !seam.pending ? 'ok' : null;
}

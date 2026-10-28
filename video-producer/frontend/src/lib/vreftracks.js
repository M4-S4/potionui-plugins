import { MAX_VREF_TRACKS, VREF_ITEMS, VREF_ROLES, VREF_TRACKS, trackItemsOf, videoTracksOf } from './vrefs.js';
import { VIDEO_TRACKS, engineKey, videoCap, videoFrames } from './reception.js';
import { excludedVrefsOf, setExcludedVrefs } from './shots.js';

export const VREF_COLOR = 'viz-8';
export const VREF_FALLBACK = 5;
export const LONGEST_SECONDS = 15;
export const ROW_PREFIX = 'vtrack:';
const EPSILON = 1e-6;

export const vrefLabel = (slot) => `vref${slot}`;

export const trackOf = (doc, id) => videoTracksOf(doc).find((track) => track.id === id) ?? null;

export const trackRowId = (track) => `${ROW_PREFIX}${track.id}`;

export function freeSlot(doc) {
	const taken = new Set(videoTracksOf(doc).map((track) => track.slot));
	for (let slot = 1; slot <= MAX_VREF_TRACKS; slot++) if (!taken.has(slot)) return slot;
	return null;
}

function listOf(doc, key) {
	if (!Array.isArray(doc[key])) doc[key] = [];
	return doc[key];
}

function dropEmpty(doc, key) {
	if (Array.isArray(doc[key]) && !doc[key].length) delete doc[key];
}

export function addVrefTrack(doc, id, name = '') {
	const slot = freeSlot(doc);
	if (slot === null) return null;
	const track = { id, slot, name, role: VREF_ROLES[0] };
	listOf(doc, VREF_TRACKS).push(track);
	return track;
}

export const itemSpan = (srcDur) => (Number.isFinite(srcDur) && srcDur > 0 ? srcDur : VREF_FALLBACK);

export function addVrefItem(doc, { id, track, assetId, start, srcDur, fromTake = null }) {
	const item = { id, track, assetId, start, dur: itemSpan(srcDur), srcIn: 0 };
	if (typeof fromTake === 'string' && fromTake) item.fromTake = fromTake;
	listOf(doc, VREF_ITEMS).push(item);
	return item;
}

export const overlaps = (item, start, end) => Math.min(end, item.start + item.dur) - Math.max(start, item.start) > EPSILON;

export const trackBusy = (doc, trackId, start, end) => trackItemsOf(doc, trackId).some((item) => overlaps(item, start, end));

export function takeTracks(doc, takeId) {
	const ids = new Set((Array.isArray(doc?.[VREF_ITEMS]) ? doc[VREF_ITEMS] : []).filter((item) => takeId && item?.fromTake === takeId).map((item) => item.track));
	return videoTracksOf(doc).filter((track) => ids.has(track.id));
}

export function fitVrefItems(doc, assetId, srcDur) {
	if (!(Number.isFinite(srcDur) && srcDur > 0)) return [];
	const fitted = (doc[VREF_ITEMS] ?? []).filter((item) => item.assetId === assetId && item.srcIn === 0 && item.dur === VREF_FALLBACK);
	for (const item of fitted) item.dur = srcDur;
	return fitted;
}

const tagOf = (slot) => new RegExp(`(?<![0-9A-Za-z_])@vref${slot}(?![0-9A-Za-z_])`, 'i');
const TAGS = /(?<![0-9A-Za-z_])@vref([1-9])(?![0-9A-Za-z_])/gi;

export const vrefTag = (slot) => `@${vrefLabel(slot)}`;

export const citedSlots = (text) => [...new Set([...String(text ?? '').matchAll(TAGS)].map((match) => Number(match[1])))];

export function citeTrack(text, slot, at = null) {
	const value = String(text ?? '');
	const where = Number.isInteger(at) ? Math.min(Math.max(at, 0), value.length) : value.length;
	if (citedSlots(value).includes(slot)) return { text: value, caret: where, added: false };
	const before = value.slice(0, where);
	const after = value.slice(where);
	const lead = before && !/[\s([]$/.test(before) ? ' ' : '';
	const tail = /^[\p{L}\p{N}_@]/u.test(after) ? ' ' : '';
	const head = `${before}${lead}${vrefTag(slot)}`;
	return { text: `${head}${tail}${after}`, caret: head.length, added: true };
}

const escaped = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function labelParts(text, tracks) {
	const value = String(text ?? '');
	const known = (tracks ?? []).filter((track) => track?.label && Number.isInteger(track.slot));
	if (!known.length || !value) return value ? [{ text: value, slot: null }] : [];
	const slots = new Map(known.map((track) => [track.label, track.slot]));
	const pattern = new RegExp(`(${known.map((track) => escaped(track.label)).join('|')})`);
	return value
		.split(pattern)
		.filter((part) => part !== '')
		.map((part) => ({ text: part, slot: slots.get(part) ?? null }));
}

export function citingShots(doc, slot) {
	const tag = tagOf(slot);
	const cited = new Set((doc?.prompts ?? []).filter((prompt) => prompt?.shotId && tag.test(String(prompt.text ?? ''))).map((prompt) => prompt.shotId));
	return (doc?.clips ?? []).filter((clip) => cited.has(clip.id));
}

export function removeVrefTrack(doc, id) {
	const tracks = Array.isArray(doc[VREF_TRACKS]) ? doc[VREF_TRACKS] : [];
	const index = tracks.findIndex((track) => track?.id === id);
	if (index < 0) return null;
	const [track] = tracks.splice(index, 1);
	const list = Array.isArray(doc[VREF_ITEMS]) ? doc[VREF_ITEMS] : [];
	const items = [];
	for (let i = list.length - 1; i >= 0; i--) if (list[i]?.track === id) items.unshift(...list.splice(i, 1));
	for (const clip of doc.clips ?? []) {
		const excluded = excludedVrefsOf(clip);
		if (excluded.includes(id)) setExcludedVrefs(clip, excluded.filter((x) => x !== id));
	}
	dropEmpty(doc, VREF_TRACKS);
	dropEmpty(doc, VREF_ITEMS);
	return { track, items };
}

export function removeVrefItems(doc, gone) {
	const ids = new Set(gone.map((item) => item.id));
	const list = Array.isArray(doc[VREF_ITEMS]) ? doc[VREF_ITEMS] : [];
	for (let i = list.length - 1; i >= 0; i--) if (ids.has(list[i]?.id)) list.splice(i, 1);
	dropEmpty(doc, VREF_ITEMS);
}

export function lengthChoices() {
	const { minFrames, chunk, fps } = VIDEO_TRACKS;
	const most = videoFrames(LONGEST_SECONDS);
	const choices = [];
	for (let frames = minFrames; frames <= most; frames += chunk) choices.push({ frames, seconds: frames / fps });
	return choices;
}

export const trackFrames = (track) => videoFrames(videoCap(track?.seconds));

export function setTrackFrames(track, frames) {
	if (!Number.isInteger(frames) || frames <= VIDEO_TRACKS.minFrames) delete track.seconds;
	else track.seconds = frames / VIDEO_TRACKS.fps;
}

export function setTrackOff(track, off) {
	if (off) track.off = true;
	else delete track.off;
}

export const OVERLAY = { sent: 'sent', ignored: 'ignored', blocked: 'ignored', unknown: 'ignored', trimmed: 'warn', short: 'warn', missing: 'warn' };

export function trackMarks(shots, trackId) {
	const marks = [];
	for (const shot of shots) {
		const entry = shot.videoTracks.find((x) => x.track.id === trackId);
		const tone = entry ? OVERLAY[entry.status] : null;
		if (!tone) continue;
		const span = entry.status === 'sent' ? entry.window : entry.span;
		if (span && span[1] > span[0]) marks.push({ clip: shot.clip, engine: shot.engine, status: entry.status, tone, span, frames: entry.frames });
	}
	return marks;
}

export const receivingCount = (shots, trackId) => shots.filter((shot) => shot.videoTracks.some((x) => x.track.id === trackId && x.status === 'sent')).length;

export const SHOULD_GO = ['ignored', 'trimmed', 'short', 'missing'];
export const LEFT_ASIDE = ['excluded', 'off'];

export function trackShots(shots, trackId) {
	return shots.flatMap((shot) => {
		const entry = shot.videoTracks.find((x) => x.track.id === trackId);
		return entry ? [{ clip: shot.clip, engine: shot.engine, entry }] : [];
	});
}

export function trackGroups(shots, trackId) {
	const groups = [];
	for (const { clip, engine, entry } of trackShots(shots, trackId)) {
		const aside = LEFT_ASIDE.includes(entry.status);
		const key = aside ? entry.status : `${engineKey(engine)}|${entry.status}|${entry.status === 'sent' ? entry.frames : ''}`;
		let group = groups.find((g) => g.key === key);
		if (!group) groups.push((group = { key, status: entry.status, engine: aside ? null : engine, entry, clips: [] }));
		group.clips.push(clip);
	}
	return [...groups.filter((g) => !LEFT_ASIDE.includes(g.status)), ...LEFT_ASIDE.flatMap((status) => groups.filter((g) => g.status === status))];
}

export function trackIssues(shots, tracks) {
	return (tracks ?? []).flatMap((track) =>
		trackGroups(shots, track.id)
			.filter((g) => SHOULD_GO.includes(g.status))
			.map((g) => ({ ...g, key: `${track.id}|${g.key}`, track }))
	);
}

export function sendings(shots) {
	const sent = new Map();
	for (const shot of shots) for (const x of shot.videoTracks) if (x.status === 'sent') sent.set(x.track.id, [...(sent.get(x.track.id) ?? []), shot.clip.id]);
	return sent;
}

export function sendingChanges(before, shots) {
	const after = sendings(shots);
	const changes = [];
	for (const id of new Set([...before.keys(), ...after.keys()])) {
		const was = new Set(before.get(id) ?? []);
		const now = new Set(after.get(id) ?? []);
		const entries = shots.map((shot) => ({ shot, entry: shot.videoTracks.find((x) => x.track.id === id) ?? null }));
		const track = entries.find((x) => x.entry)?.entry.track ?? null;
		const started = entries.filter((x) => now.has(x.shot.clip.id) && !was.has(x.shot.clip.id)).map((x) => x.shot.clip);
		const stopped = entries.filter((x) => was.has(x.shot.clip.id) && !now.has(x.shot.clip.id)).map((x) => ({ clip: x.shot.clip, engine: x.shot.engine, status: x.entry?.status ?? null }));
		if (track && (started.length || stopped.length)) changes.push({ track, started, stopped });
	}
	return changes.sort((a, b) => a.track.slot - b.track.slot);
}

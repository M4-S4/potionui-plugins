import table from './reception.json';
import { isH3, presetProfiles } from './generation.js';
import { excludedVrefsOf, isGlobal, ownsReference, shotReferences } from './shots.js';
import { referencePromptOf } from './refprompt.js';
import { CHARACTERS, PLACES, cardsOf, shotsCasting, voiceReferences } from './bible.js';
import { MUX, audioBehavior } from './sound.js';
import { trackItemsOf, videoTracksOf } from './vrefs.js';

export const LIMITS = table.limits;
export const ORDER = table.order;
export const VIDEO_TRACKS = table.videoTracks;
export const FAMILIES = ['cloud', 'h3'];
export const RECEIVED = ['sent', 'mixed'];
export const STATUSES = ['sent', 'trimmed', 'missing', 'mixed', 'ignored', 'excluded', 'blocked', 'unknown'];
export const TRACK_STATUSES = ['sent', 'trimmed', 'short', 'missing', 'ignored', 'excluded', 'off', 'blocked', 'unknown'];
export const MOTION = 'motion';
export const CONTINUATION = 'continuation';
export const UNDER = 'under';
export const BEFORE = 'before';
export const CANVAS = 'canvas';
export const DRAFT = 'draft';

const EPSILON = 1e-6;
const finite = (value) => typeof value === 'number' && Number.isFinite(value);
const round6 = (value) => Math.round(value * 1e6) / 1e6;
const halfEven = (value) => {
	const near = Math.round(value);
	return Math.abs(value % 1) === 0.5 && near % 2 !== 0 ? near - 1 : near;
};

export function videoFrames(seconds) {
	if (!finite(seconds) || seconds <= 0) return 0;
	const frames = Math.floor(seconds * VIDEO_TRACKS.fps + EPSILON);
	const { head, chunk } = VIDEO_TRACKS;
	return frames >= head ? Math.floor((frames - head) / chunk) * chunk + head : 0;
}

export const leastSeconds = () => VIDEO_TRACKS.minFrames / VIDEO_TRACKS.fps;

export const videoCap = (seconds) => (finite(seconds) && seconds > 0 ? Math.max(seconds, leastSeconds()) : leastSeconds());

export const windowSide = (role) => VIDEO_TRACKS.roles[Object.hasOwn(VIDEO_TRACKS.roles, role) ? role : MOTION];

export function videoRegion(role, start, seconds, cap) {
	const length = Math.max(0, Math.min(seconds, videoCap(cap)));
	return windowSide(role) === BEFORE ? [Math.max(0, start - length), start] : [start, start + length];
}

export function videoPieces(items, role, start, seconds, cap) {
	const [begin, end] = videoRegion(role, start, seconds, cap);
	const spans = [];
	for (const item of items) {
		if (!finite(item?.start) || !finite(item?.dur) || item.dur <= EPSILON) continue;
		const low = Math.max(begin, item.start);
		const high = Math.min(end, item.start + item.dur);
		if (high - low > EPSILON) spans.push([low, high, item]);
	}
	spans.sort((a, b) => a[0] - b[0]);
	const frames = videoFrames(spans.reduce((sum, [low, high]) => sum + high - low, 0));
	const under = windowSide(role) === UNDER;
	let left = frames / VIDEO_TRACKS.fps;
	const pieces = [];
	for (const [low, high, item] of under ? spans : [...spans].reverse()) {
		if (left <= EPSILON) break;
		const take = Math.min(left, high - low);
		left -= take;
		const [from, to] = under ? [low, low + take] : [high - take, high];
		pieces.push({ id: item.id, from: round6(from), to: round6(to) });
	}
	pieces.sort((a, b) => a.from - b.from);
	return { frames, pieces };
}

export function cutSize(aspect, resolution = null, setting = null) {
	const chosen = VIDEO_TRACKS.sizes.includes(setting) ? setting : VIDEO_TRACKS.size;
	if (chosen === DRAFT && resolution) return [resolution[0], resolution[1]];
	const { shortEdge, maxPixels, multiple } = VIDEO_TRACKS.canvas;
	const ratio = aspect > 0 ? aspect : 16 / 9;
	let [width, height] = ratio >= 1 ? [shortEdge * ratio, shortEdge] : [shortEdge, shortEdge / ratio];
	if (width * height > maxPixels) {
		const scale = Math.sqrt(maxPixels / (width * height));
		width *= scale;
		height *= scale;
	}
	return [Math.max(multiple, halfEven(width / multiple) * multiple), Math.max(multiple, halfEven(height / multiple) * multiple)];
}

const readableVideo = (doc, item) => {
	const asset = (doc?.assets ?? []).find((a) => a.id === item.assetId) ?? null;
	return asset?.kind === 'video' && mediaKey(asset) !== null;
};

const playsIn = (item, [begin, end]) => finite(item?.start) && finite(item?.dur) && item.dur > EPSILON && Math.min(end, item.start + item.dur) - Math.max(begin, item.start) > EPSILON;

export function shotSeconds(clip, info) {
	const most = info?.limits?.maxDuration;
	const dur = finite(clip?.dur) && clip.dur > 0 ? clip.dur : 0;
	return finite(most) && most > 0 && most < dur ? most : dur;
}

export function shotVideoTracks(doc, clip, seconds) {
	const start = finite(clip?.start) ? clip.start : 0;
	const excluded = new Set(excludedVrefsOf(clip));
	const found = [];
	for (const track of videoTracksOf(doc)) {
		const region = videoRegion(track.role, start, seconds, track.seconds);
		const items = trackItemsOf(doc, track.id).filter((item) => playsIn(item, region));
		if (!items.length) continue;
		const entry = { track, slot: track.slot };
		if (track.off === true) found.push({ ...entry, status: 'off' });
		else if (excluded.has(track.id)) found.push({ ...entry, status: 'excluded' });
		else {
			const readable = items.filter((item) => readableVideo(doc, item));
			if (!readable.length) {
				found.push({ ...entry, status: 'missing' });
				continue;
			}
			const { frames, pieces } = videoPieces(readable, track.role, start, seconds, track.seconds);
			if (frames < VIDEO_TRACKS.minFrames) found.push({ ...entry, status: 'short' });
			else found.push({ ...entry, status: 'ready', frames, pieces, window: [pieces[0].from, pieces.at(-1).to] });
		}
	}
	return found;
}

export const takesReferences = (profile) => table.references.includes(profile);
export const familyOf = (info) => (info?.cloud ? 'cloud' : isH3(info) ? 'h3' : 'other');

const matches = (rule, family, profile) => (!rule.profiles || rule.profiles.includes(profile)) && (!rule.families || rule.families.includes(family));

export const layoutOf = (family, profile = null) => table.layouts.find((rule) => matches(rule, family, profile))?.layout ?? null;

export const engineKey = (engine) => `${engine?.preset ?? ''}|${engine?.model ?? ''}|${engine?.profile ?? ''}`;

export function mediaKey(asset) {
	const origin = asset?.origin;
	if (origin?.kind === 'history' && origin.generationId && origin.fileId != null) return `history:${origin.generationId}:${origin.fileId}`;
	if (origin?.kind === 'library' && origin.itemId) return `library:${origin.itemId}`;
	return null;
}

const assetOf = (doc, id) => (id ? ((doc?.assets ?? []).find((a) => a.id === id) ?? null) : null);

function mediaStatuses(doc, own, shared, tracks, videos, tracked) {
	const counts = Object.fromEntries(Object.keys(LIMITS).map((kind) => [kind, 0]));
	const seen = new Set();
	const statuses = new Map();
	const add = (reference) => {
		const asset = assetOf(doc, reference.assetId);
		const key = mediaKey(asset);
		if (!key || !Object.hasOwn(counts, asset.kind)) return statuses.set(reference.id, 'missing');
		if (seen.has(key)) return statuses.set(reference.id, 'sent');
		if (counts[asset.kind] >= LIMITS[asset.kind]) return statuses.set(reference.id, 'trimmed');
		counts[asset.kind] += 1;
		seen.add(key);
		statuses.set(reference.id, 'sent');
	};
	for (const step of ORDER) {
		if (step === 'own') own.forEach(add);
		else if (step === 'tracks') {
			counts.audio = Math.min(LIMITS.audio, counts.audio + tracks);
			for (const video of videos) {
				const sent = counts.video < LIMITS.video;
				if (sent) counts.video += 1;
				tracked.set(video.track.id, sent ? 'sent' : 'trimmed');
			}
		} else shared.forEach(add);
	}
	return statuses;
}

export function shotReception(doc, clip, engine, tracks = 0) {
	const { inherited, own } = shotReferences(doc, clip);
	const shared = inherited.filter((x) => !x.excluded).map((x) => x.reference);
	const info = engine?.info ?? null;
	const profile = engine?.profile ?? null;
	const state = !info ? 'unknown' : presetProfiles(info).includes(profile) ? 'ready' : 'blocked';
	const layout = state === 'ready' ? layoutOf(familyOf(info), profile) : null;
	const override = layout ? referencePromptOf(clip) : null;
	const found = shotVideoTracks(doc, clip, shotSeconds(clip, info));
	const tracked = new Map(found.filter((x) => x.status !== 'ready').map((x) => [x.track.id, x.status]));
	const going = found.filter((x) => x.status !== 'off' && x.status !== 'excluded');
	let statuses;
	if (state !== 'ready') {
		statuses = new Map([...own, ...shared].map((r) => [r.id, state]));
		for (const x of going) tracked.set(x.track.id, state);
	} else if (takesReferences(profile)) statuses = mediaStatuses(doc, own, shared, tracks, going.filter((x) => x.status === 'ready'), tracked);
	else {
		const mixes = audioBehavior(info, profile) === MUX;
		const voices = voiceReferences(doc);
		statuses = new Map([...own, ...shared].map((r) => [r.id, mixes && assetOf(doc, r.assetId)?.kind === 'audio' && !voices.has(r.id) ? 'mixed' : 'ignored']));
		for (const x of going) tracked.set(x.track.id, 'ignored');
	}
	for (const x of inherited) if (x.excluded) statuses.set(x.reference.id, 'excluded');
	const videoTracks = found.map((x) => ({ track: x.track, slot: x.slot, status: tracked.get(x.track.id), frames: x.frames ?? 0, window: tracked.get(x.track.id) === 'sent' ? x.window : null }));
	return { clip, engine, state, layout, overridden: Boolean(override) && override.layout === layout, ignoredLayout: Boolean(override) && override.layout !== layout, statuses, videoTracks };
}

export function linkedCard(doc, reference) {
	for (const kind of [CHARACTERS, PLACES]) {
		const card = cardsOf(doc, kind).find((c) => (c.references ?? []).includes(reference?.id));
		if (card) return { kind, card, voice: false };
	}
	const owner = cardsOf(doc, CHARACTERS).find((c) => c.voiceRef && c.voiceRef === reference?.id);
	return owner ? { kind: CHARACTERS, card: owner, voice: true } : null;
}

function grouped(items, keyOf, make) {
	const groups = [];
	for (const item of items) {
		const key = keyOf(item);
		let group = groups.find((g) => g.key === key);
		if (!group) groups.push((group = { key, ...make(item), shots: [] }));
		group.shots.push(item);
	}
	return groups;
}

export function receptionOf(reference, doc, engineOf, tracksOf = () => 0) {
	const shots = (doc?.clips ?? [])
		.filter((clip) => isGlobal(reference) || ownsReference(clip, reference))
		.map((clip) => {
			const shot = shotReception(doc, clip, engineOf(clip), tracksOf(clip));
			return { ...shot, status: shot.statuses.get(reference.id) };
		});
	const groups = grouped(
		shots,
		(shot) => (shot.status === 'excluded' ? 'excluded' : `${engineKey(shot.engine)}|${shot.status}`),
		(shot) => ({ engine: shot.status === 'excluded' ? null : shot.engine, status: shot.status })
	);
	const linked = linkedCard(doc, reference);
	return {
		reference,
		shots,
		groups: [...groups.filter((g) => g.status !== 'excluded'), ...groups.filter((g) => g.status === 'excluded')],
		going: shots.filter((shot) => shot.status !== 'excluded').map((shot) => shot.clip),
		linked,
		cast: linked && !linked.voice ? shotsCasting(doc, linked.kind, linked.card.id) : []
	};
}

export function projectReception(doc, engineOf, tracksOf = () => 0) {
	const shots = (doc?.clips ?? []).map((clip) => shotReception(doc, clip, engineOf(clip), tracksOf(clip)));
	return grouped(
		shots,
		(shot) => engineKey(shot.engine),
		(shot) => ({ engine: shot.engine, state: shot.state, references: takesReferences(shot.engine?.profile) })
	).map((group) => {
		const counts = {};
		for (const shot of group.shots) for (const status of shot.statuses.values()) counts[status] = (counts[status] ?? 0) + 1;
		return { ...group, counts };
	});
}

export function cardReception(doc, kind, card, engineOf, tracksOf = () => 0) {
	const ids = [...(card?.references ?? []), ...(kind === CHARACTERS && card?.voiceRef ? [card.voiceRef] : [])];
	const references = [...new Set(ids)].filter((id) => (doc?.references ?? []).some((r) => r.id === id));
	const shots = shotsCasting(doc, kind, card?.id).map((clip) => {
		const shot = shotReception(doc, clip, engineOf(clip), tracksOf(clip));
		return { ...shot, received: references.filter((id) => RECEIVED.includes(shot.statuses.get(id))).length };
	});
	return {
		references,
		shots,
		groups: grouped(
			shots,
			(shot) => `${engineKey(shot.engine)}|${shot.state}|${shot.received > 0}`,
			(shot) => ({ engine: shot.engine, state: shot.state, received: shot.received > 0 })
		)
	};
}

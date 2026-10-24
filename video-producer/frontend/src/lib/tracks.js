import { ulid } from './ulid.js';

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

export const newVideoTrack = () => ({ mute: false, solo: false });

export const newLaneId = () => ulid();

export function videoTrack(doc) {
	const video = isObject(doc?.video) ? doc.video : {};
	return { mute: video.mute === true, solo: video.solo === true };
}

export function anySolo(doc) {
	return videoTrack(doc).solo || (doc?.lanes ?? []).some((lane) => lane?.solo === true);
}

export function laneAudible(doc, lane) {
	return isObject(lane) && !lane.mute && (!anySolo(doc) || lane.solo === true);
}

export function clipSoundAudible(doc, clip) {
	const video = videoTrack(doc);
	return !video.mute && !clip?.mute && (!anySolo(doc) || video.solo);
}

export function laneCode(lanes, id) {
	const index = (lanes ?? []).findIndex((lane) => lane.id === id);
	return index < 0 ? '' : `A${index + 1}`;
}

export function laneTitle(lanes, lane) {
	const code = laneCode(lanes, lane?.id);
	return lane?.name ? `${code} · ${lane.name}` : code;
}

export function laneFor(doc, role) {
	return doc.lanes.find((lane) => lane.role === role) ?? doc.lanes[0] ?? null;
}

export function laneItemCount(doc, id) {
	return (doc.audio ?? []).filter((item) => item.lane === id).length;
}

export const SOUND_FALLBACK = 8;

export const soundSpan = (srcDur) => (Number.isFinite(srcDur) && srcDur > 0 ? srcDur : SOUND_FALLBACK);

export const newSound = (assetId, lane, start, srcDur) => ({ id: ulid(), assetId, lane, start, dur: soundSpan(srcDur), srcIn: 0, fadeIn: 0.5, fadeOut: 0.5, gain: -6 });

export function fitSounds(doc, assetId, srcDur) {
	if (!(Number.isFinite(srcDur) && srcDur > 0)) return [];
	const fitted = (doc.audio ?? []).filter((item) => item.assetId === assetId && item.srcIn === 0 && item.dur === SOUND_FALLBACK);
	for (const item of fitted) item.dur = srcDur;
	return fitted;
}

export const SLICE_SECONDS = 5;
export const SLICE_MIN = 1;
export const SLICE_MAX = 60;
export const MAX_SLICES = 200;
export const JOIN_TOLERANCE = 0.025;

const SLICE_EDGE = 0.1;

const exact = (v) => Math.round(v * 1e6) / 1e6;

export function sliceLength(value) {
	const n = Number(value);
	return Number.isFinite(n) ? Math.round(Math.min(SLICE_MAX, Math.max(SLICE_MIN, n)) * 10) / 10 : SLICE_SECONDS;
}

export function sliceCuts(dur, seconds) {
	const cuts = [];
	for (let k = 1; exact(k * seconds) < exact(dur - SLICE_EDGE); k++) {
		if (k >= MAX_SLICES) return null;
		cuts.push(exact(k * seconds));
	}
	return cuts;
}

export function shotCuts(item, clips) {
	const end = item.start + item.dur;
	const bounds = (clips ?? []).flatMap((clip) => [clip.start, clip.start + clip.dur]).sort((a, b) => a - b);
	const cuts = [];
	for (const at of bounds) {
		if (exact(at - item.start) < SLICE_EDGE || exact(end - at) < SLICE_EDGE) continue;
		const offset = exact(at - item.start);
		if (cuts.length && exact(offset - cuts.at(-1)) < SLICE_EDGE) cuts[cuts.length - 1] = offset;
		else cuts.push(offset);
	}
	return cuts.length >= MAX_SLICES ? null : cuts;
}

export function sliceItem(item, seconds, makeId = ulid) {
	return sliceAt(item, sliceCuts(item.dur, seconds), makeId);
}

export function shotSlices(item, clips, makeId = ulid) {
	return sliceAt(item, shotCuts(item, clips), makeId);
}

function sliceAt(item, cuts, makeId) {
	if (!cuts?.length) return cuts;
	const edges = [0, ...cuts, item.dur];
	const last = edges.length - 2;
	return edges.slice(0, -1).map((from, i) => ({
		...item,
		id: i === 0 ? item.id : makeId(),
		start: exact(item.start + from),
		dur: exact(edges[i + 1] - from),
		srcIn: exact(item.srcIn + from),
		fadeIn: i === 0 ? item.fadeIn : 0,
		fadeOut: i === last ? item.fadeOut : 0
	}));
}

const near = (a, b) => Math.abs(a - b) <= JOIN_TOLERANCE;

export const continues = (a, b) => b !== a && b.lane === a.lane && b.assetId === a.assetId && near(b.start, a.start + a.dur) && near(b.srcIn, a.srcIn + a.dur);

export function sliceChain(doc, item) {
	const items = doc.audio ?? [];
	const chain = [item];
	for (let prev = items.find((x) => continues(x, item)); prev && !chain.includes(prev); prev = items.find((x) => continues(x, prev))) chain.unshift(prev);
	for (let next = items.find((x) => continues(item, x)); next && !chain.includes(next); next = items.find((x) => continues(next, x))) chain.push(next);
	return chain;
}

export function joinRuns(chain, sameKind) {
	const runs = [];
	for (const item of chain) {
		const run = runs.at(-1);
		if (run && sameKind(run.at(-1), item)) run.push(item);
		else runs.push([item]);
	}
	return runs;
}

export function joined(run) {
	const [first] = run;
	const last = run.at(-1);
	const merged = { ...first, dur: exact(last.start + last.dur - first.start), fadeOut: last.fadeOut };
	const own = run.find((x) => typeof x.reference === 'boolean');
	if (own) merged.reference = own.reference;
	else delete merged.reference;
	return merged;
}

export function removeLane(doc, id) {
	const index = doc.lanes.findIndex((lane) => lane.id === id);
	if (index < 0) return null;
	const [lane] = doc.lanes.splice(index, 1);
	const items = [];
	for (let i = doc.audio.length - 1; i >= 0; i--) if (doc.audio[i].lane === id) items.unshift(...doc.audio.splice(i, 1));
	if (doc.engine && doc.engine.audioDriver === id) doc.engine.audioDriver = doc.lanes[0]?.id ?? '';
	return { lane, items };
}

export function migrateTracks(doc) {
	const next = { ...doc, video: videoTrack(doc) };
	if (Array.isArray(doc.clips)) next.clips = doc.clips.map((clip) => (isObject(clip) && typeof clip.mute !== 'boolean' ? { ...clip, mute: false } : clip));
	if (Array.isArray(doc.lanes)) {
		const seen = new Set();
		next.lanes = doc.lanes.map((lane) => {
			if (!isObject(lane)) return lane;
			const id = typeof lane.id === 'string' && lane.id && !seen.has(lane.id) ? lane.id : newLaneId();
			seen.add(id);
			return id === lane.id ? lane : { ...lane, id };
		});
	}
	return next;
}

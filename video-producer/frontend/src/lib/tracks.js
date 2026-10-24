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

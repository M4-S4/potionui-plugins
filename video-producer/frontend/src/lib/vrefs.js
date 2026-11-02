import { isObject } from './values.js';

export const VREF_TRACKS = 'vrefTracks';
export const VREF_ITEMS = 'vrefItems';
export const VREF_ROLES = ['motion', 'continuation'];
export const MAX_VREF_TRACKS = 3;

const finite = (value) => typeof value === 'number' && Number.isFinite(value);

export function vrefTracksOf(value) {
	const tracks = [];
	const ids = new Set();
	const slots = new Set();
	for (const track of Array.isArray(value) ? value : []) {
		if (tracks.length === MAX_VREF_TRACKS) break;
		if (!isObject(track)) continue;
		const { id, slot } = track;
		if (typeof id !== 'string' || !id || ids.has(id)) continue;
		if (!Number.isInteger(slot) || slot < 1 || slot > MAX_VREF_TRACKS || slots.has(slot)) continue;
		const kept = { id, slot, name: typeof track.name === 'string' ? track.name : '', role: VREF_ROLES.includes(track.role) ? track.role : VREF_ROLES[0] };
		if (finite(track.seconds) && track.seconds > 0) kept.seconds = track.seconds;
		if (typeof track.off === 'boolean') kept.off = track.off;
		tracks.push(kept);
		ids.add(id);
		slots.add(slot);
	}
	return tracks;
}

export function vrefItemsOf(value, tracks, assets) {
	const known = new Set(tracks.map((track) => track.id));
	const kinds = new Map((Array.isArray(assets) ? assets : []).filter(isObject).map((asset) => [asset.id, asset.kind]));
	const items = [];
	const ids = new Set();
	for (const item of Array.isArray(value) ? value : []) {
		if (!isObject(item)) continue;
		const { id, assetId } = item;
		if (typeof id !== 'string' || !id || ids.has(id) || !known.has(item.track)) continue;
		if (!(finite(item.start) && finite(item.dur) && item.dur > 0)) continue;
		if (!(assetId === null || assetId === undefined || (typeof assetId === 'string' && assetId))) continue;
		if ((kinds.has(assetId ?? null) ? kinds.get(assetId ?? null) : 'video') !== 'video') continue;
		const kept = { id, track: item.track, assetId: assetId ?? null, start: item.start, dur: item.dur, srcIn: finite(item.srcIn) && item.srcIn >= 0 ? item.srcIn : 0 };
		if ('fromTake' in item && (item.fromTake === null || typeof item.fromTake === 'string')) kept.fromTake = item.fromTake;
		items.push(kept);
		ids.add(id);
	}
	return items;
}

export function migrateVrefs(doc) {
	if (!isObject(doc) || !(VREF_TRACKS in doc || VREF_ITEMS in doc)) return doc;
	const tracks = vrefTracksOf(doc[VREF_TRACKS]);
	const items = vrefItemsOf(doc[VREF_ITEMS], tracks, doc.assets);
	const next = { ...doc };
	for (const [key, list] of [
		[VREF_TRACKS, tracks],
		[VREF_ITEMS, items]
	]) {
		if (list.length) next[key] = list;
		else delete next[key];
	}
	return next;
}

export function videoTracksOf(doc) {
	return (Array.isArray(doc?.[VREF_TRACKS]) ? doc[VREF_TRACKS] : []).filter((track) => isObject(track) && track.id && Number.isInteger(track.slot)).sort((a, b) => a.slot - b.slot);
}

export function trackItemsOf(doc, trackId) {
	return (Array.isArray(doc?.[VREF_ITEMS]) ? doc[VREF_ITEMS] : []).filter((item) => isObject(item) && item.track === trackId).sort((a, b) => (a.start ?? 0) - (b.start ?? 0));
}

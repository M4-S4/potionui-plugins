import { newAsset } from './starter.js';
import { ulid } from './ulid.js';

export const FIRST_ROLES = ['first', 'début', 'debut'];
export const LAST_ROLES = ['last', 'fin'];
export const PREVIOUS_LAST = 'previous_last';
export const SEAM_STRENGTH = 100;

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' ? value : '');
const integer = (value) => (Number.isInteger(value) ? value : null);
const snap = (value) => +(Math.round(value / 0.04) * 0.04).toFixed(3);

export function roleKind(role) {
	const value = String(role ?? '')
		.trim()
		.toLowerCase();
	if (FIRST_ROLES.includes(value)) return 'first';
	if (LAST_ROLES.includes(value)) return 'last';
	return null;
}

export function previousShot(doc, shotId) {
	const i = doc.clips.findIndex((c) => c.id === shotId);
	return i > 0 ? doc.clips[i - 1] : null;
}

export function framesOf(doc, shotId, kind) {
	return (doc.frames ?? []).filter((f) => f.shotId === shotId && roleKind(f.role) === kind);
}

export function seamImage(doc, shotId, kind) {
	for (const f of framesOf(doc, shotId, kind)) {
		const a = f.assetId ? doc.assets?.find((x) => x.id === f.assetId) : null;
		if (a?.kind === 'image' && a.src) return a;
	}
	return null;
}

export function requestBody(source) {
	if (!source || source === PREVIOUS_LAST) return { source: PREVIOUS_LAST };
	return { source: { take_id: source.takeId, at: source.at } };
}

export function frameTime(clip, kind) {
	return kind === 'last' ? snap(clip.start + Math.max(0, clip.dur - 0.04)) : snap(clip.start);
}

export function playheadPick(clip, playhead, placed) {
	const rel = Math.min(clip.dur, Math.max(0, playhead - clip.start));
	const at = Math.max(0, Math.round(((placed ? clip.srcIn : 0) + rel) * 1000) / 1000);
	return { kind: rel < clip.dur / 2 ? 'first' : 'last', at };
}

export function normalizeSeamMedia(value) {
	if (!isObject(value) || !text(value.url)) return null;
	const type = text(value.media_type) || 'image';
	if (type !== 'image') return null;
	const itemId = text(value.item_id) || (typeof value.item_id === 'number' ? String(value.item_id) : '') || text(value.origin?.itemId);
	if (!itemId) return null;
	return { itemId, url: value.url, filename: text(value.filename), width: integer(value.width), height: integer(value.height) };
}

export function seamAsset(media, fallbackName) {
	const res = media.width && media.height ? `${media.width}×${media.height}` : null;
	return newAsset({ kind: 'image', name: media.filename || fallbackName, src: media.url, origin: { kind: 'library', itemId: media.itemId }, width: media.width, height: media.height, res });
}

export function placeSeamFrame(doc, clip, kind, asset, makeId = ulid) {
	if (!doc.assets.some((a) => a.id === asset.id)) doc.assets.push(asset);
	const existing = framesOf(doc, clip.id, kind);
	const fields = { shotId: clip.id, time: frameTime(clip, kind), assetId: asset.id, role: kind, strength: SEAM_STRENGTH };
	if (existing.length) {
		Object.assign(existing[0], fields);
		for (const extra of existing.slice(1)) doc.frames.splice(doc.frames.indexOf(extra), 1);
		return existing[0];
	}
	const frame = { id: makeId(), ...fields };
	doc.frames.push(frame);
	return frame;
}

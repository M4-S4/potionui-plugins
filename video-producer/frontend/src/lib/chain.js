import { newAsset } from './starter.js';
import { seamAsset, seamImage } from './seam.js';

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' ? value : '');
const number = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null);
const assetOf = (doc, id) => (id ? ((doc.assets ?? []).find((a) => a.id === id) ?? null) : null);

export const chainOn = (doc) => doc?.firstFromPrevious !== false;

export function setChain(doc, on) {
	if (on) delete doc.firstFromPrevious;
	else doc.firstFromPrevious = false;
}

export function ignoresFirstFrame(option) {
	const modes = option && option.kind !== 'cloud' ? (option.info?.directorModes ?? []) : [];
	return modes.length > 0 && !modes.includes('i2v');
}

export const cutEnd = (clip) => Math.round((Math.max(0, clip?.srcIn ?? 0) + Math.max(0, clip?.dur ?? 0)) * 1000) / 1000;

export function chainSource(doc, clip) {
	const a = assetOf(doc, clip?.assetId);
	if (!a?.src) return null;
	if (a.kind === 'image') return { shotId: clip.id, takeId: null, assetId: a.id, at: null };
	if (a.kind !== 'video' || !(a.origin || a.generated)) return null;
	return { shotId: clip.id, takeId: a.generated ? (a.resultId ?? null) : null, assetId: a.id, at: cutEnd(clip) };
}

function frameIndex(doc, source) {
	const a = assetOf(doc, source.assetId);
	const fps = number(a?.fps) || number(doc.fps) || 25;
	const at = number(a?.srcDur) ? Math.min(source.at, a.srcDur) : source.at;
	return Math.max(0, Math.ceil(at * fps - 1e-6) - 1);
}

export function sameFrame(doc, taken, source) {
	if (!taken || !source || taken.shotId !== source.shotId || taken.assetId !== source.assetId) return false;
	if (taken.at === null || source.at === null) return taken.at === source.at;
	return frameIndex(doc, taken) === frameIndex(doc, source);
}

export function chainState(doc, index) {
	const from = doc.clips?.[index - 1];
	const to = doc.clips?.[index];
	if (!from || !to) return null;
	const source = chainSource(doc, from);
	const image = seamImage(doc, to.id, 'first');
	if (isObject(image?.frameOf)) return { state: sameFrame(doc, image.frameOf, source) ? 'fresh' : 'stale', from, to, source, image };
	if (!image && source && chainOn(doc) && to.stage === 'todo') return { state: 'offer', from, to, source, image: null };
	return null;
}

export function chainPlan(doc, clip) {
	if (!chainOn(doc)) return null;
	const i = (doc.clips ?? []).findIndex((c) => c.id === clip?.id);
	if (i <= 0 || seamImage(doc, clip.id, 'first')) return null;
	return chainSource(doc, doc.clips[i - 1]);
}

export function normalizeFrameSource(value) {
	if (!isObject(value) || !text(value.shotId) || !text(value.assetId)) return null;
	return { shotId: value.shotId, takeId: text(value.takeId) || null, assetId: value.assetId, at: number(value.at) };
}

export function frameAsset(media, source, fallbackName) {
	return { ...seamAsset(media, fallbackName), frameOf: { ...source } };
}

export function stillAsset(doc, source, name) {
	const a = assetOf(doc, source.assetId);
	return newAsset({ kind: 'image', name, src: a.src, origin: a.origin, width: a.width, height: a.height, res: a.res, frameOf: { ...source } });
}

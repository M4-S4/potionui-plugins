import { newAsset } from './starter.js';
import { framesOf, normalizeSeamMedia, seamAsset, seamImage } from './seam.js';

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' ? value : '');
const number = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null);
const assetOf = (doc, id) => (id ? ((doc.assets ?? []).find((a) => a.id === id) ?? null) : null);

export const chainOn = (doc) => doc?.firstFromPrevious !== false;

export function setChain(doc, on) {
	if (on) delete doc.firstFromPrevious;
	else doc.firstFromPrevious = false;
}

export const ownChain = (clip) => (typeof clip?.firstFromPrevious === 'boolean' ? clip.firstFromPrevious : null);

export const shotChained = (doc, clip) => ownChain(clip) ?? chainOn(doc);

export function chainFrames(doc, clip) {
	const i = (doc.clips ?? []).findIndex((c) => c.id === clip?.id);
	const previous = i > 0 ? doc.clips[i - 1] : null;
	if (!previous) return [];
	return framesOf(doc, clip.id, 'first').filter((f) => isObject(assetOf(doc, f.assetId)?.frameOf));
}

export function setShotChain(doc, clip, on) {
	clip.firstFromPrevious = on;
	if (on) return [];
	const dropped = chainFrames(doc, clip);
	doc.frames = (doc.frames ?? []).filter((f) => !dropped.includes(f));
	return dropped;
}

export function resetShotChain(doc, clip) {
	const on = chainOn(doc);
	delete clip.firstFromPrevious;
	if (!on) doc.frames = (doc.frames ?? []).filter((f) => !chainFrames(doc, clip).includes(f));
}

export const chainWaiting = (take) => take?.status === 'queued' && take?.chain?.state === 'waiting';

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
	if (!image && source && shotChained(doc, to) && to.stage === 'todo') return { state: 'offer', from, to, source, image: null };
	return null;
}

export function seamChain(doc, index, takes = [], textOnly = false) {
	const from = doc.clips?.[index - 1];
	const to = doc.clips?.[index];
	if (!from || !to) return null;
	const base = { from, to, own: ownChain(to) !== null, after: null };
	if (!shotChained(doc, to)) return { ...base, state: 'off' };
	if (textOnly) return { ...base, state: 'textOnly' };
	const waiting = takes.find((take) => take.shotId === to.id && chainWaiting(take));
	if (waiting) return { ...base, state: 'waiting', take: waiting, after: takes.find((take) => take.id === waiting.chain.after) ?? null };
	const image = seamImage(doc, to.id, 'first');
	if (image && !isObject(image.frameOf)) return { ...base, state: 'own' };
	if (image) return { ...base, state: chainState(doc, index)?.state === 'stale' ? 'stale' : 'fresh' };
	return { ...base, state: chainSource(doc, from) ? 'ready' : 'later' };
}

export const chainAssetId = (take) => `chain-${take.id}`;

export function takeFrameAsset(doc, take, name) {
	const source = take.chain?.source;
	if (!source) return null;
	if (take.chain.frame) return { ...frameAsset(take.chain.frame, source, name), id: chainAssetId(take) };
	if (source.at !== null || !assetOf(doc, source.assetId)) return null;
	return { ...stillAsset(doc, source, name), id: chainAssetId(take) };
}

const PLACEABLE = ['queued', 'running', 'done'];

export function placesTakeFrame(doc, take, takes = [], removed = () => false) {
	if (take?.chain?.state !== 'taken' || !take.chain.source || !PLACEABLE.includes(take.status)) return false;
	if (assetOf(doc, chainAssetId(take)) || removed(take.id) || (take.status === 'done' && assetOf(doc, `gen-${take.id}`))) return false;
	const i = (doc.clips ?? []).findIndex((c) => c.id === take.shotId);
	if (i <= 0 || doc.clips[i - 1].id !== take.chain.previous) return false;
	const current = seamImage(doc, take.shotId, 'first');
	if (!current) return true;
	if (!isObject(current.frameOf)) return false;
	if (!current.id.startsWith('chain-')) return true;
	const placed = takes.find((other) => chainAssetId(other) === current.id);
	return !placed || (placed.chain?.batch !== take.chain.batch && (placed.createdAt ?? '') <= (take.createdAt ?? ''));
}

export function chainPlan(doc, clip) {
	if (!shotChained(doc, clip)) return null;
	const i = (doc.clips ?? []).findIndex((c) => c.id === clip?.id);
	if (i <= 0 || seamImage(doc, clip.id, 'first')) return null;
	return chainSource(doc, doc.clips[i - 1]);
}

export function normalizeFrameSource(value) {
	if (!isObject(value) || !text(value.shotId) || !text(value.assetId)) return null;
	return { shotId: value.shotId, takeId: text(value.takeId) || null, assetId: value.assetId, at: number(value.at) };
}

const CHAIN_STATES = ['waiting', 'taken'];

export function normalizeChain(value) {
	if (!isObject(value) || !text(value.previous) || !CHAIN_STATES.includes(value.state)) return null;
	return { previous: value.previous, after: text(value.after) || null, state: value.state, batch: text(value.batch) || null, source: normalizeFrameSource(value.source), frame: normalizeSeamMedia(value.frame) };
}

export function frameAsset(media, source, fallbackName) {
	return { ...seamAsset(media, fallbackName), frameOf: { ...source } };
}

export function stillAsset(doc, source, name) {
	const a = assetOf(doc, source.assetId);
	return newAsset({ kind: 'image', name, src: a.src, origin: a.origin, width: a.width, height: a.height, res: a.res, frameOf: { ...source } });
}

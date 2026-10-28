import table from './formatstable.js';

export const CADENCES = [...table.cadence.values];
export const DEFAULT_CADENCE = table.cadence.default;
export const SLOWER = table.cadence.slower;
export const INTERPOLATORS = ['auto', 'rife', 'rtx'];
export const ACTIVE_RENDITIONS = ['waiting', 'queued', 'running'];

const positive = (value) => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null);
const same = (a, b) => typeof a === 'number' && typeof b === 'number' && Math.abs(a - b) < 1e-6;

export function projectFps(doc) {
	return positive(doc?.fps) ?? DEFAULT_CADENCE;
}

export function targetOf(doc) {
	const fps = projectFps(doc);
	return Number.isInteger(fps) && CADENCES.includes(fps) ? fps : null;
}

export function needsConform(takeFps, fps) {
	const source = positive(takeFps);
	const target = positive(fps);
	return source !== null && target !== null && source < target * (1 - SLOWER) - 1e-9;
}

export function nearlyAsFast(takeFps, fps) {
	const source = positive(takeFps);
	const target = positive(fps);
	return source !== null && target !== null && source < target && !needsConform(source, target);
}

export function interpolatorChoice(doc) {
	const chosen = doc?.finalPass?.interpolator;
	return INTERPOLATORS.includes(chosen) ? chosen : 'auto';
}

export function interpolatorsReady(me) {
	const ready = me?.features?.interpolators ?? {};
	return { rife: ready.rife === true, rtx: ready.rtx === true };
}

export function pickInterpolator(choice, me) {
	const ready = interpolatorsReady(me);
	if (choice === 'auto') return ready.rtx ? 'rtx' : ready.rife ? 'rife' : null;
	return ready[choice] ? choice : null;
}

export function isActiveRendition(rendition) {
	return ACTIVE_RENDITIONS.includes(rendition?.status);
}

export function renditionFor(renditions, takeId, fps) {
	const found = (renditions ?? []).filter((x) => x.takeId === takeId && same(x.fps, fps) && (isActiveRendition(x) || x.status === 'done'));
	return found.at(-1) ?? null;
}

export function lastRendition(renditions, takeId, fps) {
	return (renditions ?? []).filter((x) => x.takeId === takeId && same(x.fps, fps)).at(-1) ?? null;
}

export function takeCadence(take, renditions, doc) {
	const fps = targetOf(doc);
	const from = positive(take?.fps);
	if (!take || take.kind === 'keyframe' || take.status !== 'done' || fps === null || from === null) return { state: 'none', from, to: fps, rendition: null };
	if (!needsConform(from, fps)) return { state: nearlyAsFast(from, fps) ? 'near' : 'none', from, to: fps, rendition: null };
	const current = renditionFor(renditions, take.id, fps);
	if (current?.status === 'done') return { state: 'conformed', from, to: fps, rendition: current };
	if (current) return { state: 'conforming', from, to: fps, rendition: current };
	const last = lastRendition(renditions, take.id, fps);
	return { state: last?.status === 'failed' ? 'failed' : 'slow', from, to: fps, rendition: last };
}

export function placedTakes(doc, takes) {
	const byId = new Map((takes ?? []).map((take) => [take.id, take]));
	const assets = new Map((doc?.assets ?? []).map((asset) => [asset.id, asset]));
	const placed = [];
	for (const clip of doc?.clips ?? []) {
		const asset = assets.get(clip.assetId);
		const take = asset?.resultId ? byId.get(asset.resultId) : null;
		if (take && !placed.some((item) => item.take.id === take.id)) placed.push({ clip, take });
	}
	return placed;
}

export function exportCadence(doc, takes, renditions) {
	const fps = targetOf(doc);
	const slow = [];
	const conforming = [];
	const conformed = [];
	const near = new Map();
	for (const { take } of placedTakes(doc, takes)) {
		const found = takeCadence(take, renditions, doc);
		if (found.state === 'slow' || found.state === 'failed') slow.push(take);
		else if (found.state === 'conforming') conforming.push(take);
		else if (found.state === 'conformed') conformed.push(take);
		else if (found.state === 'near') near.set(found.from, (near.get(found.from) ?? 0) + 1);
	}
	const rates = [...new Set(slow.map((take) => take.fps))].sort((a, b) => a - b);
	return {
		fps,
		slow,
		rates,
		conforming,
		conformed,
		near: [...near].map(([rate, count]) => ({ fps: rate, count })).sort((a, b) => a.fps - b.fps)
	};
}

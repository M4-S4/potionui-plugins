import table from './formatstable.js';

export const CADENCES = [...table.cadence.values];
export const DEFAULT_CADENCE = table.cadence.default;
export const SLOWER = table.cadence.slower;
export const INTERPOLATORS = ['auto', 'rife', 'rtx'];
export const ACTIVE_RENDITIONS = ['waiting', 'queued', 'running'];
export const SPEEDS = [...table.cadence.speeds];
export const SLOW_SPEEDS = SPEEDS.filter((speed) => speed < 1);

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

export function speedOf(clip) {
	return SLOW_SPEEDS.includes(clip?.speed) ? clip.speed : 1;
}

export function sourceSeconds(clip, seconds = clip?.dur ?? 0) {
	return seconds * speedOf(clip);
}

export function neededFps(doc, clip, take) {
	const film = targetOf(doc);
	if (film === null || !take) return null;
	const fps = film / speedOf(clip);
	return needsConform(take.fps, fps) ? fps : null;
}

export function finalCadence(doc, take) {
	const clip = (doc?.clips ?? []).find((c) => c.id === take?.shotId) ?? null;
	const fps = neededFps(doc, clip, take);
	return { slow: fps !== null, from: positive(take?.fps), fps };
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

export function shotCadence(take, clip, renditions, doc) {
	const film = targetOf(doc);
	const from = positive(take?.fps);
	const speed = speedOf(clip);
	if (!take || take.kind === 'keyframe' || take.status !== 'done' || film === null || from === null) return { state: 'none', from, to: film, speed, rendition: null };
	const fps = film / speed;
	if (!needsConform(from, fps)) return { state: speed === 1 && nearlyAsFast(from, fps) ? 'near' : 'none', from, to: fps, speed, rendition: null };
	const current = renditionFor(renditions, take.id, fps);
	if (current?.status === 'done') return { state: 'conformed', from, to: fps, speed, rendition: current };
	if (current) return { state: 'conforming', from, to: fps, speed, rendition: current };
	const last = lastRendition(renditions, take.id, fps);
	return { state: last?.status === 'failed' ? 'failed' : 'slow', from, to: fps, speed, rendition: last };
}

export function takeCadence(take, renditions, doc) {
	const clip = (doc?.clips ?? []).find((c) => c.id === take?.shotId) ?? null;
	return shotCadence(take, clip, renditions, doc);
}

export function placedTakes(doc, takes) {
	const byId = new Map((takes ?? []).map((take) => [take.id, take]));
	const assets = new Map((doc?.assets ?? []).map((asset) => [asset.id, asset]));
	const placed = [];
	for (const clip of doc?.clips ?? []) {
		const asset = assets.get(clip.assetId);
		const take = asset?.resultId ? byId.get(asset.resultId) : null;
		if (take) placed.push({ clip, take });
	}
	return placed;
}

export function exportCadence(doc, takes, renditions) {
	const fps = targetOf(doc);
	const slow = [];
	const slowed = [];
	const conforming = [];
	const conformed = [];
	const near = new Map();
	for (const { clip, take } of placedTakes(doc, takes)) {
		const found = shotCadence(take, clip, renditions, doc);
		if (found.state === 'slow' || found.state === 'failed') (found.speed < 1 ? slowed : slow).push(take);
		else if (found.state === 'conforming') conforming.push(take);
		else if (found.state === 'conformed') conformed.push(take);
		else if (found.state === 'near') near.set(found.from, (near.get(found.from) ?? 0) + 1);
	}
	const rates = [...new Set(slow.map((take) => take.fps))].sort((a, b) => a - b);
	return {
		fps,
		slow,
		slowed,
		rates,
		conforming,
		conformed,
		near: [...near].map(([rate, count]) => ({ fps: rate, count })).sort((a, b) => a.fps - b.fps)
	};
}

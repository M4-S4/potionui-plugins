import { UPSCALE_TARGETS, isInFlight, upscalesItself } from './generation.js';
import { labelOf } from './labels.js';
import { isStale } from './shots.js';
import { INTERPOLATORS } from './cadence.js';

export const PASS_METHODS = ['upscale', 'guided', 'render'];
export const GUIDED_PRESET = '01KX47LTX25VIDEO00000000TV';
export const UPSCALERS = ['auto', 'rtx', 'seedvr2', 'engine'];
export const RTX_SOURCES = ['compressed', 'clean'];
export const DEFAULT_RTX_SOURCE = 'compressed';
export const AUTO_TARGET = 'auto';
export const PASS_TARGETS = [AUTO_TARGET, ...UPSCALE_TARGETS];
export const PASS_STATES = ['ready', 'running', 'done', 'missing', 'source'];

const finished = (take) => take?.status === 'done' && Boolean(take.url);
const video = (take) => take?.kind !== 'keyframe';
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const newest = (list) => [...list].sort((a, b) => String(a.createdAt ?? '').localeCompare(String(b.createdAt ?? ''))).at(-1) ?? null;

export function passShot(clip, takes) {
	if (clip?.stage === 'source') return { state: 'source', final: null, source: null, take: null, stale: false, failed: null };
	const own = (takes ?? []).filter((x) => x.shotId === clip?.id && video(x));
	const finals = own.filter((x) => finished(x) && labelOf(x) === 'final');
	const final = finals.find((x) => x.id === clip?.take) ?? finals[0] ?? null;
	const flying = own.find((x) => x.quality === 'final' && isInFlight(x)) ?? null;
	const parent = final?.quality === 'final' ? (own.find((x) => x.id === final.parentTakeId && finished(x)) ?? null) : null;
	const source = final ? (parent ?? final) : null;
	const children = source ? own.filter((x) => x.parentTakeId === source.id && x.quality === 'final' && !isInFlight(x)) : [];
	const last = newest(children);
	const failed = last && (last.status === 'failed' || last.status === 'cancelled') ? last : null;
	const stale = final ? isStale(final, clip) : false;
	const state = flying ? 'running' : !final ? 'missing' : final.quality === 'final' ? 'done' : 'ready';
	return { state, final, source, take: flying, stale, failed };
}

export function passPlan(clips, takes, redo = false) {
	const rows = (clips ?? []).map((clip) => {
		const row = { clip, ...passShot(clip, takes) };
		return { ...row, include: row.state === 'ready' || (redo && row.state === 'done') };
	});
	const counts = Object.fromEntries(PASS_STATES.map((state) => [state, rows.filter((row) => row.state === state).length]));
	const included = rows.filter((row) => row.include);
	return {
		rows,
		counts,
		included,
		sources: included.map((row) => row.source.id),
		missing: rows.filter((row) => row.state === 'missing').map((row) => row.clip),
		generated: rows.length - counts.source
	};
}

export function passProgress(clips, takes) {
	const { counts, generated } = passPlan(clips, takes);
	return { generated, done: counts.done, running: counts.running, ready: counts.ready, missing: counts.missing, complete: generated > 0 && counts.done === generated };
}

export function passFlying(takes) {
	return (takes ?? []).filter((x) => x.quality === 'final' && x.parentTakeId && PASS_METHODS.includes(x.kind) && isInFlight(x));
}

export function migratePass(value) {
	if (!isObject(value)) return null;
	const kept = {};
	if (PASS_METHODS.includes(value.method)) kept.method = value.method;
	if (PASS_TARGETS.includes(value.target)) kept.target = value.target;
	if (UPSCALERS.includes(value.upscaler)) kept.upscaler = value.upscaler;
	if (RTX_SOURCES.includes(value.rtxSource)) kept.rtxSource = value.rtxSource;
	if (INTERPOLATORS.includes(value.interpolator)) kept.interpolator = value.interpolator;
	return Object.keys(kept).length ? kept : null;
}

export function passChoice(saved, targets = PASS_TARGETS, guided = false) {
	const kept = migratePass(saved) ?? {};
	const method = kept.method === 'guided' && !guided ? 'upscale' : (kept.method ?? 'upscale');
	const target = targets.includes(kept.target) ? kept.target : (targets[0] ?? AUTO_TARGET);
	return { method, target, upscaler: kept.upscaler ?? 'auto', rtxSource: kept.rtxSource ?? DEFAULT_RTX_SOURCE, interpolator: kept.interpolator ?? 'auto', conform: true };
}

export function upscalerReady(upscaler, me, presetIds = []) {
	const ready = me?.features?.upscalers ?? {};
	const own = presetIds.every((id) => upscalesItself(id));
	if (upscaler === 'rtx') return ready.rtx === true;
	if (upscaler === 'seedvr2') return ready.seedvr2 === true;
	if (upscaler === 'engine') return own;
	return me?.features?.upscaler === true || own;
}

export function rtxSourceShown(upscaler, me) {
	const ready = me?.features?.upscalers ?? {};
	return upscaler === 'rtx' || (upscaler === 'auto' && ready.rtx === true && ready.seedvr2 !== true);
}

export function passBody(sources, choice) {
	const body = { takes: [...sources], method: choice.method, target: choice.target };
	if (choice.method === 'upscale' && choice.upscaler !== 'auto') body.upscaler = choice.upscaler;
	if (choice.method === 'upscale' && RTX_SOURCES.includes(choice.rtxSource) && choice.rtxSource !== DEFAULT_RTX_SOURCE) body.rtx_source = choice.rtxSource;
	if (choice.conform === true) body.conform = true;
	return body;
}

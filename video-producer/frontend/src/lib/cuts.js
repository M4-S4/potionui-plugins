import { newAsset, newClip } from './starter.js';

export const CUT_TOOL = 'cut_finder';
export const SENSITIVITY = { min: 0, max: 100, step: 5, value: 50 };
export const SHORTEST = { min: 0.1, max: 30, step: 0.1, value: 0.5 };
export const CUT_MODES = ['source', 'motion'];
export const MAX_CUT_SHOTS = 200;
export const POLL_MS = 700;
export const NAME_LENGTH = 60;
const STEP = 0.04;

export function cutInput(origin) {
	if (origin?.kind === 'library' && typeof origin.itemId === 'string' && origin.itemId) return { item_id: origin.itemId };
	if (origin?.kind === 'history' && typeof origin.fileId === 'string' && origin.fileId) return { generation_file_id: origin.fileId };
	return null;
}

export const cuttable = (asset) => asset?.kind === 'video' && cutInput(asset.origin) !== null;

export function bounded(value, { min, max, value: fallback }) {
	const n = Number(value);
	return value === null || value === '' || !Number.isFinite(n) ? fallback : Math.min(max, Math.max(min, n));
}

export function cutRequest(origin, { sensitivity, shortest } = {}) {
	const input = cutInput(origin);
	if (!input) return null;
	const params = { sensitivity: bounded(sensitivity, SENSITIVITY), min_shot_seconds: bounded(shortest, SHORTEST) };
	return { steps: [{ tool: CUT_TOOL, params }], inputs: [input], output: { mode: 'new' } };
}

export function shotLength(duration) {
	const n = Number(duration);
	if (duration === null || !Number.isFinite(n) || n <= 0) return null;
	return Math.max(STEP, +(Math.floor(n / STEP + 1e-6) * STEP).toFixed(3));
}

export function cutName(name, fallback) {
	const stem = String(name ?? '')
		.replace(/\.[A-Za-z0-9]{2,5}$/, '')
		.trim();
	return (stem || fallback).slice(0, NAME_LENGTH);
}

export function cutFailure(error) {
	if (!error) return null;
	if (error.code === 'too_many_queued') return 'busy';
	if (error.code === 'invalid_params' && /shot limit/i.test(error.message ?? '')) return 'tooMany';
	if (error.code === 'tool_failed' && /no cuts/i.test(error.message ?? '')) return 'none';
	return 'failed';
}

export function buildCuts(items, { mode, label, makeId }) {
	const pieces = (items ?? []).filter((item) => item?.id && item.url && item.mediaType === 'video');
	const assets = [];
	const clips = [];
	const references = [];
	pieces.forEach((item, i) => {
		const name = label(i + 1);
		const size = item.width && item.height ? { width: item.width, height: item.height, res: `${item.width}×${item.height}` } : {};
		const asset = newAsset({ id: makeId(), kind: 'video', name: item.name || name, src: item.url, origin: { kind: 'library', itemId: item.id }, srcDur: item.duration ?? null, fps: item.fps ?? null, ...size });
		const own = mode === 'motion' ? {} : { assetId: asset.id, stage: 'source' };
		const clip = newClip({ id: makeId(), label: name, dur: shotLength(item.duration) ?? 4, firstFromPrevious: false, ...own });
		assets.push(asset);
		clips.push(clip);
		if (mode === 'motion') references.push({ id: makeId(), name, space: 'mouvement', type: 'Control video', assetId: asset.id, role: 'Mouvement', scope: { type: 'shot', shotId: clip.id } });
	});
	return { assets, clips, references };
}

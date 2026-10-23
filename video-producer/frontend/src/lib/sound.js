import { laneAudible } from './tracks.js';
import { excludedLanesOf, excludedOf, isGlobal, ownsReference } from './shots.js';

export { excludedLanesOf, setExcludedLanes } from './shots.js';

export const SOUND_SPACE = 'son';
export const SOUND_TYPES = ['Voix', 'Musique', 'Ambiance'];
export const SOUND_ROLE = 'Son';
export const MAX_MARGIN = 10;

export const CONDITION = 'condition';
export const MUX = 'mux';
export const IGNORED = 'ignored';

const EPSILON = 1e-6;

export function referenceMargin(engine) {
	const value = engine?.referenceMargin;
	return typeof value === 'number' && Number.isFinite(value) ? Math.min(MAX_MARGIN, Math.max(0, value)) : 0;
}

export function setReferenceMargin(engine, value) {
	const n = Math.round(Math.min(MAX_MARGIN, Math.max(0, Number(value) || 0)) * 10) / 10;
	if (n > 0) engine.referenceMargin = n;
	else delete engine.referenceMargin;
}

export const isReferenceLane = (lane) => lane?.reference === true;

export function setReferenceLane(lane, on) {
	if (on) lane.reference = true;
	else delete lane.reference;
}

export function referenceLanes(doc, clip, excluded = excludedLanesOf(clip)) {
	const skip = new Set(excluded);
	return (doc?.lanes ?? []).filter(isReferenceLane).map((lane) => ({ lane, excluded: skip.has(lane.id) }));
}

export function conditionWindow(doc, clip) {
	const margin = referenceMargin(doc?.engine);
	return [Math.max(0, clip.start - margin), clip.start + clip.dur + margin];
}

export const muxWindow = (clip) => [clip.start, clip.start + clip.dur];

export function trackPortion(doc, laneId, [start, end]) {
	return (doc?.audio ?? [])
		.filter((item) => item.lane === laneId && item.dur > EPSILON && Math.min(end, item.start + item.dur) - Math.max(start, item.start) > EPSILON)
		.sort((a, b) => a.start - b.start)
		.map((item) => ({ item, from: Math.max(start, item.start), to: Math.min(end, item.start + item.dur) }));
}

const audioAsset = (doc, reference) => (doc?.assets ?? []).find((a) => a.id === reference?.assetId && a.kind === 'audio') ?? null;

export function soundReferences(doc, clip) {
	const references = (doc?.references ?? []).filter((r) => audioAsset(doc, r));
	const skip = new Set(excludedOf(clip));
	return [...references.filter((r) => ownsReference(clip, r)), ...references.filter((r) => isGlobal(r) && !skip.has(r.id))];
}

export function audioBehavior(preset, profile) {
	if (!preset) return null;
	if (profile === 'Ref2VA') return CONDITION;
	if (preset.cloud) return IGNORED;
	return preset.audioMux ? MUX : IGNORED;
}

export function shotSound(doc, clip, preset, profile) {
	if (!clip) return null;
	const references = soundReferences(doc, clip);
	const lanes = referenceLanes(doc, clip).filter((x) => !x.excluded).map((x) => x.lane);
	if (!references.length && !lanes.length) return null;
	const behavior = audioBehavior(preset, profile);
	const window = behavior === CONDITION ? conditionWindow(doc, clip) : muxWindow(clip);
	const sent = [];
	const warnings = [];
	for (const lane of lanes) {
		if (!laneAudible(doc, lane)) warnings.push({ code: 'audio_track_muted', laneId: lane.id });
		else if (!trackPortion(doc, lane.id, window).length) warnings.push({ code: 'audio_track_empty', laneId: lane.id });
		else sent.push(lane.id);
	}
	return { behavior, window, references, lanes: sent, warnings, sends: behavior !== IGNORED && (sent.length > 0 || references.length > 0) };
}

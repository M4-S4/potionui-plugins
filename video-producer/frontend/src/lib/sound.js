import { joinRuns, laneAudible, sliceChain } from './tracks.js';
import { excludedLanesOf, excludedOf, isGlobal, ownsReference } from './shots.js';
import { voiceReferences } from './bible.js';
import formats from './formatstable.js';

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

export const hasOwnReference = (item) => typeof item?.reference === 'boolean';

export const isReferenceItem = (item, lane) => (hasOwnReference(item) ? item.reference : isReferenceLane(lane));

export function setReferenceItem(item, lane, on) {
	if (on === isReferenceLane(lane)) delete item.reference;
	else item.reference = on;
}

export function followLane(item) {
	delete item.reference;
}

const laneOf = (doc, laneId) => (doc?.lanes ?? []).find((lane) => lane.id === laneId) ?? null;

export function joinPlan(doc, item) {
	const lane = laneOf(doc, item.lane);
	const chain = sliceChain(doc, item);
	return { chain, runs: joinRuns(chain, (a, b) => isReferenceItem(a, lane) === isReferenceItem(b, lane) && a.gain === b.gain) };
}

const itemsUnder = (doc, laneId, [start, end]) =>
	(doc?.audio ?? []).filter((item) => item.lane === laneId && item.dur > EPSILON && Math.min(end, item.start + item.dur) - Math.max(start, item.start) > EPSILON);

export const freeReferenceLane = (doc, span) => (doc?.lanes ?? []).find((lane) => isReferenceLane(lane) && !itemsUnder(doc, lane.id, span).length) ?? null;

export const takeSound = ({ id, assetId, lane, start, dur, fromTake }) => ({ id, assetId, lane, start, dur, srcIn: 0, fadeIn: 0, fadeOut: 0, gain: 0, fromTake });

export function conditionWindow(doc, clip) {
	const margin = referenceMargin(doc?.engine);
	return [Math.max(0, clip.start - margin), clip.start + clip.dur + margin];
}

export const muxWindow = (clip) => [clip.start, clip.start + clip.dur];

export function referenceLanes(doc, clip, excluded = excludedLanesOf(clip), window = conditionWindow(doc, clip)) {
	const skip = new Set(excluded);
	return (doc?.lanes ?? [])
		.filter((lane) => {
			const heard = itemsUnder(doc, lane.id, window);
			return heard.some((item) => isReferenceItem(item, lane)) || (!heard.length && isReferenceLane(lane));
		})
		.map((lane) => ({ lane, excluded: skip.has(lane.id) }));
}

export function trackPortion(doc, laneId, [start, end]) {
	const lane = laneOf(doc, laneId);
	return itemsUnder(doc, laneId, [start, end])
		.filter((item) => isReferenceItem(item, lane))
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
	if (profile === 'Ref2VA' && !formats.engines.ltx.presets.includes(preset.id)) return CONDITION;
	if (preset.cloud) return IGNORED;
	return preset.audioMux ? MUX : IGNORED;
}

export function shotSound(doc, clip, preset, profile) {
	if (!clip) return null;
	const behavior = audioBehavior(preset, profile);
	const window = behavior === CONDITION ? conditionWindow(doc, clip) : muxWindow(clip);
	const voices = voiceReferences(doc);
	const references = soundReferences(doc, clip).filter((r) => behavior === CONDITION || !voices.has(r.id));
	const lanes = referenceLanes(doc, clip, excludedLanesOf(clip), window)
		.filter((x) => !x.excluded)
		.map((x) => x.lane);
	if (!references.length && !lanes.length) return null;
	const sent = [];
	const warnings = [];
	for (const lane of lanes) {
		if (!laneAudible(doc, lane)) warnings.push({ code: 'audio_track_muted', laneId: lane.id });
		else if (!trackPortion(doc, lane.id, window).length) warnings.push({ code: 'audio_track_empty', laneId: lane.id });
		else sent.push(lane.id);
	}
	return { behavior, window, references, lanes: sent, warnings, sends: behavior !== IGNORED && (sent.length > 0 || references.length > 0) };
}

import { chainOn, chainSource, ignoresFirstFrame, sameFrame } from './chain.js';
import { presetProfiles } from './generation.js';
import { previousShot, seamImage } from './seam.js';

export const MAKE = ['first', 'last', 'both'];
export const RETRIEVE = ['previous', 'next', 'neighbors'];
export const CHOICES = [...MAKE, ...RETRIEVE];

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const assetOf = (doc, id) => (id ? ((doc.assets ?? []).find((a) => a.id === id) ?? null) : null);
const flying = (take) => take?.kind !== 'keyframe' && (take?.status === 'queued' || take?.status === 'running');
const round = (value) => Math.round(Math.max(0, value ?? 0) * 1000) / 1000;

export const retrieves = (choice) => RETRIEVE.includes(choice);
export const targetsStart = (choice) => ['first', 'both', 'previous', 'neighbors'].includes(choice);
export const targetsEnd = (choice) => ['last', 'both', 'next', 'neighbors'].includes(choice);
export const sidesOf = (choice) => (choice === 'neighbors' ? ['previous', 'next'] : retrieves(choice) ? [choice] : []);

export function nextShot(doc, shotId) {
	const clips = doc?.clips ?? [];
	const i = clips.findIndex((c) => c.id === shotId);
	return i >= 0 && i < clips.length - 1 ? clips[i + 1] : null;
}

export function startOfCut(doc, clip) {
	const a = assetOf(doc, clip?.assetId);
	if (!a?.src) return null;
	if (a.kind === 'image') return { shotId: clip.id, takeId: null, assetId: a.id, at: null };
	if (a.kind !== 'video' || !(a.origin || a.generated)) return null;
	return { shotId: clip.id, takeId: a.generated ? (a.resultId ?? null) : null, assetId: a.id, at: round(clip.srcIn) };
}

export const draftChained = (doc, draft) => (typeof draft?.firstFromPrevious === 'boolean' ? draft.firstFromPrevious : chainOn(doc));

export function previousSource(doc, clip, draft, takes = []) {
	const shot = clip ? previousShot(doc, clip.id) : null;
	if (!shot) return { side: 'previous', state: 'none', shot: null };
	const source = chainSource(doc, shot);
	const image = assetOf(doc, draft?.first);
	if (source) {
		const taken = isObject(image?.frameOf) && image.frameOf.shotId === shot.id;
		return { side: 'previous', state: taken && sameFrame(doc, image.frameOf, source) ? 'current' : taken ? 'stale' : 'ready', shot, source };
	}
	const take = takes.find((x) => x.shotId === shot.id && flying(x));
	if (!take) return { side: 'previous', state: 'empty', shot };
	return { side: 'previous', state: draftChained(doc, draft) && !draft?.first ? 'linked' : 'pending', shot, take };
}

export function nextSource(doc, clip, draft, takes = []) {
	const shot = clip ? nextShot(doc, clip.id) : null;
	if (!shot) return { side: 'next', state: 'none', shot: null };
	const image = assetOf(doc, draft?.last);
	const source = startOfCut(doc, shot);
	if (source) {
		const taken = isObject(image?.frameOf) && image.frameOf.shotId === shot.id && image.frameOf.assetId === source.assetId && image.frameOf.at === source.at;
		const same = source.at === null && image?.id === source.assetId;
		return { side: 'next', state: taken || same ? 'current' : 'ready', shot, source };
	}
	const start = seamImage(doc, shot.id, 'first');
	if (start) return { side: 'next', state: image?.id === start.id ? 'current' : 'ready', shot, image: start };
	const take = takes.find((x) => x.shotId === shot.id && flying(x));
	return take ? { side: 'next', state: 'pending', shot, take } : { side: 'next', state: 'empty', shot };
}

export function neighborSources(doc, clip, draft, takes = []) {
	return { previous: previousSource(doc, clip, draft, takes), next: nextSource(doc, clip, draft, takes) };
}

const usable = (source) => source.state === 'ready' || source.state === 'stale' || (source.side === 'previous' && source.state === 'pending');
export const inPlace = (source) => source.state === 'current' || source.state === 'linked';

export function retrieveChoices(sources) {
	const of = (side) => ({ id: side, sources: [sources[side]], enabled: usable(sources[side]), done: inPlace(sources[side]) });
	const both = [sources.previous, sources.next];
	const neighbors = { id: 'neighbors', sources: both, enabled: both.every((x) => usable(x) || inPlace(x)) && both.some(usable), done: both.every(inPlace) };
	return [of('previous'), of('next'), neighbors];
}

export function takesLastFrame(option) {
	if (!option) return true;
	if (option.kind === 'cloud') return option.modelInfo?.lastFrame !== false;
	const modes = option.info?.directorModes ?? [];
	return modes.length === 0 || modes.includes('flf');
}

export function frameNotes({ option, profile, choice, hasStart, chained }) {
	const start = targetsStart(choice);
	const end = targetsEnd(choice);
	if (option && profile === 'Ref2VA' && presetProfiles(option.info).includes('Ref2VA')) return ['refs'];
	if (ignoresFirstFrame(option)) return ['textOnly'];
	const notes = [];
	if (end && !takesLastFrame(option)) notes.push('noLastFrame');
	else if (end && !start && !hasStart && !chained) notes.push('endWithoutStart');
	return notes;
}

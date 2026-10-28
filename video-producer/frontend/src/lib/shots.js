import { labelOf } from './labels.js';
import { SEAM_STRENGTH, frameTime, framesOf } from './seam.js';
import { migrateShotEngine, setShotEngine, shotEngineOf } from './engine.js';
import { KINDS, castCards, castOf, cardsOf, migrateCast, sameCast, setCast, usable } from './bible.js';
import { linesOf, migrateDialogue, sameDialogue, setDialogue } from './dialogue.js';
import { migrateReferencePrompt, referencePromptOf, sameReferencePrompt, setReferencePrompt } from './refprompt.js';
import { merge3 } from './merge.js';

export const MIN_DRAFTS = 1;
export const MAX_DRAFTS = 8;

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const count = (value) => (Number.isInteger(value) ? Math.min(MAX_DRAFTS, Math.max(MIN_DRAFTS, value)) : null);

export const projectDrafts = (engine) => count(engine?.variants) ?? MIN_DRAFTS;

export function draftsOf(clip, engine) {
	return count(clip?.drafts) ?? projectDrafts(engine);
}

export function sharedDrafts(clips, engine) {
	const values = [...new Set(clips.map((c) => draftsOf(c, engine)))];
	return values.length === 1 ? values[0] : null;
}

export function setDrafts(clips, value) {
	const n = count(Number(value));
	if (n === null) return false;
	for (const c of clips) c.drafts = n;
	return true;
}

export function generationCounts(clips, engine, override = null) {
	const forced = count(override);
	if (forced !== null) return { variants: forced, shot_variants: {} };
	const variants = projectDrafts(engine);
	const shot_variants = {};
	for (const c of clips) {
		const n = draftsOf(c, engine);
		if (n !== variants) shot_variants[c.id] = n;
	}
	return { variants, shot_variants };
}

export function takeCount(clips, engine, override = null) {
	const { variants, shot_variants } = generationCounts(clips, engine, override);
	return clips.reduce((sum, c) => sum + (shot_variants[c.id] ?? variants), 0);
}

export const isGlobal = (reference) => !isObject(reference?.scope) || reference.scope.type !== 'shot';
export const ownsReference = (clip, reference) => !isGlobal(reference) && reference.scope.shotId === clip?.id;

export function excludedOf(clip) {
	const exclude = clip?.referenceOverrides?.exclude;
	return Array.isArray(exclude) ? exclude.filter((id) => typeof id === 'string' && id) : [];
}

const idList = (list) => [...new Set((Array.isArray(list) ? list : []).filter((id) => typeof id === 'string' && id))];

function setOverride(clip, key, ids) {
	const unique = idList(ids);
	if (unique.length) clip.referenceOverrides = { ...(isObject(clip.referenceOverrides) ? clip.referenceOverrides : {}), [key]: unique };
	else if (isObject(clip.referenceOverrides)) {
		const { [key]: dropped, ...rest } = clip.referenceOverrides;
		if (Object.keys(rest).length) clip.referenceOverrides = rest;
		else delete clip.referenceOverrides;
	}
}

export function setExcluded(clip, ids) {
	setOverride(clip, 'exclude', ids);
}

export const excludedLanesOf = (clip) => idList(clip?.referenceOverrides?.excludeLanes);

export function setExcludedLanes(clip, ids) {
	setOverride(clip, 'excludeLanes', ids);
}

export const excludedVrefsOf = (clip) => idList(clip?.referenceOverrides?.excludeVrefs);

export function setExcludedVrefs(clip, ids) {
	setOverride(clip, 'excludeVrefs', ids);
}

const cardReferences = (card) => idList(card?.references);

export function shotReferences(doc, clip, excluded = excludedOf(clip), cast = clip?.cast) {
	const references = Array.isArray(doc?.references) ? doc.references : [];
	const skip = new Set(excluded);
	const own = references.filter((r) => ownsReference(clip, r));
	const placed = new Set(own.map((r) => r.id));
	const chosen = castCards(doc, cast);
	const fromCast = [];
	for (const card of [...chosen.characters, ...(chosen.place ? [chosen.place] : [])]) {
		for (const id of cardReferences(card)) {
			const reference = references.find((r) => r?.id === id);
			if (!reference || placed.has(id)) continue;
			placed.add(id);
			fromCast.push({ reference, excluded: skip.has(id) });
		}
	}
	const linked = new Set(KINDS.flatMap((kind) => cardsOf(doc, kind).filter(usable).flatMap(cardReferences)));
	const casting = new Set(fromCast.map((x) => x.reference.id));
	return {
		inherited: references.filter(isGlobal).map((reference) => ({ reference, excluded: skip.has(reference.id), cast: casting.has(reference.id), notCast: !casting.has(reference.id) && linked.has(reference.id) })),
		cast: fromCast,
		own
	};
}

export const isShared = (x) => !x.excluded && !x.cast && !x.notCast;

export function sentReferences(doc, clip) {
	const { inherited, cast, own } = shotReferences(doc, clip);
	return [...own, ...cast.filter((x) => !x.excluded).map((x) => x.reference), ...inherited.filter(isShared).map((x) => x.reference)];
}

export const revisionOf = (clip) => (Number.isInteger(clip?.revision) && clip.revision > 0 ? clip.revision : 0);

export function touch(clip) {
	if (clip) clip.revision = revisionOf(clip) + 1;
}

export function isStale(take, clip) {
	if (!take || !clip) return false;
	return (Number.isInteger(take.shotRevision) ? take.shotRevision : 0) < revisionOf(clip);
}

export function shotStale(clip, takes) {
	const finished = (takes ?? []).filter((x) => x.status === 'done');
	if (!finished.length) return false;
	const placed = finished.find((x) => x.id === clip?.take) ?? finished.find((x) => labelOf(x) === 'final');
	return placed ? isStale(placed, clip) : finished.every((x) => isStale(x, clip));
}

const sameList = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

export function inputsChanged(before, after) {
	return (
		before.text.trim() !== after.text.trim() ||
		Math.abs(Number(before.dur) - Number(after.dur)) > 1e-6 ||
		before.first !== after.first ||
		before.last !== after.last ||
		!sameList([...before.exclude].sort(), [...after.exclude].sort()) ||
		!sameList([...(before.excludeLanes ?? [])].sort(), [...(after.excludeLanes ?? [])].sort()) ||
		!sameList([...(before.excludeVrefs ?? [])].sort(), [...(after.excludeVrefs ?? [])].sort()) ||
		!sameList(before.own.map((r) => `${r.id}:${r.assetId}:${r.type}`), after.own.map((r) => `${r.id}:${r.assetId}:${r.type}`)) ||
		!sameCast(before.cast, after.cast) ||
		!sameDialogue(before.dialogue, after.dialogue) ||
		!sameReferencePrompt(before.referencePrompt, after.referencePrompt)
	);
}

const MAX_STORED_DRAFTS = 16;

function migrateClip(clip) {
	if (!isObject(clip)) return clip;
	const next = migrateShotEngine({ ...clip });
	if ('drafts' in next && !(Number.isInteger(next.drafts) && next.drafts >= MIN_DRAFTS && next.drafts <= MAX_STORED_DRAFTS)) delete next.drafts;
	if ('revision' in next && !(Number.isInteger(next.revision) && next.revision >= 0)) delete next.revision;
	if ('firstFromPrevious' in next && typeof next.firstFromPrevious !== 'boolean') delete next.firstFromPrevious;
	if ('referenceOverrides' in next) {
		const kept = Object.entries({ exclude: idList(excludedOf(next)), excludeLanes: excludedLanesOf(next), excludeVrefs: excludedVrefsOf(next) }).filter(([, list]) => list.length);
		if (kept.length) next.referenceOverrides = Object.fromEntries(kept);
		else delete next.referenceOverrides;
	}
	if ('referencePrompt' in next) {
		const override = migrateReferencePrompt(next.referencePrompt);
		if (override) next.referencePrompt = override;
		else delete next.referencePrompt;
	}
	if ('cast' in next) {
		const cast = migrateCast(next.cast);
		if (cast) next.cast = cast;
		else delete next.cast;
	}
	if ('dialogue' in next) {
		const lines = migrateDialogue(next.dialogue);
		if (lines) next.dialogue = lines;
		else delete next.dialogue;
	}
	return next;
}

export function migrateShots(doc) {
	if (!isObject(doc) || !Array.isArray(doc.clips)) return doc;
	return { ...doc, clips: doc.clips.map(migrateClip) };
}

const MIN_SHOT = 0.4;
const snap = (value) => +(Math.round(value / 0.04) * 0.04).toFixed(3);
export const SHOT_CAP = 60;
export const TAKE_SLACK = 0.05;

export function durationLimit(doc, clip, engineMax = null) {
	const media = (doc.assets ?? []).find((a) => a.id === clip?.assetId) ?? null;
	const srcIn = clip?.srcIn ?? 0;
	const length = typeof media?.srcDur === 'number' ? media.srcDur : null;
	if (media?.generated) {
		const take = length === null ? null : length - srcIn;
		return engineMax > 0 ? { max: engineMax, by: 'engine', take } : { max: SHOT_CAP, by: null, take };
	}
	return { max: (length ?? SHOT_CAP) - srcIn, by: length ? 'source' : null, take: null };
}

export const overrunsTake = (take, before, dur) => take !== null && dur > before + 1e-6 && dur > take + TAKE_SLACK;

export function releaseShot(clip) {
	const released = { take: clip.take ?? null };
	Object.assign(clip, { assetId: null, take: null, srcIn: 0, stage: 'todo' });
	return released;
}

export function releaseOverrun(doc, clip, before) {
	if (!overrunsTake(durationLimit(doc, clip).take, before, clip.dur)) return null;
	return releaseShot(clip);
}
const promptFor = (doc, clip) => (doc.prompts ?? []).find((p) => p.shotId === clip.id) ?? null;
const frameAsset = (doc, clip, kind) => framesOf(doc, clip.id, kind).find((f) => f.assetId)?.assetId ?? null;
const ownCopy = (r) => ({ id: r.id, name: r.name, space: r.space, type: r.type, assetId: r.assetId ?? null, role: r.role });

export function shotDraft(doc, clip, engine) {
	return {
		text: promptFor(doc, clip)?.text ?? '',
		dur: clip.dur,
		first: frameAsset(doc, clip, 'first'),
		last: frameAsset(doc, clip, 'last'),
		exclude: excludedOf(clip),
		excludeLanes: excludedLanesOf(clip),
		excludeVrefs: excludedVrefsOf(clip),
		own: shotReferences(doc, clip).own.map(ownCopy),
		drafts: draftsOf(clip, engine),
		engine: shotEngineOf(clip),
		cast: castOf(clip),
		dialogue: linesOf(clip),
		referencePrompt: referencePromptOf(clip),
		firstFromPrevious: typeof clip.firstFromPrevious === 'boolean' ? clip.firstFromPrevious : null
	};
}

export function rebaseDraft(before, draft, current) {
	const { value, conflicts } = merge3(before, draft, current);
	const lists = { exclude: value.exclude ?? [], excludeLanes: value.excludeLanes ?? [], excludeVrefs: value.excludeVrefs ?? [], own: value.own ?? [] };
	return { draft: { ...value, ...lists, cast: castOf({ cast: value.cast }) }, conflicts };
}

function placeFrame(doc, clip, kind, assetId, makeId) {
	const existing = framesOf(doc, clip.id, kind);
	if (!assetId) {
		for (const f of existing) doc.frames.splice(doc.frames.indexOf(f), 1);
		return;
	}
	const fields = { shotId: clip.id, time: frameTime(clip, kind), assetId, role: kind, strength: existing[0]?.strength ?? SEAM_STRENGTH };
	if (existing.length) {
		Object.assign(existing[0], fields);
		for (const extra of existing.slice(1)) doc.frames.splice(doc.frames.indexOf(extra), 1);
	} else doc.frames.push({ id: makeId(), ...fields });
}

function writeReferences(doc, clip, own) {
	const kept = new Map(own.map((r) => [r.id, r]));
	for (let i = doc.references.length - 1; i >= 0; i--) {
		const r = doc.references[i];
		if (!ownsReference(clip, r)) continue;
		const next = kept.get(r.id);
		if (next) {
			Object.assign(r, { name: next.name, type: next.type, role: next.role, assetId: next.assetId });
			kept.delete(r.id);
		} else doc.references.splice(i, 1);
	}
	for (const r of kept.values()) doc.references.push({ ...r, scope: { type: 'shot', shotId: clip.id } });
}

export function applyShotDraft(doc, clip, before, draft, { makeId, maxDur = Infinity, engine = null } = {}) {
	const changed = inputsChanged(before, draft);
	const text = draft.text.trim();
	const prompt = promptFor(doc, clip);
	const covered = prompt && Math.abs(prompt.start - clip.start) < 1e-6 && Math.abs(prompt.dur - clip.dur) < 1e-6;
	const dur = snap(Math.min(Math.max(MIN_SHOT, Number(draft.dur) || clip.dur), Math.max(MIN_SHOT, maxDur)));
	const resized = Math.abs(dur - clip.dur) > 1e-6;
	const was = clip.dur;
	clip.dur = dur;
	if (prompt) {
		prompt.text = text;
		if (covered) prompt.dur = dur;
	} else if (text) doc.prompts.push({ id: makeId(), shotId: clip.id, start: clip.start, dur, strength: 75, text });
	if (resized || before.first !== draft.first) placeFrame(doc, clip, 'first', draft.first, makeId);
	if (resized || before.last !== draft.last) placeFrame(doc, clip, 'last', draft.last, makeId);
	setExcluded(clip, draft.exclude);
	if ('excludeLanes' in draft) setExcludedLanes(clip, draft.excludeLanes);
	if ('excludeVrefs' in draft) setExcludedVrefs(clip, draft.excludeVrefs);
	writeReferences(doc, clip, draft.own);
	if (draft.drafts !== before.drafts || Number.isInteger(clip.drafts)) clip.drafts = count(draft.drafts) ?? projectDrafts(engine);
	if ('engine' in draft) setShotEngine(clip, draft.engine);
	if ('cast' in draft) setCast(clip, draft.cast);
	if ('dialogue' in draft) setDialogue(clip, draft.dialogue);
	if ('referencePrompt' in draft) setReferencePrompt(clip, draft.referencePrompt);
	if ('firstFromPrevious' in draft && draft.firstFromPrevious !== before.firstFromPrevious) {
		if (typeof draft.firstFromPrevious === 'boolean') clip.firstFromPrevious = draft.firstFromPrevious;
		else delete clip.firstFromPrevious;
	}
	const released = resized ? releaseOverrun(doc, clip, was) : null;
	if (changed) touch(clip);
	return { changed, resized, released };
}

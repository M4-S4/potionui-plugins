import table from './reception.json';
import { isH3, presetProfiles } from './generation.js';
import { isGlobal, ownsReference, shotReferences } from './shots.js';
import { referencePromptOf } from './refprompt.js';
import { CHARACTERS, PLACES, cardsOf, shotsCasting, voiceReferences } from './bible.js';
import { MUX, audioBehavior } from './sound.js';

export const LIMITS = table.limits;
export const FAMILIES = ['cloud', 'h3'];
export const RECEIVED = ['sent', 'mixed'];
export const STATUSES = ['sent', 'trimmed', 'missing', 'mixed', 'ignored', 'excluded', 'blocked', 'unknown'];

export const takesReferences = (profile) => table.references.includes(profile);
export const familyOf = (info) => (info?.cloud ? 'cloud' : isH3(info) ? 'h3' : 'other');

const matches = (rule, family, profile) => (!rule.profiles || rule.profiles.includes(profile)) && (!rule.families || rule.families.includes(family));

export const layoutOf = (family, profile = null) => table.layouts.find((rule) => matches(rule, family, profile))?.layout ?? null;

export const engineKey = (engine) => `${engine?.preset ?? ''}|${engine?.model ?? ''}|${engine?.profile ?? ''}`;

export function mediaKey(asset) {
	const origin = asset?.origin;
	if (origin?.kind === 'history' && origin.generationId && origin.fileId != null) return `history:${origin.generationId}:${origin.fileId}`;
	if (origin?.kind === 'library' && origin.itemId) return `library:${origin.itemId}`;
	return null;
}

const assetOf = (doc, id) => (id ? ((doc?.assets ?? []).find((a) => a.id === id) ?? null) : null);

function mediaStatuses(doc, own, shared, tracks) {
	const counts = Object.fromEntries(Object.keys(LIMITS).map((kind) => [kind, 0]));
	const seen = new Set();
	const statuses = new Map();
	const add = (reference) => {
		const asset = assetOf(doc, reference.assetId);
		const key = mediaKey(asset);
		if (!key || !Object.hasOwn(counts, asset.kind)) return statuses.set(reference.id, 'missing');
		if (seen.has(key)) return statuses.set(reference.id, 'sent');
		if (counts[asset.kind] >= LIMITS[asset.kind]) return statuses.set(reference.id, 'trimmed');
		counts[asset.kind] += 1;
		seen.add(key);
		statuses.set(reference.id, 'sent');
	};
	own.forEach(add);
	counts.audio = Math.min(LIMITS.audio, counts.audio + tracks);
	shared.forEach(add);
	return statuses;
}

export function shotReception(doc, clip, engine, tracks = 0) {
	const { inherited, own } = shotReferences(doc, clip);
	const shared = inherited.filter((x) => !x.excluded).map((x) => x.reference);
	const info = engine?.info ?? null;
	const profile = engine?.profile ?? null;
	const state = !info ? 'unknown' : presetProfiles(info).includes(profile) ? 'ready' : 'blocked';
	const layout = state === 'ready' ? layoutOf(familyOf(info), profile) : null;
	const override = layout ? referencePromptOf(clip) : null;
	let statuses;
	if (state !== 'ready') statuses = new Map([...own, ...shared].map((r) => [r.id, state]));
	else if (takesReferences(profile)) statuses = mediaStatuses(doc, own, shared, tracks);
	else {
		const mixes = audioBehavior(info, profile) === MUX;
		const voices = voiceReferences(doc);
		statuses = new Map([...own, ...shared].map((r) => [r.id, mixes && assetOf(doc, r.assetId)?.kind === 'audio' && !voices.has(r.id) ? 'mixed' : 'ignored']));
	}
	for (const x of inherited) if (x.excluded) statuses.set(x.reference.id, 'excluded');
	return { clip, engine, state, layout, overridden: Boolean(override) && override.layout === layout, ignoredLayout: Boolean(override) && override.layout !== layout, statuses };
}

export function linkedCard(doc, reference) {
	for (const kind of [CHARACTERS, PLACES]) {
		const card = cardsOf(doc, kind).find((c) => (c.references ?? []).includes(reference?.id));
		if (card) return { kind, card, voice: false };
	}
	const owner = cardsOf(doc, CHARACTERS).find((c) => c.voiceRef && c.voiceRef === reference?.id);
	return owner ? { kind: CHARACTERS, card: owner, voice: true } : null;
}

function grouped(items, keyOf, make) {
	const groups = [];
	for (const item of items) {
		const key = keyOf(item);
		let group = groups.find((g) => g.key === key);
		if (!group) groups.push((group = { key, ...make(item), shots: [] }));
		group.shots.push(item);
	}
	return groups;
}

export function receptionOf(reference, doc, engineOf, tracksOf = () => 0) {
	const shots = (doc?.clips ?? [])
		.filter((clip) => isGlobal(reference) || ownsReference(clip, reference))
		.map((clip) => {
			const shot = shotReception(doc, clip, engineOf(clip), tracksOf(clip));
			return { ...shot, status: shot.statuses.get(reference.id) };
		});
	const groups = grouped(
		shots,
		(shot) => (shot.status === 'excluded' ? 'excluded' : `${engineKey(shot.engine)}|${shot.status}`),
		(shot) => ({ engine: shot.status === 'excluded' ? null : shot.engine, status: shot.status })
	);
	const linked = linkedCard(doc, reference);
	return {
		reference,
		shots,
		groups: [...groups.filter((g) => g.status !== 'excluded'), ...groups.filter((g) => g.status === 'excluded')],
		going: shots.filter((shot) => shot.status !== 'excluded').map((shot) => shot.clip),
		linked,
		cast: linked && !linked.voice ? shotsCasting(doc, linked.kind, linked.card.id) : []
	};
}

export function projectReception(doc, engineOf, tracksOf = () => 0) {
	const shots = (doc?.clips ?? []).map((clip) => shotReception(doc, clip, engineOf(clip), tracksOf(clip)));
	return grouped(
		shots,
		(shot) => engineKey(shot.engine),
		(shot) => ({ engine: shot.engine, state: shot.state, references: takesReferences(shot.engine?.profile) })
	).map((group) => {
		const counts = {};
		for (const shot of group.shots) for (const status of shot.statuses.values()) counts[status] = (counts[status] ?? 0) + 1;
		return { ...group, counts };
	});
}

export function cardReception(doc, kind, card, engineOf, tracksOf = () => 0) {
	const ids = [...(card?.references ?? []), ...(kind === CHARACTERS && card?.voiceRef ? [card.voiceRef] : [])];
	const references = [...new Set(ids)].filter((id) => (doc?.references ?? []).some((r) => r.id === id));
	const shots = shotsCasting(doc, kind, card?.id).map((clip) => {
		const shot = shotReception(doc, clip, engineOf(clip), tracksOf(clip));
		return { ...shot, received: references.filter((id) => RECEIVED.includes(shot.statuses.get(id))).length };
	});
	return {
		references,
		shots,
		groups: grouped(
			shots,
			(shot) => `${engineKey(shot.engine)}|${shot.state}|${shot.received > 0}`,
			(shot) => ({ engine: shot.engine, state: shot.state, received: shot.received > 0 })
		)
	};
}

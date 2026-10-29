const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' ? value : '');
const score = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null);
export const STATES = ['done', 'queued', 'failed', 'unavailable', 'missing', 'no_images'];
const state = (value) => (STATES.includes(value) ? value : 'missing');
const count = (value) => (Number.isInteger(value) && value > 0 ? value : 0);

export const SEAM_LOW = 0.7;
export const CAST_LOW = 0.6;
export const FACE_LOW = 0.7;
export const PLACE_LOW = 0.55;
export const FINAL_LOW = 0.8;
export const DRIFT_LOW = 0.8;
export const PUSH_IN_HIGH = 1.5;
export const IDENTITY_LOW = 0.6;
const KINDS = ['character', 'place'];
const METHODS = ['face', 'whole'];
const share = (value) => (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null);
const ratio = (value) => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null);
const time = (value) => (typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null);

function normalizeIdentity(value) {
	if (!isObject(value) || score(value.score) === null) return null;
	return { score: value.score, at: time(value.at) };
}

function normalizeCard(value) {
	if (!isObject(value) || !text(value.card_id)) return null;
	return { cardId: value.card_id, label: text(value.label), kind: KINDS.includes(value.kind) ? value.kind : 'character', score: score(value.score), status: state(value.status), method: METHODS.includes(value.method) ? value.method : null, seen: share(value.seen) };
}

function normalizeTakeLook(value) {
	if (!isObject(value) || !text(value.take_id)) return null;
	return { takeId: value.take_id, shotId: text(value.shot_id) || null, status: state(value.status), cards: (Array.isArray(value.cards) ? value.cards : []).map(normalizeCard).filter(Boolean), pushIn: ratio(value.push_in), identity: normalizeIdentity(value.identity) };
}

function normalizeSeamLook(value) {
	if (!isObject(value) || !text(value.shot_id)) return null;
	return { shotId: value.shot_id, previousId: text(value.previous_id) || null, fromTake: text(value.from_take) || null, toTake: text(value.to_take) || null, score: score(value.score), identity: score(value.identity), status: state(value.status) };
}

function normalizeFinal(value) {
	if (!isObject(value) || !text(value.take_id)) return null;
	return { takeId: value.take_id, parentId: text(value.parent_id) || null, shotId: text(value.shot_id) || null, score: score(value.score), face: score(value.face), status: state(value.status) };
}

function normalizeChain(value) {
	if (!isObject(value) || !text(value.shot_id) || !text(value.from_take)) return null;
	return { shotId: value.shot_id, previousId: text(value.previous_id) || null, fromTake: value.from_take, cards: (Array.isArray(value.cards) ? value.cards : []).map(normalizeCard).filter(Boolean) };
}

function normalizeDrift(value) {
	if (!isObject(value) || !text(value.take_id) || !text(value.card_id)) return null;
	return { takeId: value.take_id, cardId: value.card_id, shotId: text(value.shot_id) || null, score: score(value.score) };
}

export function normalizeLooks(value) {
	const data = isObject(value) ? value : {};
	const embedder = isObject(data.embedder) ? data.embedder : {};
	const faces = isObject(data.faces) ? data.faces : {};
	const identity = isObject(data.identity) ? data.identity : {};
	const thresholds = isObject(data.thresholds) ? data.thresholds : {};
	return {
		embedder: { model: text(embedder.model) || null, available: embedder.available === true },
		faces: { model: text(faces.model) || null, available: faces.available === true },
		identity: { model: text(identity.model) || null, available: identity.available === true },
		thresholds: {
			seam: score(thresholds.seam) ?? SEAM_LOW,
			cast: score(thresholds.cast) ?? CAST_LOW,
			face: score(thresholds.face) ?? FACE_LOW,
			place: score(thresholds.place) ?? PLACE_LOW,
			final: score(thresholds.final) ?? FINAL_LOW,
			drift: score(thresholds.drift) ?? DRIFT_LOW,
			pushIn: ratio(thresholds.push_in) ?? PUSH_IN_HIGH,
			identity: score(thresholds.identity) ?? IDENTITY_LOW
		},
		seams: (Array.isArray(data.seams) ? data.seams : []).map(normalizeSeamLook).filter(Boolean),
		takes: (Array.isArray(data.takes) ? data.takes : []).map(normalizeTakeLook).filter(Boolean),
		candidates: (Array.isArray(data.candidates) ? data.candidates : []).map(normalizeTakeLook).filter(Boolean),
		finals: (Array.isArray(data.finals) ? data.finals : []).map(normalizeFinal).filter(Boolean),
		drift: (Array.isArray(data.drift) ? data.drift : []).map(normalizeDrift).filter(Boolean),
		chains: (Array.isArray(data.chains) ? data.chains : []).map(normalizeChain).filter(Boolean),
		missing: count(data.missing),
		queued: count(data.queued)
	};
}

export function seamLook(looks, from, to) {
	if (!looks || !from?.take || !to?.take) return null;
	return looks.seams.find((s) => s.shotId === to.id && s.previousId === from.id && s.fromTake === from.take && s.toTake === to.take) ?? null;
}

export const lowSeam = (looks, seam) => seam?.status === 'done' && seam.score !== null && seam.score < looks.thresholds.seam;

export const takeLook = (looks, takeId) => (looks && takeId ? (looks.takes.find((x) => x.takeId === takeId) ?? null) : null);

export const candidateLook = (looks, takeId) => (looks && takeId ? (looks.candidates.find((x) => x.takeId === takeId) ?? null) : null);

export function candidateScore(look) {
	const done = (look?.cards ?? []).filter((c) => c.status === 'done' && c.score !== null);
	return done.length ? done.reduce((sum, c) => sum + c.score, 0) / done.length : null;
}

export function bestCandidate(looks, takeIds) {
	const scored = takeIds.map((id) => [id, candidateScore(candidateLook(looks, id))]).filter(([, value]) => value !== null);
	if (scored.length < 2) return null;
	return scored.reduce((best, item) => (item[1] > best[1] ? item : best))[0];
}

export const cardThreshold = (looks, card) => (card.kind === 'place' ? looks.thresholds.place : card.method === 'face' ? looks.thresholds.face : looks.thresholds.cast);

export const lowCard = (looks, card) => card?.status === 'done' && card.score !== null && card.score < cardThreshold(looks, card);

export const lowCards = (looks, look) => (look?.cards ?? []).filter((c) => lowCard(looks, c));

export function chainLook(looks, from, to) {
	if (!looks || !from?.take || !to) return null;
	return looks.chains.find((c) => c.shotId === to.id && c.previousId === from.id && c.fromTake === from.take) ?? null;
}

export const chainThreshold = (looks, card) => (card.kind !== 'place' && card.method === 'face' ? looks.thresholds.drift : cardThreshold(looks, card));

export const chainDrifts = (looks, from, to) => (chainLook(looks, from, to)?.cards ?? []).filter((c) => c.status === 'done' && c.score !== null && c.score < chainThreshold(looks, c));

export const finalLook = (looks, takeId) => (looks && takeId ? (looks.finals.find((x) => x.takeId === takeId) ?? null) : null);

export const lowFinal = (looks, found) => found?.status === 'done' && found.score !== null && found.score < looks.thresholds.final;

export const driftOf = (looks, takeId, cardId) => (looks && takeId ? (looks.drift.find((x) => x.takeId === takeId && x.cardId === cardId) ?? null) : null);

export const lowDrift = (looks, found) => Boolean(found) && found.score !== null && found.score < looks.thresholds.drift;

export function castIssues(looks, clips) {
	if (!looks) return [];
	return clips.flatMap((clip) => {
		const look = clip.take ? takeLook(looks, clip.take) : null;
		return lowCards(looks, look).map((card) => ({ clip, takeId: look.takeId, card }));
	});
}

export const pushedIn = (looks, look) => Boolean(looks) && look?.status === 'done' && look.pushIn !== null && look.pushIn > looks.thresholds.pushIn;

export function pushInIssues(looks, clips) {
	if (!looks) return [];
	return clips.flatMap((clip) => {
		const look = clip.take ? takeLook(looks, clip.take) : null;
		return pushedIn(looks, look) ? [{ clip, takeId: look.takeId, pushIn: look.pushIn }] : [];
	});
}

export const faceChanged = (looks, look) => Boolean(looks) && look?.status === 'done' && look.identity !== null && look.identity.score < looks.thresholds.identity;

export const seamFaceChanged = (looks, seam) => Boolean(looks) && seam?.status === 'done' && seam.identity !== null && seam.identity < looks.thresholds.identity;

export function identityIssues(looks, clips) {
	if (!looks) return [];
	return clips.flatMap((clip, index) => {
		const look = clip.take ? takeLook(looks, clip.take) : null;
		const previous = index ? clips[index - 1] : null;
		const seam = previous ? seamLook(looks, previous, clip) : null;
		return [
			...(faceChanged(looks, look) ? [{ kind: 'take', clip, takeId: look.takeId, score: look.identity.score, at: look.identity.at }] : []),
			...(seamFaceChanged(looks, seam) ? [{ kind: 'seam', clip, previous, takeId: clip.take, score: seam.identity }] : [])
		];
	});
}

export const issueKey = (item) => [item.kind ?? 'look', item.clip?.id, item.takeId, item.card?.cardId].filter((part) => part !== undefined && part !== null).join(':');

export const percent = (value) => Math.round((value ?? 0) * 100);

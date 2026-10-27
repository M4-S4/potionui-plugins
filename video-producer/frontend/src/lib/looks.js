const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' ? value : '');
const score = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null);
const STATES = ['done', 'queued', 'failed', 'unavailable', 'missing', 'no_images'];
const state = (value) => (STATES.includes(value) ? value : 'missing');
const count = (value) => (Number.isInteger(value) && value > 0 ? value : 0);

export const SEAM_LOW = 0.7;
export const CAST_LOW = 0.6;

function normalizeCard(value) {
	if (!isObject(value) || !text(value.card_id)) return null;
	return { cardId: value.card_id, label: text(value.label), score: score(value.score), status: state(value.status) };
}

function normalizeTakeLook(value) {
	if (!isObject(value) || !text(value.take_id)) return null;
	return { takeId: value.take_id, shotId: text(value.shot_id) || null, status: state(value.status), cards: (Array.isArray(value.cards) ? value.cards : []).map(normalizeCard).filter(Boolean) };
}

function normalizeSeamLook(value) {
	if (!isObject(value) || !text(value.shot_id)) return null;
	return { shotId: value.shot_id, previousId: text(value.previous_id) || null, fromTake: text(value.from_take) || null, toTake: text(value.to_take) || null, score: score(value.score), status: state(value.status) };
}

export function normalizeLooks(value) {
	const data = isObject(value) ? value : {};
	const embedder = isObject(data.embedder) ? data.embedder : {};
	const thresholds = isObject(data.thresholds) ? data.thresholds : {};
	return {
		embedder: { model: text(embedder.model) || null, available: embedder.available === true },
		thresholds: { seam: score(thresholds.seam) ?? SEAM_LOW, cast: score(thresholds.cast) ?? CAST_LOW },
		seams: (Array.isArray(data.seams) ? data.seams : []).map(normalizeSeamLook).filter(Boolean),
		takes: (Array.isArray(data.takes) ? data.takes : []).map(normalizeTakeLook).filter(Boolean),
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

export const lowCards = (looks, look) => (look?.cards ?? []).filter((c) => c.status === 'done' && c.score !== null && c.score < looks.thresholds.cast);

export function castIssues(looks, clips) {
	if (!looks) return [];
	return clips.flatMap((clip) => {
		const look = clip.take ? takeLook(looks, clip.take) : null;
		return lowCards(looks, look).map((card) => ({ clip, takeId: look.takeId, card }));
	});
}

export const percent = (value) => Math.round((value ?? 0) * 100);

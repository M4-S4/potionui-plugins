export const REFINE = 'refine_faces';
export const REMIX = 'remix';
export const TASKS = [REFINE, REMIX];
export const STRENGTHS = ['light', 'balanced', 'strong'];
export const DEFAULT_SECONDS = 1;
export const PROMPT_LIMIT = 2000;

const finite = (value) => typeof value === 'number' && Number.isFinite(value);

export const isRetouch = (take) => take?.kind === 'retouch';

export const canRetouch = (take) => Boolean(take) && take.kind !== 'keyframe' && take.status === 'done' && Boolean(take.url) && finite(take.fps) && take.fps > 0 && finite(take.durationS) && take.durationS > 0;

export function framesOf(take) {
	return Math.max(1, Math.round(take.durationS * take.fps));
}

export function snap(take, start, end) {
	const total = framesOf(take);
	let first = Math.round(Math.max(0, finite(start) ? start : 0) * take.fps);
	let last = Math.round(Math.max(0, finite(end) ? end : 0) * take.fps);
	first = Math.min(Math.max(0, first), total - 1);
	last = Math.min(Math.max(last, first + 1), total);
	return { first, last, frames: last - first, start: first / take.fps, end: last / take.fps, seconds: (last - first) / take.fps, total };
}

export function initialRange(take, at = null) {
	const duration = take.durationS;
	const length = Math.min(DEFAULT_SECONDS, duration);
	const middle = finite(at) ? at : duration / 2;
	const start = Math.min(Math.max(0, middle - length / 2), duration - length);
	return snap(take, start, start + length);
}

export function moveEdge(take, range, edge, time) {
	if (edge === 'in') return snap(take, Math.min(time, range.end - 1 / take.fps), range.end);
	return snap(take, range.start, Math.max(time, range.start + 1 / take.fps));
}

export function offerOf(offers, task) {
	return (offers ?? []).find((offer) => offer.task === task) ?? null;
}

export function rangeProblem(offer, range, fps) {
	if (!offer || !range) return null;
	const slack = 0.5 / fps;
	if (finite(offer.minS) && range.seconds < offer.minS - slack) return { code: 'tooShort', limit: offer.minS };
	if (finite(offer.maxS) && range.seconds > offer.maxS + slack) return { code: 'tooLong', limit: offer.maxS };
	return null;
}

export function overLimit(offer, range) {
	if (!offer || !finite(offer.maxS) || range.seconds <= offer.maxS) return null;
	return { start: range.start + offer.maxS, end: range.end };
}

export function touchesEnd(range) {
	return range.last >= range.total;
}

export function blockReason(state, take, offer) {
	if (!take || !canRetouch(take)) return 'takeNotDone';
	if (!offer) return 'loading';
	if (!offer.engines.length) return 'engineMissing';
	if (offer.task === REFINE && offer.missing.length) return 'detectorMissing';
	if (offer.task === REFINE && !state.faces && !state.hands) return 'nothingToRefine';
	if (offer.task === REMIX && !state.prompt.trim()) return 'promptRequired';
	if (rangeProblem(offer, state.range, take.fps)) return rangeProblem(offer, state.range, take.fps).code;
	return null;
}

export function retouchBody(state) {
	const body = { task: state.task, start_s: Number(state.range.start.toFixed(6)), end_s: Number(state.range.end.toFixed(6)) };
	if (state.presetId) body.preset_id = state.presetId;
	if (state.task === REMIX) body.prompt = state.prompt.trim().slice(0, PROMPT_LIMIT);
	else Object.assign(body, { strength: state.strength, faces: state.faces, hands: state.hands });
	return body;
}

export function shareOf(range, duration) {
	if (!range || !(duration > 0)) return { left: 0, width: 0 };
	return { left: (range.start / duration) * 100, width: ((range.end - range.start) / duration) * 100 };
}

export function retouchPair(takes) {
	if (!Array.isArray(takes) || takes.length !== 2) return null;
	const [a, b] = takes;
	if (isRetouch(b) && b.parentTakeId === a.id) return { source: a, retouched: b };
	if (isRetouch(a) && a.parentTakeId === b.id) return { source: b, retouched: a };
	return null;
}

import { isObject } from './values.js';

export const MAX_REQUEST = 1000;
export const WRITE_TIMEOUT_MS = 150000;

export const WRITER_CODES = [
	'no_llm',
	'llm_not_available',
	'llm_disabled',
	'vision_not_supported',
	'writer_unavailable',
	'preset_not_available',
	'write_timeout',
	'write_busy',
	'write_cancelled',
	'write_failed',
	'empty_reply',
	'blocked',
	'too_much_media',
	'media_unreadable',
	'media_too_large',
	'media_outside_storage',
	'media_unsupported'
];

const text = (value) => (typeof value === 'string' ? value : '');
const VREF_TAG = /^@vref[1-9]$/i;
const NUMBERED_TAG = /^<(?:Subject|Picture|Video|Audio) \d+>$/;

export function normalizeWriterStatus(value) {
	if (!isObject(value)) return null;
	const available = value.available === true;
	return {
		available,
		vision: available && value.vision === true,
		name: text(value.name) || null,
		code: available ? null : text(value.code) || 'no_llm',
		message: available ? null : text(value.message) || null
	};
}

export function normalizeWritten(value) {
	if (!isObject(value) || !text(value.text).trim()) return null;
	const count = (n) => (Number.isInteger(n) && n > 0 ? n : 0);
	const lostTags = Array.isArray(value.lost_tags) ? value.lost_tags.filter((tag) => typeof tag === 'string' && VREF_TAG.test(tag)) : [];
	const keptTags = Array.isArray(value.kept_tags) ? value.kept_tags.filter((tag) => typeof tag === 'string' && NUMBERED_TAG.test(tag)) : [];
	return { text: value.text.trim(), name: text(value.name) || null, images: count(value.images), imagesSkipped: count(value.images_skipped), imagesDropped: count(value.images_dropped), lostTags, keptTags };
}

export function writeBody(request, option, doc) {
	return { request: request.trim(), preset_id: option.preset, model_id: option.model ?? null, doc };
}

export const writerIdle = () => ({ phase: 'closed', request: '', proposal: null, before: null, applied: null, error: null, run: 0 });

export function canWrite(state, status) {
	return status?.available === true && state.phase !== 'writing' && state.request.trim().length > 0 && state.request.length <= MAX_REQUEST;
}

export function canUndo(state, currentText) {
	return state.applied !== null && state.before !== null && currentText === state.applied;
}

export function writerStep(state, event) {
	switch (event.type) {
		case 'open':
			return { ...state, phase: state.phase === 'closed' ? 'open' : state.phase };
		case 'close':
			return { ...state, phase: 'closed', proposal: null, error: null, run: state.run + 1 };
		case 'edit':
			return { ...state, request: String(event.request ?? '') };
		case 'start':
			return { ...state, phase: 'writing', proposal: null, error: null, run: state.run + 1 };
		case 'cancel':
			return state.phase === 'writing' ? { ...state, phase: 'open', run: state.run + 1 } : state;
		case 'done':
			if (state.phase !== 'writing' || event.run !== state.run) return state;
			return { ...state, phase: 'proposed', proposal: event.written };
		case 'fail':
			if (state.phase !== 'writing' || event.run !== state.run) return state;
			return { ...state, phase: 'failed', error: event.error };
		case 'reject':
			return state.phase === 'proposed' ? { ...state, phase: 'open', proposal: null } : state;
		case 'accept':
			if (state.phase !== 'proposed') return state;
			return { ...state, phase: 'closed', proposal: null, before: String(event.current ?? ''), applied: state.proposal.text, request: '' };
		case 'undo':
			return { ...state, before: null, applied: null };
		case 'forget':
			return state.applied === null ? state : { ...state, before: null, applied: null };
		default:
			return state;
	}
}

export const writerCode = (error) => (WRITER_CODES.includes(error?.code) ? error.code : null);

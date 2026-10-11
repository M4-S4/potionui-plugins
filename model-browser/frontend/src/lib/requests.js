// Model requests (PLAN.md section 4.4): the calls to `/requests`, what a status means, the order
// and the tabs of the requests panel, who may cancel or decide, the count on the toolbar button,
// the request dialog's form, and the toasts. No Svelte in here: tested with `node --test`
// (see requests.test.js).
//
// A request, as `GET /requests` lists it (backend requests.py, routes_requests.py):
//   { id, user_id, username, source, source_model_id, source_version_id, file_id,
//     snapshot: { name, type, mb_type, version_name, base_model, file_name, size_bytes, nsfw, poi,
//                 license, thumbnail_url, source_url, sha256, already_installed, hidden? },
//     note, status, decided_by, decided_by_username, decision_note, sha256, created_at, updated_at }
// with `status` open | approved | rejected | cancelled | done | failed. `snapshot.mb_type` is the
// type asked for, `license` the licence's summary, `thumbnail_url` an image anyone may see (the
// server drops it for a viewer who does not see the model, and says `hidden`). Any field may be
// missing: `normalizeRequest` gives each one a value of the right type.

import { MODEL_TYPES, allowedTypes, can, isUnrestricted, normalizeMe } from './capabilities.js';
import { callPlugin, getMe } from './client.js';
import { baseName, downloadWarnings, sizeProblem } from './downloadForm.js';
import { formatBytes, formatDate, modelTypeLabel } from './format.js';

/** How often the requests panel asks again while it is open. */
export const POLL_INTERVAL_MS = 15_000;

/** Requests asked for per list. */
export const LIST_LIMIT = 100;

/** The longest note, to the admin or to the requester. */
export const MAX_NOTE_LENGTH = 1000;

/** Every status, in the order of the status filter. */
export const STATUSES = ['open', 'approved', 'done', 'failed', 'rejected', 'cancelled'];

const STATUS_INFO = {
	open: { label: 'Open', tone: 'info', hint: 'Waiting for an admin to decide' },
	approved: { label: 'Approved', tone: 'signal', hint: 'Approved: the file is being downloaded' },
	done: { label: 'Done', tone: 'success', hint: 'Downloaded and given to the requester' },
	failed: { label: 'Failed', tone: 'danger', hint: 'Approved, but the download failed' },
	rejected: { label: 'Rejected', tone: 'warning', hint: 'An admin turned the request down' },
	cancelled: { label: 'Cancelled', tone: 'neutral', hint: 'Withdrawn by the requester' }
};
const FINAL = new Set(['done', 'failed', 'rejected', 'cancelled']);

// A server timestamp without a time zone (SQLite's CURRENT_TIMESTAMP) is UTC.
const NAIVE_TIME = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function text(value) {
	return typeof value === 'string' ? value : '';
}

function idText(value) {
	return value === undefined || value === null ? '' : String(value);
}

function countOf(value) {
	return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? Math.floor(value) : null;
}

/** A url as it came when its protocol is one of `protocols`, else '' (never a `javascript:` link). */
function urlWith(value, protocols) {
	if (typeof value !== 'string' || !value) return '';
	try {
		return protocols.includes(new URL(value).protocol) ? value : '';
	} catch {
		return '';
	}
}

/** The licence's summary: the server sends the text; an object's `summary` is read too. */
function licenseText(value) {
	if (typeof value === 'string') return value;
	return isObject(value) ? text(value.summary) : '';
}

function statusOf(value) {
	return typeof value === 'string' ? value : value?.status;
}

// Statuses ---------------------------------------------------------------------------------

/**
 * What a status looks like: its label, the tone of its pill, and a sentence for its tooltip.
 *
 * @param {string} status
 * @returns {{ label: string, tone: 'info' | 'signal' | 'success' | 'danger' | 'warning' | 'neutral', hint: string }}
 */
export function statusInfo(status) {
	return STATUS_INFO[status] ?? { label: typeof status === 'string' && status ? status : 'Unknown', tone: 'neutral', hint: '' };
}

export function statusLabel(status) {
	return statusInfo(status).label;
}

export function statusTone(status) {
	return statusInfo(status).tone;
}

/** Whether a request (or a status) still waits for a decision. */
export function isOpen(request) {
	return statusOf(request) === 'open';
}

/** Whether nothing more happens to a request (or a status): done, failed, rejected or cancelled. */
export function isFinal(request) {
	return FINAL.has(statusOf(request));
}

// Normalising ------------------------------------------------------------------------------

/** A request with every field present and of the right type. */
export function normalizeRequest(raw) {
	const source = isObject(raw) ? raw : {};
	const snapshot = isObject(source.snapshot) ? source.snapshot : {};
	const size = snapshot.size_bytes;
	return {
		id: idText(source.id),
		user_id: idText(source.user_id),
		username: text(source.username),
		source: text(source.source),
		source_model_id: idText(source.source_model_id),
		source_version_id: idText(source.source_version_id),
		file_id: idText(source.file_id),
		model_type: text(source.model_type),
		snapshot: {
			name: text(snapshot.name),
			type: text(snapshot.type),
			mb_type: text(snapshot.mb_type),
			version_name: text(snapshot.version_name),
			base_model: text(snapshot.base_model),
			file_name: text(snapshot.file_name),
			size_bytes: typeof size === 'number' && Number.isFinite(size) && size >= 0 ? size : null,
			nsfw: snapshot.nsfw === true,
			poi: snapshot.poi === true,
			license: licenseText(snapshot.license),
			thumbnail_url: urlWith(snapshot.thumbnail_url, ['https:']),
			source_url: urlWith(snapshot.source_url, ['https:', 'http:']),
			sha256: text(snapshot.sha256),
			already_installed: snapshot.already_installed === true,
			hidden: snapshot.hidden === true
		},
		note: text(source.note),
		status: text(source.status),
		decided_by: idText(source.decided_by),
		decided_by_username: text(source.decided_by_username),
		decision_note: text(source.decision_note),
		sha256: text(source.sha256),
		created_at: text(source.created_at),
		updated_at: text(source.updated_at)
	};
}

/**
 * The `data` of `GET /requests` (`{ requests, open_count, can_approve }`, or a bare list):
 * the requests that have an id, normalised; `openCount` null when the server does not say.
 *
 * @returns {{ requests: ReturnType<typeof normalizeRequest>[], openCount: number | null, canApprove: boolean }}
 */
export function normalizeListing(data) {
	const source = isObject(data) ? data : {};
	const list = Array.isArray(data) ? data : Array.isArray(source.requests) ? source.requests : [];
	return {
		requests: list.filter(isObject).map(normalizeRequest).filter((request) => request.id),
		openCount: countOf(source.open_count),
		canApprove: source.can_approve === true
	};
}

/** A server timestamp in milliseconds (one without a time zone is UTC), or null. */
export function parseTime(value) {
	if (typeof value !== 'string' || !value) return null;
	const ms = Date.parse(NAIVE_TIME.test(value) ? `${value.replace(' ', 'T')}Z` : value);
	return Number.isNaN(ms) ? null : ms;
}

// Order, tabs, rights ----------------------------------------------------------------------

/** Open requests first, then the newest first (ids, which grow with time, break ties). Never mutates. */
export function sortRequests(requests) {
	const time = (request) => parseTime(request.created_at) ?? parseTime(request.updated_at) ?? 0;
	return [...requests].sort((a, b) => {
		const open = Number(isOpen(b)) - Number(isOpen(a));
		if (open) return open;
		const newer = time(b) - time(a);
		if (newer) return newer;
		return a.id < b.id ? 1 : a.id > b.id ? -1 : 0;
	});
}

/** Whether the user may decide on other people's requests (`approve`; admins hold everything). */
export function canDecide(me) {
	return can(me, 'approve');
}

/**
 * Whether the user may approve or reject this open request: those who decide, but not on their
 * own request unless they are an admin (the server answers 403 otherwise).
 */
export function canDecideOn(me, request) {
	if (!canDecide(me) || !isOpen(request)) return false;
	if (isUnrestricted(me)) return true;
	const userId = me?.user?.id;
	return !userId || request?.user_id !== userId;
}

/** Whether the user may withdraw this request: their own, still open. */
export function canCancel(me, request) {
	const userId = me?.user?.id;
	return !!userId && isOpen(request) && request?.user_id === userId;
}

/** Whether the page shows the Requests button: the user may ask for models or decide on requests. */
export function showsRequests(me) {
	return can(me, 'request') || can(me, 'approve');
}

/**
 * The requests of each part of the panel, sorted: `mine` (the user's own), `review` (the open
 * ones, for those who may decide; empty otherwise) and `all`.
 */
export function groupRequests(requests, me) {
	const sorted = sortRequests(requests);
	const userId = me?.user?.id ?? '';
	return {
		mine: userId ? sorted.filter((request) => request.user_id === userId) : sorted,
		review: canDecide(me) ? sorted.filter(isOpen) : [],
		all: sorted
	};
}

/**
 * The tabs of the panel: those who decide get "To review" (with the count when known), their own
 * requests when they may ask for models (not admins, who download directly) and "All"; the others
 * only see their own requests, without tabs.
 *
 * @returns {{ id: 'review' | 'mine' | 'all', label: string, count?: number }[]}
 */
export function panelTabs(me, reviewCount = null) {
	if (!canDecide(me)) return [{ id: 'mine', label: 'My requests' }];
	const review = { id: 'review', label: 'To review' };
	if (typeof reviewCount === 'number') review.count = reviewCount;
	const tabs = [review];
	if (can(me, 'request') && !isUnrestricted(me)) tabs.push({ id: 'mine', label: 'Mine' });
	tabs.push({ id: 'all', label: 'All' });
	return tabs;
}

/** The tab the panel opens on. */
export function defaultTab(me) {
	return canDecide(me) ? 'review' : 'mine';
}

/**
 * The query of `GET /requests` for a tab (`status` only applies to "All").
 *
 * @returns {{ status?: string, all: boolean, limit: number }}
 */
export function tabQuery(tab, status = '') {
	if (tab === 'review') return { status: 'open', all: true, limit: LIST_LIMIT };
	if (tab === 'all') return STATUSES.includes(status) ? { status, all: true, limit: LIST_LIMIT } : { all: true, limit: LIST_LIMIT };
	return { all: false, limit: LIST_LIMIT };
}

/** The requests a tab shows, sorted; filtered here too, whatever the server sent. */
export function tabRequests(tab, requests, me, status = '') {
	const groups = groupRequests(requests, me);
	if (tab === 'review') return groups.review;
	if (tab === 'mine') return groups.mine;
	return STATUSES.includes(status) ? groups.all.filter((request) => request.status === status) : groups.all;
}

// The count on the toolbar button ----------------------------------------------------------

/**
 * The number on the Requests button: for those who decide, the open requests they may act on
 * (`open_count` when the answer has it); for the others, their own open requests.
 *
 * @param {any} me
 * @param {{ requests?: any[], openCount?: number | null }} listing  From `normalizeListing`.
 */
export function badgeCount(me, listing) {
	const requests = listing?.requests ?? [];
	if (canDecide(me)) return typeof listing?.openCount === 'number' ? listing.openCount : requests.filter(isOpen).length;
	const userId = me?.user?.id ?? '';
	return requests.filter((request) => isOpen(request) && (!userId || request.user_id === userId)).length;
}

/** The count known from `/me` without another call: approvers' `requests.open_count`, else null. */
export function initialBadgeCount(me) {
	const count = me?.requests?.open_count;
	return canDecide(me) && typeof count === 'number' ? count : null;
}

/**
 * Ask the server for the count again: `/me`'s `requests.open_count` for those who decide (the
 * open requests when it is missing), the user's own open requests for the others. Null when the
 * server could not say.
 *
 * @returns {Promise<number | null>}
 */
export async function fetchBadgeCount(api, me) {
	if (canDecide(me)) {
		const meResult = await getMe(api);
		const fromMe = meResult.ok ? normalizeMe(meResult.data).requests.open_count : null;
		if (fromMe !== null) return fromMe;
		const listed = await listRequests(api, tabQuery('review'));
		return listed.ok ? badgeCount(me, normalizeListing(listed.data)) : null;
	}
	const listed = await listRequests(api, { status: 'open', all: false, limit: LIST_LIMIT });
	return listed.ok ? badgeCount(me, normalizeListing(listed.data)) : null;
}

// Calls --------------------------------------------------------------------------------------

function requestPath(id, action = '') {
	return `/requests/${encodeURIComponent(String(id))}${action ? `/${action}` : ''}`;
}

/** A note as sent: trimmed, '' when empty. */
export function cleanNote(note) {
	return typeof note === 'string' ? note.trim() : '';
}

/**
 * `POST /requests` (`request`): ask for one file. Answers `{ request, already_requested }`, or
 * 409 `already_available` (the file is already in the user's models), 403 `forbidden`, 404, 400.
 *
 * @param {any} api
 * @param {{ source: string, model_id: string, version_id: string, file_id: string, model_type?: string, note?: string }} body
 */
export function createRequest(api, body) {
	return callPlugin(api, 'post', '/requests', body);
}

/**
 * `GET /requests` (`request` or `approve`): the user's own requests, or everyone's for those who
 * decide. Answers `{ requests, open_count, can_approve }`.
 *
 * @param {any} api
 * @param {{ status?: string, all?: boolean, limit?: number }} [options]
 */
export function listRequests(api, { status, all, limit } = {}) {
	const params = new URLSearchParams();
	if (typeof status === 'string' && status) params.set('status', status);
	if (typeof all === 'boolean') params.set('all', String(all));
	if (typeof limit === 'number') params.set('limit', String(limit));
	const query = params.toString();
	return callPlugin(api, 'get', `/requests${query ? `?${query}` : ''}`);
}

/**
 * `POST /requests/{id}/approve` (`approve`): download the file for the requester. Answers
 * `{ request, pending, download, already_installed, already_queued }`, or 409 `not_open`,
 * 403 `not_visible_to_requester` / `forbidden` / `limit_exceeded`.
 *
 * @param {any} api
 * @param {string} id
 * @param {{ note?: string, modelType?: string, assignGroupId?: string }} [options]  Only what is set is sent.
 */
export function approveRequest(api, id, { note, modelType, assignGroupId } = {}) {
	const body = {};
	const cleaned = cleanNote(note);
	if (cleaned) body.note = cleaned;
	if (typeof modelType === 'string' && modelType) body.model_type = modelType;
	if (typeof assignGroupId === 'string' && assignGroupId) body.assign_group_id = assignGroupId;
	return callPlugin(api, 'post', requestPath(id, 'approve'), body);
}

/** `POST /requests/{id}/reject` (`approve`), with an optional note for the requester. Answers `{ request }`. */
export function rejectRequest(api, id, { note } = {}) {
	const cleaned = cleanNote(note);
	return callPlugin(api, 'post', requestPath(id, 'reject'), cleaned ? { note: cleaned } : {});
}

/** `DELETE /requests/{id}`: the author withdraws an open request. Answers `{ request }`. */
export function cancelRequest(api, id) {
	return callPlugin(api, 'delete', requestPath(id));
}

// The request dialog -------------------------------------------------------------------------

/**
 * The request form's starting values: the type the source suggests when the user's request
 * parameters allow it (capabilities.allowedTypes, `purpose: 'request'`), else none (they must
 * choose: the server needs a type).
 */
export function initialRequestForm(me, detail) {
	return { modelType: allowedTypes(me, detail?.mb_type, { purpose: 'request' }).selected, note: '' };
}

/** Why a note cannot be sent, or ''. */
export function noteProblem(note) {
	return cleanNote(note).length > MAX_NOTE_LENGTH ? `At most ${MAX_NOTE_LENGTH} characters` : '';
}

/** What stops the request form from being sent, per field ('' when nothing), by the request parameters. */
export function requestFormProblems(form, { me, detail, file }) {
	const { types } = allowedTypes(me, detail?.mb_type, { purpose: 'request' });
	let modelType = '';
	if (!form.modelType) modelType = 'Choose what to file this model as';
	else if (!types.includes(form.modelType)) modelType = 'Your permissions do not allow requesting this model type';
	return { modelType, note: noteProblem(form.note), size: sizeProblem(me, file?.size_bytes, { purpose: 'request' }) };
}

/** The body of `POST /requests`: the ids, the type when chosen, the note when written. */
export function buildRequestBody({ detail, version, file, form }) {
	const body = {
		source: detail.source,
		model_id: String(detail.id),
		version_id: String(version.id),
		file_id: String(file.id)
	};
	if (form.modelType) body.model_type = form.modelType;
	const note = cleanNote(form.note);
	if (note) body.note = note;
	return body;
}

/** The warnings of the request dialog: NSFW, then those of a download (early access, login, licence). */
export function requestWarnings({ detail, version, file }) {
	const warnings = [];
	if (detail?.nsfw || version?.nsfw) {
		warnings.push({
			tone: 'warning',
			title: 'NSFW',
			text: 'This model is marked NSFW: the admin sees it in your request, and the approval checks your content policy again.'
		});
	}
	return [...warnings, ...downloadWarnings({ detail, version, file })];
}

// Showing a request ---------------------------------------------------------------------------

/** The type the request asks for: the requester's choice when the server keeps it, else the source's suggestion. */
export function requestedType(request) {
	return request?.model_type || request?.snapshot?.mb_type || '';
}

/** The model name of a request (or its file name). */
export function requestTitle(request) {
	return request?.snapshot?.name || request?.snapshot?.file_name || 'Model';
}

/**
 * The details under the name: version, file, size, type, source.
 *
 * @param {any} request
 * @param {(id: string) => string} [sourceLabel]
 * @returns {string[]}
 */
export function requestMeta(request, sourceLabel) {
	const snapshot = request?.snapshot ?? {};
	const type = modelTypeLabel(requestedType(request)) || snapshot.type;
	const source = request?.source ? (sourceLabel ? sourceLabel(request.source) : request.source) : '';
	return [snapshot.version_name, snapshot.file_name, formatBytes(snapshot.size_bytes), type, source].filter(Boolean);
}

/** The host of the request's source page ('civitai.com'), or ''. */
export function sourceHost(request) {
	try {
		return new URL(request?.snapshot?.source_url ?? '').hostname;
	} catch {
		return '';
	}
}

/**
 * Who asked and when: 'Asked by alice · Oct 11, 2026' ('Asked on Oct 11, 2026' for the user's
 * own); `title` is the full date and time.
 *
 * @returns {{ text: string, title: string }}
 */
export function requestByline(request, { showUser = true, locale } = {}) {
	const time = parseTime(request?.created_at);
	const date = time === null ? '' : formatDate(time, locale);
	let title = '';
	if (time !== null) {
		try {
			title = new Date(time).toLocaleString(locale);
		} catch {
			title = new Date(time).toISOString();
		}
	}
	if (!showUser) return { text: date ? `Asked on ${date}` : '', title };
	return { text: [`Asked by ${request?.username || 'an unknown user'}`, date].filter(Boolean).join(' · '), title };
}

/** Who decided, for a decided request: 'Approved by bob', 'Rejected by bob'; '' otherwise (open, cancelled). */
export function decisionLine(request) {
	const by = request?.decided_by_username;
	switch (request?.status) {
		case 'approved':
		case 'done':
		case 'failed':
			return by ? `Approved by ${by}` : 'Approved';
		case 'rejected':
			return by ? `Rejected by ${by}` : 'Rejected';
		default:
			return '';
	}
}

// Deciding --------------------------------------------------------------------------------------

/** The "File as" choices when approving: the requested type first and selected, then every PotionUI type. */
export function approvalTypeChoice(request) {
	const requested = requestedType(request);
	return {
		types: requested ? [requested, ...MODEL_TYPES.filter((type) => type !== requested)] : [...MODEL_TYPES],
		selected: requested
	};
}

/** What stops the approve form: a type is needed when the request names none; the note's length. */
export function approvalProblems(request, form) {
	return {
		modelType: !form?.modelType && !requestedType(request) ? 'Choose what to file this model as' : '',
		note: noteProblem(form?.note)
	};
}

/** The options of `approveRequest` for the approve form: the note, and the type only when it changes the requested one. */
export function approvalOptions(request, form) {
	const modelType = typeof form?.modelType === 'string' ? form.modelType : '';
	return { note: cleanNote(form?.note), modelType: modelType && modelType !== requestedType(request) ? modelType : '' };
}

// Toasts ----------------------------------------------------------------------------------------

function fileOf(request) {
	return request?.snapshot?.file_name || request?.snapshot?.name || 'the file';
}

function whoOf(request) {
	return request?.username || 'the requester';
}

function decisionError(error, verb) {
	if (error?.code === 'not_open') return { level: 'info', message: 'This request was already handled', refresh: true };
	if (error?.code === 'not_found') return { level: 'info', message: 'This request no longer exists', refresh: true };
	return { level: 'error', message: `Could not ${verb} the request: ${error?.message || 'unknown error'}`, refresh: false };
}

/**
 * The toast for the answer of `POST /requests`. `close`: the dialog has nothing left to do.
 *
 * @param {{ ok: boolean, data?: any, error?: any }} result
 * @param {{ name?: string }} file
 * @returns {{ level: 'success' | 'info' | 'error', message: string, close: boolean }}
 */
export function createToast(result, file) {
	const name = baseName(file?.name) || 'This file';
	if (result.ok) {
		if (result.data?.already_requested) {
			return { level: 'info', message: `You already asked for ${name}: your request is still open`, close: true };
		}
		return { level: 'success', message: `Request sent: an admin will review ${name}`, close: true };
	}
	if (result.error?.code === 'already_available') return { level: 'info', message: `${name} is already in your models`, close: true };
	return { level: 'error', message: `Request refused: ${result.error?.message || 'unknown error'}`, close: false };
}

/**
 * The toast for the answer of an approval. `refresh`: the list changed (or was stale).
 *
 * @returns {{ level: 'success' | 'info' | 'error', message: string, refresh: boolean }}
 */
export function approveToast(result, request) {
	if (!result.ok) return decisionError(result.error, 'approve');
	const data = result.data ?? {};
	if (data.already_installed) {
		return { level: 'success', message: `Approved: ${fileOf(request)} was already installed, now assigned to ${whoOf(request)}`, refresh: true };
	}
	if (data.already_queued) return { level: 'info', message: `Approved: ${fileOf(request)} is already being downloaded`, refresh: true };
	return { level: 'success', message: `Approved: downloading ${fileOf(request)} for ${whoOf(request)}`, refresh: true };
}

/** The toast for the answer of a rejection. */
export function rejectToast(result, request) {
	if (!result.ok) return decisionError(result.error, 'reject');
	return { level: 'success', message: `Rejected the request of ${whoOf(request)} for ${fileOf(request)}`, refresh: true };
}

/** The toast for the answer of a cancellation. */
export function cancelToast(result, request) {
	if (!result.ok) return decisionError(result.error, 'cancel');
	return { level: 'success', message: `Request cancelled: ${fileOf(request)}`, refresh: true };
}

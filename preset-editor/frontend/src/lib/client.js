function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function text(value) {
	return typeof value === 'string' ? value : '';
}

const STATUS_BY_CODE = {
	invalid_request: 400,
	invalid_path: 400,
	not_text: 400,
	unauthorized: 401,
	forbidden: 403,
	not_found: 404,
	conflict: 409,
	not_local: 409,
	id_in_use: 409,
	target_in_use: 409,
	lint_errors: 409,
	load_failed: 409,
	swap_failed: 409,
	precondition_failed: 412,
	too_large: 413,
	precondition_required: 428,
	internal_error: 500,
	copy_failed: 500
};

const CODE_BY_STATUS = {
	400: 'invalid_request',
	401: 'unauthorized',
	403: 'forbidden',
	404: 'not_found',
	409: 'conflict',
	412: 'precondition_failed',
	422: 'invalid_request',
	500: 'internal_error',
	503: 'unavailable'
};

const AUTH_DETAIL = /not authenticated|could not validate credentials|invalid (?:or expired )?token|token (?:has )?expired/i;
const ADMIN_DETAIL = /admin/i;

function defaultMessage(status) {
	if (status === 401) return 'Your session has expired: sign in again';
	if (status === 403) return 'You do not have permission to do this';
	if (status === 404) return 'Not found';
	if (status >= 500) return 'The server could not complete the request';
	return 'Request failed';
}

export function normalizeError(body, status = 0) {
	let code = '';
	let message = '';
	let lint = null;
	let errors = null;
	let httpStatus = Number.isInteger(status) && status > 0 ? status : 0;
	if (isObject(body)) {
		const { detail } = body;
		if (typeof detail === 'string') {
			message = detail;
			if (!httpStatus && AUTH_DETAIL.test(detail)) httpStatus = 401;
			else if (!httpStatus && ADMIN_DETAIL.test(detail)) httpStatus = 403;
		} else if (Array.isArray(detail)) {
			message = detail
				.map((item) => (isObject(item) && typeof item.msg === 'string' ? item.msg : ''))
				.filter(Boolean)
				.join('; ');
			code = 'invalid_request';
			if (!httpStatus) httpStatus = 422;
		} else {
			const fields = isObject(detail) ? detail : body;
			code = text(fields.error);
			message = text(fields.message);
			if (isObject(fields.lint)) lint = fields.lint;
			if (Array.isArray(fields.errors)) errors = fields.errors.filter((item) => typeof item === 'string');
		}
	}
	if (!httpStatus) httpStatus = STATUS_BY_CODE[code] ?? 0;
	if (!code) code = CODE_BY_STATUS[httpStatus] ?? 'error';
	if (!message) message = defaultMessage(httpStatus);
	const error = { status: httpStatus, code, message };
	if (lint) error.lint = lint;
	if (errors) error.errors = errors;
	if (isObject(body)) {
		const fields = isObject(body.detail) ? body.detail : body;
		if (typeof fields.etag === 'string') error.etag = fields.etag;
		if (typeof fields.content === 'string') error.content = fields.content;
	}
	return error;
}

function thrownError(err) {
	if (err instanceof SyntaxError) {
		return { status: 0, code: 'invalid_response', message: 'The server sent a response that is not valid JSON' };
	}
	if (err instanceof TypeError) {
		return { status: 0, code: 'network_error', message: 'Could not reach the server' };
	}
	return { status: 0, code: 'network_error', message: err instanceof Error && err.message ? err.message : 'Request failed' };
}

export function unwrap(payload) {
	if (isObject(payload) && payload.success === true) return { ok: true, data: payload.data };
	if (!isObject(payload)) {
		return { ok: false, error: { status: 0, code: 'invalid_response', message: 'Unexpected response from the server' } };
	}
	return { ok: false, error: normalizeError(payload) };
}

export async function callPlugin(api, method, path, body) {
	if (!api || typeof api[method] !== 'function') {
		return { ok: false, error: { status: 0, code: 'no_api', message: 'The page has no connection to the server' } };
	}
	let payload;
	try {
		payload = body === undefined ? await api[method](path) : await api[method](path, body);
	} catch (err) {
		return { ok: false, error: thrownError(err) };
	}
	return unwrap(payload);
}

export async function callCore(api, path, { method = 'GET', body, form, headers: extra = {} } = {}) {
	const token = typeof api?.getToken === 'function' ? api.getToken() : null;
	const headers = { Accept: 'application/json', ...extra };
	if (token) headers.Authorization = `Bearer ${token}`;
	const init = { method, headers, credentials: 'include', cache: 'no-store' };
	if (form !== undefined) {
		init.body = form;
	} else if (body !== undefined) {
		headers['Content-Type'] = 'application/json';
		init.body = JSON.stringify(body);
	}
	let response;
	try {
		response = await fetch(path, init);
	} catch (err) {
		return { ok: false, error: thrownError(err) };
	}
	let payload = null;
	try {
		payload = await response.json();
	} catch {
	}
	if (!response.ok) return { ok: false, error: normalizeError(payload, response.status || 0) };
	return unwrap(payload);
}

const PLUGIN_PREFIX = '/api/plugins/preset-editor';

function segment(value) {
	return encodeURIComponent(String(value));
}

function filePath(value) {
	return String(value).split('/').map(segment).join('/');
}

export function getMe(api) {
	return callPlugin(api, 'get', '/me');
}

export function listCatalog(api) {
	return callCore(api, '/api/presets?include_uninstalled=true');
}

export function listDrafts(api) {
	return callPlugin(api, 'get', '/drafts');
}

export function getDraft(api, draftId) {
	return callPlugin(api, 'get', `/drafts/${segment(draftId)}`);
}

export function createCopyDraft(api, body) {
	return callPlugin(api, 'post', '/drafts', { mode: 'copy', ...body });
}

export function createDraft(api, body) {
	return callPlugin(api, 'post', '/drafts', body);
}

export function readFile(api, draftId, path) {
	return callPlugin(api, 'get', `/drafts/${segment(draftId)}/files/${filePath(path)}`);
}

export function writeFile(api, draftId, path, content, etag) {
	return callCore(api, `${PLUGIN_PREFIX}/drafts/${segment(draftId)}/files/${filePath(path)}`, {
		method: 'PUT',
		body: { content },
		headers: etag ? { 'If-Match': etag } : {}
	});
}

export function deleteFile(api, draftId, path) {
	return callPlugin(api, 'delete', `/drafts/${segment(draftId)}/files/${filePath(path)}`);
}

export function addMode(api, draftId, body) {
	return callPlugin(api, 'post', `/drafts/${segment(draftId)}/modes`, body);
}

export function removeMode(api, draftId, mode) {
	return callPlugin(api, 'delete', `/drafts/${segment(draftId)}/modes/${segment(mode)}`);
}

export function mediaUrl(draftId, path) {
	return `${PLUGIN_PREFIX}/drafts/${segment(draftId)}/public/${filePath(path)}`;
}

export function listMedia(api, draftId) {
	return callPlugin(api, 'get', `/drafts/${segment(draftId)}/media`);
}

export function uploadMedia(api, draftId, file, { role = 'gallery', caption = '', mode = '' } = {}) {
	const form = new FormData();
	form.append('file', file, file.name);
	form.append('role', role);
	if (caption) form.append('caption', caption);
	if (mode) form.append('mode', mode);
	return callCore(api, `${PLUGIN_PREFIX}/drafts/${segment(draftId)}/media`, { method: 'POST', form });
}

export function updateMedia(api, draftId, body) {
	return callCore(api, `${PLUGIN_PREFIX}/drafts/${segment(draftId)}/media`, { method: 'PUT', body });
}

export function deleteMedia(api, draftId, path) {
	return callPlugin(api, 'delete', `/drafts/${segment(draftId)}/media/${filePath(path)}`);
}

export function sharedReference(api) {
	return callPlugin(api, 'get', '/reference/shared');
}

export function pipesReference(api) {
	return callCore(api, '/api/docs/live/pipes');
}

export function deleteDraft(api, draftId) {
	return callPlugin(api, 'delete', `/drafts/${segment(draftId)}`);
}

export function lintDraft(api, draftId) {
	return callPlugin(api, 'post', `/drafts/${segment(draftId)}/lint`, {});
}

export function publishDraft(api, draftId, { install } = {}) {
	return callPlugin(api, 'post', `/drafts/${segment(draftId)}/publish`, install === undefined ? {} : { install });
}

export function editPreset(api, presetId) {
	return callPlugin(api, 'post', `/presets/${segment(presetId)}/edit`, {});
}

export function deletePreset(api, presetId) {
	return callPlugin(api, 'delete', `/presets/${segment(presetId)}`);
}

export function listHistory(api, presetId) {
	return callPlugin(api, 'get', `/presets/${segment(presetId)}/history`);
}

export function restoreVersion(api, presetId, stamp) {
	return callPlugin(api, 'post', `/presets/${segment(presetId)}/history/${segment(stamp)}/restore`, {});
}

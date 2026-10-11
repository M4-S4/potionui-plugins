// Plain-JS calls to the Model Browser backend and the few core routes the page needs. No Svelte
// in here, so the logic can be unit tested with `node --test` (see client.test.js).
//
// Plugin routes go through the `api` object the host hands to `mountPlugin`
// (routes/plugins/[pluginId]/[...path]/+page.svelte): `api.get(path)` / `api.post(path, body)`
// target `/api/plugins/model-browser<path>` with the user's token and resolve to the parsed JSON
// body *whatever the HTTP status*; they reject only when the request fails or the body is not
// JSON. The status is therefore read back from the error code of the envelope
// (`{detail: {success: false, error, message}}`).
//
// Core routes (`/api/settings/...`, `/api/backends`) are called with `fetch` and
// `Authorization: Bearer ${api.getToken()}`; the token only ever goes in that header.
//
// Every call resolves to `{ ok: true, data }` or `{ ok: false, error }`, where `error` is
// `{ status, code, message, retryAfter }` (`status` 0 when unknown, `retryAfter` in seconds or
// null). None of them rejects.

/**
 * @typedef {object} HealthResult
 * @property {boolean} ok            True when the backend answered and reports itself healthy.
 * @property {string} [version]      Backend version, when it reports one.
 * @property {string} [error]        Human readable reason, set when `ok` is false.
 */

/**
 * @typedef {object} ApiError
 * @property {number} status        HTTP status, read or inferred from the error code; 0 when unknown.
 * @property {string} code          The envelope's error code (`not_found`, `rate_limited`, ...).
 * @property {string} message       For people.
 * @property {number | null} retryAfter  Seconds to wait before retrying (429), when known.
 */

/** @typedef {{ ok: true, data: any } | { ok: false, error: ApiError }} CallResult */

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function text(value) {
	return typeof value === 'string' ? value : '';
}

/** Message of an error body: `{detail: 'text'}`, `{detail: {message}}` or `{message}`. */
function errorText(body) {
	if (typeof body.detail === 'string' && body.detail) return body.detail;
	const fields = isObject(body.detail) ? body.detail : body;
	for (const candidate of [fields.message, fields.error]) {
		if (typeof candidate === 'string' && candidate) return candidate;
	}
	return 'Request failed';
}

/** Message of whatever `api.get` threw (network failure, or a body that is not JSON). */
function thrownText(err) {
	if (err instanceof SyntaxError) return 'The backend sent a response that is not valid JSON';
	if (err instanceof Error && err.message) return err.message;
	if (typeof err === 'string' && err) return err;
	return 'Request failed';
}

/**
 * Ask the backend whether it is up.
 *
 * `api` is the object the host hands to `mountPlugin`: `api.get(path)` resolves to the parsed
 * JSON body whatever the HTTP status, and only rejects when the request itself fails or the
 * body is not JSON. So failures arrive in three ways, all folded into `{ ok: false, error }`:
 *   - a rejection (network down, non-JSON body);
 *   - an error body: `{ success: false, message }` or FastAPI's `{ detail }`;
 *   - a body that does not look like a health answer.
 * A healthy answer is `{ success: true, data: { status: 'ok', version } }`; the flat form
 * `{ status: 'ok', version }` is accepted too. Never rejects.
 *
 * @param {{ get: (path: string) => Promise<unknown> }} api
 * @returns {Promise<HealthResult>}
 */
export async function fetchHealth(api) {
	let payload;
	try {
		payload = await api.get('/health');
	} catch (err) {
		return { ok: false, error: thrownText(err) };
	}

	if (!isObject(payload)) return { ok: false, error: 'Unexpected response from /health' };
	if (payload.success === false || payload.detail !== undefined) {
		return { ok: false, error: errorText(payload) };
	}

	const body = isObject(payload.data) ? payload.data : payload;
	const hasStatus = typeof body.status === 'string';
	const healthy = hasStatus ? body.status === 'ok' : body.ok === true || payload.success === true;
	if (!healthy) {
		return { ok: false, error: hasStatus ? `Backend status: ${body.status}` : 'Unexpected response from /health' };
	}
	return typeof body.version === 'string' ? { ok: true, version: body.version } : { ok: true };
}

/**
 * Status line text for a health check. `null` means the check is still running.
 *
 * @param {HealthResult | null} result
 * @returns {string}
 */
export function healthLabel(result) {
	if (!result) return 'Backend: checking…';
	if (!result.ok) return `Backend error: ${result.error ?? 'unknown error'}`;
	return result.version ? `Backend: ok (v${result.version.replace(/^v/i, '')})` : 'Backend: ok';
}

// Errors -------------------------------------------------------------------------------------

/** HTTP status of the backend's error codes (routes_sources.py, routes_downloads.py, permissions.py). */
const STATUS_BY_CODE = {
	invalid_request: 400,
	invalid: 400,
	unauthorized: 401,
	forbidden: 403,
	not_found: 404,
	unknown_source: 404,
	blocked: 409,
	rate_limited: 429,
	internal_error: 500,
	source_unavailable: 502
};

const CODE_BY_STATUS = {
	400: 'invalid_request',
	401: 'unauthorized',
	403: 'forbidden',
	404: 'not_found',
	409: 'conflict',
	422: 'invalid_request',
	429: 'rate_limited',
	500: 'internal_error',
	502: 'source_unavailable',
	503: 'unavailable'
};

// The core's own auth dependencies answer with a plain `{detail: '...'}`.
const AUTH_DETAIL = /not authenticated|could not validate credentials|invalid (?:or expired )?token|token (?:has )?expired/i;

function defaultMessage(status) {
	if (status === 401) return 'Your session has expired: sign in again';
	if (status === 403) return 'You do not have permission to do this';
	if (status === 404) return 'Not found';
	if (status === 429) return 'Too many requests: try again in a moment';
	if (status >= 500) return 'The server could not complete the request';
	return 'Request failed';
}

/**
 * Seconds to wait, from a `Retry-After` value or from a message such as
 * "CivitAI rate limit reached; try again in 30 s". Null when it says nothing.
 *
 * @param {unknown} value
 * @returns {number | null}
 */
export function parseRetryAfter(value) {
	if (typeof value === 'number') return Number.isFinite(value) && value >= 0 ? Math.ceil(value) : null;
	if (typeof value !== 'string' || !value.trim()) return null;
	if (/^\s*\d+(?:\.\d+)?\s*$/.test(value)) return Math.ceil(Number(value));
	const match = value.match(/(?:try again|retry)\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*(?:s\b|sec|second)/i);
	return match ? Math.ceil(Number(match[1])) : null;
}

/**
 * An error answer as `{ status, code, message, retryAfter }`.
 *
 * @param {unknown} body       The parsed JSON body (any shape, or null).
 * @param {number} [status]    The HTTP status when known (core calls); 0 or omitted otherwise.
 * @param {string | null} [retryAfterHeader]  The `Retry-After` header when known.
 * @returns {ApiError}
 */
export function normalizeError(body, status = 0, retryAfterHeader = null) {
	let code = '';
	let message = '';
	let httpStatus = Number.isInteger(status) && status > 0 ? status : 0;
	if (isObject(body)) {
		const { detail } = body;
		if (typeof detail === 'string') {
			message = detail;
			if (!httpStatus && AUTH_DETAIL.test(detail)) httpStatus = 401;
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
		}
	}
	if (!httpStatus) httpStatus = STATUS_BY_CODE[code] ?? 0;
	if (!code) code = CODE_BY_STATUS[httpStatus] ?? 'error';
	if (!message) message = defaultMessage(httpStatus);
	const limited = httpStatus === 429 || code === 'rate_limited';
	const retryAfter = limited ? parseRetryAfter(retryAfterHeader) ?? parseRetryAfter(message) : null;
	return { status: httpStatus, code, message, retryAfter };
}

/** The error of a request that got no usable answer. */
function thrownError(err) {
	if (err instanceof SyntaxError) {
		return { status: 0, code: 'invalid_response', message: 'The server sent a response that is not valid JSON', retryAfter: null };
	}
	if (err instanceof TypeError) {
		return { status: 0, code: 'network_error', message: 'Could not reach the server', retryAfter: null };
	}
	return { status: 0, code: 'network_error', message: thrownText(err), retryAfter: null };
}

/**
 * A parsed answer as a call result: the envelope's `data` on success, a normalised error otherwise.
 *
 * @param {unknown} payload
 * @param {number} [status]
 * @param {string | null} [retryAfterHeader]
 * @returns {CallResult}
 */
export function unwrap(payload, status = 0, retryAfterHeader = null) {
	if (status >= 400) return { ok: false, error: normalizeError(payload, status, retryAfterHeader) };
	if (isObject(payload) && payload.success === true) return { ok: true, data: payload.data };
	if (isObject(payload) && payload.success === undefined && payload.detail === undefined && 'data' in payload) {
		return { ok: true, data: payload.data };
	}
	if (!isObject(payload)) {
		return { ok: false, error: { status, code: 'invalid_response', message: 'Unexpected response from the server', retryAfter: null } };
	}
	return { ok: false, error: normalizeError(payload, status, retryAfterHeader) };
}

// Plugin routes ------------------------------------------------------------------------------

/** @returns {Promise<CallResult>} */
async function callPlugin(api, method, path, body) {
	if (!api || typeof api[method] !== 'function') {
		return { ok: false, error: { status: 0, code: 'no_api', message: 'The page has no connection to the server', retryAfter: null } };
	}
	let payload;
	try {
		payload = body === undefined ? await api[method](path) : await api[method](path, body);
	} catch (err) {
		return { ok: false, error: thrownError(err) };
	}
	return unwrap(payload);
}

function encodeSegment(value) {
	return encodeURIComponent(String(value));
}

/**
 * The path of a model's detail route: `/<source>/models/<id>`, each segment of the id encoded
 * on its own (Hugging Face ids are `org/repo`, read by the backend's `{model_id:path}`).
 */
export function modelPath(source, id) {
	return `/${encodeSegment(source)}/models/${String(id).split('/').map(encodeSegment).join('/')}`;
}

/** `GET /me`: capabilities, download parameters and NSFW context of the signed-in user. */
export function getMe(api) {
	return callPlugin(api, 'get', '/me');
}

/** `GET /sources`: the enabled sources and their filters. */
export function getSources(api) {
	return callPlugin(api, 'get', '/sources');
}

/**
 * `GET /{source}/search?<query>`: one page of results.
 *
 * @param {any} api
 * @param {string} source
 * @param {string} query  From `search.searchRequest` (no '?').
 */
export function searchModels(api, source, query) {
	return callPlugin(api, 'get', `/${encodeSegment(source)}/search${query ? `?${query}` : ''}`);
}

/** `GET /{source}/models/{id}`: the model as this user may see it (404 when they may not). */
export function getModel(api, source, id) {
	return callPlugin(api, 'get', modelPath(source, id));
}

/** `GET /{source}/models/{id}/nsfw-media`: the urls of the model's NSFW images (404 under a `blocked` ceiling). */
export function getNsfwMedia(api, source, id) {
	return callPlugin(api, 'get', `${modelPath(source, id)}/nsfw-media`);
}

/** `POST /installed`: which of these SHA256 are installed (and visible to the user). At most 200. */
export function getInstalled(api, sha256s) {
	return callPlugin(api, 'post', '/installed', { sha256s: [...new Set(sha256s)].slice(0, 200) });
}

/** `POST /downloads`: queue one file (body built by `downloadForm.buildDownloadBody`). */
export function startDownload(api, body) {
	return callPlugin(api, 'post', '/downloads', body);
}

/**
 * `GET /downloads`: the downloads started through the plugin, newest first.
 *
 * @param {any} api
 * @param {{ all?: boolean, limit?: number }} [options]  `all: false` keeps the user's own rows
 *        (an admin or an `approve` holder gets everyone's by default).
 */
export function listDownloads(api, { all, limit } = {}) {
	const params = new URLSearchParams();
	if (typeof all === 'boolean') params.set('all', String(all));
	if (typeof limit === 'number') params.set('limit', String(limit));
	const query = params.toString();
	return callPlugin(api, 'get', `/downloads${query ? `?${query}` : ''}`);
}

// Core routes --------------------------------------------------------------------------------

/** @returns {Promise<CallResult>} */
async function callCore(api, path, { method = 'GET', body, fetchImpl } = {}) {
	const doFetch = fetchImpl ?? globalThis.fetch;
	if (typeof doFetch !== 'function') {
		return { ok: false, error: { status: 0, code: 'no_fetch', message: 'This browser cannot reach the server', retryAfter: null } };
	}
	const token = typeof api?.getToken === 'function' ? api.getToken() : null;
	const headers = { Accept: 'application/json' };
	if (token) headers.Authorization = `Bearer ${token}`;
	const init = { method, headers, credentials: 'include', cache: 'no-store' };
	if (body !== undefined) {
		headers['Content-Type'] = 'application/json';
		init.body = JSON.stringify(body);
	}

	let response;
	try {
		response = await doFetch(path, init);
	} catch (err) {
		return { ok: false, error: thrownError(err) };
	}
	let payload = null;
	try {
		payload = await response.json();
	} catch {
		// Not JSON (a proxy's error page, an empty body): reported from the status.
	}
	const retryAfter = typeof response.headers?.get === 'function' ? response.headers.get('Retry-After') : null;
	if (!response.ok) return { ok: false, error: normalizeError(payload, response.status || 0, retryAfter) };
	return unwrap(payload, 0, retryAfter);
}

/**
 * Change the user's app-wide NSFW display mode: `PUT /api/settings/<key>` with `{ value: mode }`,
 * as the app's own control does (frontend/src/lib/stores/nsfwFilter.ts).
 *
 * @param {any} api
 * @param {'blur' | 'show' | 'hide'} mode
 * @param {{ key?: string, fetchImpl?: typeof fetch }} [options]  `key` from `/me` (`nsfw.setting_key`).
 */
export function setNsfwMode(api, mode, { key = 'media_nsfw_filter_mode', fetchImpl } = {}) {
	return callCore(api, `/api/settings/${encodeSegment(key)}`, { method: 'PUT', body: { value: mode }, fetchImpl });
}

/**
 * The remote backends a download can go to: `GET /api/backends`, enabled ones whose driver is
 * `native.remote`, as `{ id, name }`.
 *
 * @param {any} api
 * @param {{ fetchImpl?: typeof fetch }} [options]
 * @returns {Promise<{ ok: true, data: { id: string, name: string }[] } | { ok: false, error: ApiError }>}
 */
export async function listRemoteBackends(api, { fetchImpl } = {}) {
	const result = await callCore(api, '/api/backends', { fetchImpl });
	if (!result.ok) return result;
	const backends = Array.isArray(result.data) ? result.data : [];
	return {
		ok: true,
		data: backends
			.filter((backend) => isObject(backend) && backend.enabled !== false && backend.driver === 'native.remote' && backend.id)
			.map((backend) => ({ id: String(backend.id), name: text(backend.name) || String(backend.id) }))
	};
}

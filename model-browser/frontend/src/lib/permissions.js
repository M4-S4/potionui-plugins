// Plain-JS helpers for the Permissions admin tab: the editable form behind the API payload, its
// validation, and the two calls to /permissions. No Svelte in here, so the logic can be unit
// tested with `node --test` (see permissions.test.js).
//
// The API (backend/routes_permissions.py) answers `GET` and `PUT /permissions` with
//   { success: true, data: { capabilities, sources, model_types, groups: [
//       { group_id, name, is_system, capabilities,
//         params: { sources, model_types, max_file_gb, assign_to, allow_remote } } ] } }
// and fails with `{ detail: { success: false, error, message } }` (400 / 401 / 403) or a plain
// `{ detail: 'text' }` from the core's own auth dependencies.

/**
 * @typedef {object} GroupParams
 * @property {string[]} sources
 * @property {string[]} model_types   Empty: every type is allowed.
 * @property {string} max_file_gb     The text of the size field; '' means no limit.
 * @property {string} assign_to       'user' | 'group'
 * @property {boolean} allow_remote
 */

/**
 * @typedef {object} GroupRow
 * @property {string} group_id
 * @property {string} name
 * @property {boolean} is_system
 * @property {string[]} capabilities
 * @property {GroupParams} params
 */

/**
 * @typedef {object} FormState
 * @property {{ capabilities: string[], sources: string[], model_types: string[] }} allowed
 *           The values each field accepts, as the API lists them (display order).
 * @property {GroupRow[]} groups
 */

/** localStorage key under which the host keeps the signed-in user's token. */
export const AUTH_TOKEN_KEY = 'auth_token';

/** Who a downloaded model is assigned to (backend `permissions_store.ASSIGN_TO`). */
export const ASSIGN_TO = ['user', 'group'];

// Used only when the API leaves a field out, which it does not do today. They mirror
// `permissions_store.CAPABILITIES` and `DEFAULT_SOURCES`.
const FALLBACK_CAPABILITIES = ['browse', 'request', 'download', 'approve'];
const FALLBACK_SOURCES = ['civitai', 'huggingface', 'openmodeldb'];

// A decimal number written with a dot: '4', '4.5', '.5', '5.', '1e3'. Stricter than `Number()`,
// which also accepts '0x10' and 'Infinity'.
const GB_PATTERN = /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** The strings of a list, duplicates dropped, order kept; `fallback` when it is not a list. */
function stringList(value, fallback) {
	if (!Array.isArray(value)) return [...fallback];
	return [...new Set(value.filter((item) => typeof item === 'string'))];
}

function sortedUnique(list) {
	return [...new Set(list)].sort();
}

/**
 * Read the text of a "maximum file size in GB" field.
 *
 * Empty (or `null`) means no limit and gives `{ ok: true, value: null }`; a positive number
 * written with a dot gives `{ ok: true, value }`; anything else (zero, negative, a comma,
 * half-typed '1e', letters) is `{ ok: false }`, so it can never be saved as "no limit" by mistake.
 *
 * @param {unknown} text
 * @returns {{ ok: true, value: number | null } | { ok: false }}
 */
export function parseMaxFileGb(text) {
	if (text === null || text === undefined) return { ok: true, value: null };
	if (typeof text === 'number') {
		return Number.isFinite(text) && text > 0 ? { ok: true, value: text } : { ok: false };
	}
	if (typeof text !== 'string') return { ok: false };
	const trimmed = text.trim();
	if (trimmed === '') return { ok: true, value: null };
	if (!GB_PATTERN.test(trimmed)) return { ok: false };
	const value = Number(trimmed);
	return Number.isFinite(value) && value > 0 ? { ok: true, value } : { ok: false };
}

/** The API's `max_file_gb` (number or null) as the text of the field. */
function formatMaxFileGb(value) {
	if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? String(value) : '';
	return typeof value === 'string' ? value.trim() : '';
}

function toRow(group) {
	const params = isObject(group.params) ? group.params : {};
	const id = String(group.group_id);
	return {
		group_id: id,
		name: typeof group.name === 'string' && group.name ? group.name : id,
		is_system: group.is_system === true,
		capabilities: sortedUnique(stringList(group.capabilities, [])),
		params: {
			sources: sortedUnique(stringList(params.sources, FALLBACK_SOURCES)),
			model_types: sortedUnique(stringList(params.model_types, [])),
			max_file_gb: formatMaxFileGb(params.max_file_gb),
			assign_to: typeof params.assign_to === 'string' ? params.assign_to : 'user',
			allow_remote: params.allow_remote === true
		}
	};
}

/**
 * The editable form for an API answer: the response body of `GET` or `PUT /permissions`
 * (`{ success, data }`), or its `data` alone. Every call returns fresh objects, so one answer
 * can feed both the "saved" copy and the copy being edited.
 *
 * @param {unknown} payload
 * @returns {FormState}
 */
export function toFormState(payload) {
	const data = isObject(payload) && isObject(payload.data) ? payload.data : payload;
	const source = isObject(data) ? data : {};
	return {
		allowed: {
			capabilities: stringList(source.capabilities, FALLBACK_CAPABILITIES),
			sources: stringList(source.sources, []),
			model_types: stringList(source.model_types, [])
		},
		groups: (Array.isArray(source.groups) ? source.groups : [])
			.filter((group) => isObject(group) && group.group_id !== undefined && group.group_id !== null)
			.map(toRow)
	};
}

/**
 * The body of `PUT /permissions` for a form: every group with its capabilities and parameters
 * (the API replaces the whole table, and keeps the parameters of a group that does not hold
 * `download` for the day it does), lists sorted, the size parsed, '' sent as null.
 *
 * Throws a `RangeError` when a size is not a valid number: run `validateState` first.
 *
 * @param {FormState} state
 */
export function toPutBody(state) {
	return {
		groups: state.groups.map((group) => {
			const size = parseMaxFileGb(group.params.max_file_gb);
			if (!size.ok) throw new RangeError(`Invalid maximum file size for the group '${group.group_id}'`);
			return {
				group_id: group.group_id,
				capabilities: sortedUnique(group.capabilities),
				params: {
					sources: sortedUnique(group.params.sources),
					model_types: sortedUnique(group.params.model_types),
					max_file_gb: size.value,
					assign_to: group.params.assign_to,
					allow_remote: group.params.allow_remote === true
				}
			};
		})
	};
}

/** The entries of `values` that are not in `allowed`. */
function outside(values, allowed) {
	return values.filter((value) => !allowed.includes(value));
}

/**
 * What stops a form from being saved, as readable messages (empty: it can be saved). Mirrors
 * what the API refuses: capabilities, sources and model types must be ones it lists, the size
 * must be a number above 0 or empty, `assign_to` must be 'user' or 'group'.
 *
 * @param {FormState} state
 * @returns {string[]}
 */
export function validateState(state) {
	const allowed = state?.allowed ?? { capabilities: [], sources: [], model_types: [] };
	const problems = [];
	for (const group of state?.groups ?? []) {
		const fail = (message) => problems.push(`${group.name || group.group_id}: ${message}`);

		for (const capability of outside(group.capabilities, allowed.capabilities)) {
			fail(`unknown permission '${capability}'`);
		}
		for (const source of outside(group.params.sources, allowed.sources)) {
			fail(`unknown source '${source}'`);
		}
		for (const type of outside(group.params.model_types, allowed.model_types)) {
			fail(`unknown model type '${type}'`);
		}
		if (!parseMaxFileGb(group.params.max_file_gb).ok) {
			fail('the maximum file size must be a number above 0 (decimals with a dot), or empty for no limit');
		}
		if (!ASSIGN_TO.includes(group.params.assign_to)) {
			fail("'assign to' must be 'user' or 'group'");
		}
	}
	return problems;
}

/** A form reduced to what the API stores, in a fixed order, so two forms can be compared. */
function canonical(state) {
	return (state?.groups ?? []).map((group) => {
		const size = parseMaxFileGb(group.params.max_file_gb);
		return {
			id: group.group_id,
			capabilities: sortedUnique(group.capabilities),
			sources: sortedUnique(group.params.sources),
			modelTypes: sortedUnique(group.params.model_types),
			// '5' and '5.0' are the same limit; text that is not a number only equals itself.
			maxFileGb: size.ok ? size.value : `invalid:${String(group.params.max_file_gb).trim()}`,
			assignTo: group.params.assign_to,
			allowRemote: group.params.allow_remote === true
		};
	});
}

/**
 * Whether `state` differs from `initial` in anything the API stores (names, order of the
 * lists and the way a number is written do not count).
 *
 * @param {FormState | null} initial
 * @param {FormState | null} state
 */
export function isDirty(initial, state) {
	if (!initial || !state) return initial !== state;
	return JSON.stringify(canonical(initial)) !== JSON.stringify(canonical(state));
}

/** A deep copy of a form (works on Svelte's `$state` proxies, which `structuredClone` refuses). */
export function cloneState(state) {
	return JSON.parse(JSON.stringify(state));
}

/** `list` with `id` added (`on`) or removed, sorted. Never mutates `list`. */
export function toggleItem(list, id, on) {
	const rest = list.filter((item) => item !== id);
	return sortedUnique(on ? [...rest, id] : rest);
}

/**
 * The checkboxes to draw: every allowed id, then any selected id the API does not list any
 * more (a type the core dropped since the row was saved) so the admin can still untick it.
 *
 * @param {string[]} allowed
 * @param {string[]} selected
 */
export function optionsFor(allowed, selected) {
	return [...allowed, ...outside(selected, allowed)];
}

// Talking to the API -----------------------------------------------------------------------
//
// An admin tab is mounted with `{ pluginId, plugin }` only: unlike a plugin page it gets no `api`
// object, so the calls below use `fetch` with the user's token, the way the core's own admin
// tabs do.

/**
 * The signed-in user's token, from the browser's localStorage (null when there is none or the
 * storage is unavailable). It is only ever put in a request header.
 *
 * @param {{ getItem: (key: string) => string | null }} [storage]  Defaults to `localStorage`.
 * @returns {string | null}
 */
export function readToken(storage) {
	try {
		const store = storage ?? globalThis.localStorage;
		return store?.getItem(AUTH_TOKEN_KEY) || null;
	} catch {
		return null;
	}
}

/** Message of an error body: FastAPI's `detail` (text, `{message}` or a list), or `{message}`. */
function errorText(body, status) {
	if (isObject(body)) {
		const { detail } = body;
		if (typeof detail === 'string' && detail) return detail;
		if (Array.isArray(detail)) {
			const text = detail
				.map((item) => (isObject(item) && typeof item.msg === 'string' ? item.msg : ''))
				.filter(Boolean)
				.join('; ');
			if (text) return text;
		}
		const fields = isObject(detail) ? detail : body;
		for (const candidate of [fields.message, fields.error]) {
			if (typeof candidate === 'string' && candidate) return candidate;
		}
	}
	if (status === 401) return 'Your session has expired: sign in again';
	if (status === 403) return 'Only administrators can edit these permissions';
	return `The server answered with an error (HTTP ${status})`;
}

/** Message of whatever `fetch` threw (it rejects with a TypeError when the server is unreachable). */
function thrownText(err) {
	if (err instanceof TypeError) return 'Could not reach the server';
	if (err instanceof Error && err.message) return err.message;
	if (typeof err === 'string' && err) return err;
	return 'Request failed';
}

/**
 * @typedef {{ ok: true, data: any } | { ok: false, status: number, error: string }} CallResult
 *          `data` is the `data` object of the API answer; `status` is 0 when the request never
 *          got an answer.
 */

/** @returns {Promise<CallResult>} Never rejects. */
async function call({ pluginId = 'model-browser', method, body, token, fetchImpl }) {
	const bearer = token === undefined ? readToken() : token;
	const headers = { Accept: 'application/json' };
	if (bearer) headers.Authorization = `Bearer ${bearer}`;
	const init = { method, headers, credentials: 'include', cache: 'no-store' };
	if (body !== undefined) {
		headers['Content-Type'] = 'application/json';
		init.body = JSON.stringify(body);
	}
	const url = `/api/plugins/${encodeURIComponent(pluginId)}/permissions`;

	let response;
	try {
		response = await (fetchImpl ?? fetch)(url, init);
	} catch (err) {
		return { ok: false, status: 0, error: thrownText(err) };
	}

	let payload = null;
	try {
		payload = await response.json();
	} catch {
		// Not JSON (a proxy's error page, an empty body): reported below from the status.
	}

	if (!response.ok) return { ok: false, status: response.status, error: errorText(payload, response.status) };
	if (!isObject(payload) || payload.success === false || !isObject(payload.data) || !Array.isArray(payload.data.groups)) {
		return { ok: false, status: response.status, error: 'Unexpected response from the server' };
	}
	return { ok: true, data: payload.data };
}

/**
 * `GET /api/plugins/<pluginId>/permissions` (admin only).
 *
 * @param {{ pluginId?: string, token?: string | null, fetchImpl?: typeof fetch }} [options]
 *        `token` defaults to the one in localStorage; `fetchImpl` to the global `fetch`.
 * @returns {Promise<CallResult>}
 */
export function fetchPermissions(options = {}) {
	return call({ ...options, method: 'GET' });
}

/**
 * `PUT /api/plugins/<pluginId>/permissions` with a body from `toPutBody`; answers with the
 * stored state, like `GET`.
 *
 * @param {{ groups: object[] }} body
 * @param {{ pluginId?: string, token?: string | null, fetchImpl?: typeof fetch }} [options]
 * @returns {Promise<CallResult>}
 */
export function savePermissions(body, options = {}) {
	return call({ ...options, method: 'PUT', body });
}

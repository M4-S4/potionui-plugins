// Plain-JS helpers for talking to the Model Browser backend. No Svelte in here, so the
// logic can be unit tested with `node --test` (see client.test.js).

/**
 * @typedef {object} HealthResult
 * @property {boolean} ok            True when the backend answered and reports itself healthy.
 * @property {string} [version]      Backend version, when it reports one.
 * @property {string} [error]        Human readable reason, set when `ok` is false.
 */

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
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
	if (!result) return 'Backend: checking\u2026';
	if (!result.ok) return `Backend error: ${result.error ?? 'unknown error'}`;
	return result.version ? `Backend: ok (v${result.version.replace(/^v/i, '')})` : 'Backend: ok';
}

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function text(value) {
	return typeof value === 'string' ? value : '';
}

const STATUS_BY_CODE = {
	invalid_request: 400,
	unauthorized: 401,
	forbidden: 403,
	not_found: 404,
	conflict: 409,
	precondition_failed: 412,
	internal_error: 500
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
		}
	}
	if (!httpStatus) httpStatus = STATUS_BY_CODE[code] ?? 0;
	if (!code) code = CODE_BY_STATUS[httpStatus] ?? 'error';
	if (!message) message = defaultMessage(httpStatus);
	return { status: httpStatus, code, message };
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

export function getMe(api) {
	return callPlugin(api, 'get', '/me');
}

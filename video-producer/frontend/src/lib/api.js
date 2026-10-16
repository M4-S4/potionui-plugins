const CODE_BY_STATUS = {
	400: 'invalid_request',
	401: 'unauthorized',
	403: 'forbidden',
	404: 'not_found',
	409: 'conflict',
	422: 'invalid_request',
	429: 'rate_limited',
	500: 'server_error',
	502: 'server_error',
	503: 'unavailable',
	504: 'server_error'
};

const STATUS_BY_CODE = {
	invalid_request: 400,
	unauthorized: 401,
	forbidden: 403,
	not_found: 404,
	conflict: 409,
	rate_limited: 429,
	server_error: 500,
	internal_error: 500,
	unavailable: 503
};

const AUTH_DETAIL = /not authenticated|could not validate credentials|invalid (?:or expired )?token|token (?:has )?expired/i;

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function text(value) {
	return typeof value === 'string' ? value : '';
}

function failure(status, code, message = '') {
	return { ok: false, error: { status, code, message } };
}

export function normalizeError(body, status = 0) {
	let httpStatus = Number.isInteger(status) && status > 0 ? status : 0;
	let code = '';
	let message = '';
	if (isObject(body)) {
		const { detail } = body;
		if (typeof detail === 'string') {
			message = detail;
			if (!httpStatus && AUTH_DETAIL.test(detail)) httpStatus = 401;
		} else if (Array.isArray(detail)) {
			code = 'invalid_request';
			message = detail.map((item) => text(item?.msg)).filter(Boolean).join('; ');
			if (!httpStatus) httpStatus = 422;
		} else {
			const fields = isObject(detail) ? detail : body;
			code = text(fields.error) || text(fields.code);
			message = text(fields.message);
		}
	}
	if (!httpStatus) httpStatus = STATUS_BY_CODE[code] ?? 0;
	if (!code) code = CODE_BY_STATUS[httpStatus] ?? (httpStatus >= 500 ? 'server_error' : 'unknown');
	return { status: httpStatus, code, message };
}

function thrown(err) {
	if (err?.name === 'AbortError') return failure(0, 'aborted');
	if (err instanceof SyntaxError) return failure(0, 'invalid_response');
	return failure(0, 'network_error', text(err?.message));
}

export function unwrap(payload) {
	if (!isObject(payload)) return failure(0, 'invalid_response');
	if (payload.success === true) return { ok: true, data: payload.data };
	if (payload.success === undefined && payload.detail === undefined && 'data' in payload) {
		return { ok: true, data: payload.data };
	}
	return { ok: false, error: normalizeError(payload) };
}

async function call(api, method, path, body) {
	if (typeof api?.[method] !== 'function') return failure(0, 'no_api');
	try {
		return unwrap(body === undefined ? await api[method](path) : await api[method](path, body));
	} catch (err) {
		return thrown(err);
	}
}

function quotaOf(limits) {
	let entries = [];
	if (Array.isArray(limits)) entries = limits.filter(isObject);
	else if (isObject(limits) && 'limit' in limits) entries = [limits];
	else if (isObject(limits)) {
		entries = Object.entries(limits)
			.filter(([, value]) => isObject(value))
			.map(([kind, value]) => ({ kind, ...value }));
	}
	const entry = entries.find((item) => text(item.kind).endsWith('gpu_minutes')) ?? entries[0];
	if (!entry || entry.exempt === true) return null;
	const limit = Number(entry.limit);
	if (entry.limit === null || entry.limit === undefined || !Number.isFinite(limit)) return null;
	const used = Number.isFinite(Number(entry.used)) ? Number(entry.used) : 0;
	const remaining = Number.isFinite(entry.remaining) ? entry.remaining : limit - used;
	return { kind: text(entry.kind), limit, used, remaining: Math.max(0, remaining), resetsAt: text(entry.resets_at) || null };
}

export function normalizeMe(data) {
	const me = isObject(data) ? data : {};
	const user = isObject(me.user) ? me.user : {};
	const plugin = isObject(me.plugin) ? me.plugin : {};
	return {
		locale: text(me.locale) || null,
		version: text(plugin.version) || null,
		username: text(user.username) || text(me.username),
		isAdmin: me.is_admin === true || user.is_admin === true,
		quota: quotaOf(me.limits)
	};
}

export async function coreFetch(api, path, init = {}) {
	const headers = new Headers(init.headers);
	const token = typeof api?.getToken === 'function' ? api.getToken() : null;
	if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
	let response;
	try {
		response = await fetch(path, { ...init, headers, credentials: 'include' });
	} catch (err) {
		return thrown(err);
	}
	if (response.ok) return { ok: true, response };
	let body = null;
	try {
		body = await response.json();
	} catch {
		body = null;
	}
	return { ok: false, error: normalizeError(body, response.status) };
}

export function createClient(api) {
	return {
		async me() {
			const result = await call(api, 'get', '/me');
			return result.ok ? { ok: true, data: normalizeMe(result.data) } : result;
		},
		saveLocale(locale) {
			return call(api, 'put', '/me', { locale });
		},
		coreFetch(path, init) {
			return coreFetch(api, path, init);
		}
	};
}

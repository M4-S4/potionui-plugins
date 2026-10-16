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
	return { ok: false, error: { status, code, message, data: null } };
}

function number(value, fallback = null) {
	const n = Number(value);
	return value === null || value === undefined || value === '' || !Number.isFinite(n) ? fallback : n;
}

export function normalizeError(body, status = 0) {
	let httpStatus = Number.isInteger(status) && status > 0 ? status : 0;
	let code = '';
	let message = '';
	let data = null;
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
			if (fields.data !== undefined) data = fields.data;
		}
	}
	if (!httpStatus) httpStatus = STATUS_BY_CODE[code] ?? 0;
	if (!code) code = CODE_BY_STATUS[httpStatus] ?? (httpStatus >= 500 ? 'server_error' : 'unknown');
	return { status: httpStatus, code, message, data };
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
	if (typeof api?.request === 'function') {
		try {
			return unwrap(await api.request(method.toUpperCase(), path, body));
		} catch (err) {
			if (Number.isInteger(err?.status) && err.status > 0) return { ok: false, error: normalizeError(isObject(err.body) ? err.body : { detail: err.detail ?? err.message }, err.status) };
			return thrown(err);
		}
	}
	if (typeof api?.[method] !== 'function') return failure(0, 'no_api');
	try {
		return unwrap(body === undefined ? await api[method](path) : await api[method](path, body));
	} catch (err) {
		return thrown(err);
	}
}

function mapped(result, pick) {
	if (!result.ok) return result;
	const data = pick(isObject(result.data) ? result.data : {});
	return data ? { ok: true, data } : failure(0, 'invalid_response');
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
		quota: quotaOf(me.limits),
		lastProjectId: text(me.last_project_id) || null
	};
}

export function normalizeProjectSummary(value) {
	if (!isObject(value) || !text(value.id)) return null;
	return {
		id: value.id,
		name: text(value.name),
		version: number(value.version, 0),
		createdAt: text(value.created_at) || null,
		updatedAt: text(value.updated_at) || null,
		shots: number(value.shots, 0),
		duration: number(value.duration_s, 0)
	};
}

export function normalizeProject(value) {
	if (!isObject(value) || !text(value.id)) return null;
	return {
		id: value.id,
		name: text(value.name),
		version: number(value.version, 0),
		doc: isObject(value.doc) ? value.doc : null,
		createdAt: text(value.created_at) || null,
		updatedAt: text(value.updated_at) || null,
		unchanged: value.unchanged === true
	};
}

export function normalizeVersion(value) {
	if (!isObject(value) || number(value.version) === null) return null;
	return {
		id: text(value.id) || String(value.version),
		version: number(value.version),
		label: text(value.label) || null,
		sourceVersion: number(value.source_version),
		createdAt: text(value.created_at) || null,
		shots: number(value.shots, 0)
	};
}

export function normalizeOrigin(value) {
	if (!isObject(value)) return null;
	const fileId = typeof value.fileId === 'number' && Number.isFinite(value.fileId) ? value.fileId : text(value.fileId);
	if (value.kind === 'history' && text(value.generationId) && (fileId || fileId === 0)) return { kind: 'history', generationId: value.generationId, fileId };
	if (value.kind === 'library' && text(value.itemId)) return { kind: 'library', itemId: value.itemId };
	return null;
}

const MEDIA_TYPES = ['image', 'video', 'audio'];

export function normalizeMedia(value) {
	if (!isObject(value) || !MEDIA_TYPES.includes(value.media_type) || !text(value.url)) return null;
	return {
		kind: value.kind === 'library' ? 'library' : 'history',
		mediaType: value.media_type,
		url: value.url,
		filename: text(value.filename),
		origin: normalizeOrigin(value.origin)
	};
}

function list(values, normalize) {
	return Array.isArray(values) ? values.map(normalize).filter(Boolean) : null;
}

const projectPath = (id) => `/projects/${encodeURIComponent(id)}`;

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
		saveLastProject(id) {
			return call(api, 'put', '/me', { last_project_id: id ?? null });
		},
		async listProjects() {
			return mapped(await call(api, 'get', '/projects'), (data) => list(data.projects, normalizeProjectSummary));
		},
		async createProject(doc, name) {
			return mapped(await call(api, 'post', '/projects', name ? { doc, name } : { doc }), (data) => normalizeProject(data.project));
		},
		async getProject(id) {
			return mapped(await call(api, 'get', projectPath(id)), (data) => normalizeProject(data.project));
		},
		async saveProject(id, doc, version, label) {
			return mapped(await call(api, 'put', projectPath(id), label ? { doc, version, label } : { doc, version }), (data) => normalizeProject(data.project));
		},
		async deleteProject(id) {
			return mapped(await call(api, 'delete', projectPath(id)), (data) => (text(data.deleted) ? { deleted: data.deleted } : null));
		},
		async listVersions(id) {
			return mapped(await call(api, 'get', `${projectPath(id)}/versions`), (data) => list(data.versions, normalizeVersion));
		},
		async restoreVersion(id, version) {
			return mapped(await call(api, 'post', `${projectPath(id)}/versions/${encodeURIComponent(version)}/restore`, {}), (data) => normalizeProject(data.project));
		},
		async resolveMedia(origin) {
			return mapped(await call(api, 'post', '/media/resolve', { origin }), (data) => normalizeMedia(data.media));
		},
		coreFetch(path, init) {
			return coreFetch(api, path, init);
		}
	};
}

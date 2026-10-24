import { progressText } from './generation.js';
import { LABELS, legacyLabel } from './labels.js';
import { filenameFrom, lastSegment, normalizeJob, jobPath } from './exports.js';
import { normalizeSeamMedia, requestBody } from './seam.js';
import { normalizeFrameSource } from './chain.js';
import { normalizeKeyframeEstimate, normalizeKeyframePreset } from './keyframes.js';

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

export function requestError(err) {
	if (Number.isInteger(err?.status) && err.status > 0) return normalizeError(isObject(err.body) ? err.body : { detail: err.detail ?? err.message }, err.status);
	return thrown(err).error;
}

export function unwrap(payload) {
	if (!isObject(payload)) return failure(0, 'invalid_response');
	if (payload.success === true) return { ok: true, data: payload.data };
	if (payload.success === undefined && payload.detail === undefined && 'data' in payload) {
		return { ok: true, data: payload.data };
	}
	return { ok: false, error: normalizeError(payload) };
}

async function rawCall(api, method, path, body, signal) {
	try {
		const init = { method: method.toUpperCase(), signal };
		if (body !== undefined) {
			init.headers = { 'Content-Type': 'application/json' };
			init.body = JSON.stringify(body);
		}
		const response = await api.fetchRaw(path, init);
		let payload = null;
		try {
			payload = await response.json();
		} catch {
			payload = null;
		}
		if (!response.ok) return { ok: false, error: normalizeError(payload, response.status) };
		return unwrap(payload);
	} catch (err) {
		return thrown(err);
	}
}

async function settle(response) {
	let payload = null;
	try {
		payload = await response.json();
	} catch {
		payload = null;
	}
	if (!response.ok) return { ok: false, error: normalizeError(payload, response.status) };
	return unwrap(payload);
}

export async function upload(api, path, form, signal) {
	if (typeof api?.fetchRaw === 'function') {
		try {
			return await settle(await api.fetchRaw(path, { method: 'POST', body: form, signal }));
		} catch (err) {
			return thrown(err);
		}
	}
	if (typeof api?.uploadFile !== 'function') return failure(0, 'no_api');
	try {
		return unwrap(await api.uploadFile(path, form));
	} catch (err) {
		return { ok: false, error: requestError(err) };
	}
}

export async function fetchBytes(api, path, signal) {
	if (typeof api?.fetchRaw !== 'function') return failure(0, 'no_api');
	try {
		const response = await api.fetchRaw(path, { method: 'GET', signal });
		if (!response.ok) return settle(response);
		return { ok: true, data: await response.arrayBuffer() };
	} catch (err) {
		return thrown(err);
	}
}

async function call(api, method, path, body, signal) {
	if (signal && typeof api?.fetchRaw === 'function') return rawCall(api, method, path, body, signal);
	if (typeof api?.request === 'function') {
		try {
			return unwrap(await api.request(method.toUpperCase(), path, body));
		} catch (err) {
			return { ok: false, error: requestError(err) };
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

const ENGINE_KINDS = ['local', 'remote', 'cloud'];

function strings(values) {
	return Array.isArray(values) ? values.filter((value) => typeof value === 'string' && value) : [];
}

function normalizeModel(value) {
	if (!isObject(value) || !text(value.id)) return null;
	return {
		id: value.id,
		name: text(value.name) || value.id,
		providerModelId: text(value.provider_model_id) || null,
		tasks: strings(value.tasks),
		typicalSeconds: number(value.typical_seconds),
		maxSeconds: number(value.max_seconds)
	};
}

export function normalizeEngine(value) {
	if (!isObject(value) || !text(value.id) || !ENGINE_KINDS.includes(value.kind)) return null;
	return {
		id: value.id,
		name: text(value.name) || value.id,
		kind: value.kind,
		driver: text(value.driver) || null,
		device: text(value.execution_device) || null,
		vramTotal: number(value.vram_total_gb),
		vramFree: number(value.vram_free_gb),
		isDefault: value.is_default === true,
		models: value.kind === 'cloud' ? (list(value.models, normalizeModel) ?? []) : []
	};
}

function normalizeResolution(value) {
	if (typeof value === 'string' && value) return { value, label: value };
	if (!isObject(value) || !text(value.value)) return null;
	return { value: value.value, label: text(value.label) || value.value };
}

const FIELD_LIMITS = ['min', 'max', 'step', 'strength_min', 'strength_max', 'strength_step', 'strength_default', 'max_items', 'max_length'];

function normalizeChoice(value) {
	if (!isObject(value) || typeof value.value !== 'string') return null;
	return { value: value.value, label: text(value.label) || value.value };
}

function normalizeReaction(value) {
	return isObject(value) && isObject(value.then) && value.when !== undefined ? { when: value.when, then: value.then } : null;
}

export function normalizeField(value) {
	if (!isObject(value) || !text(value.name) || !text(value.type)) return null;
	const limits = isObject(value.limits) ? value.limits : {};
	return {
		name: value.name,
		type: value.type,
		label: text(value.label) || null,
		group: strings(value.group),
		audience: value.audience === 'advanced' ? 'advanced' : 'simple',
		gate: text(value.gate) || null,
		default: value.default === undefined ? null : value.default,
		required: value.required === true,
		limits: {
			...Object.fromEntries(FIELD_LIMITS.filter((key) => number(limits[key]) !== null).map((key) => [key, number(limits[key])])),
			...(text(limits.model_type) ? { model_type: limits.model_type } : {})
		},
		reactions: list(value.reactions, normalizeReaction) ?? [],
		options: list(value.options, normalizeChoice) ?? [],
		recommended: strings(value.recommended)
	};
}

function modeOptions(modes) {
	if (!isObject(modes)) return {};
	return Object.fromEntries(
		Object.entries(modes)
			.filter(([, mode]) => isObject(mode) && Array.isArray(mode.options))
			.map(([name, mode]) => [name, list(mode.options, normalizeField)])
	);
}

export function normalizeModelEntry(value) {
	if (!isObject(value) || !text(value.id)) return null;
	const file = text(value.filename).replaceAll('\\', '/').split('/').pop() || null;
	return { id: value.id, ref: `model:${value.id}`, name: text(value.custom_name) || text(value.name) || file || value.id, file };
}

export function normalizePreset(value) {
	if (!isObject(value) || !text(value.id)) return null;
	const modes = Array.isArray(value.modes) ? strings(value.modes) : isObject(value.modes) ? Object.keys(value.modes) : [];
	const limits = isObject(value.limits) ? value.limits : {};
	const directorModes = strings(value.director_modes);
	return {
		id: value.id,
		name: text(value.name) || value.id,
		cloud: value.engine === 'cloud',
		driver: text(value.driver) || null,
		backendId: text(value.backend_id) || null,
		profile: text(value.profile).trim() || null,
		video: Boolean(value.video_director) || directorModes.length > 0,
		upscaler: value.upscaler === true,
		modes,
		resolutions: list(value.resolutions, normalizeResolution) ?? [],
		fps: number(value.fps),
		fpsLocked: value.fps_locked === true,
		limits: { defaultDuration: number(limits.default_duration), maxDuration: number(limits.max_duration) },
		directorModes,
		audioMux: value.audio_mux === true,
		profiles: Array.isArray(value.profiles) ? strings(value.profiles) : null,
		presetModes: strings(value.video_director?.preset_modes),
		options: modeOptions(value.modes)
	};
}

export function normalizeMe(data) {
	const me = isObject(data) ? data : {};
	const user = isObject(me.user) ? me.user : {};
	const plugin = isObject(me.plugin) ? me.plugin : {};
	const settings = isObject(me.settings) ? me.settings : {};
	const features = isObject(me.features) ? me.features : {};
	return {
		locale: text(me.locale) || null,
		version: text(plugin.version) || null,
		username: text(user.username) || text(me.username),
		isAdmin: me.is_admin === true || user.is_admin === true,
		quota: quotaOf(me.limits),
		lastProjectId: text(me.last_project_id) || null,
		engines: list(me.engines, normalizeEngine) ?? [],
		presets: list(me.presets, normalizePreset) ?? [],
		keyframePresets: list(me.keyframe_presets, normalizeKeyframePreset) ?? [],
		features: { upscaler: features.upscaler === true },
		upscaleTargets: strings(me.upscale_targets),
		ffmpeg: typeof me.ffmpeg === 'boolean' ? me.ffmpeg : null,
		settings: { draftResolution: text(settings.draft_resolution) || null, maxParallelJobs: number(settings.max_parallel_jobs) }
	};
}

const TAKE_STATES = ['queued', 'running', 'done', 'failed', 'cancelled'];
const DIRECTOR_MODES = ['t2v', 'i2v', 'flf', 'refs'];

function idText(value) {
	if (typeof value === 'number' && Number.isFinite(value)) return String(value);
	return text(value) || null;
}

export function normalizeTake(value) {
	if (!isObject(value) || !text(value.id)) return null;
	return {
		id: value.id,
		projectId: text(value.project_id) || null,
		shotId: text(value.shot_id) || null,
		generationId: idText(value.generation_id),
		quality: value.quality === 'final' ? 'final' : 'draft',
		kind: ['upscale', 'keyframe'].includes(value.kind) ? value.kind : 'render',
		parentTakeId: text(value.parent_take_id) || null,
		presetId: text(value.preset_id) || null,
		mode: text(value.mode) || null,
		directorMode: DIRECTOR_MODES.includes(value.director_mode) ? value.director_mode : null,
		backendId: text(value.backend_id) || null,
		modelId: text(value.model_id) || null,
		seed: number(value.seed),
		resolution: text(value.resolution) || null,
		status: TAKE_STATES.includes(value.status) ? value.status : 'queued',
		progress: number(value.progress),
		step: progressText(value.step),
		variant: text(value.variant) || 'A',
		chosen: value.chosen === true || value.chosen === 1,
		flag: value.flag === 'keep' || value.flag === 'reject' ? value.flag : null,
		label: LABELS.includes(value.label) ? value.label : legacyLabel(value.chosen, value.flag),
		shotRevision: Number.isInteger(value.shot_revision) && value.shot_revision > 0 ? value.shot_revision : 0,
		priority: Number.isInteger(value.priority) ? value.priority : 0,
		profile: text(value.profile) || null,
		promptText: text(value.prompt_text),
		url: text(value.url) || null,
		thumbUrl: text(value.thumb_url) || null,
		fileId: idText(value.file_id),
		width: number(value.width),
		height: number(value.height),
		durationS: number(value.duration_s),
		fps: number(value.fps),
		errorCode: text(value.error_code) || null,
		errorMessage: text(value.error_message) || null,
		unitsReserved: number(value.units_reserved, 0),
		createdAt: text(value.created_at) || null,
		startedAt: text(value.started_at) || null,
		finishedAt: text(value.finished_at) || null
	};
}

function normalizeNote(value) {
	if (!isObject(value) || !text(value.code)) return null;
	return { code: value.code, message: text(value.message), data: isObject(value.data) ? value.data : null };
}

const ENGINE_FAMILIES = ['h3', 'ltx', 'wan', 'cloud', 'other'];

function normalizeComposed(value) {
	if (!isObject(value) || !text(value.shot_id)) return null;
	return {
		shotId: value.shot_id,
		presetId: text(value.preset_id) || null,
		profile: text(value.profile) || null,
		engine: ENGINE_FAMILIES.includes(value.engine) ? value.engine : 'other',
		prompt: text(value.prompt),
		warnings: list(value.warnings, normalizeNote) ?? []
	};
}

export function normalizePrompts(value) {
	if (!isObject(value)) return null;
	return { prompts: list(value.prompts, normalizeComposed) ?? [], blocks: list(value.blocks, normalizeNote) ?? [] };
}

function normalizeShotEstimate(value) {
	if (!isObject(value) || !text(value.shot_id)) return null;
	return {
		shotId: value.shot_id,
		directorMode: DIRECTOR_MODES.includes(value.director_mode) ? value.director_mode : null,
		seconds: number(value.seconds),
		resolution: text(value.resolution) || null,
		fps: number(value.fps)
	};
}

function usd(value) {
	if (typeof value === 'string') return value || null;
	return number(value) === null ? null : String(value);
}

export function normalizeEstimate(value) {
	if (!isObject(value)) return null;
	const vram = isObject(value.vram) ? value.vram : null;
	const time = isObject(value.time) ? value.time : {};
	const quota = isObject(value.quota) ? value.quota : null;
	const cost = isObject(value.cost) ? value.cost : null;
	return {
		shots: list(value.shots, normalizeShotEstimate) ?? [],
		vram: vram
			? {
					estimateGb: number(vram.estimate_gb),
					freeGb: number(vram.free_gb),
					totalGb: number(vram.total_gb),
					streams: vram.streams === true,
					unknown: vram.unknown === true,
					backendId: text(vram.backend_id) || null
				}
			: null,
		time: { seconds: number(time.seconds), samples: number(time.samples, 0) },
		quota: quota
			? {
					limit: number(quota.limit),
					used: number(quota.used),
					remaining: number(quota.remaining),
					exempt: quota.exempt === true,
					neededMinutes: number(quota.needed_minutes, 0),
					applies: quota.applies !== false,
					blocks: quota.blocks === true
				}
			: null,
		cost: cost ? { totalUsd: usd(cost.total_usd), known: cost.known === true, message: text(cost.message) || null } : null,
		blocks: list(value.blocks, normalizeNote) ?? [],
		warnings: list(value.warnings, normalizeNote) ?? []
	};
}

export function normalizeQueue(value) {
	if (!isObject(value)) return null;
	const slots = isObject(value.slots) ? value.slots : {};
	const elsewhere = isObject(value.elsewhere) ? value.elsewhere : {};
	const raw = Array.isArray(value.takes) ? value.takes : [];
	const positions = {};
	for (const take of raw) if (isObject(take) && text(take.id) && Number.isInteger(take.queue_position) && take.queue_position > 0) positions[take.id] = take.queue_position;
	return {
		takes: list(raw, normalizeTake) ?? [],
		slots: { inFlight: number(slots.in_flight, 0), max: number(slots.max) },
		elsewhere: { waiting: number(elsewhere.waiting, 0), inFlight: number(elsewhere.in_flight, 0) },
		positions
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

const SCENE_JOB_STATES = ['queued', 'running', 'done', 'failed', 'cancelled'];
const SPLAT_FORMATS = ['ply', 'spz', 'splat'];
const SCENE_FILE_FORMATS = [...SPLAT_FORMATS, 'glb', 'gltf'];

export function normalizeView(value) {
	if (!isObject(value)) return null;
	const fov = number(value.fov);
	const aspect = number(value.aspect);
	const depth = number(value.depth);
	return fov > 0 && fov < 180 && aspect > 0 && depth > 0 ? { fov, aspect, depth } : null;
}

export function normalizeSceneJob(value) {
	if (!isObject(value) || !idText(value.id)) return null;
	const count = number(value.count);
	return {
		id: idText(value.id),
		sceneId: text(value.sceneId) || text(value.scene_id) || null,
		status: SCENE_JOB_STATES.includes(value.status) ? value.status : 'queued',
		progress: Math.min(100, Math.max(0, number(value.progress, 0))),
		error: text(value.error) || (isObject(value.error) ? text(value.error.code) || text(value.error.message) : '') || null,
		fileId: idText(value.fileId ?? value.file_id),
		count: Number.isInteger(count) ? count : null,
		view: normalizeView(value.view)
	};
}

export function normalizeSceneFile(value) {
	if (!isObject(value) || !idText(value.id)) return null;
	return { id: idText(value.id), format: SCENE_FILE_FORMATS.includes(value.format) ? value.format : null, size: number(value.size), view: normalizeView(value.view) };
}

export function normalizeSavedMedia(value, type) {
	if (!isObject(value) || !text(value.url)) return null;
	if ((text(value.media_type) || type) !== type) return null;
	const itemId = idText(value.item_id) || text(value.origin?.itemId);
	if (!itemId) return null;
	return { itemId, url: value.url, filename: text(value.filename), width: Number.isInteger(value.width) ? value.width : null, height: Number.isInteger(value.height) ? value.height : null };
}

function list(values, normalize) {
	return Array.isArray(values) ? values.map(normalize).filter(Boolean) : null;
}

const projectPath = (id) => `/projects/${encodeURIComponent(id)}`;
const renderPath = (projectId, renderId) => `${projectPath(projectId)}/renders/${encodeURIComponent(renderId)}`;
const takePath = (projectId, takeId) => `${projectPath(projectId)}/takes/${encodeURIComponent(takeId)}`;
const pickTake = (data) => normalizeTake(data.take);
const keyframePath = (projectId, shotId) => `${projectPath(projectId)}/shots/${encodeURIComponent(shotId)}/keyframes`;

export async function downloadFrom(api, path, filename, save) {
	if (typeof api?.download === 'function') {
		try {
			await api.download(path, filename);
			return { ok: true, data: { filename: filename || lastSegment(path) } };
		} catch (err) {
			return { ok: false, error: requestError(err) };
		}
	}
	if (typeof api?.fetchRaw !== 'function') return failure(0, 'no_api');
	let response;
	try {
		response = await api.fetchRaw(path, { method: 'GET' });
	} catch (err) {
		return thrown(err);
	}
	if (!response.ok) {
		let body = null;
		try {
			body = await response.json();
		} catch {
			body = null;
		}
		return { ok: false, error: normalizeError(body, response.status) };
	}
	const name = filename || filenameFrom(response.headers?.get?.('Content-Disposition')) || lastSegment(path);
	try {
		save(name, await response.blob());
	} catch (err) {
		return thrown(err);
	}
	return { ok: true, data: { filename: name } };
}

export async function coreUpload(api, path, form, { onProgress = () => {}, signal = null } = {}) {
	if (typeof api?.fetchRawFromApp !== 'function') return failure(0, 'no_api');
	if (signal?.aborted) return failure(0, 'aborted');
	const onUploadProgress = (loaded, total) => {
		if (total > 0) onProgress(Math.min(100, (loaded / total) * 100));
	};
	try {
		return await settle(await api.fetchRawFromApp(path, { method: 'POST', body: form, signal: signal ?? undefined, onUploadProgress }));
	} catch (err) {
		return thrown(err);
	}
}

export const MODEL_LIST_LIMIT = 200;

export async function coreModels(api, presetId, modelType, signal = null) {
	if (typeof api?.fetchRawFromApp !== 'function') return failure(0, 'no_api');
	const query = new URLSearchParams({ limit: String(MODEL_LIST_LIMIT) });
	if (modelType) query.set('model_type', modelType);
	try {
		const result = await settle(await api.fetchRawFromApp(`/api/presets/${encodeURIComponent(presetId)}/models?${query}`, { method: 'GET', signal: signal ?? undefined }));
		return mapped(result, (data) => list(data.models, normalizeModelEntry));
	} catch (err) {
		return thrown(err);
	}
}

export function createClient(api, save) {
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
		async listTakes(projectId) {
			return mapped(await call(api, 'get', `${projectPath(projectId)}/takes`), (data) => list(data.takes, normalizeTake));
		},
		async labelTake(projectId, takeId, label) {
			return mapped(await call(api, 'post', `${takePath(projectId, takeId)}/label`, { label }), pickTake);
		},
		async deleteTake(projectId, takeId) {
			return mapped(await call(api, 'delete', takePath(projectId, takeId)), (data) => (text(data.deleted) ? { deleted: data.deleted } : null));
		},
		async finalTake(projectId, takeId, method, target) {
			return mapped(await call(api, 'post', `${takePath(projectId, takeId)}/final`, { method, target }), pickTake);
		},
		async estimate(projectId, body, signal) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/estimate`, body, signal), normalizeEstimate);
		},
		async prompts(projectId, body, signal) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/prompts`, body, signal), normalizePrompts);
		},
		async generate(projectId, body) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/generate`, body), (data) => list(data.takes, normalizeTake));
		},
		async prioritizeTake(projectId, takeId) {
			return mapped(await call(api, 'post', `${takePath(projectId, takeId)}/prioritize`, {}), pickTake);
		},
		async cancelTake(takeId) {
			return mapped(await call(api, 'post', `/takes/${encodeURIComponent(takeId)}/cancel`, {}), pickTake);
		},
		async retryTake(takeId) {
			return mapped(await call(api, 'post', `/takes/${encodeURIComponent(takeId)}/retry`, {}), pickTake);
		},
		async queue(projectId) {
			return mapped(await call(api, 'get', `${projectPath(projectId)}/queue`), normalizeQueue);
		},
		async keyframes(projectId, shotId) {
			return mapped(await call(api, 'get', keyframePath(projectId, shotId)), (data) => list(data.takes, normalizeTake));
		},
		async estimateKeyframes(projectId, shotId, body, signal) {
			return mapped(await call(api, 'post', `${keyframePath(projectId, shotId)}/estimate`, body, signal), normalizeKeyframeEstimate);
		},
		async generateKeyframes(projectId, shotId, body) {
			return mapped(await call(api, 'post', keyframePath(projectId, shotId), body), (data) => list(data.takes, normalizeTake));
		},
		async exportVideo(projectId, body) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/exports/video`, body), (data) => normalizeJob(data.job));
		},
		async exportJob(jobId) {
			return mapped(await call(api, 'get', jobPath(jobId)), (data) => normalizeJob(data.job));
		},
		async cancelExport(jobId) {
			const result = await call(api, 'delete', jobPath(jobId));
			return result.ok ? { ok: true, data: normalizeJob(result.data?.job) } : result;
		},
		async listExports(projectId) {
			return mapped(await call(api, 'get', `${projectPath(projectId)}/exports`), (data) => list(data.jobs, normalizeJob));
		},
		async seamFrame(projectId, shotId, source) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/shots/${encodeURIComponent(shotId)}/seam-frame`, requestBody(source)), (data) => normalizeSeamMedia(data.media));
		},
		async endFrame(projectId, shotId) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/shots/${encodeURIComponent(shotId)}/end-frame`, {}), (data) => {
				const media = normalizeSeamMedia(data.media);
				const source = normalizeFrameSource(data.source);
				return media && source ? { media, source } : null;
			});
		},
		async sceneFromImage(projectId, body) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/scenes/from-image`, body), (data) => normalizeSceneJob(data.job));
		},
		async sceneJobs(projectId) {
			return mapped(await call(api, 'get', `${projectPath(projectId)}/scenes/jobs`), (data) => list(data.jobs, normalizeSceneJob));
		},
		async cancelSceneJob(projectId, jobId) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/scenes/jobs/${encodeURIComponent(jobId)}/cancel`, {}), (data) => normalizeSceneJob(data.job));
		},
		async uploadSceneFile(projectId, file, kind, signal) {
			const form = new FormData();
			form.append('file', file, file.name);
			form.append('kind', kind);
			return mapped(await upload(api, `${projectPath(projectId)}/scene-files`, form, signal), (data) => normalizeSceneFile(data.file));
		},
		sceneFile(projectId, fileId, signal) {
			return fetchBytes(api, `${projectPath(projectId)}/scene-files/${encodeURIComponent(fileId)}`, signal);
		},
		async capture(projectId, png, name) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/captures`, { png, name }), (data) => normalizeSavedMedia(data.media, 'image'));
		},
		async createRender(projectId, body) {
			return mapped(await call(api, 'post', `${projectPath(projectId)}/renders`, body), (data) => (idText(data.render?.id) ? { id: idText(data.render.id) } : null));
		},
		async renderFrames(projectId, renderId, start, images) {
			return mapped(await call(api, 'post', `${renderPath(projectId, renderId)}/frames`, { start, images }), (data) => ({ received: number(data.received, images.length) }));
		},
		async finishRender(projectId, renderId) {
			return mapped(await call(api, 'post', `${renderPath(projectId, renderId)}/finish`, {}), (data) => normalizeSavedMedia(data.media, 'video'));
		},
		deleteRender(projectId, renderId) {
			return call(api, 'delete', renderPath(projectId, renderId));
		},
		download(path, filename) {
			return downloadFrom(api, path, filename, save);
		},
		uploadMedia(form, options) {
			return coreUpload(api, '/api/media/upload', form, options);
		},
		async uploadedMedia(filename) {
			return mapped(await call(api, 'post', '/media/uploaded', { filename }), (data) => normalizeMedia(data.media));
		},
		presetModels(presetId, modelType, signal) {
			return coreModels(api, presetId, modelType, signal);
		}
	};
}

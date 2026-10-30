import { pickSize, ratioOf } from './formats.js';

export const PROFILES = ['FL2VA', 'Ref2VA', 'Hybrid AV'];
export const MINIMAX_H3_IDS = ['01KX47H3MINIMAX000000000VA', '01KX47H3FASTH30000000000VA', '01KX47H3VDNMINIMAX000000VA', '01M54HN72B0KY7H63BKQ16T253', '01M54HN72PABVRE54YNQA2Q7ZT'];
export const UPSCALE_TARGETS = ['hd720', 'fhd1080', 'qhd1440', 'uhd2160'];
export const FAILURE_CODES = [
	'cuda_oom',
	'gpu_restart_required',
	'host_ram_oom',
	'missing_model_file',
	'disk_full',
	'corrupt_weights',
	'auth_required',
	'backend_unreachable',
	'banned_prompt',
	'content_blocked',
	'content_check_unavailable',
	'cloud_auth',
	'cloud_credits',
	'cloud_refused',
	'cloud_rate_limited',
	'cloud_invalid_request',
	'cloud_unavailable',
	'cloud_timeout',
	'cloud_failed',
	'cloud_expired',
	'unclassified',
	'generation_failed',
	'preset_not_available',
	'duplicate_submission',
	'no_backend',
	'submit_failed',
	'generation_not_found',
	'no_output',
	'user_not_found',
	'previous_take_failed',
	'previous_take_cancelled',
	'previous_take_gone',
	'chain_frame_failed'
];
const CLOUD_DRIVERS = { '01M3SV8HJTGT3JPPH2BA5MP6PR': 'cloud.openrouter', '01M48T0Q8Q0V2WNW3WTX3FY1MW': 'cloud.google' };
const LEGACY_BACKENDS = { local: 'local', studio: 'remote', cloud: 'cloud' };
const NATIVE_KINDS = ['local', 'remote'];

export function failureText(take, t) {
	if (FAILURE_CODES.includes(take?.errorCode)) return t(`generation.failed.${take.errorCode}`, { id: take.generationId ?? '—' });
	return take?.errorMessage || t('generation.card.error', { code: take?.errorCode ?? '—' });
}

export const isInFlight = (take) => take?.status === 'queued' || take?.status === 'running';
export const isH3 = (presetOrId) => MINIMAX_H3_IDS.includes(typeof presetOrId === 'string' ? presetOrId : presetOrId?.id);

export function presetLabel(preset) {
	if (!preset) return '';
	return isH3(preset) ? preset.name.replace(/^MiniMax-H3[-\s]?/, 'MiniMax H3 ').trim() : preset.name;
}

export function withProfile(label, profile) {
	const missing = (profile || '').split('·').map((part) => part.trim()).filter((part) => part && !label.toLowerCase().includes(part.toLowerCase()));
	return missing.length ? `${label} · ${missing.join(' · ')}` : label;
}

export function presetProfiles(preset) {
	if (!preset) return [];
	if (preset.profiles) return preset.profiles;
	return isH3(preset) ? [...PROFILES] : ['FL2VA'];
}

export const optionKey = (preset, model) => `${preset ?? ''}|${model ?? ''}`;

export function cloudPresetFor(engine, presets) {
	const cloud = presets.filter((p) => p.cloud && p.video);
	const driverOf = (p) => p.driver ?? CLOUD_DRIVERS[p.id] ?? null;
	return (
		cloud.find((p) => p.backendId && p.backendId === engine.id) ??
		cloud.find((p) => driverOf(p) && driverOf(p) === engine.driver) ??
		(cloud.length === 1 && !driverOf(cloud[0]) && !cloud[0].backendId ? cloud[0] : null)
	);
}

export const nativeEngine = (me) => (me?.engines ?? []).find((e) => NATIVE_KINDS.includes(e.kind)) ?? null;

export const hasNativeEngine = (me) => nativeEngine(me) !== null;

export const rtxUnchecked = (me) => nativeEngine(me)?.kind === 'remote';

export function engineOptions(me) {
	const engines = me?.engines ?? [];
	const presets = (me?.presets ?? []).filter((p) => p.video);
	const native = nativeEngine(me);
	const options = [];
	if (native) {
		for (const preset of presets.filter((p) => !p.cloud)) {
			options.push({ key: optionKey(preset.id, null), preset: preset.id, model: null, backend: native.id, kind: native.kind, label: withProfile(presetLabel(preset), preset.profile), group: native.name, info: preset, modelInfo: null });
		}
	}
	for (const engine of engines.filter((e) => e.kind === 'cloud')) {
		const preset = cloudPresetFor(engine, presets);
		if (!preset) continue;
		for (const model of engine.models) {
			options.push({ key: optionKey(preset.id, model.id), preset: preset.id, model: model.id, backend: engine.id, kind: 'cloud', label: model.name, group: engine.name, info: preset, modelInfo: model });
		}
	}
	return options;
}

export function optionFor(options, engine) {
	if (!engine?.preset) return null;
	return options.find((o) => o.key === optionKey(engine.preset, engine.model ?? null)) ?? null;
}

function migratedBackend(backend, engines) {
	if (engines.some((e) => e.id === backend)) return backend;
	const kind = LEGACY_BACKENDS[backend];
	const match = kind ? engines.find((e) => e.kind === kind) : null;
	return (match ?? engines[0])?.id ?? backend;
}

export function migrateEngine(engine, me) {
	const engines = me?.engines ?? [];
	const options = engineOptions(me);
	const backend = migratedBackend(engine?.backend ?? '', engines);
	const preset = typeof engine?.preset === 'string' && engine.preset ? engine.preset : null;
	const model = preset && typeof engine?.model === 'string' && engine.model ? engine.model : null;
	if (preset) {
		const current = optionFor(options, { preset, model });
		return { backend: current ? current.backend : backend, preset, model };
	}
	const fallback = options.find((o) => o.backend === backend) ?? options[0];
	return fallback ? { backend: fallback.backend, preset: fallback.preset, model: fallback.model } : { backend, preset: null, model: null };
}

export function aggregate(takes) {
	const flying = (takes ?? []).filter(isInFlight);
	if (!flying.length) return { state: 'idle', progress: 0, step: '', count: 0, running: 0 };
	const running = flying.filter((t) => t.status === 'running');
	const progress = flying.reduce((sum, t) => sum + (t.status === 'running' ? Math.min(100, Math.max(0, t.progress ?? 0)) : 0), 0) / flying.length;
	return { state: 'running', progress, step: running.find((t) => t.step)?.step ?? '', count: flying.length, running: running.length };
}

export const activityStep = (activity) => (activity?.state === 'running' ? activity.step || '' : '');

export function parseResolution(value) {
	const match = /^\s*(\d+)\s*[x×]\s*(\d+)\s*$/.exec(value ?? '');
	return match ? { width: Number(match[1]), height: Number(match[2]) } : null;
}

export function aspectOf(aspect, resolution) {
	const ratio = ratioOf(aspect);
	if (ratio !== null) return ratio;
	const size = parseResolution(resolution);
	return size ? size.width / size.height : 16 / 9;
}

const optionValues = (preset) => (preset?.resolutions ?? []).map((r) => r.value);

const offered = (preset) => optionValues(preset).some((value) => parseResolution(value));

export function draftResolution(preset, setting, aspect = 16 / 9, chosen = null) {
	if (!offered(preset)) return null;
	return pickSize(optionValues(preset), aspect, 'draft', setting, chosen, preset?.id ?? null).size;
}

export function finalResolution(preset, aspect = 16 / 9, chosen = null) {
	if (!offered(preset)) return null;
	return pickSize(optionValues(preset), aspect, 'final', null, chosen, preset?.id ?? null).size;
}

const MARKERS = ['PIPE', 'PROGRESS', 'MODEL', 'GPU', 'RESOLUTION', 'NUMBER', 'EFFECT', 'TIME'];

function readable(text) {
	if (typeof text !== 'string') return '';
	let out = '';
	let afterMarker = false;
	for (const part of text.split(/(<<[^>]*>>)/g)) {
		if (part.startsWith('<<') && part.endsWith('>>')) {
			const [type, value] = part.slice(2, -2).split(':');
			const label = MARKERS.includes(type?.toUpperCase()) && value ? value.trim() : '';
			if (!label) continue;
			out = afterMarker ? `${out.trimEnd()} · ${label}` : out + label;
			afterMarker = true;
		} else {
			if (part.trim()) afterMarker = false;
			out += part;
		}
	}
	return out.replace(/\s+/g, ' ').trim();
}

export function progressText(message, currentStep) {
	const raw = typeof message === 'string' ? message : '';
	const fallback = readable(currentStep);
	const onlyMarkers = /^\s*(<<[^>]*>>\s*)+$/.test(raw);
	if (!raw.trim() || (onlyMarkers && fallback)) return fallback || readable(raw) || null;
	return readable(raw) || fallback || null;
}

export const upscalesItself = (presetId) => presetId === MINIMAX_H3_IDS[0];

export function canUpscale(take, me) {
	if (!take) return false;
	if (upscalesItself(take.presetId)) return (me?.presets ?? []).some((p) => p.id === take.presetId);
	return me?.features?.upscaler === true;
}

export function takeAsset(take, name) {
	const origin = take.generationId && take.fileId ? { kind: 'history', generationId: take.generationId, fileId: take.fileId } : null;
	const width = Number.isInteger(take.width) ? take.width : null;
	const height = Number.isInteger(take.height) ? take.height : null;
	return {
		id: `gen-${take.id}`,
		kind: 'video',
		name,
		src: take.url,
		origin,
		srcDur: take.durationS ?? null,
		width,
		height,
		fps: take.fps ?? null,
		res: width && height ? `${width}×${height}` : null,
		generated: true,
		quality: take.quality,
		resultId: take.id,
		role: null
	};
}


export function sortTakes(takes) {
	return [...takes].sort((a, b) => {
		if (a.quality !== b.quality) return a.quality === 'draft' ? -1 : 1;
		const at = a.createdAt ?? '';
		const bt = b.createdAt ?? '';
		if (at !== bt) return at < bt ? -1 : 1;
		return String(a.variant).localeCompare(String(b.variant));
	});
}

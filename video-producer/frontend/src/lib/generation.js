export const PROFILES = ['FL2VA', 'Ref2VA', 'Hybrid AV'];
export const MINIMAX_H3_IDS = ['01KX47H3MINIMAX000000000VA', '01KX47H3FASTH30000000000VA', '01KX47H3VDNMINIMAX000000VA', '01M54HN72B0KY7H63BKQ16T253', '01M54HN72PABVRE54YNQA2Q7ZT'];
export const UPSCALE_TARGETS = ['hd720', 'fhd1080', 'qhd1440', 'uhd2160'];
const CLOUD_DRIVERS = { '01M3SV8HJTGT3JPPH2BA5MP6PR': 'cloud.openrouter', '01M48T0Q8Q0V2WNW3WTX3FY1MW': 'cloud.google' };
const LEGACY_BACKENDS = { local: 'local', studio: 'remote', cloud: 'cloud' };
const NATIVE_KINDS = ['local', 'remote'];

export const isInFlight = (take) => take?.status === 'queued' || take?.status === 'running';
export const isH3 = (presetOrId) => MINIMAX_H3_IDS.includes(typeof presetOrId === 'string' ? presetOrId : presetOrId?.id);

export function presetLabel(preset) {
	if (!preset) return '';
	return isH3(preset) ? preset.name.replace(/^MiniMax-H3[-\s]?/, 'MiniMax H3 ').trim() : preset.name;
}

export function withProfile(label, profile) {
	if (!profile || label.toLowerCase().includes(profile.toLowerCase())) return label;
	return `${label} · ${profile}`;
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

export function engineOptions(me) {
	const engines = me?.engines ?? [];
	const presets = (me?.presets ?? []).filter((p) => p.video);
	const native = engines.find((e) => NATIVE_KINDS.includes(e.kind));
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

export function parseResolution(value) {
	const match = /^\s*(\d+)\s*[x×]\s*(\d+)\s*$/.exec(value ?? '');
	return match ? { width: Number(match[1]), height: Number(match[2]) } : null;
}

const area = (value) => {
	const size = parseResolution(value);
	return size ? size.width * size.height : null;
};

const ASPECT_TOLERANCE = 0.03;

export function aspectOf(aspect, resolution) {
	const text = String(aspect ?? '');
	for (const separator of [':', '/', 'x']) {
		const parts = text.split(separator);
		if (parts.length !== 2) continue;
		const width = Number(parts[0]);
		const height = Number(parts[1]);
		if (!Number.isFinite(width) || !Number.isFinite(height) || parts[0].trim() === '' || parts[1].trim() === '') break;
		if (width > 0 && height > 0) return width / height;
	}
	const size = parseResolution(resolution);
	return size ? size.width / size.height : 16 / 9;
}

function matching(preset, aspect) {
	const sizes = (preset?.resolutions ?? []).map((r) => ({ value: r.value, size: parseResolution(r.value) })).filter((x) => x.size);
	if (!sizes.length) return [];
	const distance = (x) => Math.abs(Math.log(x.size.width / x.size.height) - Math.log(aspect));
	const closest = Math.min(...sizes.map(distance));
	return sizes.filter((x) => distance(x) <= closest + ASPECT_TOLERANCE);
}

export function draftResolution(preset, setting, aspect = 16 / 9) {
	const size = parseResolution(setting);
	const candidates = matching(preset, aspect);
	if (!size || !candidates.length) return null;
	const [width, height] = size.width >= size.height === aspect >= 1 ? [size.width, size.height] : [size.height, size.width];
	const wanted = `${width}x${height}`;
	if (candidates.some((x) => x.value === wanted)) return wanted;
	const target = width * height;
	const areaOf = (x) => x.size.width * x.size.height;
	return candidates.reduce((a, b) => {
		const da = Math.abs(areaOf(a) - target);
		const db = Math.abs(areaOf(b) - target);
		return db < da || (db === da && areaOf(b) < areaOf(a)) ? b : a;
	}).value;
}

export function finalResolution(preset, aspect = 16 / 9) {
	const candidates = matching(preset, aspect);
	return candidates.length ? candidates.reduce((a, b) => (b.size.width * b.size.height > a.size.width * a.size.height ? b : a)).value : null;
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

export function upscaleTargetFor(resolution, targets = UPSCALE_TARGETS) {
	const wanted = { '720p': 'hd720', '1080p': 'fhd1080', '1440p': 'qhd1440', '4K': 'uhd2160' }[resolution] ?? 'fhd1080';
	return targets.includes(wanted) ? wanted : (targets[targets.length - 1] ?? null);
}

export const upscalesItself = (presetId) => presetId === MINIMAX_H3_IDS[0];

export function canUpscale(take, me) {
	if (!take || take.legacy) return false;
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
		role: null,
		synth: null,
		transcript: null,
		character: null,
		lipSync: null
	};
}

export function legacyTake(result) {
	return {
		id: result.id,
		shotId: result.clipId,
		legacy: true,
		quality: result.quality === 'final' ? 'final' : 'draft',
		kind: 'render',
		variant: result.variant,
		status: 'done',
		seed: result.seed ?? null,
		chosen: result.status === 'chosen',
		flag: result.status === 'redo' ? 'reject' : null,
		profile: result.profile ?? null,
		promptText: result.local ?? '',
		parentTakeId: result.parent ?? null,
		directorMode: null,
		resolution: null,
		backendId: null,
		generationId: null,
		url: null,
		thumbUrl: null,
		created: result.created ?? null,
		range: result.range,
		look: result.look ?? null
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

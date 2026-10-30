import { optionKey } from './generation.js';
import { isShared, shotReferences } from './shots.js';
import { isObject } from './values.js';

export const KEYFRAME = 'keyframe';
export const ROLES = ['first', 'last'];
export const MAKE_ROLES = ['first', 'last', 'both'];
export const REASONS = ['missing_models', 'no_image_mode', 'no_backend', 'no_key', 'no_edit_model'];
export const MODES = ['edit', 'img2img'];
export const MIN_CANDIDATES = 2;
export const MAX_CANDIDATES = 4;
export const DEFAULT_CANDIDATES = 2;
export const PICTURE_ROLES = ['frame', 'setting', 'character', 'object', 'style'];
export const NOTE_CODES = ['preset_missing', 'preset_unusable', 'no_model', 'no_references', 'missing_models', 'quota_exceeded', 'shot_not_found', 'reference_unavailable', 'references_trimmed', 'aspect_mismatch', 'time_unknown', 'vram_unknown', 'vram_stream'];
export const PRESET_STATES = ['not_loaded', 'not_installed', 'not_assigned', 'not_edit', 'unknown'];

const SPACES = ['identite', 'decors3d'];
const TYPE_ROLES = { Personnage: 'character', Décor: 'setting', Objet: 'object', Style: 'style' };

const text = (value) => (typeof value === 'string' ? value : '');
const strings = (values) => (Array.isArray(values) ? values.filter((value) => typeof value === 'string' && value) : []);
const count = (value) => (Number.isInteger(value) && value > 0 ? value : null);
const number = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null);

export const clampCount = (value) => Math.min(MAX_CANDIDATES, Math.max(MIN_CANDIDATES, Number.isInteger(value) ? value : DEFAULT_CANDIDATES));
export const isKeyframe = (take) => take?.kind === KEYFRAME;
export const inFlight = (take) => take?.status === 'queued' || take?.status === 'running';

function normalizeModel(value) {
	if (!isObject(value) || !text(value.id)) return null;
	return { id: value.id, name: text(value.name) || value.id, maxImages: count(value.max_images) };
}

export function normalizeKeyframePreset(value) {
	if (!isObject(value) || !text(value.id)) return null;
	const reason = value.usable === false ? (REASONS.includes(value.reason) ? value.reason : 'no_image_mode') : null;
	return {
		id: value.id,
		name: text(value.name) || value.id,
		cloud: value.engine === 'cloud',
		driver: text(value.driver) || null,
		backendId: text(value.backend_id) || null,
		recommendedVram: number(value.requires?.recommended_vram_gb),
		mode: MODES.includes(value.mode) ? value.mode : null,
		maxImages: count(value.max_images),
		usable: reason === null,
		reason,
		missing: strings(value.missing),
		models: Array.isArray(value.models) ? value.models.map(normalizeModel).filter(Boolean) : []
	};
}

export function keyframeOptions(presets) {
	const options = [];
	for (const preset of presets ?? []) {
		const base = { preset: preset.id, cloud: preset.cloud, mode: preset.mode, disabled: false, reason: null, missing: [], info: preset };
		if (!preset.usable) options.push({ ...base, key: optionKey(preset.id, null), model: null, label: preset.name, group: null, maxImages: null, disabled: true, reason: preset.reason, missing: preset.missing });
		else if (preset.cloud) {
			for (const model of preset.models) options.push({ ...base, key: optionKey(preset.id, model.id), model: model.id, label: model.name, group: preset.name, maxImages: model.maxImages ?? preset.maxImages });
		} else options.push({ ...base, key: optionKey(preset.id, null), model: null, label: preset.name, group: null, maxImages: preset.maxImages });
	}
	return options;
}

export function storedChoice(engine) {
	const own = isObject(engine?.keyframes) ? engine.keyframes : {};
	const preset = text(own.preset) || null;
	return { preset, model: preset ? text(own.model) || null : null };
}

const matching = (options, choice) => options.find((o) => o.key === optionKey(choice.preset, choice.model)) ?? options.find((o) => o.disabled && o.preset === choice.preset) ?? null;

export function chosenOption(options, choice) {
	if (!choice?.preset) return options.find((o) => !o.disabled) ?? null;
	return matching(options, choice);
}

export const presetAbsent = (options, choice) => Boolean(choice?.preset) && !matching(options, choice);

export function choiceOf(option) {
	return option.model ? { preset: option.preset, model: option.model } : { preset: option.preset };
}

const imageAsset = (doc, id) => {
	const found = id ? (doc.assets ?? []).find((a) => a.id === id) : null;
	return found?.kind === 'image' ? found : null;
};

export const isPictureReference = (reference) => SPACES.includes(reference?.space);

export const pictureRole = (reference) => (reference.space === 'decors3d' ? 'setting' : (TYPE_ROLES[reference.type] ?? 'character'));

export function draftPictures(doc, clip, draft, role = 'first', framing = false) {
	if (!doc || !clip || !draft) return [];
	const found = [];
	const add = (asset, pictureRole, name, origin) => {
		if (!asset || found.some((p) => p.assetId === asset.id)) return;
		found.push({ assetId: asset.id, role: pictureRole, name: name || '', origin });
	};
	const first = imageAsset(doc, draft.first);
	if (first && (role === 'last' || role === 'both' || framing)) add(first, 'frame', '', 'frame');
	const { inherited, cast } = shotReferences(doc, clip, draft.exclude ?? [], draft.cast);
	const fromCast = cast.filter((x) => !x.excluded).map((x) => x.reference);
	const shared = inherited.filter(isShared).map((x) => x.reference);
	for (const reference of [...(draft.own ?? []), ...fromCast, ...shared]) {
		if (SPACES.includes(reference.space)) add(imageAsset(doc, reference.assetId), pictureRole(reference), reference.name, 'reference');
	}
	const rank = (p) => PICTURE_ROLES.indexOf(p.role);
	return found.map((p, i) => [p, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(([p]) => p);
}

export function requestBody({ option, role, count: wanted, prompt, pictures }) {
	return {
		preset_id: option.preset,
		model_id: option.model,
		role: MAKE_ROLES.includes(role) ? role : 'first',
		count: clampCount(wanted),
		prompt: text(prompt),
		references: (pictures ?? []).map((p) => ({ asset_id: p.assetId, role: p.role, name: p.name }))
	};
}

export const requestKey = (body) => JSON.stringify(body);

function normalizeNote(value) {
	if (!isObject(value) || !text(value.code)) return null;
	return { code: value.code, message: text(value.message), data: isObject(value.data) ? value.data : null };
}

function normalizeReference(value) {
	if (!isObject(value)) return null;
	return { rank: count(value.rank), assetId: text(value.asset_id) || null, role: PICTURE_ROLES.includes(value.role) ? value.role : 'setting', name: text(value.name), origin: text(value.origin) || null };
}

const notes = (values) => (Array.isArray(values) ? values.map(normalizeNote).filter(Boolean) : []);

function normalizePart(value) {
	if (!isObject(value) || !ROLES.includes(value.role)) return null;
	return { role: value.role, resolution: text(value.resolution) || null, prompt: text(value.prompt), references: Array.isArray(value.references) ? value.references.map(normalizeReference).filter(Boolean) : [] };
}

export function normalizeKeyframeEstimate(value) {
	if (!isObject(value)) return null;
	const vram = isObject(value.vram) ? value.vram : {};
	const time = isObject(value.time) ? value.time : {};
	const quota = isObject(value.quota) ? value.quota : {};
	const cost = isObject(value.cost) ? value.cost : null;
	return {
		role: MAKE_ROLES.includes(value.role) ? value.role : 'first',
		count: clampCount(value.count),
		resolution: text(value.resolution) || null,
		prompt: text(value.prompt),
		references: Array.isArray(value.references) ? value.references.map(normalizeReference).filter(Boolean) : [],
		parts: Array.isArray(value.parts) ? value.parts.map(normalizePart).filter(Boolean) : [],
		vram: { estimateGb: number(vram.estimate_gb), freeGb: number(vram.free_gb), streams: vram.streams === true, unknown: vram.unknown !== false },
		time: { seconds: number(time.seconds), perCandidate: number(time.per_candidate), samples: count(time.samples) ?? 0 },
		quota: { applies: quota.applies === true, neededMinutes: number(quota.needed_minutes) ?? 0, remaining: number(quota.remaining), limit: number(quota.limit), exempt: quota.exempt === true },
		cost: cost ? { totalUsd: typeof cost.total_usd === 'string' ? cost.total_usd : number(cost.total_usd) === null ? null : String(cost.total_usd), known: cost.known === true } : null,
		blocks: notes(value.blocks),
		warnings: notes(value.warnings)
	};
}

export const blocked = (estimate) => Boolean(estimate?.blocks?.length);

export function ordered(takes) {
	const letters = (take) => String(take.variant ?? '');
	return [...(takes ?? [])].filter(isKeyframe).sort((a, b) => letters(a).length - letters(b).length || letters(a).localeCompare(letters(b)));
}

export const assetIdOf = (take) => `gen-${take.id}`;

export function acceptedRoles(take, draft) {
	const id = assetIdOf(take);
	return ROLES.filter((role) => draft?.[role] === id);
}

export function keyframeAsset(take, name) {
	const width = Number.isInteger(take.width) ? take.width : null;
	const height = Number.isInteger(take.height) ? take.height : null;
	return {
		id: assetIdOf(take),
		kind: 'image',
		name,
		src: take.url,
		origin: take.generationId && take.fileId ? { kind: 'history', generationId: take.generationId, fileId: take.fileId } : null,
		srcDur: null,
		width,
		height,
		fps: null,
		res: width && height ? `${width}×${height}` : null,
		generated: true,
		quality: 'draft',
		resultId: take.id,
		role: null
	};
}

export const usable = (take) => isKeyframe(take) && take.status === 'done' && Boolean(take.url) && Boolean(take.generationId && take.fileId);

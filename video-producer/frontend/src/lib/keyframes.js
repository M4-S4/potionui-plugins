import { optionKey } from './generation.js';
import { roleKind } from './seam.js';
import { isGlobal } from './shots.js';

export const KEYFRAME = 'keyframe';
export const ROLES = ['first', 'last'];
export const MIN_CANDIDATES = 2;
export const MAX_CANDIDATES = 4;
export const DEFAULT_CANDIDATES = 2;
export const PICTURE_ROLES = ['frame', 'setting', 'character', 'object', 'style'];
export const NOTE_CODES = ['preset_missing', 'no_model', 'no_references', 'missing_models', 'quota_exceeded', 'shot_not_found', 'reference_unavailable', 'references_trimmed', 'aspect_mismatch', 'time_unknown', 'vram_unknown', 'vram_stream'];
export const PRESET_STATES = ['not_loaded', 'not_installed', 'not_assigned', 'not_edit', 'unknown'];

const SPACES = ['identite', 'decors3d'];
const TYPE_ROLES = { Personnage: 'character', Décor: 'setting', Objet: 'object', Style: 'style' };
const STATES = ['queued', 'running', 'done', 'failed', 'cancelled'];

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' ? value : '');
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
	return {
		id: value.id,
		name: text(value.name) || value.id,
		cloud: value.engine === 'cloud',
		driver: text(value.driver) || null,
		backendId: text(value.backend_id) || null,
		recommendedVram: number(value.requires?.recommended_vram_gb),
		maxImages: count(value.max_images),
		models: Array.isArray(value.models) ? value.models.map(normalizeModel).filter(Boolean) : []
	};
}

export function keyframeOptions(presets) {
	const options = [];
	for (const preset of presets ?? []) {
		if (preset.cloud) {
			for (const model of preset.models) options.push({ key: optionKey(preset.id, model.id), preset: preset.id, model: model.id, label: model.name, group: preset.name, cloud: true, maxImages: model.maxImages ?? preset.maxImages, info: preset });
		} else {
			options.push({ key: optionKey(preset.id, null), preset: preset.id, model: null, label: preset.name, group: null, cloud: false, maxImages: preset.maxImages, info: preset });
		}
	}
	return options;
}

export function storedChoice(engine) {
	const own = isObject(engine?.keyframes) ? engine.keyframes : {};
	const preset = text(own.preset) || null;
	return { preset, model: preset ? text(own.model) || null : null };
}

export function chosenOption(options, choice) {
	if (!choice?.preset) return options[0] ?? null;
	return options.find((o) => o.key === optionKey(choice.preset, choice.model)) ?? null;
}

export const presetAbsent = (options, choice) => Boolean(choice?.preset) && !options.some((o) => o.key === optionKey(choice.preset, choice.model));

export function choiceOf(option) {
	return option.model ? { preset: option.preset, model: option.model } : { preset: option.preset };
}

const imageAsset = (doc, id) => {
	const found = id ? (doc.assets ?? []).find((a) => a.id === id) : null;
	return found?.kind === 'image' ? found : null;
};

function savedFirstFrame(doc, shotId) {
	return (doc.frames ?? []).find((f) => f.shotId === shotId && roleKind(f.role) === 'first' && f.assetId) ?? null;
}

function scenePicture(doc, saved, first) {
	if (!saved?.sceneId || saved.assetId !== first) return null;
	const scene = (doc.scenes ?? []).find((s) => s.id === saved.sceneId);
	return scene?.kind === 'splat' && scene.status === 'done' ? imageAsset(doc, scene.sourceAssetId) : null;
}

export const pictureRole = (reference) => (reference.space === 'decors3d' ? 'setting' : (TYPE_ROLES[reference.type] ?? 'character'));

export function draftPictures(doc, clip, draft, role = 'first') {
	if (!doc || !clip || !draft) return [];
	const found = [];
	const add = (asset, pictureRole, name, origin) => {
		if (!asset || found.some((p) => p.assetId === asset.id)) return;
		found.push({ assetId: asset.id, role: pictureRole, name: name || '', origin });
	};
	const saved = savedFirstFrame(doc, clip.id);
	const first = imageAsset(doc, draft.first);
	if (first && (role === 'last' || (saved?.assetId === draft.first && saved.sceneId))) add(first, 'frame', '', 'frame');
	const scene = scenePicture(doc, saved, draft.first);
	if (scene) add(scene, 'setting', '', 'scene');
	const skip = new Set(draft.exclude ?? []);
	const shared = (doc.references ?? []).filter((r) => isGlobal(r) && !skip.has(r.id));
	for (const reference of [...(draft.own ?? []), ...shared]) {
		if (SPACES.includes(reference.space)) add(imageAsset(doc, reference.assetId), pictureRole(reference), reference.name, 'reference');
	}
	const rank = (p) => PICTURE_ROLES.indexOf(p.role);
	return found.map((p, i) => [p, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(([p]) => p);
}

export function requestBody({ option, role, count: wanted, prompt, pictures }) {
	return {
		preset_id: option.preset,
		model_id: option.model,
		role: ROLES.includes(role) ? role : 'first',
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

export function normalizeKeyframeEstimate(value) {
	if (!isObject(value)) return null;
	const vram = isObject(value.vram) ? value.vram : {};
	const time = isObject(value.time) ? value.time : {};
	const quota = isObject(value.quota) ? value.quota : {};
	const cost = isObject(value.cost) ? value.cost : null;
	return {
		role: ROLES.includes(value.role) ? value.role : 'first',
		count: clampCount(value.count),
		resolution: text(value.resolution) || null,
		prompt: text(value.prompt),
		references: Array.isArray(value.references) ? value.references.map(normalizeReference).filter(Boolean) : [],
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
		role: null,
		synth: null,
		transcript: null,
		character: null,
		lipSync: null
	};
}

export const usable = (take) => isKeyframe(take) && take.status === 'done' && Boolean(take.url) && Boolean(take.generationId && take.fileId);

export const takeState = (take) => (STATES.includes(take?.status) ? take.status : 'queued');

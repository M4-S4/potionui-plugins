import { PROFILES } from './generation.js';

export const QUALITIES = ['draft', 'final'];
export const SEED_MAX = 2 ** 31 - 1;

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const filled = (value) => typeof value === 'string' && value !== '';

export const validSeed = (value) => Number.isInteger(value) && value >= 0 && value <= SEED_MAX;

export function shotEngineOf(clip) {
	const engine = isObject(clip?.engine) ? clip.engine : {};
	const own = {};
	if (filled(engine.preset)) {
		own.preset = engine.preset;
		own.model = filled(engine.model) ? engine.model : null;
		if (filled(engine.backend)) own.backend = engine.backend;
	}
	if (PROFILES.includes(engine.profile)) own.profile = engine.profile;
	if (QUALITIES.includes(engine.quality)) own.quality = engine.quality;
	if (validSeed(engine.seed)) own.seed = engine.seed;
	return own;
}

export const hasOwnEngine = (clip) => Object.keys(shotEngineOf(clip)).length > 0;

export function setShotEngine(clip, engine) {
	const own = shotEngineOf({ engine });
	if (Object.keys(own).length) clip.engine = own;
	else delete clip.engine;
}

export const projectQuality = (engine) => (engine?.quality === 'final' ? 'final' : 'draft');

export function effectiveEngine(clip, doc, quality = projectQuality(doc?.engine)) {
	const own = shotEngineOf(clip);
	const project = doc?.engine ?? {};
	const preset = 'preset' in own ? own.preset : (project.preset ?? null);
	return {
		preset,
		model: 'preset' in own ? own.model : (project.model ?? null),
		profile: own.profile ?? doc?.direction?.mode ?? 'FL2VA',
		quality: own.quality ?? quality,
		seed: own.seed ?? null
	};
}

export function migrateShotEngine(clip) {
	if (!isObject(clip) || !('engine' in clip)) return clip;
	const next = { ...clip };
	setShotEngine(next, clip.engine);
	return next;
}

export function randomSeed(random = Math.random) {
	return Math.floor(random() * (SEED_MAX + 1));
}

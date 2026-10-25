import { ulid } from './ulid.js';
import { migrateTracks, newLaneId, newVideoTrack } from './tracks.js';
import { migrateShots } from './shots.js';
import { migrateBible } from './bible.js';
import { migrateOptions } from './options.js';

const SHOT_DURATION = 5;
export const PROMPT_LANGUAGES = ['en', 'fr'];
export const DEFAULT_PROMPT_LANGUAGE = 'en';

export const promptLanguageOf = (value) => (PROMPT_LANGUAGES.includes(value) ? value : DEFAULT_PROMPT_LANGUAGE);

export function newClip(extra = {}) {
	return { id: ulid(), assetId: null, start: 0, dur: 4, srcIn: 0, label: '', stage: 'todo', take: null, fadeIn: 0, fadeOut: 0, exposure: 0, contrast: 100, saturation: 100, temperature: 0, preset: 'Original', flag: null, mute: false, ...extra };
}

export function newAsset(extra = {}) {
	return {
		id: ulid(),
		kind: 'video',
		name: '',
		src: null,
		origin: null,
		srcDur: null,
		width: null,
		height: null,
		fps: null,
		res: null,
		generated: false,
		quality: null,
		resultId: null,
		role: null,
		synth: null,
		transcript: null,
		character: null,
		lipSync: null,
		...extra
	};
}

function lane(name, role, vol, pan) {
	return {
		id: newLaneId(),
		name,
		role,
		vol,
		pan,
		mute: false,
		solo: false,
		automation: 'off',
		sends: { R1: role === 'Dialogue' ? -18 : -12, D1: -60 },
		inserts: [
			{ type: 'eq', on: true, low: 0, mid: 0, high: role === 'Dialogue' ? 2 : 0 },
			{ type: 'comp', on: role === 'Dialogue', threshold: -18, ratio: 3, attack: 10, release: 120 }
		]
	};
}

function baseDoc(t, name, promptLanguage) {
	const lanes = [
		lane(t('starter.lane.dialogue'), 'Dialogue', 0, 0),
		lane(t('starter.lane.music'), 'Musique', -2, 0),
		lane(t('starter.lane.ambience'), 'Ambiance', -6, -0.2),
		lane(t('starter.lane.foley'), 'SFX', -4, 0.3)
	];
	return {
		name,
		promptLanguage: promptLanguageOf(promptLanguage),
		fps: 25,
		aspect: '16:9',
		resolution: '1080p',
		direction: { univers: '', personnages: '', photographie: '', palette: '', rythme: '', mode: 'FL2VA' },
		synopsis: '',
		clips: [],
		audio: [],
		titles: [],
		prompts: [],
		frames: [],
		markers: [],
		references: [],
		scenes: [],
		assets: [],
		lanes,
		video: newVideoTrack(),
		aux: [
			{ id: 'R1', name: t('starter.lane.reverb'), vol: -6, mute: false },
			{ id: 'D1', name: t('starter.lane.delay'), vol: -10, mute: false }
		],
		master: { vol: 0 },
		engine: { quality: 'draft', variants: 2, backend: '', preset: null, model: null }
	};
}

export function emptyDoc(t, promptLanguage = DEFAULT_PROMPT_LANGUAGE) {
	return baseDoc(t, t('lib.default.project'), promptLanguage);
}

function starterDirection(t) {
	return {
		univers: t('starter.direction.univers'),
		personnages: t('starter.direction.personnages'),
		photographie: t('starter.direction.photographie'),
		palette: t('starter.direction.palette'),
		rythme: t('starter.direction.rythme'),
		mode: 'FL2VA'
	};
}

function starterPrompts(t) {
	return [t('starter.shot.1.prompt'), t('starter.shot.2.prompt'), t('starter.shot.3.prompt'), t('starter.shot.4.prompt'), t('starter.shot.5.prompt')];
}

export function starterDoc(t, promptT = t, promptLanguage = DEFAULT_PROMPT_LANGUAGE) {
	const doc = baseDoc(t, t('starter.name'), promptLanguage);
	doc.synopsis = t('starter.synopsis');
	doc.direction = starterDirection(promptT);
	const texts = starterPrompts(promptT);
	const shots = [t('starter.shot.1.label'), t('starter.shot.2.label'), t('starter.shot.3.label'), t('starter.shot.4.label'), t('starter.shot.5.label')].map((label, i) => [label, texts[i]]);
	shots.forEach(([label, text], i) => {
		const clip = newClip({ label, start: i * SHOT_DURATION, dur: SHOT_DURATION });
		doc.clips.push(clip);
		doc.prompts.push({ id: ulid(), shotId: clip.id, start: clip.start, dur: clip.dur, strength: 75, text });
	});
	doc.titles.push({ id: ulid(), text: t('starter.title.text'), sub: t('starter.title.sub'), start: 0, dur: 4 });
	doc.markers.push({ id: ulid(), time: doc.clips[2].start, label: t('starter.marker.castOff'), kind: 'marker' });
	return doc;
}

const RETIRED_SCENES = ['sample', 'file'];
const CAPTURE = 'Capture 3D';
const RETIRED_SET_TYPES = ['Scène d’essai', "Scène d'essai", 'Gaussian Splat'];
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const retiredSet = (r) => isObject(r) && r.space === 'decors3d' && RETIRED_SET_TYPES.includes(r.type);
const RETIRED_KEYS = ['controls', 'plans3d'];
const isNumber = (v) => typeof v === 'number';
const span = (item) => {
	const start = isNumber(item.start) ? item.start : 0;
	return [start, start + (isNumber(item.dur) ? item.dur : 0)];
};

function guidedShot(control, clips) {
	const shots = Array.isArray(clips) ? clips.filter((c) => isObject(c) && typeof c.id === 'string' && c.id) : [];
	if (control.shotId) return shots.some((c) => c.id === control.shotId) ? control.shotId : null;
	const [start, end] = span(control);
	let best = null;
	for (const clip of shots) {
		const [first, last] = span(clip);
		const covered = Math.min(end, last) - Math.max(start, first);
		if (!best || covered > best.covered) best = { covered, id: clip.id };
	}
	return best && best.covered > 0 ? best.id : null;
}

function motionReferences(doc, references) {
	const videos = new Set((Array.isArray(doc.assets) ? doc.assets : []).filter((a) => isObject(a) && a.kind === 'video').map((a) => a.id));
	const known = new Set(references.filter(isObject).map((r) => r.id));
	const added = [];
	for (const control of Array.isArray(doc.controls) ? doc.controls : []) {
		if (!isObject(control) || control.source !== 'scene3d' || !videos.has(control.assetId)) continue;
		if (typeof control.id !== 'string' || !control.id || known.has(control.id)) continue;
		const shotId = guidedShot(control, doc.clips);
		if (shotId === null) continue;
		added.push({ id: control.id, name: typeof control.name === 'string' ? control.name : '', space: 'mouvement', type: 'Control video', assetId: control.assetId, role: 'Mouvement', scope: { type: 'shot', shotId } });
		known.add(control.id);
	}
	return added;
}

export function migrate(doc) {
	if (!isObject(doc)) return doc;
	const next = migrateShots(migrateTracks(doc));
	if (Array.isArray(doc.scenes)) next.scenes = doc.scenes.filter((s) => isObject(s) && !RETIRED_SCENES.includes(s.kind));
	if (Array.isArray(doc.frames)) next.frames = doc.frames.filter((f) => !(isObject(f) && f.role === CAPTURE && !f.assetId));
	if (Array.isArray(doc.references)) {
		const kept = doc.references.filter((r) => !retiredSet(r) || r.assetId).map((r) => (retiredSet(r) ? { ...r, type: CAPTURE } : r));
		next.references = [...kept, ...motionReferences(doc, kept)];
	}
	for (const key of RETIRED_KEYS) delete next[key];
	if ('bible' in doc) next.bible = migrateBible(doc.bible);
	if (isObject(doc.engine)) next.engine = migrateOptions(doc.engine);
	return next;
}

export const SCENE_LISTS = ['scenes'];

export const absentLists = (stored) => SCENE_LISTS.filter((key) => !isObject(stored) || !(key in stored));

export function storedDoc(snapshot, absent) {
	const empty = absent.filter((key) => Array.isArray(snapshot[key]) && !snapshot[key].length);
	if (!empty.length) return snapshot;
	const kept = { ...snapshot };
	for (const key of empty) delete kept[key];
	return kept;
}

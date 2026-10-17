import { ulid } from './ulid.js';

const SHOT_DURATION = 5;
export const PROMPT_LANGUAGES = ['en', 'fr'];
export const DEFAULT_PROMPT_LANGUAGE = 'en';

export const promptLanguageOf = (value) => (PROMPT_LANGUAGES.includes(value) ? value : DEFAULT_PROMPT_LANGUAGE);

export function newClip(extra = {}) {
	return { id: ulid(), assetId: null, start: 0, dur: 4, srcIn: 0, label: '', stage: 'todo', take: null, fadeIn: 0, fadeOut: 0, exposure: 0, contrast: 100, saturation: 100, temperature: 0, preset: 'Original', flag: null, ...extra };
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

function lane(id, name, role, vol, pan) {
	return {
		id,
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
		controls: [],
		plans3d: [],
		markers: [],
		references: [],
		scenes: [],
		assets: [],
		lanes: [
			lane('A1', t('starter.lane.dialogue'), 'Dialogue', 0, 0),
			lane('A2', t('starter.lane.music'), 'Musique', -2, 0),
			lane('A3', t('starter.lane.ambience'), 'Ambiance', -6, -0.2),
			lane('A4', t('starter.lane.foley'), 'SFX', -4, 0.3)
		],
		aux: [
			{ id: 'R1', name: t('starter.lane.reverb'), vol: -6, mute: false },
			{ id: 'D1', name: t('starter.lane.delay'), vol: -10, mute: false }
		],
		master: { vol: 0 },
		results: [],
		profiles: [],
		engine: {
			seed: 48121,
			quality: 'Standard',
			resolution: '1080p',
			steps: 30,
			guidance: 6.5,
			overlap: 1,
			windowLen: 5,
			loras: [],
			post: { upscale: false, interpolation: true, denoise: true },
			variants: 2,
			backend: '',
			preset: null,
			model: null,
			consistency: 70,
			lockIdentity: true,
			motionPriority: true,
			audioDriver: 'A1',
			lipSync: true,
			offset: 0,
			followCut: true,
			naming: '{projet}_{fenêtre}_{variante}',
			autoInsert: false
		},
		hybrid: { continuite: 80, identite: 55, audio: 10, mouvement: 40, style: 50 }
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

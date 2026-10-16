import { t } from '../i18n/index.svelte.js';

export const backends = [
	{ id: 'local', vram: 24, speed: 1, cost: null },
	{ id: 'studio', vram: 96, speed: 2.2, cost: null },
	{ id: 'cloud', vram: 80, speed: 3.4, cost: 0.42 }
];

export function engineName(b) {
	if (b?.id === 'local') return t('lib.backend.local');
	if (b?.id === 'studio') return t('lib.backend.studio');
	return t('lib.backend.cloud');
}

export const stages = {
	source: {
		get label() {
			return t('lib.stage.source');
		},
		tone: 'text-fg-muted',
		dot: 'bg-fg-subtle'
	},
	todo: {
		get label() {
			return t('lib.stage.todo');
		},
		tone: 'text-warning',
		dot: 'bg-warning'
	},
	draft: {
		get label() {
			return t('lib.stage.draft');
		},
		tone: 'text-signal',
		dot: 'bg-signal'
	},
	final: {
		get label() {
			return t('lib.stage.final');
		},
		tone: 'text-success',
		dot: 'bg-success'
	}
};

export const directionFields = [
	{
		key: 'univers',
		get label() {
			return t('lib.direction.univers.label');
		},
		get hint() {
			return t('lib.direction.univers.hint');
		}
	},
	{
		key: 'personnages',
		get label() {
			return t('lib.direction.personnages.label');
		},
		get hint() {
			return t('lib.direction.personnages.hint');
		}
	},
	{
		key: 'photographie',
		get label() {
			return t('lib.direction.photographie.label');
		},
		get hint() {
			return t('lib.direction.photographie.hint');
		}
	},
	{
		key: 'palette',
		get label() {
			return t('lib.direction.palette.label');
		},
		get hint() {
			return t('lib.direction.palette.hint');
		}
	},
	{
		key: 'rythme',
		get label() {
			return t('lib.direction.rythme.label');
		},
		get hint() {
			return t('lib.direction.rythme.hint');
		}
	}
];

export const roleColor = {
	Vidéo: 'viz-1',
	Dialogue: 'viz-2',
	Ambiance: 'viz-3',
	Musique: 'viz-4',
	Prompts: 'viz-5',
	SFX: 'viz-6',
	Frames: 'viz-7',
	Guides: 'viz-8'
};

export function sceneLabel(scene) {
	return scene?.kind === 'file' ? t('lib.scene.file') : t('lib.scene.sample');
}

export const motionPresets = {
	Orbite: [
		{ t: 0, az: -60, el: 20, dist: 13, focal: 30, height: 1.5 },
		{ t: 0.5, az: 0, el: 20, dist: 13, focal: 30, height: 1.5 },
		{ t: 1, az: 60, el: 20, dist: 13, focal: 30, height: 1.5 }
	],
	'Travelling avant': [
		{ t: 0, az: 0, el: 12, dist: 18, focal: 28, height: 1.4 },
		{ t: 1, az: 0, el: 10, dist: 8, focal: 32, height: 1.4 }
	],
	Élévation: [
		{ t: 0, az: -10, el: 4, dist: 12, focal: 24, height: 1.2 },
		{ t: 1, az: 10, el: 42, dist: 15, focal: 24, height: 2.4 }
	]
};

export function motionPresetLabel(name) {
	if (name === 'Orbite') return t('lib.motionPreset.orbit');
	if (name === 'Travelling avant') return t('lib.motionPreset.dolly');
	if (name === 'Élévation') return t('lib.motionPreset.rise');
	return name;
}

export function audioRoleLabel(role) {
	if (role === 'Dialogue') return t('lib.audioRole.dialogue');
	if (role === 'Musique') return t('lib.audioRole.music');
	if (role === 'Ambiance') return t('lib.audioRole.ambience');
	if (role === 'SFX') return t('lib.audioRole.sfx');
	return role;
}

export function frameRoleLabel(role) {
	if (role === 'Début') return t('lib.frameRole.start');
	if (role === 'Fin') return t('lib.frameRole.end');
	if (role === 'Transition') return t('lib.frameRole.transition');
	if (role === 'Identité') return t('lib.frameRole.identity');
	if (role === 'Style') return t('lib.frameRole.style');
	if (role === 'Capture 3D') return t('lib.frameRole.capture3d');
	return role;
}

export function modeLabel(mode) {
	if (mode === 'Génération IA') return t('lib.mode.ai');
	if (mode === 'Rendu 3D') return t('lib.mode.render3d');
	if (mode === 'Rendu 3D + IA') return t('lib.mode.render3dAi');
	return mode;
}

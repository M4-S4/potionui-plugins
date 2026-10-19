import { t } from '../i18n/index.svelte.js';

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
	if (scene?.kind === 'splat') return t('lib.scene.splat');
	if (scene?.kind === 'glb') return t('lib.scene.glb');
	return t('lib.scene.splatfile', { format: String(scene?.format ?? 'ply').toUpperCase() });
}

export function audioRoleLabel(role) {
	if (role === 'Dialogue') return t('lib.audioRole.dialogue');
	if (role === 'Musique') return t('lib.audioRole.music');
	if (role === 'Ambiance') return t('lib.audioRole.ambience');
	if (role === 'SFX') return t('lib.audioRole.sfx');
	return role;
}

export function frameRoleLabel(role) {
	if (role === 'Début' || role === 'first') return t('lib.frameRole.start');
	if (role === 'Fin' || role === 'last') return t('lib.frameRole.end');
	if (role === 'Transition') return t('lib.frameRole.transition');
	if (role === 'Identité') return t('lib.frameRole.identity');
	if (role === 'Style') return t('lib.frameRole.style');
	if (role === 'Capture 3D') return t('lib.frameRole.capture3d');
	return role;
}

export const PRODUCTION_MODES = ['ai', 'render3d', 'render3d_ai'];

export function modeLabel(mode) {
	if (mode === 'ai') return t('lib.mode.ai');
	if (mode === 'render3d') return t('lib.mode.render3d');
	if (mode === 'render3d_ai') return t('lib.mode.render3dAi');
	return mode;
}

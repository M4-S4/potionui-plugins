import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, select, toast, productionRange, secs, clipAt, overlaps } from './state.svelte.js';
import { ulid } from './ulid.js';
import { SOUND_ROLE, SOUND_SPACE, SOUND_TYPES } from './sound.js';

export const families = [
	{
		id: 'identite',
		icon: 'user',
		get label() {
			return t('lib.family.identite.label');
		},
		get short() {
			return t('lib.family.identite.short');
		},
		get hint() {
			return t('lib.family.identite.hint');
		}
	},
	{
		id: 'decors3d',
		icon: 'cube',
		get label() {
			return t('lib.family.decors3d.label');
		},
		get short() {
			return t('lib.family.decors3d.short');
		},
		get hint() {
			return t('lib.family.decors3d.hint');
		}
	},
	{
		id: 'mouvement',
		icon: 'route',
		get label() {
			return t('lib.family.mouvement.label');
		},
		get short() {
			return t('lib.family.mouvement.short');
		},
		get hint() {
			return t('lib.family.mouvement.hint');
		}
	},
	{
		id: SOUND_SPACE,
		icon: 'wave',
		get label() {
			return t('lib.family.son.label');
		},
		get short() {
			return t('lib.family.son.short');
		},
		get hint() {
			return t('lib.family.son.hint');
		}
	}
];
const types = { identite: ['Personnage', 'Décor', 'Objet', 'Style'], decors3d: ['Capture 3D'], mouvement: ['Control video', 'Trajectoire'], [SOUND_SPACE]: SOUND_TYPES };
const roles = { identite: 'Identité', decors3d: 'Décor 3D', mouvement: 'Mouvement', [SOUND_SPACE]: SOUND_ROLE };

export const typesOf = (space) => types[space] ?? [];

export function refTypeLabel(type) {
	if (type === 'Personnage') return t('lib.refType.character');
	if (type === 'Décor') return t('lib.refType.set');
	if (type === 'Objet') return t('lib.refType.object');
	if (type === 'Style') return t('lib.refType.style');
	if (type === 'Capture 3D') return t('lib.refType.capture3d');
	if (type === 'Control video') return t('lib.refType.control');
	if (type === 'Trajectoire') return t('lib.refType.trajectory');
	if (type === 'Voix') return t('lib.refType.voice');
	if (type === 'Musique') return t('lib.refType.music');
	if (type === 'Ambiance') return t('lib.refType.ambience');
	return type;
}

export function refRoleLabel(role) {
	if (role === 'Identité') return t('lib.refRole.identity');
	if (role === 'Style') return t('lib.refRole.style');
	if (role === 'Décor') return t('lib.refRole.set');
	if (role === 'Objet') return t('lib.refRole.object');
	if (role === 'Décor 3D') return t('lib.refRole.set3d');
	if (role === 'Mouvement') return t('lib.refRole.motion');
	if (role === 'Caméra') return t('lib.refRole.camera');
	if (role === SOUND_ROLE) return t('lib.refRole.sound');
	return role;
}

export function openReferences(space = 'all') {
	ui.workspace = 'director';
	ui.dockTab = 'references';
	ui.refSpace = space;
}

export function addReference(space = ui.refSpace === 'all' ? 'identite' : ui.refSpace) {
	const type = types[space][0];
	const r = { id: ulid(), name: t('lib.default.reference', { type: refTypeLabel(type) }), space, type, assetId: null, role: roles[space], scope: { type: 'global' } };
	act(() => doc.references.push(r));
	select('reference', r.id);
	toast(t('lib.refs.added'));
}

export function attachToRange() {
	const s = ui.selection?.kind === 'reference' ? doc.references.find((r) => r.id === ui.selection.id) : null;
	if (!s) return toast(t('lib.refs.selectOne'), 'warning');
	const [a, b] = productionRange();
	const shot = clipAt((a + b) / 2) ?? doc.clips.find((c) => overlaps(c.start, c.dur, [a, b]));
	if (!shot) return toast(t('lib.block.noRange'), 'warning');
	act(() => (s.scope = { type: 'shot', shotId: shot.id }));
	toast(t('lib.refs.attached', { name: s.name, start: secs(shot.start), end: secs(shot.start + shot.dur) }));
}

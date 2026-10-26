import { CHARACTERS, PLACES, cardsOf } from './bible.js';
import { isGlobal } from './shots.js';
import { SOUND_ROLE, SOUND_SPACE } from './sound.js';

export const TAG_CLASS = 'inline-flex max-w-full min-w-0 items-center gap-1 rounded-sm border border-line-strong px-1 text-2xs text-fg-muted';

export const TYPE_KEYS = { Personnage: 'character', Décor: 'set', Objet: 'object', Style: 'style', 'Capture 3D': 'capture3d', 'Control video': 'control', Trajectoire: 'trajectory', Voix: 'voice', Musique: 'music', Ambiance: 'ambience' };
export const TYPE_ICONS = { Personnage: 'user', Décor: 'mountain', Objet: 'diamond', Style: 'palette', 'Capture 3D': 'cube', 'Control video': 'film', Trajectoire: 'route', Voix: 'mic', Musique: 'music', Ambiance: 'wave' };
export const FAMILY_ICONS = { identite: 'user', decors3d: 'cube', mouvement: 'route', [SOUND_SPACE]: 'wave' };
export const ROLE_KEYS = { Identité: 'identity', Style: 'style', Décor: 'set', Objet: 'object', Mouvement: 'motion', Caméra: 'camera', [SOUND_ROLE]: 'sound' };
export const DEFAULT_ROLES = { identite: 'Identité', decors3d: 'Décor', mouvement: 'Mouvement', [SOUND_SPACE]: SOUND_ROLE };
export const CARD_ICONS = { [CHARACTERS]: 'user', [PLACES]: 'mountain' };
export const PICTURE_ICONS = { frame: 'image', setting: 'mountain', character: 'user', object: 'diamond', style: 'palette' };

export const typeIcon = (reference) => TYPE_ICONS[reference?.type] ?? FAMILY_ICONS[reference?.space] ?? 'bookmark';

function roleShown(reference) {
	const role = reference?.role;
	if (!role || role === DEFAULT_ROLES[reference.space]) return false;
	return !ROLE_KEYS[role] || ROLE_KEYS[role] !== TYPE_KEYS[reference.type];
}

export function referenceTags(doc, reference) {
	if (!reference) return [];
	const tags = [{ kind: 'type', icon: typeIcon(reference), type: reference.type, space: reference.space }];
	if (roleShown(reference)) tags.push({ kind: 'role', role: reference.role });
	if (isGlobal(reference)) tags.push({ kind: 'scope', global: true, shot: null, number: null });
	else {
		const clips = doc?.clips ?? [];
		const i = clips.findIndex((c) => c.id === reference.scope.shotId);
		tags.push({ kind: 'scope', global: false, shot: i >= 0 ? clips[i] : null, number: i >= 0 ? i + 1 : null });
	}
	for (const kind of [CHARACTERS, PLACES]) {
		for (const card of cardsOf(doc, kind)) {
			const linked = (card.references ?? []).includes(reference.id);
			const voice = kind === CHARACTERS && card.voiceRef === reference.id;
			if (linked || voice) tags.push({ kind: 'card', card, cardKind: kind, voice: voice && !linked, icon: CARD_ICONS[kind] });
		}
	}
	return tags;
}

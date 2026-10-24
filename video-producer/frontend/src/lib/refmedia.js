import { SOUND_SPACE, SOUND_TYPES } from './sound.js';

const KINDS = {
	identite: { Personnage: 'image', Décor: 'image', Objet: 'image', Style: 'image' },
	decors3d: { 'Capture 3D': 'image' },
	mouvement: { 'Control video': 'video', Trajectoire: 'video' },
	[SOUND_SPACE]: Object.fromEntries(SOUND_TYPES.map((type) => [type, 'audio']))
};

export const typesOf = (space) => Object.keys(KINDS[space] ?? {});

export function refMediaKind(space, type) {
	const kinds = KINDS[space];
	return kinds ? (kinds[type] ?? Object.values(kinds)[0]) : null;
}

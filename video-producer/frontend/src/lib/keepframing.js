import table from './keepframingtable.js';

const MOVES = new Set(table.moves);
const VERBS = new Set(table.phrases.verbs);
const PARTICLES = new Set(table.phrases.particles);

const words = (text) => String(text ?? '').toLowerCase().match(/[a-z]+/g) ?? [];

export function moves(text) {
	const found = words(text);
	return found.some((word) => MOVES.has(word)) || found.some((word, i) => i > 0 && VERBS.has(found[i - 1]) && PARTICLES.has(word));
}

export const undoneAction = (draft) => Boolean(draft) && Boolean(draft.first) && (draft.keepFraming === true ? !draft.last : draft.first === draft.last) && moves(draft.text);

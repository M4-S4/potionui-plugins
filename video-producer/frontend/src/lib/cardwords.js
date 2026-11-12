export const CARD_WORDS = ['card', 'label', 'picture'];
export const DEFAULT_CARD_WORDS = 'card';

export const cardWordsOf = (doc) => (CARD_WORDS.includes(doc?.cardWords) ? doc.cardWords : DEFAULT_CARD_WORDS);

export function setCardWords(doc, value) {
	if (!CARD_WORDS.includes(value)) return;
	if (value === DEFAULT_CARD_WORDS) delete doc.cardWords;
	else doc.cardWords = value;
}

export const shotCardWordsOf = (clip) => (CARD_WORDS.includes(clip?.cardWords) ? clip.cardWords : null);

export function setShotCardWords(clip, value) {
	if (CARD_WORDS.includes(value)) clip.cardWords = value;
	else delete clip.cardWords;
}

export function shotCardWordsView(composed, own) {
	const used = CARD_WORDS.includes(composed?.cardWords) ? composed.cardWords : null;
	const mine = CARD_WORDS.includes(own) ? own : null;
	const replaced = Boolean(used) && composed?.reference?.layout === 'refs' && composed.reference.overridden === true;
	return { show: Boolean(used || mine), used, replaced, disabled: replaced };
}

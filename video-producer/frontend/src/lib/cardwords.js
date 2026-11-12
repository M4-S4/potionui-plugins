export const CARD_WORDS = ['card', 'label', 'picture'];
export const DEFAULT_CARD_WORDS = 'card';

export const cardWordsOf = (doc) => (CARD_WORDS.includes(doc?.cardWords) ? doc.cardWords : DEFAULT_CARD_WORDS);

export function setCardWords(doc, value) {
	if (!CARD_WORDS.includes(value)) return;
	if (value === DEFAULT_CARD_WORDS) delete doc.cardWords;
	else doc.cardWords = value;
}

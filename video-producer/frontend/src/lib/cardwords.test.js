import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';
import { CARD_WORDS, cardWordsOf, setCardWords } from './cardwords.js';

globalThis.Image = class {
	set src(value) {}
};

const { doc, ui, dispose } = await import('./state.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;

after(() => dispose());

test('a project keeps the card words beside a picture unless it chose the label or the picture alone', () => {
	assert.equal(cardWordsOf({}), 'card');
	assert.equal(cardWordsOf({ cardWords: 'none' }), 'card');
	assert.equal(cardWordsOf({ cardWords: 'picture' }), 'picture');
	const project = { cardWords: 'label' };
	setCardWords(project, 'picture');
	assert.equal(project.cardWords, 'picture');
	setCardWords(project, 'unknown');
	assert.equal(project.cardWords, 'picture');
	setCardWords(project, 'card');
	assert.equal('cardWords' in project, false);
	assert.deepEqual(CARD_WORDS, ['card', 'label', 'picture']);
});

test('the project properties offer the three card words and show the one the project uses', async () => {
	delete doc.cardWords;
	ui.modal = { type: 'project' };
	const control = async () => hostUis(await renderComponent(MODALS), 'SegmentedControl').find((item) => item.ariaLabel === t('project.cardWords.title'));
	const shown = await control();
	assert.deepEqual(
		shown.items.map((item) => item.id),
		['card', 'label', 'picture']
	);
	assert.deepEqual(
		shown.items.map((item) => item.label),
		[t('project.cardWords.card'), t('project.cardWords.label'), t('project.cardWords.picture')]
	);
	assert.equal(shown.selected, 'card');
	assert.ok(textOf(await renderComponent(MODALS)).includes(t('project.cardWords.cardHelp')));
	doc.cardWords = 'picture';
	assert.equal((await control()).selected, 'picture');
	assert.ok(textOf(await renderComponent(MODALS)).includes(t('project.cardWords.pictureHelp')));
	delete doc.cardWords;
	ui.modal = null;
});

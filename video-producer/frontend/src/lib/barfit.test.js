import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { renderComponent } from './svelte-harness.js';
import { fitChip, shortPresetName } from './barfit.js';
import { DECK_COMPACT_CENTRE, DECK_HEIGHT, deckChipFolded, deckCompact, deckLine } from './deck.js';
import { DRAWER_WIDTH, drawerPlace } from './deck-drawer.js';

const { doc, ui, dispose } = await import('./state.svelte.js');

const t = (key, params = {}) => `${key}${Object.keys(params).length ? JSON.stringify(params) : ''}`;
const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;
const WAN = '01KX47WANVIDEO0000000000TV';

const widths = { engine: 117, short: 65, prefixes: [52], ellipsis: 8, sep: 14, profile: 36, size: 50, drafts: 16, cell: 187, cellGap: 6 };

after(() => dispose());

test('barfit: the chip keeps the whole engine name while it fits, then the short name of the preset, then engine · profile, then the engine alone', () => {
	assert.deepEqual(fitChip({ room: 600, ...widths }), { cell: true, engine: 'full', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 454, ...widths }), { cell: true, engine: 'full', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 453, ...widths }), { cell: true, engine: 'short', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 402, ...widths }), { cell: true, engine: 'short', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 401, ...widths }), { cell: true, engine: 'short', tier: 'profile', cut: null });
	assert.deepEqual(fitChip({ room: 308, ...widths }), { cell: true, engine: 'short', tier: 'profile', cut: null });
	assert.deepEqual(fitChip({ room: 307, ...widths }), { cell: true, engine: 'short', tier: 'engine', cut: null });
	assert.deepEqual(fitChip({ room: 258, ...widths }), { cell: true, engine: 'short', tier: 'engine', cut: null });
});

test('barfit: the Estimated cell gives way before the engine name is cut, and the cut lands after a whole word with a clean ellipsis', () => {
	assert.deepEqual(fitChip({ room: 257, ...widths }), { cell: false, engine: 'short', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 209, ...widths }), { cell: false, engine: 'short', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 208, ...widths }), { cell: false, engine: 'short', tier: 'profile', cut: null });
	assert.deepEqual(fitChip({ room: 115, ...widths }), { cell: false, engine: 'short', tier: 'profile', cut: null });
	assert.deepEqual(fitChip({ room: 114, ...widths }), { cell: false, engine: 'short', tier: 'engine', cut: null });
	assert.deepEqual(fitChip({ room: 65, ...widths }), { cell: false, engine: 'short', tier: 'engine', cut: null });
	assert.deepEqual(fitChip({ room: 64, ...widths }), { cell: false, engine: 'cut', tier: 'engine', cut: 0 });
	assert.deepEqual(fitChip({ room: 60, ...widths }), { cell: false, engine: 'cut', tier: 'engine', cut: 0 });
	assert.deepEqual(fitChip({ room: 59, ...widths }), { cell: false, engine: 'cut', tier: 'engine', cut: -1 });
	assert.deepEqual(fitChip({ room: 200, ...widths, prefixes: [30, 52, 70], short: 90 }), { cell: false, engine: 'short', tier: 'profile', cut: null });
	assert.deepEqual(fitChip({ room: 80, ...widths, prefixes: [30, 52, 70], short: 90, engine: 130 }), { cell: false, engine: 'cut', tier: 'engine', cut: 2 });
	assert.deepEqual(fitChip({ room: 70, ...widths, prefixes: [30, 52, 70], short: 90, engine: 130 }), { cell: false, engine: 'cut', tier: 'engine', cut: 1 });
	assert.deepEqual(fitChip({ room: 400, ...widths, cell: 0 }), { cell: false, engine: 'full', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 160, ...widths, short: null }), { cell: false, engine: 'full', tier: 'engine', cut: null });
	assert.deepEqual(fitChip({ room: 167, ...widths, short: null }), { cell: false, engine: 'full', tier: 'profile', cut: null });
	assert.deepEqual(fitChip({ room: 300, ...widths, profile: 0, size: 0 }), { cell: true, engine: 'short', tier: 'full', cut: null });
	assert.deepEqual(fitChip({ room: 350, ...widths, profile: 0, size: 0 }), { cell: true, engine: 'full', tier: 'full', cut: null });
});

test('barfit: the short name of a preset drops its hardware tier in brackets, never a word', () => {
	assert.equal(shortPresetName('MiniMax H3 (12 GB)'), 'MiniMax H3');
	assert.equal(shortPresetName('LTX-2.5 (8 GB) '), 'LTX-2.5');
	assert.equal(shortPresetName('Wan 2.2 TI2V 5B'), 'Wan 2.2 TI2V 5B');
	assert.equal(shortPresetName('(12 GB)'), '(12 GB)');
	assert.equal(shortPresetName(''), '');
	assert.equal(shortPresetName(null), '');
	const parts = { engine: 'MiniMax H3 (12 GB)', short: 'MiniMax H3', prefixes: ['MiniMax'], profile: 'FL2VA', size: '832×480', drafts: 1 };
	assert.deepEqual(deckChipFolded(parts, { engine: 'full', tier: 'full' }, t), ['MiniMax H3 (12 GB)', 'FL2VA', '832×480', 'production.deck.drafts{"count":1}']);
	assert.deepEqual(deckChipFolded(parts, { engine: 'short', tier: 'full' }, t), ['MiniMax H3', 'FL2VA', '832×480', 'production.deck.drafts{"count":1}']);
	assert.deepEqual(deckChipFolded(parts, { engine: 'short', tier: 'profile' }, t), ['MiniMax H3', 'FL2VA']);
	assert.deepEqual(deckChipFolded({ ...parts, profile: '' }, { engine: 'short', tier: 'profile' }, t), ['MiniMax H3']);
	assert.deepEqual(deckChipFolded(parts, { engine: 'short', tier: 'engine' }, t), ['MiniMax H3']);
	assert.deepEqual(deckChipFolded(parts, { engine: 'cut', tier: 'engine', cut: 0 }, t), ['MiniMax…']);
	assert.deepEqual(deckChipFolded(parts, { engine: 'cut', tier: 'engine', cut: -1 }, t), ['MiniMax H3']);
	assert.deepEqual(deckChipFolded({ ...parts, drafts: null }, { engine: 'full', tier: 'full' }, t), ['MiniMax H3 (12 GB)', 'FL2VA', '832×480', 'production.deck.draftsMixed']);
});

test('barfit: the deck folds to 56 px under a 420 px centre or a 1024 px page, measured as if the deck were full, and comes back as soon as the room is back', () => {
	assert.equal(DECK_HEIGHT, 92);
	assert.equal(DECK_COMPACT_CENTRE, 420);
	assert.equal(deckCompact({ narrow: false, centre: 420 }), false);
	assert.equal(deckCompact({ narrow: false, centre: 419 }), true);
	assert.equal(deckCompact({ narrow: false, centre: 441 }), false);
	assert.equal(deckCompact({ narrow: false, centre: 378 }), true);
	assert.equal(deckCompact({ narrow: true, centre: 900 }), true);
	assert.equal(deckCompact({ narrow: false, centre: 455, deck: 56 }), true);
	assert.equal(deckCompact({ narrow: false, centre: 456, deck: 56 }), false);
	assert.equal(deckCompact({ narrow: false, centre: 437, deck: 74 }), true);
	assert.equal(deckCompact({ narrow: false, centre: 438, deck: 74 }), false);
	assert.equal(deckCompact({ narrow: false }), false);
	assert.equal(deckCompact(), false);
	assert.equal(deckLine({ compact: false, eyebrow: 'Plan 03 · 8,0 s → 10,0 s', detail: { text: '1 prompt', warn: false } }), '1 prompt');
	assert.equal(deckLine({ compact: true, eyebrow: 'Plan 03 · 8,0 s → 10,0 s', detail: { text: '1 prompt', warn: false } }), 'Plan 03 · 8,0 s → 10,0 s · 1 prompt');
	assert.equal(deckLine({ compact: true, eyebrow: 'Plan 03', detail: { text: '', warn: false } }), 'Plan 03');
	assert.equal(deckLine({ compact: true, eyebrow: 'Plan 03', detail: { text: 'no prompt', warn: true } }), 'no prompt');
	assert.equal(deckLine({ compact: true, eyebrow: '', detail: { text: '1 prompt', warn: false } }), '1 prompt');
});

test('barfit: the deck measures the chip on a hidden ruler that carries every width the fit needs, one span per word prefix of the engine name', async () => {
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2 TI2V (12 GB)', video: true, cloud: false, profiles: ['FL2VA'] }] };
	doc.engine = { backend: 'native', preset: WAN, model: null };
	doc.clips = [];
	const html = await renderComponent(DECK);
	const ruler = html.slice(html.indexOf('class="vp-deck-chip-ruler" aria-hidden="true"'), html.indexOf('</span>', html.lastIndexOf('data-rule="cell-value"')));
	for (const part of ['engine', 'short', 'ellipsis', 'sep', 'profile', 'size', 'drafts', 'cell-label', 'cell-value']) assert.equal((ruler.match(new RegExp(`data-rule="${part}"`, 'g')) ?? []).length, 1, part);
	assert.deepEqual([...ruler.matchAll(/data-rule="prefix">([^<]*)</g)].map((m) => m[1]), ['Wan', 'Wan 2.2']);
	assert.match(ruler, /data-rule="engine">Wan 2\.2 TI2V \(12 GB\)</);
	assert.match(ruler, /data-rule="short">Wan 2\.2 TI2V</);
	assert.match(html, /<button[^>]*class="vp-deck-chip"[^>]*aria-expanded="false"/);
	assert.doesNotMatch(html, /class="vp-deck-chip"[^>]*aria-label=/);
});

test('barfit: the Settings drawer keeps its 440 px while the page is 1024 px wide or more, and takes the whole width of the space under it', () => {
	const deck = { top: 784, left: 56, width: 1376 };
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 1376 } }), { width: DRAWER_WIDTH, maxHeight: 600, space: 784 });
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 1376 }, full: true }), { width: 1376, maxHeight: 600, space: 784 });
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 300 }, full: false }), { width: 276, maxHeight: 600, space: 784 });
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 300 }, full: true }), { width: 300, maxHeight: 600, space: 784 });
});

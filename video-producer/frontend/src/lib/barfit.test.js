import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CHIP_TIERS, fitChip, shortPresetName } from './barfit.js';
import { DECK_COMPACT_CENTRE, DECK_COMPACT_HEIGHT, DECK_HEIGHT, deckChipFolded, deckCompact, deckLine } from './deck.js';
import { DRAWER_WIDTH, drawerPlace } from './deck-drawer.js';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const page = read('../VideoProducerPage.svelte');
const rule = (selector) => page.match(new RegExp(`\\.vp-root ${selector.replace(/[.[\]()'=>:]/g, '\\$&')} \\{([^}]*)\\}`))?.[1] ?? '';
const t = (key, params = {}) => `${key}${Object.keys(params).length ? JSON.stringify(params) : ''}`;

const widths = { engine: 117, short: 65, prefixes: [52], ellipsis: 8, sep: 14, profile: 36, size: 50, drafts: 16, cell: 187, cellGap: 6 };

test('barfit: the chip keeps the whole engine name while it fits, then the short name of the preset, then engine · profile, then the engine alone', () => {
	assert.deepEqual(CHIP_TIERS, ['full', 'profile', 'engine']);
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
	assert.equal(DECK_COMPACT_HEIGHT, 56);
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

test('barfit: the compact deck is drawn by the is-compact class, 56 px high, thumbnail 40, mark 48, one title and one detail line, no cell, chip and icon buttons at 32 px, without a jump when motion is reduced', () => {
	const deck = read('../components/production/ProductionDeck.svelte');
	assert.match(deck, /const centre = deckEl\.closest\('\.vp-root'\)\?\.querySelector\('main'\) \?\? null;/);
	assert.match(deck, /compact = deckCompact\(\{ narrow, centre: centre \? centre\.getBoundingClientRect\(\)\.height : Infinity, deck: deckEl\.getBoundingClientRect\(\)\.height \}\);/);
	assert.match(deck, /const resized = new ResizeObserver\(read\);\n\t\tresized\.observe\(centre\);/);
	assert.match(deck, /<div bind:this=\{deckEl\} class="vp-deck" class:is-compact=\{compact\}/);
	assert.match(deck, /<span class="vp-deck-eyebrow" aria-hidden=\{compact\}>\{eyebrow\}<\/span>/);
	assert.match(deck, /const showCell = \$derived\(!compact && fit\.cell\);/);
	assert.match(deck, /\{#if showCell\}\n\t+<InfoTip lines=\{cellLines\} wrapperClass="vp-deck-timing">/);
	assert.match(deck, /const cellText = \$derived\(showCell \? '' : `\$\{cell\.label\} \$\{cell\.value\}\$\{cell\.sub \? ` · \$\{cell\.sub\}` : ''\}`\);/);
	assert.match(deck, /const chipTip = \$derived\(\[engineTip, showProfile \? profileHint\(doc\.direction\.mode, t\) : '', cellText, t\('production\.deck\.chipTip'\)\]\.filter\(Boolean\)\.join\(' · '\)\);/);
	const viewport = read('viewport.svelte.js');
	assert.match(viewport, /export const COMPACT_WIDTH = 1024;/);
	assert.match(viewport, /compact: Boolean\(query\(COMPACT\)\?\.matches\)/);
	assert.match(viewport, /viewport\.compact = compact\.matches;/);
	assert.match(rule('.vp-deck'), /height: 92px;[\s\S]*transition: height 180ms/);
	assert.match(rule('.vp-deck.is-compact'), /^ height: 56px; $/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-thumb'), /width: 40px; height: 40px;/);
	assert.match(rule('.vp-deck-clock'), /white-space: nowrap;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-clock'), /display: none;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-eyebrow'), /height: 0; opacity: 0;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-title'), /font-size: 13px;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-detail'), /min-height: 18px;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-detail-text.is-whole'), /-webkit-line-clamp: 1;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-generate'), /width: 48px; height: 48px;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-mark'), /width: 42px; height: 42px;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-icon-button'), /width: 32px; height: 32px;/);
	assert.match(rule('.vp-deck.is-compact .vp-deck-chip'), /height: 32px;/);
	assert.match(page, /\.vp-root:has\(\.vp-deck\.is-compact\) \.vp-toasts \{ bottom: calc\(2\.5rem \+ 56px\); \}/);
	const reduced = page.slice(page.indexOf('@media (prefers-reduced-motion: reduce)'));
	assert.match(reduced, /\.vp-root \.vp-deck,\n\t+\.vp-root \.vp-deck-thumb,\n\t+\.vp-root \.vp-deck-eyebrow,\n\t+\.vp-root \.vp-deck-mark,[\s\S]*?transition: none !important;/);
	assert.match(page, /:root\[data-motion='reduce'\] \.vp-root \.vp-deck,[\s\S]*?\.vp-deck-mark \{ transition: none; \}/);
});

test('barfit: the chip is measured on a hidden ruler in the font of the chip, with the cell, and refitted when its texts or its room change', () => {
	const deck = read('../components/production/ProductionDeck.svelte');
	assert.match(deck, /<span bind:this=\{rulerEl\} class="vp-deck-chip-ruler" aria-hidden="true">/);
	for (const part of ['engine', 'short', 'ellipsis', 'sep', 'profile', 'size', 'drafts', 'cell-label', 'cell-value']) assert.match(deck, new RegExp(`data-rule="${part}"`), part);
	assert.match(deck, /\{#each enginePrefixes as prefix, i \(i\)\}<span class="vp-deck-chip-engine" data-rule="prefix">\{prefix\}<\/span>\{\/each\}/);
	assert.match(deck, /const chrome = chipEl\.getBoundingClientRect\(\)\.width - chipTextEl\.getBoundingClientRect\(\)\.width;/);
	assert.match(deck, /const others = groupEl\.getBoundingClientRect\(\)\.width - chipEl\.getBoundingClientRect\(\)\.width;/);
	assert.match(deck, /room: utilityEl\.getBoundingClientRect\(\)\.width - others - chrome,/);
	assert.match(deck, /const cellWidth = compact \? 0 : Math\.max\(width\('cell-label'\), width\('cell-value'\)\) \+ CELL_PAD;/);
	assert.match(deck, /resized\.observe\(utilityEl\);\n\t\tresized\.observe\(groupEl\);\n\t\tresized\.observe\(rulerEl\);\n\t\tchanged\.observe\(rulerEl, \{ childList: true, subtree: true, characterData: true \}\);/);
	assert.match(deck, /aria-label=\{folded \? chipFull\.join\(' · '\) : undefined\}/);
	assert.match(rule('.vp-deck-chip-ruler'), /position: absolute;[\s\S]*height: 0;[\s\S]*visibility: hidden;[\s\S]*font-size: 12px; white-space: pre;/);
	assert.match(rule('.vp-deck-timing'), /margin-right: 2px; padding: 0 8px;/);
	assert.match(rule('.vp-deck-utility'), /position: relative;[\s\S]*gap: 4px;/);
	assert.match(deck, /const CELL_PAD = 16;\n\tconst CELL_GAP = 6;/);
});

test('barfit: the Settings drawer keeps its 440 px while the page is 1024 px wide or more, and takes the whole width of the space under it', () => {
	const deck = { top: 784, left: 56, width: 1376 };
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 1376 } }), { width: DRAWER_WIDTH, maxHeight: 600, space: 784 });
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 1376 }, full: true }), { width: 1376, maxHeight: 600, space: 784 });
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 300 }, full: false }), { width: 276, maxHeight: 600, space: 784 });
	assert.deepEqual(drawerPlace({ deck, root: { top: 0, width: 300 }, full: true }), { width: 300, maxHeight: 600, space: 784 });
	const drawer = read('../components/production/ProductionDrawer.svelte');
	assert.match(drawer, /import \{ viewport \} from '\.\.\/\.\.\/lib\/viewport\.svelte\.js';/);
	assert.match(drawer, /full: viewport\.compact \}\);/);
	assert.match(drawer, /\$effect\(\(\) => \{\n\t\tviewport\.compact;\n\t\tanchorTo\(\);\n\t\}\);/);
	assert.doesNotMatch(drawer, /drawerFocus|closeDrawer/);
	assert.match(drawer, /import \{ closesOnOutsidePointer \} from '\.\.\/\.\.\/lib\/drawer\.js';/);
});

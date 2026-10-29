import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DRAWER_INSET, DRAWER_MAX_HEIGHT, DRAWER_WIDTH, drawerCloses, drawerPlace, drawerRows, profileControl, profileHint, profileOptions, tabTarget } from './deck-drawer.js';
import { deckChip } from './deck.js';

const t = (key, params = {}) => `${key}${Object.keys(params).length ? JSON.stringify(params) : ''}`;
const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const node = (children = []) => {
	const self = { children, contains: (el) => el === self || children.some((child) => (child.contains ? child.contains(el) : child === el)) };
	return self;
};

test('drawer: the rows follow the engine, the profile, the sizes, the sound and the shots with their own engine', () => {
	assert.deepEqual(drawerRows(), ['engine', 'drafts', 'edit']);
	assert.deepEqual(drawerRows({ engine: true, profile: true, sizes: true, guided: true, own: 2 }), ['engine', 'profile', 'draftSize', 'finalSize', 'drafts', 'margin', 'own', 'edit']);
	assert.deepEqual(drawerRows({ engine: false, sizes: true }), ['engine', 'drafts', 'edit']);
	assert.deepEqual(drawerRows({ engine: true, sizes: false, guided: true }), ['engine', 'drafts', 'margin', 'edit']);
});

test('drawer: the profile is a segmented control when the current one is supported, a pop-up with the current one greyed when it is not', () => {
	const items = [{ id: 'FL2VA', label: 'FL2VA' }, { id: 'Ref2VA', label: 'Ref2VA' }];
	assert.equal(profileControl({ items, current: 'FL2VA' }), 'segmented');
	assert.equal(profileControl({ items, current: 'Hybrid AV' }), 'popup');
	assert.equal(profileControl({ items: [], current: 'FL2VA' }), 'none');
	assert.deepEqual(profileOptions({ items, current: 'Ref2VA' }), items);
	assert.deepEqual(profileOptions({ items, current: 'Hybrid AV' }), [{ id: 'Hybrid AV', label: 'Hybrid AV', unsupported: true }, ...items]);
	assert.deepEqual(profileOptions({ items, current: '' }), items);
	assert.equal(profileHint('FL2VA', t), 'production.profile.fl2va');
	assert.equal(profileHint('Ref2VA', t), 'production.profile.ref2va');
	assert.equal(profileHint('Hybrid AV', t), 'production.profile.hybrid');
});

test('drawer: it is 440 px wide, never wider than the plugin root, never taller than the space above the deck, which the backdrop covers', () => {
	const deck = { top: 768, right: 1384, left: 56, width: 1328 };
	const root = { top: 0, left: 56, width: 1328 };
	assert.deepEqual(drawerPlace({ deck, root }), { width: DRAWER_WIDTH, maxHeight: DRAWER_MAX_HEIGHT, space: 768 });
	const low = drawerPlace({ deck: { ...deck, top: 400 }, root });
	assert.equal(low.maxHeight, 400 - DRAWER_INSET);
	assert.equal(low.space, 400);
	const narrow = drawerPlace({ deck: { top: 500, right: 400, left: 0, width: 400 }, root: { top: 0, left: 0, width: 400 } });
	assert.deepEqual(narrow, { width: 400 - DRAWER_INSET, maxHeight: 500 - DRAWER_INSET, space: 500 });
	assert.deepEqual(drawerPlace({ deck: { top: 500, right: 400, left: 0, width: 400 }, root: null }), { width: 400 - DRAWER_INSET, maxHeight: 0, space: 0 });
	assert.equal(DRAWER_WIDTH, 440);
});

test('drawer: Tab cycles inside the dialog, and comes back in when the focus escaped', () => {
	const [a, b, c] = ['a', 'b', 'c'];
	const list = [a, b, c];
	assert.equal(tabTarget({ list, active: a }), null);
	assert.equal(tabTarget({ list, active: c }), a);
	assert.equal(tabTarget({ shift: true, list, active: a }), c);
	assert.equal(tabTarget({ shift: true, list, active: b }), null);
	assert.equal(tabTarget({ list, active: null, inside: false }), a);
	assert.equal(tabTarget({ shift: true, list, active: null, inside: false }), c);
	assert.equal(tabTarget({ list: [] }), null);
});

test('drawer: a pointer outside the dialog and the chip closes it, unless another layer is on top', () => {
	const field = {};
	const dialog = node([field]);
	const chip = {};
	const toggle = node([chip]);
	const elsewhere = {};
	assert.equal(drawerCloses({ target: elsewhere, dialog, toggle, top: true }), true);
	assert.equal(drawerCloses({ target: field, dialog, toggle, top: true }), false);
	assert.equal(drawerCloses({ target: chip, dialog, toggle, top: true }), false);
	assert.equal(drawerCloses({ target: elsewhere, dialog, toggle, top: false }), false);
	assert.equal(drawerCloses({ target: null, dialog, toggle, top: true }), false);
	assert.equal(drawerCloses({ target: elsewhere, dialog, toggle: null, top: true }), true);
});

test('drawer: the chip of the deck opens it, keeps the focus to give it back, and the More menu keeps the results, the queue and the final pass only', () => {
	const deck = source('../components/production/ProductionDeck.svelte');
	assert.match(deck, /import ProductionDrawer from '\.\/ProductionDrawer\.svelte';/);
	assert.match(deck, /let drawerOpen = \$state\(false\);/);
	assert.match(deck, /<button bind:this=\{chipEl\} type="button" class="vp-deck-chip" aria-expanded=\{drawerOpen\} aria-haspopup="dialog" onclick=\{toggleDrawer\}>/);
	assert.match(deck, /function toggleDrawer\(\) \{\n\t\tif \(drawerOpen\) \{\n\t\t\tdrawerOpen = false;\n\t\t\treturn;\n\t\t\}\n\t\tsetReturnFocus\(chipEl\);\n\t\tui\.menuOpen = null;\n\t\tdrawerOpen = true;\n\t\}/);
	assert.match(deck, /\{#if drawerOpen\}\n\t\t<ProductionDrawer anchor=\{deckEl\} toggle=\{chipEl\} \{clips\} \{engineTip\} onclose=\{\(\) => \(drawerOpen = false\)\} \/>\n\t\{\/if\}/);
	assert.match(deck, /<div bind:this=\{deckEl\} class="vp-deck" role="region"/);
	const more = deck.slice(deck.indexOf('{#if moreOpen}'), deck.indexOf('{#if drawerOpen}'));
	assert.match(more, /role="menu" aria-label=\{t\('production\.more'\)\}/);
	assert.equal((more.match(/role="menuitem"/g) ?? []).length, 3);
	assert.match(more, /fromMore\(openResults\)/);
	assert.match(more, /fromMore\(\(\) => setTimeout\(openQueue\)\)/);
	assert.match(more, /fromMore\(openFinalPass\)/);
	for (const gone of ['engineSelect', 'profilePicker', 'marginField', 'ownShots', '@render', 'engine-more']) assert.doesNotMatch(deck, new RegExp(gone), gone);
});

test('drawer: it is a modal layer of 440 px over the deck that Escape, the Close button and a pointer outside close, with the focus trapped and given back', () => {
	const drawer = source('../components/production/ProductionDrawer.svelte');
	assert.match(drawer, /let \{ anchor, toggle = null, clips = \[\], engineTip = '', onclose \} = \$props\(\);/);
	assert.match(drawer, /layer = openLayer\(dialog, \{ refocus: initialFocus, close: onclose \}\);/);
	assert.match(drawer, /closeLayer\(layer\);/);
	assert.match(drawer, /if \(e\.key === 'Escape'\) \{\n\t\t\te\.preventDefault\(\);\n\t\t\te\.stopPropagation\(\);\n\t\t\tcloseTopLayer\(\);/);
	assert.match(drawer, /tabTarget\(\{ shift: e\.shiftKey, list: focusables\(dialog\), active: document\.activeElement, inside: dialog\.contains\(document\.activeElement\) \}\)/);
	assert.match(drawer, /document\.addEventListener\('pointerdown', outside, true\);/);
	assert.match(drawer, /drawerCloses\(\{ target: e\.target, dialog, toggle, top: isTopLayer\(layer\) \}\)/);
	assert.match(drawer, /if \(e\.target === backdrop\) e\.preventDefault\(\);/);
	assert.match(drawer, /drawerPlace\(\{ deck: anchor\.getBoundingClientRect\(\), root: anchor\.closest\('\.vp-root'\)\?\.getBoundingClientRect\(\) \?\? null \}\)/);
	assert.match(drawer, /class="vp-deck-backdrop" role="presentation"/);
	assert.match(drawer, /class="vp-deck-drawer"\n\trole="dialog"\n\taria-modal="true"\n\taria-label=\{t\('production\.drawer\.title'\)\}\n\ttabindex="-1"/);
	assert.match(drawer, /<h2>\{t\('production\.drawer\.title'\)\}<span class="vp-deck-drawer-sub"> \{t\('production\.drawer\.subtitle'\)\}<\/span><\/h2>/);
	assert.match(drawer, /class="vp-deck-drawer-close" aria-label=\{t\('production\.drawer\.close'\)\} onclick=\{onclose\}/);
	assert.match(drawer, /withSendings\(\(\) => act\(\(\) => \(doc\.direction\.mode = m\)\)\)/);
	assert.match(drawer, /act\(\(\) => setReferenceMargin\(doc\.engine, value\)\)/);
	assert.match(drawer, /onchange=\{\(e\) => selectEngine\(e\.currentTarget\.value\)\}/);
	assert.match(drawer, /\{#if rows\.includes\('own'\)\}\n\t\t\t\t<p class="vp-deck-drawer-help">\{t\('production\.drawer\.own', \{ count: own \}\)\}<\/p>/);
	assert.match(drawer, /\{t\('production\.editEngine'\)\}\{#if setCount\}<span class="vp-deck-badge vp-tc ml-1\.5">\{setCount\}<\/span>\{\/if\}/);
	const page = source('../VideoProducerPage.svelte');
	for (const rule of ['vp-deck-backdrop', 'vp-deck-drawer', 'vp-deck-drawer-header', 'vp-deck-drawer-body', 'vp-deck-drawer-close', 'vp-deck-drawer-grid', 'vp-deck-drawer-label', 'vp-deck-drawer-row', 'vp-deck-drawer-hint', 'vp-deck-drawer-help']) {
		assert.match(page, new RegExp(`\\.vp-root \\.${rule}\\b`), rule);
	}
	assert.match(page, /@keyframes vp-deck-drawer-in/);
	assert.match(page, /\.vp-root \.vp-deck-drawer \{ position: absolute; right: 0; bottom: 100%;/);
	assert.match(page, /\.vp-root \.vp-deck-drawer-header \{ height: 56px;/);
	assert.match(page, /\.vp-root \.vp-deck-backdrop \{ position: absolute; left: 0; right: 0; bottom: calc\(100% \+ 1px\); background: rgb\(var\(--scrim\) \/ \.32\);/);
});

test('drawer: the chip reads the same engine, profile, size and drafts the drawer writes', () => {
	const deck = source('../components/production/ProductionDeck.svelte');
	assert.match(deck, /const chip = \$derived\(deckChip\(\{ engine: engine \? \(cloud \? engine\.label : presetLabel\(engine\.info\)\) : groups\.length \? engineLabel\(\) : t\('generation\.engine\.none'\), profile: showProfile \? doc\.direction\.mode : '', size: sizes \? \(p\.quality === 'draft' \? draftRes : finalRes\) : '', drafts: clips\.length \? sharedDrafts\(clips, doc\.engine\) : 1 \}, t\)\);/);
	assert.match(deck, /const showProfile = \$derived\(profileItems\.length > 1 \|\| profileControl\(\{ items: profileItems, current: doc\.direction\.mode \}\) === 'popup'\);/);
	assert.match(deck, /chosenSize\(doc, engine\?\.preset, 'draft'\)/);
	assert.match(deck, /chosenSize\(doc, engine\?\.preset, 'final'\)/);
	assert.deepEqual(deckChip({ engine: 'MiniMax H3', profile: 'Ref2VA', size: '1344×768', drafts: 3 }, t), ['MiniMax H3', 'Ref2VA', '1344×768', 'production.deck.drafts{"count":3}']);
	assert.deepEqual(deckChip({ engine: 'MiniMax H3', profile: '', size: '832×480', drafts: null }, t), ['MiniMax H3', '832×480', 'production.deck.draftsMixed']);
});

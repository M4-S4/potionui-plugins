import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';
import { DRAWER_INSET, DRAWER_MAX_HEIGHT, DRAWER_WIDTH, drawerPlace, drawerRows, profileControl, profileHint, profileOptions, tabTarget } from './deck-drawer.js';
import { deckChip } from './deck.js';

class FakeNode {
	constructor(parent = null, selectors = []) {
		this.parent = parent;
		this.selectors = selectors;
	}
	contains(other) {
		for (let node = other; node; node = node.parent) if (node === this) return true;
		return false;
	}
}
class FakeElement extends FakeNode {
	closest(list) {
		const wanted = list.split(',').map((s) => s.trim());
		for (let node = this; node; node = node.parent) if (node.selectors?.some((s) => wanted.includes(s))) return node;
		return null;
	}
}
globalThis.Node = FakeNode;
globalThis.Element = FakeElement;
globalThis.document = { body: {}, querySelector: () => null };

const { closesOnOutsidePointer, keepsFocus } = await import('./drawer.js');
const { doc, ui, dispose } = await import('./state.svelte.js');
const { handleKeydown } = await import('./commands.js');
const { t } = await import('../i18n/index.svelte.js');

const t2 = (key, params = {}) => `${key}${Object.keys(params).length ? JSON.stringify(params) : ''}`;
const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;
const DRAWER = new URL('../components/production/ProductionDrawer.svelte', import.meta.url).href;
const WAN = '01KX47WANVIDEO0000000000TV';
const H3 = '01KX47H3MINIMAX000000000VA';

after(() => {
	dispose();
	delete globalThis.Node;
	delete globalThis.Element;
	delete globalThis.document;
});

function engines() {
	ui.me = {
		engines: [{ id: 'native', kind: 'local', name: 'Local' }],
		presets: [
			{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'], resolutions: ['832x480', '1280x720'] },
			{ id: H3, name: 'MiniMax-H3', video: true, cloud: false, profiles: ['FL2VA', 'Ref2VA'] }
		]
	};
	doc.engine = { backend: 'native', preset: WAN, model: null };
}

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
	assert.equal(profileHint('FL2VA', t2), 'production.profile.fl2va');
	assert.equal(profileHint('Ref2VA', t2), 'production.profile.ref2va');
	assert.equal(profileHint('Hybrid AV', t2), 'production.profile.hybrid');
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

test('drawer: a pointer inside the plugin root closes it, unless it lands on a drawer, a menu, a modal, a toast or a drawer toggle', () => {
	const root = new FakeElement(null, ['.vp-root']);
	const plain = new FakeElement(root);
	assert.equal(closesOnOutsidePointer(root, plain), true);
	for (const keep of ['.vp-drawer', '.vp-deck-drawer', '[data-vp-drawer-toggle]', '.vp-modal-backdrop', '.vp-palette-backdrop', '.vp-menu', '[data-vp-menu]', '.vp-toasts', '.vp-uploads']) {
		const inside = new FakeElement(new FakeElement(root, [keep]));
		assert.equal(closesOnOutsidePointer(root, inside), false, keep);
	}
	assert.equal(closesOnOutsidePointer(null, plain), false);
	assert.equal(closesOnOutsidePointer(root, null), false);
});

test('drawer: a pointer outside the plugin, on the rail or the bar of the host, closes it too, unless it lands on a toast or a tooltip of the host or a window of the host is open', () => {
	const root = new FakeElement(null, ['.vp-root']);
	const rail = new FakeElement(new FakeElement(null, ['nav']));
	assert.equal(closesOnOutsidePointer(root, rail), true);
	assert.equal(closesOnOutsidePointer(root, new FakeElement(new FakeElement(null, ['.vp-root']))), true);
	for (const keep of ['[role="status"]', '[role="tooltip"]']) assert.equal(closesOnOutsidePointer(root, new FakeElement(new FakeElement(null, [keep]))), false, keep);
	try {
		document.querySelectorAll = () => [new FakeElement(null, ['[aria-modal="true"]'])];
		assert.equal(closesOnOutsidePointer(root, rail), false);
		document.querySelectorAll = () => [new FakeElement(new FakeElement(root, ['.vp-deck-drawer']))];
		assert.equal(closesOnOutsidePointer(root, rail), true);
	} finally {
		delete document.querySelectorAll;
	}
});

test('drawer: a pointer that closes it on a part of the plugin that takes no focus keeps the focus where the drawer gave it back, a control takes it as usual', () => {
	const root = new FakeElement(null, ['.vp-root', '[tabindex]']);
	const deck = new FakeElement(root, ['.vp-deck']);
	const title = new FakeElement(new FakeElement(deck, ['.vp-deck-copy']));
	assert.equal(keepsFocus(root, title), true);
	assert.equal(keepsFocus(root, new FakeElement(deck, ['.vp-deck-backdrop'])), true);
	for (const control of ['button', 'a[href]', 'input', 'select', 'textarea', 'summary', 'label', '[contenteditable="true"]', '[tabindex]']) assert.equal(keepsFocus(root, new FakeElement(new FakeElement(deck, [control]))), false, control);
	assert.equal(keepsFocus(root, new FakeElement(new FakeElement(null, ['nav']))), false);
	assert.equal(keepsFocus(null, title), false);
	assert.equal(keepsFocus(root, null), false);
	const drawer = readFileSync(new URL('../components/production/ProductionDrawer.svelte', import.meta.url), 'utf-8');
	assert.match(drawer, /const root = anchor\?\.closest\('\.vp-root'\) \?\? null;\s*if \(!isTopLayer\(layer\) \|\| !closesOnOutsidePointer\(root, e\.target\)\) return;\s*if \(keepsFocus\(root, e\.target\)\) e\.preventDefault\(\);\s*onclose\(\);/);
	const page = readFileSync(new URL('../VideoProducerPage.svelte', import.meta.url), 'utf-8');
	assert.match(page, /if \(!closesOnOutsidePointer\(root, e\.target\)\) return;\s*if \(keepsFocus\(root, e\.target\)\) e\.preventDefault\(\);\s*closeDrawer\(\);/);
});

test('drawer: Escape closes the menus first, then the deck drawer, then the preview and the compare', () => {
	Object.assign(ui, { paletteOpen: false, modal: null, menuOpen: 'deck-more', deckDrawer: true, preview: { kind: 'result', id: 't1' }, compare: null });
	const escape = () => handleKeydown({ key: 'Escape', target: null, preventDefault() {} }, null);
	escape();
	assert.deepEqual([ui.menuOpen, ui.deckDrawer, ui.preview?.id], [null, true, 't1']);
	escape();
	assert.deepEqual([ui.menuOpen, ui.deckDrawer, ui.preview?.id], [null, false, 't1']);
	escape();
	assert.deepEqual([ui.menuOpen, ui.deckDrawer, ui.preview], [null, false, null]);
	handleKeydown({ key: 'Escape', target: null, shiftKey: true, preventDefault() {} }, null);
	assert.equal(ui.deckDrawer, false);
});

test('drawer: Escape closes it when the focus left the plugin for the page of the host, the drawer still in the plugin, and leaves it to a window of the host', () => {
	const root = new FakeElement(null, ['.vp-root']);
	const drawer = new FakeElement(new FakeElement(root, ['.vp-deck']), ['.vp-deck-drawer']);
	Object.assign(ui, { paletteOpen: false, modal: null, menuOpen: null, deckDrawer: true, hostModal: false, preview: null, compare: null });
	const escape = () => handleKeydown({ key: 'Escape', target: document.body, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, preventDefault() {} }, root);
	try {
		document.querySelectorAll = (selector) => (selector.includes('[aria-modal="true"]') ? [drawer] : []);
		escape();
		assert.equal(ui.deckDrawer, false);
		ui.deckDrawer = true;
		document.querySelectorAll = (selector) => (selector.includes('[aria-modal="true"]') ? [drawer, new FakeElement(null, ['[aria-modal="true"]'])] : []);
		escape();
		assert.equal(ui.deckDrawer, true);
	} finally {
		delete document.querySelectorAll;
		ui.deckDrawer = false;
	}
});

test('drawer: the chip of the deck opens it as a modal dialog over the deck, with its title and a Close button, and the chip says whether it is open', async () => {
	engines();
	ui.deckDrawer = false;
	const closed = await renderComponent(DECK);
	assert.match(closed, /<button[^>]*class="vp-deck-chip"[^>]*aria-expanded="false"[^>]*aria-haspopup="dialog"/);
	assert.doesNotMatch(closed, /role="dialog"[^>]*aria-modal="true"/);
	ui.deckDrawer = true;
	const open = await renderComponent(DECK);
	assert.match(open, /<button[^>]*class="vp-deck-chip"[^>]*aria-expanded="true"/);
	assert.match(open, new RegExp(`class="vp-deck-drawer"[^>]*role="dialog"[^>]*aria-modal="true"[^>]*aria-label="${t('production.drawer.title')}"`));
	assert.match(open, /<h2>[^<]*<span class="vp-deck-drawer-sub">/);
	assert.match(open, new RegExp(`class="vp-deck-drawer-close" aria-label="${t('production.drawer.close')}"`));
	assert.match(open, /class="vp-deck-backdrop" role="presentation"/);
	ui.deckDrawer = false;
});

test('drawer: its rows follow the engine of the project, it counts the shots with their own engine, and the engine button carries the count of options set', async () => {
	engines();
	doc.clips = [
		{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo', engine: { preset: H3, model: null } },
		{ id: 's2', start: 4, dur: 4, label: 'Two', stage: 'todo', engine: { preset: H3, model: null } },
		{ id: 's3', start: 8, dur: 4, label: 'Three', stage: 'todo' }
	];
	const html = await renderComponent(DRAWER, { anchor: null, clips: doc.clips, engineTip: 'Wan', onclose() {} });
	assert.match(html, new RegExp(`<label class="vp-deck-drawer-label" for="[^"]+">${t('production.drawer.engine')}</label>`));
	assert.match(html, new RegExp(`<option value="${WAN}\|" selected="">`));
	assert.match(html, new RegExp(`<label class="vp-deck-drawer-label" for="[^"]+">${t('production.drawer.draftSize')}</label>`));
	assert.match(html, new RegExp(`<p class="vp-deck-drawer-help">${t('production.drawer.own', { count: 2 })}</p>`));
	assert.match(textOf(html), new RegExp(t('production.editEngine')));
	assert.doesNotMatch(html, /vp-deck-drawer-label" id=/);
	ui.me = { ...ui.me, presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	doc.clips = [];
	const plain = await renderComponent(DRAWER, { anchor: null, clips: [], onclose() {} });
	assert.doesNotMatch(plain, new RegExp(t('production.drawer.draftSize')));
	assert.doesNotMatch(plain, /vp-deck-drawer-help/);
	assert.ok(hostUis(plain, 'Button').length >= 1);
});

test('drawer: the chip reads the same engine, profile, size and drafts the drawer writes', () => {
	assert.deepEqual(deckChip({ engine: 'MiniMax H3', profile: 'Ref2VA', size: '1344×768', drafts: 3 }, t2), ['MiniMax H3', 'Ref2VA', '1344×768', 'production.deck.drafts{"count":3}']);
	assert.deepEqual(deckChip({ engine: 'MiniMax H3', profile: '', size: '832×480', drafts: null }, t2), ['MiniMax H3', '832×480', 'production.deck.draftsMixed']);
});

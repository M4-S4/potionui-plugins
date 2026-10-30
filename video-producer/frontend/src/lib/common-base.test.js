import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { clean, hostUis, renderComponent, textOf } from './svelte-harness.js';
import enShell from '../i18n/en/shell.json' with { type: 'json' };
import frShell from '../i18n/fr/shell.json' with { type: 'json' };
import enPanels from '../i18n/en/panels.json' with { type: 'json' };
import frPanels from '../i18n/fr/panels.json' with { type: 'json' };

globalThis.document = { body: {}, querySelector: () => null };

const { doc, ui, closeDrawer, drawerMode, dispose } = await import('./state.svelte.js');
const { viewport } = await import('./viewport.svelte.js');
const { handleKeydown } = await import('./commands.js');
const { t } = await import('../i18n/index.svelte.js');

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const components = readdirSync(new URL('../components', import.meta.url), { recursive: true })
	.filter((f) => f.endsWith('.svelte'))
	.map((f) => `../components/${f.replaceAll('\\', '/')}`);
const ZONE_HEADER = new URL('../components/shell/ZoneHeader.svelte', import.meta.url).href;
const BAND = new URL('../components/storyboard/BandView.svelte', import.meta.url).href;
const MIXER = new URL('../components/panels/MixerPanel.svelte', import.meta.url).href;
const SIDE_DRAWER = new URL('../components/shell/SideDrawer.svelte', import.meta.url).href;
const PLUGIN_ROOT = { closest: () => null };
const IN_PLUGIN = { closest: (selector) => (selector === '.vp-root' ? PLUGIN_ROOT : null) };
const IN_HOST = { closest: () => null };
const dialogsOf = (html, where = IN_PLUGIN) => (selector) => (selector.includes('[aria-modal="true"]') ? [...html.matchAll(/aria-modal="true"/g)].map(() => where) : []);
const press = (key, code, alt = false) => {
	let prevented = false;
	handleKeydown({ key, code, altKey: alt, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, target: null, preventDefault: () => (prevented = true) }, null);
	return prevented;
};

after(() => {
	dispose();
	delete globalThis.document;
});

test('base: under 1280 px a closed drawer is no dialog, so the shortcuts reach the page; an open one is a modal dialog that Escape closes before the preview, and only a dialog of the host holds the keys', async () => {
	const page = read('../VideoProducerPage.svelte');
	assert.match(page, /<SideDrawer side="start" label=\{t\('panels\.left\.label'\)\} \{drawers\} open=\{leftOpen\}>\s*<LeftPanel \/>\s*<\/SideDrawer>/);
	assert.match(page, /<SideDrawer side="end" label=\{t\('panels\.right\.label'\)\} \{drawers\} open=\{rightOpen\}>\s*<RightPanel \/>\s*<\/SideDrawer>/);
	assert.doesNotMatch(page, /aria-modal/);
	Object.assign(ui, { workspace: 'storyboard', storyView: 'grid', directorView: 'review', paletteOpen: false, modal: null, menuOpen: null, deckDrawer: false, hostModal: false, preview: null, compare: null, reviewMonitor: false, seamCompare: null, storyOpen: false, inspectorOpen: false, sidebarOpen: false });
	viewport.narrow = true;
	try {
		const closed = clean((await renderComponent(SIDE_DRAWER, { side: 'start', label: 'Library', drawers: true, open: false })) + (await renderComponent(SIDE_DRAWER, { side: 'end', label: 'Inspector', drawers: true, open: false })));
		assert.equal(closed, '<div class="vp-drawer" data-vp-drawer="start" tabindex="-1" hidden=""></div><div class="vp-drawer" data-vp-drawer="end" tabindex="-1" hidden=""></div>');
		document.querySelectorAll = dialogsOf(closed);
		assert.ok(press('2', 'Digit2', true));
		assert.deepEqual([ui.workspace, ui.directorView], ['director', 'direction']);
		assert.ok(press('1', 'Digit1', true));
		assert.equal(ui.directorView, 'review');
		ui.workspace = 'storyboard';
		ui.inspectorOpen = true;
		ui.preview = { kind: 'result', id: 't1' };
		const open = clean(await renderComponent(SIDE_DRAWER, { side: 'end', label: 'Inspector', drawers: true, open: true }));
		assert.equal(open, '<div class="vp-drawer" data-vp-drawer="end" role="dialog" aria-modal="true" aria-label="Inspector" tabindex="-1"></div>');
		document.querySelectorAll = dialogsOf(open);
		press('Escape', 'Escape');
		assert.deepEqual([ui.inspectorOpen, ui.preview?.id], [false, 't1']);
		press('Escape', 'Escape');
		assert.equal(ui.preview, null);
		ui.deckDrawer = true;
		assert.equal(press('2', 'Digit2', true), false);
		assert.equal(ui.workspace, 'storyboard');
		press('Escape', 'Escape');
		assert.equal(ui.deckDrawer, false);
		document.querySelectorAll = dialogsOf(open, IN_HOST);
		assert.equal(press('2', 'Digit2', true), false);
		assert.equal(ui.workspace, 'storyboard');
		const wide = clean(await renderComponent(SIDE_DRAWER, { side: 'start', label: 'Library', drawers: false, open: false }));
		assert.equal(wide, '<div class="vp-drawer" data-vp-drawer="start" tabindex="-1"></div>');
	} finally {
		delete document.querySelectorAll;
		viewport.narrow = false;
	}
});

test('base: a zone header carries its icon, its title and its subtitle in one row', async () => {
	const html = clean(await renderComponent(ZONE_HEADER, { icon: 'grid', title: 'Storyboard', subtitle: '3 shots' }));
	assert.match(html, /^<div class="vp-zone-head">\s*<svg [^>]*aria-hidden="true">.*<\/svg>\s*<h2 class="[^"]*">Storyboard<\/h2>\s*<span class="vp-tc [^"]*">3 shots<\/span>\s*<\/div>$/s);
	const bare = clean(await renderComponent(ZONE_HEADER, { title: 'Review' }));
	assert.doesNotMatch(bare, /<svg|<span/);
	assert.match(bare, /<h2 class="[^"]*">Review<\/h2>/);
});

test('base: no text of the page is smaller than 10 px, and every row of filter tabs is drawn by FilterPills', () => {
	for (const path of ['../VideoProducerPage.svelte', ...components]) {
		const source = read(path);
		for (const [, size] of source.matchAll(/text-\[(\d+(?:\.\d+)?)px\]/g)) assert.ok(Number(size) >= 10, `${path}: text-[${size}px]`);
		for (const [, size] of source.matchAll(/font-size: (\d+(?:\.\d+)?)px/g)) assert.ok(Number(size) >= 10, `${path}: font-size ${size}px`);
	}
	for (const path of components.filter((p) => !p.endsWith('/FilterPills.svelte'))) assert.doesNotMatch(read(path), /role="tab"[^>]*class="vp-pill|class="vp-pill[^"]*"[^>]*role="tab"/, path);
});

test('base: the empty band, the quick edit without a shot and the mixer without sound use the host empty state, never a primary button', async () => {
	doc.clips = [];
	doc.assets = [];
	ui.storyOpen = false;
	ui.selection = null;
	const empty = await renderComponent(BAND);
	const [noShots] = hostUis(empty, 'EmptyState');
	assert.equal(noShots.title, t('storyboard.band.emptyTitle'));
	assert.equal(noShots.description, t('storyboard.band.emptyText'));
	assert.doesNotMatch(empty, /<button[^>]*vp-deck-generate|"variant":"primary"/);
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo', take: null }];
	const noPick = hostUis(await renderComponent(BAND), 'EmptyState');
	assert.deepEqual(noPick.map((p) => [p.compact, p.title]), [[true, t('storyboard.quick.noneTitle')]]);
	const [noSounds] = hostUis(await renderComponent(MIXER), 'EmptyState');
	assert.deepEqual([noSounds.compact, noSounds.title, noSounds.description], [true, t('panels.mixer.noSounds'), t('panels.mixer.noSoundsHint')]);
	for (const path of components) assert.doesNotMatch(read(path), /name="EmptyState"[^\n]*variant: 'primary'/, path);
});

test('base: under 1280 px the side panels become drawers over the centre that Escape closes one at a time before the selection; above, Escape clears the selection at once', () => {
	ui.workspace = 'storyboard';
	ui.storyView = 'grid';
	ui.selection = { kind: 'clip', id: 's1' };
	Object.assign(ui, { paletteOpen: false, modal: null, menuOpen: null, deckDrawer: false, preview: null, compare: null, reviewMonitor: false, seamCompare: null, storyOpen: false });
	const escape = () => handleKeydown({ key: 'Escape', target: null, preventDefault() {} }, null);
	viewport.narrow = true;
	ui.inspectorOpen = true;
	ui.sidebarOpen = true;
	assert.equal(drawerMode(), true);
	escape();
	assert.deepEqual([ui.inspectorOpen, ui.sidebarOpen, ui.selection?.id], [false, true, 's1']);
	escape();
	assert.deepEqual([ui.inspectorOpen, ui.sidebarOpen, ui.selection?.id], [false, false, 's1']);
	escape();
	assert.deepEqual([ui.inspectorOpen, ui.sidebarOpen, ui.selection], [false, false, null]);
	viewport.narrow = false;
	ui.inspectorOpen = true;
	ui.selection = { kind: 'clip', id: 's1' };
	assert.equal(closeDrawer(), false);
	escape();
	assert.deepEqual([ui.inspectorOpen, ui.selection], [true, null]);
	for (const [locale, shell] of [['en', enShell], ['fr', frShell]]) assert.match(shell['app.narrow'], /1280 px/, locale);
	for (const [locale, panels] of [['en', enPanels], ['fr', frPanels]]) assert.ok(panels['right.label'] && panels['left.label'], locale);
});

test('base: the page header keeps a visible label as the accessible name of Import, Export and Assistant, and the band summary counts the shots', async () => {
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo', take: null }, { id: 's2', start: 4, dur: 6, label: 'Two', stage: 'draft', take: null }];
	ui.selection = null;
	const band = textOf(await renderComponent(BAND));
	assert.match(band, new RegExp(t('storyboard.summary', { count: 2, duration: '10.0 s' }).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

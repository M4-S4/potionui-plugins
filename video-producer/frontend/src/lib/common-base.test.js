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

after(() => {
	dispose();
	delete globalThis.document;
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

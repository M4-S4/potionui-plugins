import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const components = readdirSync(new URL('../components', import.meta.url), { recursive: true })
	.filter((f) => f.endsWith('.svelte'))
	.map((f) => `../components/${f.replaceAll('\\', '/')}`);
const page = read('../VideoProducerPage.svelte');
const rule = (selector) => page.match(new RegExp(`\\.vp-root ${selector.replace(/[.[\]()'=>]/g, '\\$&')} \\{([^}]*)\\}`))?.[1] ?? '';

test('base: the underlined tabs are 40 px high like every area header, and the Inspector carries its tabs in its header', () => {
	assert.match(rule('.vp-tabs'), /height: 2\.5rem;/);
	assert.match(rule(".vp-tabs > [role='tab']"), /align-self: stretch;/);
	assert.doesNotMatch(rule(".vp-tabs > [role='tab']"), /(?<![-\w])height:/);
	assert.match(rule('.vp-tabs.vp-tabs-head'), /height: 100%;[\s\S]*border-bottom: 0;[\s\S]*padding: 0;/);
	assert.match(rule('.vp-panel-head'), /height: 2\.5rem;/);
	assert.match(rule('.vp-zone-head'), /height: 2\.5rem;[\s\S]*gap: 0\.75rem;[\s\S]*border-bottom: 1px solid rgb\(var\(--line\)\);[\s\S]*padding: 0 1rem;/);
	const inspector = read('../components/inspector/Inspector.svelte');
	assert.match(inspector, /<div class="vp-panel-head border-b border-line">\n\t\t\{#if item && s\.kind === 'clip'\}\n\t\t\t<Tabs\n\t\t\t\tlabel=\{t\('inspector\.tabs'\)\}\n\t\t\t\tclass="vp-tabs-head"/);
});

test('base: the centre areas share one header template, icon, title and counter on the left', () => {
	for (const path of ['../components/director/ReviewView.svelte', '../components/director/DirectionView.svelte', '../components/director/BibleView.svelte', '../components/references/ReferenceBoard.svelte', '../components/storyboard/BandView.svelte', '../components/storyboard/StoryboardView.svelte', '../components/mixer/Console.svelte']) {
		const source = read(path);
		assert.match(source, /import ZoneHeader from '\.\.\/shell\/ZoneHeader\.svelte';/, path);
		assert.match(source, /<ZoneHeader [^>]*title=/, path);
		assert.doesNotMatch(source, /class="flex h-10 shrink-0 items-center gap-[23] border-b border-line px-[24]"/, path);
	}
	const header = read('../components/shell/ZoneHeader.svelte');
	assert.match(header, /<div class="vp-zone-head">\n\t\{@render lead\?\.\(\)\}\n\t\{#if icon\}<Icon name=\{icon\} class="h-4 w-4 shrink-0 text-fg-muted" \/>\{\/if\}\n\t<h2 class="shrink-0 whitespace-nowrap text-sm font-semibold">\{title\}<\/h2>/);
});

test('base: every filter is one row of pills with their count, drawn by one component', () => {
	const pills = read('../components/shell/FilterPills.svelte');
	assert.match(pills, /class="no-scrollbar flex min-w-0 items-center gap-1 overflow-x-auto p-1 \{className\}" role="tablist"/);
	assert.match(pills, /\{#if item\.count != null\}<span class="vp-tc text-2xs text-fg-subtle">\{item\.count\}<\/span>\{\/if\}/);
	for (const path of ['../components/panels/MediaBrowser.svelte', '../components/references/ReferenceBoard.svelte', '../components/director/ReviewView.svelte', '../components/mixer/Console.svelte']) {
		const source = read(path);
		assert.match(source, /<FilterPills /, path);
		assert.match(source, /count: /, path);
	}
	for (const path of components.filter((p) => !p.endsWith('/FilterPills.svelte'))) assert.doesNotMatch(read(path), /role="tab"[^>]*class="vp-pill|class="vp-pill[^"]*"[^>]*role="tab"/, path);
	assert.doesNotMatch(read('../components/panels/MediaBrowser.svelte'), /flex flex-wrap gap-1" role="tablist"/);
});

test('base: no text of the page is smaller than 10 px', () => {
	for (const path of ['../VideoProducerPage.svelte', ...components]) {
		const source = read(path);
		for (const [, size] of source.matchAll(/text-\[(\d+(?:\.\d+)?)px\]/g)) assert.ok(Number(size) >= 10, `${path}: text-[${size}px]`);
		for (const [, size] of source.matchAll(/font-size: (\d+(?:\.\d+)?)px/g)) assert.ok(Number(size) >= 10, `${path}: font-size ${size}px`);
	}
	assert.match(read('../components/storyboard/BandLanes.svelte'), /text-left text-2xs font-semibold leading-\[10px\]/);
});

test('base: the empty band, the quick edit without a shot and the mixer without sound use the host empty state, never a primary button', () => {
	const band = read('../components/storyboard/BandView.svelte');
	assert.match(band, /<HostUi name="EmptyState" props=\{noShots\} \/>/);
	assert.match(band, /<HostUi name="EmptyState" props=\{noPick\} \/>/);
	assert.match(band, /\{ variant: 'secondary', icon: hostIconName\('wand'\), onclick: openCut, children: t\('storyboard\.story\.title'\) \},\n\t\t\t\t\{ variant: 'ghost', icon: 'plus', onclick: \(\) => addShot\(\), children: t\('storyboard\.addShot'\) \}/);
	assert.doesNotMatch(band, /variant: 'primary'/);
	assert.doesNotMatch(band, /<p class="flex h-full items-center justify-center/);
	const mixer = read('../components/panels/MixerPanel.svelte');
	assert.match(mixer, /\{#if !sounds\.length\}\n\t\t<HostUi name="EmptyState" props=\{noneProps\} \/>/);
	assert.doesNotMatch(mixer, /<p [^>]*>\{t\('panels\.mixer\.noSounds'\)\}/);
	for (const path of components) assert.doesNotMatch(read(path), /name="EmptyState"[^\n]*variant: 'primary'/, path);
	const helper = read('./empty.js');
	assert.match(helper, /mountHostSlot\(row\.appendChild\(document\.createElement\('div'\)\), 'Button', \{ size: 'xs', \.\.\.props \}\)/);
});

test('base: the band zooms with the controls of the timeline, and its Synopsis toggle is a ghost button', () => {
	const band = read('../components/storyboard/BandView.svelte');
	const timeline = read('../components/timeline/Timeline.svelte');
	for (const source of [band, timeline]) {
		assert.match(source, /icon: 'minus', label: t\('timeline\.zoomOut'\), size: 'sm', class: 'vp-h7'/);
		assert.match(source, /icon: 'plus', label: t\('timeline\.zoomIn'\), size: 'sm', class: 'vp-h7'/);
		assert.match(source, /<input class="vp-slider w-24" type="range" min="8" max="220" bind:value=\{ui\.pxPerSec\}/);
	}
	assert.match(band, /<button type="button" class="vp-toggle flex h-7 items-center gap-1\.5 rounded px-2 text-xs font-medium text-fg-muted hover:bg-surface-2 hover:text-fg" aria-pressed=\{ui\.storyOpen\}/);
	assert.doesNotMatch(band, /shadow-\[inset/);
});

test('base: the transport keeps its time controls centred and drops the volume slider before anything overlaps', () => {
	const viewer = read('../components/viewer/Viewer.svelte');
	assert.match(viewer, /style:grid-template-columns="minmax\(0, 1fr\) auto minmax\(max-content, 1fr\)"/);
	assert.match(viewer, /<div class="flex min-w-0 items-center gap-2 overflow-hidden" bind:clientWidth=\{sideW\}>/);
	assert.match(viewer, /\{#if sideW >= 136\}<input class="vp-slider w-24 shrink-0" type="range"/);
	assert.doesNotMatch(viewer, /grid-cols-\[1fr_auto_1fr\]/);
});

test('base: Media, the Sounds panel and the console import with the same two icon buttons', () => {
	const buttons = read('../components/panels/ImportButtons.svelte');
	assert.match(buttons, /icon: 'folder', label: t\('panels\.media\.import'\), size: 'sm', class: 'vp-h7', tooltip: t\('panels\.media\.importTip'\), kbd: key\('import'\), onclick: \(\) => openImport\(kind\)/);
	assert.match(buttons, /icon: 'upload', label: t\('panels\.media\.importLocal'\), size: 'sm', class: 'vp-h7', tooltip: t\('panels\.media\.importLocalTip'\), kbd: key\('import-local'\), onclick: \(\) => openLocalImport\(kind\)/);
	assert.match(read('../components/panels/MediaBrowser.svelte'), /<PanelHeader icon="image"[^>]*>\n\t\t<ImportButtons \/>\n\t<\/PanelHeader>/);
	assert.match(read('../components/panels/MixerPanel.svelte'), /<PanelHeader icon="music" title=\{t\('panels\.mixer\.sounds'\)\}[^>]*>\n\t<ImportButtons kind="audio" \/>\n<\/PanelHeader>/);
	assert.match(read('../components/mixer/Console.svelte'), /<ImportButtons kind="audio" \/>/);
	for (const path of ['../components/panels/MixerPanel.svelte', '../components/mixer/Console.svelte']) assert.doesNotMatch(read(path), /name="Button" props=\{\{ variant: 'ghost', size: 'xs', icon: '(folder|upload)'/, path);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { shadeOf } from './scrollshade.js';
import { popoverPosition } from './popover.js';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const page = read('../VideoProducerPage.svelte');
const rule = (selector) => page.match(new RegExp(`\\.vp-root ${selector.replace(/[.[\]()'=>]/g, '\\$&')} \\{([^}]*)\\}`))?.[1] ?? '';

test('overflow: a row of pills that scrolls fades the side it hides, and the wheel scrolls it sideways', () => {
	assert.equal(shadeOf(0, 300, 300), 'none');
	assert.equal(shadeOf(0, 300, 301), 'none');
	assert.equal(shadeOf(0, 300, 500), 'end');
	assert.equal(shadeOf(200, 300, 500), 'start');
	assert.equal(shadeOf(100, 300, 500), 'both');
	const action = read('scrollshade.js');
	assert.match(action, /node\.setAttribute\('data-shade', shadeOf\(node\.scrollLeft, node\.clientWidth, node\.scrollWidth\)\)/);
	assert.match(action, /if \(node\.scrollWidth <= node\.clientWidth \|\| Math\.abs\(event\.deltaY\) <= Math\.abs\(event\.deltaX\)\) return;\n\t\tnode\.scrollLeft \+= event\.deltaY;\n\t\tevent\.preventDefault\(\);/);
	assert.match(read('../components/shell/FilterPills.svelte'), /<div class="vp-pills no-scrollbar flex min-w-0 items-center gap-1 overflow-x-auto p-1 \{className\}" role="tablist" aria-label=\{label\} use:scrollShade>/);
	for (const shade of ['end', 'start', 'both']) assert.match(rule(`.vp-pills[data-shade='${shade}']`), /mask-image: linear-gradient\(to right, /, shade);
});

test('overflow: the menus of the menu bar grow to their longest label on one line, with the shortcut at the right', () => {
	const menubar = read('../components/shell/MenuBar.svelte');
	assert.match(menubar, /<div class="vp-menu vp-menu-list top-7 left-0" role="menu"/);
	assert.match(menubar, /<span class="vp-menu-label flex-1">\{item\.label\}<\/span>\n\t+\{#if item\.key\}<span class="vp-menu-key">\{item\.key\}<\/span>\{\/if\}/);
	assert.match(rule('.vp-menu.vp-menu-list'), /width: max-content;[\s\S]*max-width: calc\(100vw - 1rem\);/);
	assert.match(rule('.vp-menu-label'), /white-space: nowrap;/);
	assert.match(rule('.vp-menu-key'), /white-space: nowrap;/);
});

test('overflow: the warning of the production deck keeps its whole text, on two lines at most and in its tooltip, and names itself for a screen reader, with the count of warnings', () => {
	assert.match(read('../components/shell/InfoTip.svelte'), /aria-label=\{label \|\| undefined\} aria-describedby=\{id\}/);
	const deck = read('../components/production/ProductionDeck.svelte');
	assert.match(deck, /const noticeLabel = \$derived\(notes\.length > 1 \? t\('production\.notices', \{ count: notes\.length, text: notes\[0\] \}\) : \(notes\[0\] \?\? ''\)\);/);
	assert.match(deck, /<InfoTip lines=\{notes\.length \? notes : \[line\]\} label=\{notes\.length \? noticeLabel : ''\} wrapperClass="flex min-w-0 items-center gap-1\.5">/);
	assert.match(deck, /const line = \$derived\(deckLine\(\{ compact, eyebrow, detail \}\)\);/);
	assert.match(deck, /\{#if detail\.warn\}<Icon name="alert" class="h-3 w-3 shrink-0 text-warning" \/>\{\/if\}<span class="vp-deck-detail-text" class:text-warning=\{detail\.warn\} class:is-whole=\{detail\.warn \|\| detail\.whole\}>/);
	assert.match(rule('.vp-deck-detail-text.is-whole'), /-webkit-line-clamp: 2;[\s\S]*white-space: normal;/);
	assert.equal(rule('.vp-notice'), '');
	assert.equal(rule('.vp-production-wrap'), '');
	for (const locale of ['en', 'fr']) {
		const production = JSON.parse(read(`../i18n/${locale}/production.json`));
		assert.match(production['notices.other'], /^\{count\} .*\{text\}$/, locale);
	}
});

test('overflow: the seam panel puts the action under the whole text, and the seam popover widens, fits the window and follows its own height', () => {
	const panel = read('../components/storyboard/SeamPanel.svelte');
	assert.match(panel, /<div class="min-w-0 flex-1">\n\t+<span class="block text-fg-muted">\{issue\.text\}[\s\S]*<\/span>\n\t+\{#if !issue\.fix \|\| n === firstFix\}<div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1"><SeamFix \{clip\} \{issue\} \/><\/div>\{\/if\}\n\t+<\/div>/);
	const grid = read('../components/storyboard/StoryboardView.svelte');
	assert.match(grid, /<div class="vp-menu w-96 overflow-y-auto p-3" style:position="fixed" style:max-width="calc\(100vw - 1rem\)" role="dialog"/);
	assert.match(grid, /use:anchoredPopover=\{\(\) => seamAnchor\}/);
	const popover = read('./popover.js');
	assert.match(popover, /node\.style\.maxHeight = `\$\{window\.innerHeight - 2 \* POPOVER_MARGIN\}px`;/);
	assert.match(popover, /const above = a\.top - gap - panel\.height >= margin;/);
	assert.match(popover, /below \? a\.bottom \+ gap : above \? a\.top - panel\.height - gap : clamp\(viewport\.height - margin - panel\.height, margin, a\.bottom \+ gap\)/);
	assert.match(popover, /const resized = new ResizeObserver\(place\);\n\t+resized\.observe\(node\);\n\t+window\.addEventListener\('resize', place\);/);
	assert.deepEqual(popoverPosition({ anchor: { left: 100, right: 300, top: 400, bottom: 440 }, panel: { width: 320, height: 200 }, viewport: { width: 1440, height: 900 } }), { left: 8, top: 446, maxHeight: 884 });
	assert.deepEqual(popoverPosition({ anchor: { left: 1000, right: 1200, top: 800, bottom: 840 }, panel: { width: 352, height: 200 }, viewport: { width: 1440, height: 900 } }), { left: 848, top: 594, maxHeight: 884 });
	assert.deepEqual(popoverPosition({ anchor: { left: 1300, right: 1420, top: 100, bottom: 140 }, panel: { width: 352, height: 880 }, viewport: { width: 1440, height: 900 } }), { left: 1068, top: 12, maxHeight: 884 });
});

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent } from './svelte-harness.js';
import { scrollShade, shadeOf } from './scrollshade.js';
import { POPOVER_MARGIN, anchoredPopover, popoverPosition } from './popover.js';
import enProduction from '../i18n/en/production.json' with { type: 'json' };
import frProduction from '../i18n/fr/production.json' with { type: 'json' };

const { doc, ui, dispose } = await import('./state.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const PILLS = new URL('../components/shell/FilterPills.svelte', import.meta.url).href;
const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;

after(() => dispose());

function fakeNode(sizes) {
	const handlers = {};
	const node = {
		...sizes,
		attributes: {},
		setAttribute(name, value) {
			this.attributes[name] = value;
		},
		addEventListener(type, fn) {
			handlers[type] = fn;
		},
		removeEventListener(type) {
			delete handlers[type];
		}
	};
	return { node, handlers };
}

test('overflow: a row of pills that scrolls fades the side it hides, and the wheel scrolls it sideways only while it can still move that way', () => {
	assert.equal(shadeOf(0, 300, 300), 'none');
	assert.equal(shadeOf(0, 300, 301), 'none');
	assert.equal(shadeOf(0, 300, 500), 'end');
	assert.equal(shadeOf(200, 300, 500), 'start');
	assert.equal(shadeOf(100, 300, 500), 'both');
	const { node, handlers } = fakeNode({ scrollLeft: 0, clientWidth: 300, scrollWidth: 500 });
	const action = scrollShade(node);
	assert.equal(node.attributes['data-shade'], 'end');
	let prevented = 0;
	handlers.wheel({ deltaY: 40, deltaX: 0, preventDefault: () => (prevented += 1) });
	assert.deepEqual([node.scrollLeft, prevented], [40, 1]);
	handlers.scroll();
	assert.equal(node.attributes['data-shade'], 'both');
	handlers.wheel({ deltaY: 10, deltaX: 30, preventDefault: () => (prevented += 1) });
	assert.deepEqual([node.scrollLeft, prevented], [40, 1]);
	handlers.wheel({ deltaY: 500, deltaX: 0, preventDefault: () => (prevented += 1) });
	assert.deepEqual([node.scrollLeft, prevented], [200, 2]);
	handlers.wheel({ deltaY: 40, deltaX: 0, preventDefault: () => (prevented += 1) });
	assert.deepEqual([node.scrollLeft, prevented], [200, 2]);
	handlers.wheel({ deltaY: -500, deltaX: 0, preventDefault: () => (prevented += 1) });
	assert.deepEqual([node.scrollLeft, prevented], [0, 3]);
	handlers.wheel({ deltaY: -40, deltaX: 0, preventDefault: () => (prevented += 1) });
	assert.deepEqual([node.scrollLeft, prevented], [0, 3]);
	node.scrollWidth = 300;
	handlers.wheel({ deltaY: 40, deltaX: 0, preventDefault: () => (prevented += 1) });
	assert.deepEqual([node.scrollLeft, prevented], [0, 3]);
	action.destroy();
	assert.deepEqual(Object.keys(handlers), []);
});

test('overflow: the pills are one tab list named after their filter, each with its count, the current one selected', async () => {
	const items = [{ id: 'all', label: 'All', count: 7 }, { id: 'final', label: 'Selected', count: 2, tip: 'Finals only' }, { id: 'none', label: 'None' }];
	const html = clean(await renderComponent(PILLS, { items, value: 'final', onselect() {}, label: 'Review filter' }));
	assert.match(html, /<div class="vp-pills [^"]*" role="tablist" aria-label="Review filter">/);
	assert.equal((html.match(/role="tab"/g) ?? []).length, 3);
	assert.match(html, /aria-selected="true"[^>]*>Selected<span class="vp-tc text-2xs text-fg-subtle">2<\/span>/);
	assert.match(html, /aria-selected="false"[^>]*>All<span class="vp-tc text-2xs text-fg-subtle">7<\/span>/);
	assert.match(html, /aria-selected="false"[^>]*>None<\/button>/);
});

test('overflow: the warning of the production deck keeps its whole text in its tooltip and names itself for a screen reader, with the count of warnings', async () => {
	ui.me = null;
	doc.clips = [];
	const deck = await renderComponent(DECK);
	const notices = deck.match(/aria-label="([^"]*)" aria-describedby="vp-tip-[a-z0-9]+"/);
	assert.ok(notices, 'the deck names its notices');
	assert.equal(notices[1], t('production.notices', { count: 3, text: t('lib.block.noRange') }));
	assert.match(deck, /class="vp-deck-detail-text text-warning is-whole"/);
	for (const [locale, production] of [['en', enProduction], ['fr', frProduction]]) assert.match(production['notices.other'], /^\{count\} .*\{text\}$/, locale);
});

test('overflow: the seam popover widens, fits the window and follows its own height', () => {
	assert.deepEqual(popoverPosition({ anchor: { left: 100, right: 300, top: 400, bottom: 440 }, panel: { width: 320, height: 200 }, viewport: { width: 1440, height: 900 } }), { left: 8, top: 446, maxHeight: 884 });
	assert.deepEqual(popoverPosition({ anchor: { left: 1000, right: 1200, top: 800, bottom: 840 }, panel: { width: 352, height: 200 }, viewport: { width: 1440, height: 900 } }), { left: 848, top: 594, maxHeight: 884 });
	assert.deepEqual(popoverPosition({ anchor: { left: 1300, right: 1420, top: 100, bottom: 140 }, panel: { width: 352, height: 880 }, viewport: { width: 1440, height: 900 } }), { left: 1068, top: 12, maxHeight: 884 });
	const observed = [];
	globalThis.ResizeObserver = class {
		constructor(fn) {
			this.fn = fn;
		}
		observe(node) {
			observed.push(node);
		}
		disconnect() {
			observed.length = 0;
		}
	};
	const listeners = {};
	const previous = globalThis.window;
	globalThis.window = { innerWidth: 1440, innerHeight: 900, addEventListener: (type, fn) => (listeners[type] = fn), removeEventListener: (type) => delete listeners[type] };
	const panel = { width: 352, height: 200 };
	const node = { style: {}, getBoundingClientRect: () => panel };
	const action = anchoredPopover(node, () => ({ left: 1000, right: 1200, top: 800, bottom: 840 }));
	assert.deepEqual(node.style, { maxHeight: `${900 - 2 * POPOVER_MARGIN}px`, left: '848px', top: '594px' });
	assert.deepEqual([observed, Object.keys(listeners)], [[node], ['resize']]);
	panel.height = 880;
	listeners.resize();
	assert.deepEqual([node.style.left, node.style.top], ['848px', '12px']);
	action.update(() => ({ left: 100, right: 300, top: 400, bottom: 440 }));
	assert.equal(node.style.left, '8px');
	action.destroy();
	assert.deepEqual([observed, Object.keys(listeners)], [[], []]);
	globalThis.window = previous;
	delete globalThis.ResizeObserver;
});

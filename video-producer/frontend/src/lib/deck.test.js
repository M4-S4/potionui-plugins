import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DECK_STATES, DECK_TONES, deckCell, deckChip, deckDetail, deckEyebrow, deckState, deckTitle, deckTone, remainingSeconds } from './deck.js';

const t = (key, params = {}) => `${key}${Object.keys(params).length ? JSON.stringify(params) : ''}`;
const fmt = (s) => `${Math.round(s)}s`;
const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');

test('deck: five states with the tones of the host, running first, then blocked, then the end of the last batch', () => {
	assert.deepEqual(DECK_STATES, ['ready', 'blocked', 'running', 'done', 'failed']);
	assert.deepEqual(DECK_TONES, { ready: 'muted', blocked: 'warning', running: 'signal', done: 'success', failed: 'danger' });
	assert.equal(deckState({ state: 'ready', missing: [] }), 'ready');
	assert.equal(deckState({ state: 'running', missing: ['x'] }), 'running');
	assert.equal(deckState({ state: 'done', missing: ['x'] }), 'blocked');
	assert.equal(deckState({ state: 'failed', missing: ['x'] }), 'blocked');
	assert.equal(deckState({ state: 'done', missing: [] }), 'done');
	assert.equal(deckState({ state: 'failed', missing: [] }), 'failed');
	assert.equal(deckState({ state: 'ready' }), 'ready');
	for (const state of DECK_STATES) assert.equal(deckTone(state), DECK_TONES[state]);
	assert.equal(deckTone('other'), 'muted');
});

test('deck: the title names the shots to make, what runs, what arrived or what failed', () => {
	assert.equal(deckTitle({ state: 'ready', clips: 3 }, t), 'production.deck.ready{"count":3}');
	assert.equal(deckTitle({ state: 'blocked', clips: 1 }, t), 'production.deck.blocked');
	assert.equal(deckTitle({ state: 'running', current: { variant: 'B', shot: '02' }, percent: 42 }, t), 'production.deck.running{"variant":"B","shot":"02","percent":42}');
	assert.equal(deckTitle({ state: 'running', current: null, percent: 0 }, t), 'production.deck.generating{"percent":0}');
	assert.equal(deckTitle({ state: 'done', lastCount: 3 }, t), 'production.ready{"count":3}');
	assert.equal(deckTitle({ state: 'failed', failed: 1, failedVariant: 'C' }, t), 'production.deck.failed{"variant":"C"}');
	assert.equal(deckTitle({ state: 'failed', failed: 2, failedVariant: null }, t), 'production.deck.failedCount{"count":2}');
});

test('deck: the eyebrow gives the target and its span, or the numbers of the picked shots', () => {
	const shots = { list: '03', more: 0 };
	assert.equal(deckEyebrow({ target: 'clip', clips: 1, shots, label: 'SHOT 3', rangeText: '8,0 s → 10,0 s' }, t), 'production.scope.shot{"number":"03"} · SHOT 3 · 8,0 s → 10,0 s');
	assert.equal(deckEyebrow({ target: 'clip', clips: 1, shots, label: '', rangeText: '8,0 s → 10,0 s' }, t), 'production.scope.shot{"number":"03"} · 8,0 s → 10,0 s');
	assert.equal(deckEyebrow({ target: 'clip', clips: 0, shots: { list: '', more: 0 } }, t), 'production.target.clip · production.scope.none');
	assert.equal(deckEyebrow({ target: 'range', clips: 2, rangeText: '0,0 s → 8,0 s' }, t), 'production.target.range · 0,0 s → 8,0 s · production.count.shots{"count":2}');
	assert.equal(deckEyebrow({ target: 'sequence', clips: 6, durationText: '30,4 s' }, t), 'production.target.sequence · production.count.shots{"count":6} · 30,4 s');
	assert.equal(deckEyebrow({ target: 'picked', clips: 3, shots: { list: '01 · 03 · 05', more: 0 }, durationText: '9,4 s' }, t), 'production.scope.shots{"list":"01 · 03 · 05","more":0} · production.deck.total{"duration":"9,4 s"}');
	assert.equal(deckEyebrow({ target: 'picked', clips: 5, shots: { list: '01 · 03 · 05', more: 2 }, durationText: '9,4 s' }, t), 'production.scope.shotsMore{"list":"01 · 03 · 05","more":2} · production.deck.total{"duration":"9,4 s"}');
	assert.equal(deckEyebrow({ target: 'picked', clips: 1, shots: { list: '04', more: 0 }, durationText: '2,0 s' }, t), 'production.scope.shot{"number":"04"} · production.deck.total{"duration":"2,0 s"}');
});

test('deck: the detail carries the counts or the first warning, the reason of a block, the step and the queue, and the inline actions', () => {
	assert.deepEqual(deckDetail({ state: 'ready', counts: '1 prompt · 1 frame', missing: [], warnings: [], conflicts: 0 }, t), { text: '1 prompt · 1 frame', warn: false, actions: [] });
	assert.deepEqual(deckDetail({ state: 'ready', counts: '1 prompt', missing: [], warnings: ['text only'], conflicts: 2 }, t), { text: 'text only', warn: true, actions: ['conflicts'] });
	assert.deepEqual(deckDetail({ state: 'blocked', counts: '', missing: ['no prompt', 'no engine'], warnings: [], conflicts: 0 }, t), { text: 'no prompt', warn: true, actions: [] });
	assert.deepEqual(deckDetail({ state: 'running', step: 'Step 18/40', queued: 4 }, t), { text: 'Step 18/40 · production.deck.queued{"count":4}', warn: false, actions: ['enqueue'] });
	assert.deepEqual(deckDetail({ state: 'running', step: '', queued: 0 }, t), { text: '', warn: false, actions: ['enqueue'] });
	assert.deepEqual(deckDetail({ state: 'done' }, t), { text: '', warn: false, actions: ['results'] });
	assert.deepEqual(deckDetail({ state: 'failed' }, t), { text: '', warn: false, actions: ['results'] });
});

test('deck: the cell reads Estimated, then Elapsed with the remaining time, then Last', () => {
	assert.deepEqual(deckCell({ state: 'ready', timeText: '≈ 2 min 10', vramText: '9,2 Go', cloud: false, over: false }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min 10', sub: '9,2 Go', warn: false });
	assert.deepEqual(deckCell({ state: 'ready', timeText: '≈ 2 min', vramText: '—', cloud: true, over: true }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min', sub: '', warn: true });
	assert.deepEqual(deckCell({ state: 'blocked', timeText: '≈ 2 min', vramText: '9 Go' }, t, fmt), { label: 'production.deck.estimated', value: '—', sub: '', warn: false });
	assert.deepEqual(deckCell({ state: 'ready', noEngine: true, timeText: '—', vramText: '—' }, t, fmt), { label: 'production.deck.estimated', value: '—', sub: '', warn: false });
	assert.deepEqual(deckCell({ state: 'running', elapsed: 468, remaining: 840 }, t, fmt), { label: 'production.deck.elapsed', value: '468s', sub: 'production.deck.remaining{"duration":"840s"}', warn: false });
	assert.deepEqual(deckCell({ state: 'running', elapsed: 3, remaining: null }, t, fmt), { label: 'production.deck.elapsed', value: '3s', sub: '', warn: false });
	assert.deepEqual(deckCell({ state: 'done', lastSeconds: 380, timeText: '≈ 1 min', vramText: '9 Go' }, t, fmt), { label: 'production.deck.last', value: '380s', sub: '', warn: false });
	assert.deepEqual(deckCell({ state: 'done', lastSeconds: null, timeText: '≈ 1 min', vramText: '9 Go', cloud: false, over: false }, t, fmt), { label: 'production.deck.estimated', value: '≈ 1 min', sub: '9 Go', warn: false });
	assert.deepEqual(deckCell({ state: 'failed', timeText: '≈ 2 min 10', vramText: '13,1 Go', cloud: false, over: true }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min 10', sub: '13,1 Go', warn: true });
});

test('deck: the remaining time follows the progress once it is past 5 %', () => {
	assert.equal(remainingSeconds(0, 50), null);
	assert.equal(remainingSeconds(60, 0), null);
	assert.equal(remainingSeconds(60, 4), null);
	assert.equal(remainingSeconds(60, 100), null);
	assert.equal(remainingSeconds(60, 50), 60);
	assert.equal(remainingSeconds(100, 25), 300);
	assert.equal(remainingSeconds(90, 75), 30);
});

test('deck: the chip sums up the engine, the profile, the size and the drafts', () => {
	assert.deepEqual(deckChip({ engine: 'MiniMax H3', profile: 'FL2VA', size: '832×480', drafts: 1 }, t), ['MiniMax H3', 'FL2VA', '832×480', 'production.deck.drafts{"count":1}']);
	assert.deepEqual(deckChip({ engine: 'LTX-2.5', profile: '', size: '', drafts: null }, t), ['LTX-2.5', 'production.deck.draftsMixed']);
});

test('deck: the page mounts the deck under the timeline, before the status bar, in Storyboard and Director AI only; the 44 px bar is gone', () => {
	const page = source('../VideoProducerPage.svelte');
	assert.match(page, /grid-template-rows: auto auto minmax\(0, 1fr\) auto auto auto auto/);
	assert.match(page, /<div>\s*\{#if !bare\}<Splitter \/>\{\/if\}\s*<\/div>/);
	assert.match(page, /<\/section>\s*\{#if generates\(\)\}<ProductionDeck \/>\{\/if\}\s*<StatusBar \/>/);
	assert.doesNotMatch(page, /ProductionBar/);
	assert.throws(() => source('../components/production/ProductionBar.svelte'));
	assert.match(source('../components/production/ProductionDeck.svelte'), /class="vp-deck-grid"/);
	assert.match(page, /\.vp-root \.vp-deck-grid \{[^}]*grid-template-columns: minmax\(0, 1\.1fr\) auto minmax\(0, 1\.25fr\)/);
	assert.match(page, /\.vp-root \.vp-deck \{[^}]*height: 92px/);
	for (const rule of ['vp-deck-status', 'vp-deck-thumb', 'vp-deck-eyebrow', 'vp-deck-dot', 'vp-deck-title', 'vp-deck-detail', 'vp-deck-inline-action', 'vp-deck-run', 'vp-deck-generate', 'vp-deck-mark', 'vp-deck-mark-orbit', 'vp-deck-utility', 'vp-deck-timing', 'vp-deck-cell-label', 'vp-deck-cell-value', 'vp-deck-icon-button', 'vp-deck-queue-count', 'vp-deck-progress-track', 'vp-deck-progress-fill']) {
		assert.match(page, new RegExp(`\\.vp-root \\.${rule}\\b`), rule);
	}
	assert.match(page, /@keyframes vp-deck-mark-orbit/);
	assert.match(page, /@keyframes vp-deck-indeterminate/);
});

test('deck: the mark generates or cancels, Ctrl+G stays the command, the queue and More buttons are named, and the title is announced', () => {
	const deck = source('../components/production/ProductionDeck.svelte');
	const drawer = source('../components/production/ProductionDrawer.svelte');
	assert.match(deck, /onclick=\{\(\) => \(busy \? cancelGeneration\(\) : startGeneration\(\)\)\}/);
	assert.match(deck, /disabled=\{blocked && !busy\}/);
	assert.match(deck, /kbd: commandById\('generate'\)\?\.key/);
	assert.match(deck, /class:is-cancel=\{busy\}/);
	assert.match(deck, /data-generate=\{busy \? 'cancel' : 'start'\}/);
	assert.match(deck, /aria-label=\{t\('production\.queueLabel'\)\}/);
	assert.match(deck, /aria-label=\{t\('production\.more'\)\}/);
	assert.match(deck, /aria-live="polite"/);
	assert.match(deck, /role="region" aria-label=\{t\('production\.region'\)\}/);
	assert.match(deck, /const queueOpen = \$derived\(ui\.menuOpen === QUEUE_MENU\);/);
	assert.match(deck, /onclick=\{\(\) => \(ui\.menuOpen = queueOpen \? null : QUEUE_MENU\)\}/);
	assert.match(deck, /<QueuePanel \/>/);
	assert.match(deck, /onSelect: setProjectQuality/);
	assert.match(deck, /onSelect: pick/);
	assert.match(drawer, /act\(\(\) => setReferenceMargin\(doc\.engine, value\)\)/);
	assert.match(drawer, /onclick: \(\) => openEngineSettings\(engine\?\.preset\)/);
	assert.doesNotMatch(deck, /FinalPassButton|fitInline|ResizeObserver/);
	assert.match(deck, /const profileItems = \$derived\(supportedProfiles\(\)\.map\(\(m\) => \(\{ id: m, label: m \}\)\)\);/);
	assert.doesNotMatch(deck, /disabled: !supported/);
});

test('deck: the production state remembers when a batch started, how long the last one took and what failed', () => {
	const production = source('./production.svelte.js');
	assert.match(production, /if \(p\.state !== 'running'\) p\.startedAt = Date\.now\(\);/);
	assert.match(production, /p\.lastSeconds = p\.startedAt \? Math\.round\(\(Date\.now\(\) - p\.startedAt\) \/ 1000\) : null;/);
	assert.match(production, /p\.failed = failedTakes\.length;/);
	assert.match(production, /p\.failedVariant = failedTakes\[0\]\?\.variant \?\? null;/);
	assert.match(production, /p\.state = done\.length \? 'done' : failedTakes\.length \? 'failed' : 'ready';/);
	const state = source('./state.svelte.js');
	assert.match(state, /startedAt: null,\n\t\tlastSeconds: null,\n\t\tfailed: 0,\n\t\tfailedVariant: null,/);
	assert.match(state, /Object\.assign\(ui\.production, \{ state: 'ready', progress: 0, running: 0, step: '', lastCount: 0, startedAt: null, lastSeconds: null, failed: 0, failedVariant: null \}\);/);
});

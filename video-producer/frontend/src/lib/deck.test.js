import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { DECK_STATES, DECK_TONES, DECK_UNBLOCK, deckActions, deckCell, deckChip, deckDetail, deckEyebrow, deckLine, deckState, deckTitle, deckTone, deckUnblock, deckUnblockLabel, latestDone, remainingSeconds, selectedEverywhere } from './deck.js';
import { failureText } from './generation.js';

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
	assert.deepEqual(deckDetail({ state: 'ready', counts: '1 prompt · 1 frame', missing: [], warnings: [], conflicts: 0 }, t), { text: '1 prompt · 1 frame', warn: false, whole: false, actions: [] });
	assert.deepEqual(deckDetail({ state: 'ready', counts: '1 prompt', missing: [], warnings: ['text only'], conflicts: 2 }, t), { text: 'text only', warn: true, whole: false, actions: ['conflicts'] });
	assert.deepEqual(deckDetail({ state: 'blocked', counts: '', missing: ['no prompt', 'no engine'], warnings: [], conflicts: 0 }, t), { text: 'no prompt', warn: true, whole: true, actions: [] });
	assert.deepEqual(deckDetail({ state: 'blocked', counts: '', missing: ['no prompt'], warnings: [], conflicts: 0, unblock: true }, t), { text: 'no prompt', warn: true, whole: true, actions: ['unblock'] });
	assert.deepEqual(deckDetail({ state: 'running', step: 'Step 18/40', queued: 4 }, t), { text: 'Step 18/40 · production.deck.queued{"count":4}', warn: false, whole: false, actions: ['enqueue'] });
	assert.deepEqual(deckDetail({ state: 'running', step: '', queued: 0 }, t), { text: '', warn: false, whole: false, actions: ['enqueue'] });
});

test('deck: Done offers the Review, Compare with two finished takes, and the final render once every shot has a selected take', () => {
	assert.deepEqual(deckDetail({ state: 'done' }, t), { text: '', warn: false, whole: false, actions: ['results'] });
	assert.deepEqual(deckDetail({ state: 'done', compare: true }, t), { text: '', warn: false, whole: false, actions: ['results', 'compare'] });
	assert.deepEqual(deckDetail({ state: 'done', compare: true, finalPass: true }, t), { text: '', warn: false, whole: false, actions: ['results', 'compare', 'finalPass'] });
	assert.deepEqual(deckDetail({ state: 'done', finalPass: true }, t), { text: '', warn: false, whole: false, actions: ['results', 'finalPass'] });
	const takes = [
		{ id: 'a', shotId: 's1', status: 'done', createdAt: '2026-10-29T10:00:01Z', label: 'final' },
		{ id: 'b', shotId: 's2', status: 'done', createdAt: '2026-10-29T10:00:03Z', label: 'draft' },
		{ id: 'c', shotId: 's2', status: 'failed', createdAt: '2026-10-29T10:00:04Z' },
		{ id: 'd', shotId: 's1', status: 'done', createdAt: '2026-10-29T10:00:02Z', chosen: true }
	];
	assert.deepEqual(latestDone(takes).map((x) => x.id), ['b', 'd']);
	assert.deepEqual(latestDone(takes, 1).map((x) => x.id), ['b']);
	assert.deepEqual(latestDone([]), []);
	assert.equal(selectedEverywhere([{ id: 's1' }], takes), true);
	assert.equal(selectedEverywhere([{ id: 's1' }, { id: 's2' }], takes), false);
	assert.equal(selectedEverywhere([{ id: 's1' }, { id: 's2' }], [...takes, { id: 'e', shotId: 's2', status: 'done', label: 'final' }]), true);
	assert.equal(selectedEverywhere([{ id: 's1' }], [{ id: 'f', shotId: 's1', status: 'running', label: 'final' }]), false);
	assert.equal(selectedEverywhere([], takes), false);
});

test('deck: Failed carries the plain-language message of the take, Retry and Details, or the Review when the take is gone; the memory turns amber on cuda_oom', () => {
	assert.deepEqual(deckDetail({ state: 'failed', failure: 'The GPU is full.', retry: true, details: true }, t), { text: 'The GPU is full.', warn: false, whole: true, actions: ['retry', 'details'] });
	assert.deepEqual(deckDetail({ state: 'failed', failure: 'The GPU is full.', retry: true, details: false }, t), { text: 'The GPU is full.', warn: false, whole: true, actions: ['retry'] });
	assert.deepEqual(deckDetail({ state: 'failed', failure: 'The GPU is full.', retry: false }, t), { text: '', warn: false, whole: true, actions: ['results'] });
	assert.equal(failureText({ errorCode: 'cuda_oom', generationId: 'g-1' }, t), 'generation.failed.cuda_oom{"id":"g-1"}');
	assert.equal(failureText({ errorCode: 'unclassified', generationId: null }, t), 'generation.failed.unclassified{"id":"—"}');
	assert.equal(failureText({ errorCode: 'weird', errorMessage: 'raw text' }, t), 'raw text');
	assert.equal(failureText({ errorCode: 'weird', errorMessage: '' }, t), 'generation.card.error{"code":"weird"}');
	assert.equal(failureText(null, t), 'generation.card.error{"code":"—"}');
	assert.deepEqual(deckCell({ state: 'failed', timeText: '≈ 2 min 10', vramText: '13,1 Go', cloud: false, over: false, oom: true }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min 10', sub: '13,1 Go', warn: false, vramWarn: true });
	assert.deepEqual(deckCell({ state: 'failed', timeText: '≈ 2 min 10', vramText: '13,1 Go', cloud: false, over: false, oom: false }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min 10', sub: '13,1 Go', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'ready', timeText: '≈ 2 min 10', vramText: '13,1 Go', cloud: false, over: false, oom: true }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min 10', sub: '13,1 Go', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'failed', timeText: '≈ 2 min', vramText: '—', cloud: true, over: false, oom: true }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min', sub: '', warn: false, vramWarn: false });
});

test('deck: Blocked names the action that unblocks, from the code of the first reason', () => {
	assert.deepEqual(DECK_UNBLOCK, { noShot: 'review', noDirection: 'direction', emptyPrompts: 'shot', noEngine: 'engine', unavailable: 'engine', no_preset: 'engine', no_model: 'engine', missing_models: 'engine', profile_unsupported: 'engine' });
	assert.deepEqual(deckUnblock({ code: 'emptyPrompts', shotId: 's6' }), { action: 'shot', shotId: 's6' });
	assert.deepEqual(deckUnblock({ code: 'emptyPrompts', shotId: null }), { action: 'shot', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'noDirection', shotId: null }), { action: 'direction', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'noShot', shotId: null }), { action: 'review', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'noEngine', shotId: null }), { action: 'engine', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'unavailable', shotId: null }), { action: 'engine', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'missing_models', shotId: null }), { action: 'engine', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'audio_source_missing', shotId: 's2' }), { action: 'shot', shotId: 's2' });
	assert.equal(deckUnblock({ code: 'noRange', shotId: null }), null);
	assert.equal(deckUnblock({ code: 'quota_exceeded', shotId: null }), null);
	assert.equal(deckUnblock(null), null);
	assert.equal(deckUnblock(undefined), null);
	assert.equal(deckUnblockLabel('shot', t), 'production.deck.unblock.shot');
	assert.equal(deckUnblockLabel('direction', t), 'production.deck.unblock.direction');
	assert.equal(deckUnblockLabel('review', t), 'production.deck.unblock.review');
	assert.equal(deckUnblockLabel('engine', t), 'production.deck.unblock.engine');
});

test('deck: in the compact mode each state keeps its title and its first action, and a failure message stays alone on its line', () => {
	assert.deepEqual(deckActions(['results', 'compare', 'finalPass'], true), ['results']);
	assert.deepEqual(deckActions(['results', 'compare', 'finalPass'], false), ['results', 'compare', 'finalPass']);
	assert.deepEqual(deckActions(['retry', 'details'], true), ['retry']);
	assert.deepEqual(deckActions([], true), []);
	assert.equal(deckLine({ compact: true, eyebrow: 'PLAN 03', detail: { text: 'The GPU is full.', warn: false, whole: true } }), 'The GPU is full.');
	assert.equal(deckLine({ compact: true, eyebrow: 'PLAN 03', detail: { text: '', warn: false, whole: false } }), 'PLAN 03');
	assert.equal(deckLine({ compact: true, eyebrow: 'PLAN 03', detail: { text: '1 prompt', warn: false, whole: false } }), 'PLAN 03 · 1 prompt');
});

test('deck: the four states wire their actions in the component, the Estimated cell opens a popover that the page places, closes and refocuses like the other menus', () => {
	const deck = source('../components/production/ProductionDeck.svelte');
	const page = source('../VideoProducerPage.svelte');
	assert.match(deck, /const failedTake = \$derived\(state === 'failed' \? takeById\(p\.failedTake\) : null\);/);
	assert.match(deck, /const failure = \$derived\(failedTake \? failureText\(failedTake, t\) : ''\);/);
	assert.match(deck, /const oom = \$derived\(failedTake\?\.errorCode === 'cuda_oom'\);/);
	assert.match(deck, /const recent = \$derived\(latestDone\(takeStore\.list\)\);/);
	assert.match(deck, /const finalReady = \$derived\(selectedEverywhere\(doc\.clips, takeStore\.list\)\);/);
	assert.match(deck, /const unblock = \$derived\(state === 'blocked' \? deckUnblock\(ready\.reasons\[0\]\) : null\);/);
	assert.match(deck, /const actions = \$derived\(deckActions\(detail\.actions, compact\)\);/);
	assert.match(deck, /\{#if actions\.includes\('unblock'\) && unblock\}\n\t+<button type="button" class="vp-deck-inline-action" onclick=\{unblockNow\}>\{deckUnblockLabel\(unblock\.action, t\)\}<\/button>/);
	assert.match(deck, /if \(unblock\.action === 'direction'\) return openDirector\('direction'\);\n\t+if \(unblock\.action === 'review'\) return openDirector\('review'\);\n\t+if \(unblock\.action === 'engine'\) return toggleDrawer\(\);\n\t+const id = unblock\.shotId \?\? clips\[0\]\?\.id \?\? null;\n\t+if \(id\) ui\.modal = \{ type: 'shot', id \};/);
	assert.match(deck, /\{#if actions\.includes\('results'\)\}\n\t+<button type="button" class="vp-deck-inline-action" onclick=\{openResults\}>/);
	assert.match(deck, /\{#if actions\.includes\('compare'\)\}[\s\S]*onclick=\{compareLast\}><Icon name="compare"/);
	assert.match(deck, /ui\.compare = \[older\.id\];\n\t+toggleCompare\(newer\.id\);\n\t+openResults\(\);/);
	assert.match(deck, /\{#if actions\.includes\('finalPass'\)\}[\s\S]*onclick=\{openFinalPass\}><Icon name="arrow-up" class="h-3 w-3" \/>\{t\('generation\.finalPass\.title'\)\}/);
	assert.match(deck, /\{#if actions\.includes\('retry'\) && failedTake\}[\s\S]*onclick=\{\(\) => retryTake\(failedTake\)\}><Icon name="refresh" class="h-3 w-3" \/>\{t\('generation\.card\.retry'\)\}/);
	assert.match(deck, /\{#if actions\.includes\('details'\) && failedTake\}[\s\S]*onclick=\{\(\) => showDetails\(failedTake\)\}>\{t\('production\.deck\.details'\)\}/);
	assert.match(deck, /class:text-warning=\{cell\.warn \|\| cell\.vramWarn\}/);
	assert.match(deck, /<button bind:this=\{cellEl\} type="button" class="vp-deck-timing" aria-haspopup="dialog" aria-expanded=\{estimateOpen\} onclick=\{toggleEstimate\}>/);
	assert.match(deck, /const ESTIMATE = 'deck-estimate';\n\t+const moreOpen = \$derived\(ui\.menuOpen === MORE\);\n\t+const estimateOpen = \$derived\(ui\.menuOpen === ESTIMATE\);/);
	assert.match(deck, /<div class="vp-menu vp-deck-popover" role="dialog" aria-label=\{t\('production\.deck\.estimateTitle'\)\} tabindex="-1" hidden=\{!estimateOpen\} use:overlayLayer use:anchoredPopover=\{\(\) => cellEl\?\.getBoundingClientRect\(\) \?\? null\} use:drawerFocus=\{estimateOpen\}>/);
	assert.match(deck, /\{#each cellLines as text, i \(i\)\}<li>\{text\}<\/li>\{\/each\}/);
	assert.match(deck, /\{#if estNotes\.length\}\n\t+<ul class="vp-deck-popover-notes">/);
	assert.match(deck, /if \(!showCell && estimateOpen\) ui\.menuOpen = null;/);
	assert.doesNotMatch(deck, /<InfoTip lines=\{cellLines\}/);
	assert.match(page, /\.vp-root \.vp-deck-popover \{ position: fixed; width: 22rem; max-width: calc\(100vw - 1rem\); overflow: auto;/);
	assert.match(page, /\.vp-root \.vp-deck-popover-notes \{[^}]*color: rgb\(var\(--warning\)\);/);
	const commands = source('./commands.js');
	assert.match(commands, /else if \(ui\.menuOpen\) ui\.menuOpen = null;\n\t+else if \(ui\.deckDrawer\) ui\.deckDrawer = false;/);
	assert.match(source('../components/shell/MenuBar.svelte'), /if \(ui\.menuOpen && !e\.target\?\.closest\?\.\('\[data-vp-menu\]'\)\) ui\.menuOpen = null;/);
	const production = source('./production.svelte.js');
	assert.match(production, /const block = \(code, text, shotId = null\) => \{\n\t+missing\.push\(text\);\n\t+reasons\.push\(\{ code, shotId \}\);/);
	assert.match(production, /block\(noShot \? 'noShot' : 'noRange', noShot \? t\('lib\.block\.noShot'\) : t\('lib\.block\.noRange'\)\);/);
	assert.match(production, /block\('noDirection', t\('lib\.block\.noDirection'\)\);/);
	assert.match(production, /block\('emptyPrompts', t\('lib\.block\.emptyPrompts', \{ count: empty\.length \}\), empty\[0\]\.shotId \?\? null\);/);
	assert.match(production, /block\(doc\.engine\?\.preset \? 'unavailable' : 'noEngine', doc\.engine\?\.preset \? t\('generation\.block\.unavailable'\) : t\('generation\.block\.noEngine'\)\);/);
	assert.match(production, /return \{ range, items, missing, reasons, warnings, notes, gaps, est, noEngine \};/);
	assert.match(production, /p\.failedTake = failedTakes\[0\]\?\.id \?\? null;/);
	assert.match(source('../components/takes/TakeCard.svelte'), /const errorText = \$derived\(failureText\(take, t\)\);/);
});

test('deck: the cell reads Estimated, then Elapsed with the remaining time, then Last', () => {
	assert.deepEqual(deckCell({ state: 'ready', timeText: '≈ 2 min 10', vramText: '9,2 Go', cloud: false, over: false }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min 10', sub: '9,2 Go', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'ready', timeText: '≈ 2 min', vramText: '—', cloud: true, over: true }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min', sub: '', warn: true, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'blocked', timeText: '≈ 2 min', vramText: '9 Go' }, t, fmt), { label: 'production.deck.estimated', value: '—', sub: '', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'ready', noEngine: true, timeText: '—', vramText: '—' }, t, fmt), { label: 'production.deck.estimated', value: '—', sub: '', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'running', elapsed: 468, remaining: 840 }, t, fmt), { label: 'production.deck.elapsed', value: '468s', sub: 'production.deck.remaining{"duration":"840s"}', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'running', elapsed: 3, remaining: null }, t, fmt), { label: 'production.deck.elapsed', value: '3s', sub: '', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'done', lastSeconds: 380, timeText: '≈ 1 min', vramText: '9 Go' }, t, fmt), { label: 'production.deck.last', value: '380s', sub: '', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'done', lastSeconds: null, timeText: '≈ 1 min', vramText: '9 Go', cloud: false, over: false }, t, fmt), { label: 'production.deck.estimated', value: '≈ 1 min', sub: '9 Go', warn: false, vramWarn: false });
	assert.deepEqual(deckCell({ state: 'failed', timeText: '≈ 2 min 10', vramText: '13,1 Go', cloud: false, over: true }, t, fmt), { label: 'production.deck.estimated', value: '≈ 2 min 10', sub: '13,1 Go', warn: true, vramWarn: false });
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
	assert.doesNotMatch(deck, /FinalPassButton|fitInline/);
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
	assert.match(state, /startedAt: null,\n\t\tlastSeconds: null,\n\t\tfailed: 0,\n\t\tfailedVariant: null,\n\t\tfailedTake: null,/);
	assert.match(state, /Object\.assign\(ui\.production, \{ state: 'ready', progress: 0, running: 0, step: '', lastCount: 0, startedAt: null, lastSeconds: null, failed: 0, failedVariant: null, failedTake: null \}\);/);
});

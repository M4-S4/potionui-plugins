import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { clean, renderComponent, textOf } from './svelte-harness.js';
import { DECK_TONES, DECK_UNBLOCK, deckActions, deckCell, deckChip, deckDetail, deckEyebrow, deckLine, deckState, deckTitle, deckTone, deckUnblock, deckUnblockLabel, latestDone, remainingSeconds, selectedEverywhere } from './deck.js';
import { failureText } from './generation.js';

const { doc, ui, generates, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { t: tr } = await import('../i18n/index.svelte.js');

const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const t =(key, params = {}) => `${key}${Object.keys(params).length ? JSON.stringify(params) : ''}`;
const fmt = (s) => `${Math.round(s)}s`;
const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;
const WAN = '01KX47WANVIDEO0000000000TV';

after(() => dispose());

function scene(takes = []) {
	project.id = 'p1';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	ui.workspace = 'storyboard';
	ui.selection = { kind: 'clip', id: 's1' };
	doc.engine = { backend: 'native', preset: WAN, model: null };
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo', take: null }];
	doc.prompts = [{ id: 'pr1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'A walk along the river.' }];
	Object.assign(ui.production, { target: 'clip', state: 'ready', progress: 0, running: 0, step: '', lastCount: 0, startedAt: null, lastSeconds: null, failed: 0, failedVariant: null, failedTake: null, quality: 'draft' });
	setTakes('p1', takes);
}

const inlineActions = (html) => [...clean(html).matchAll(/<button type="button" class="vp-deck-inline-action[^"]*"[^>]*>(.*?)<\/button>/g)].map((m) => textOf(m[1]));

test('deck: five states with the tones of the host, running first, then blocked, then the end of the last batch', () => {
	assert.deepEqual(DECK_TONES, { ready: 'muted', blocked: 'warning', running: 'signal', done: 'success', failed: 'danger' });
	assert.equal(deckState({ state: 'ready', missing: [] }), 'ready');
	assert.equal(deckState({ state: 'running', missing: ['x'] }), 'running');
	assert.equal(deckState({ state: 'done', missing: ['x'] }), 'blocked');
	assert.equal(deckState({ state: 'failed', missing: ['x'] }), 'blocked');
	assert.equal(deckState({ state: 'done', missing: [] }), 'done');
	assert.equal(deckState({ state: 'failed', missing: [] }), 'failed');
	assert.equal(deckState({ state: 'ready' }), 'ready');
	for (const state of Object.keys(DECK_TONES)) assert.equal(deckTone(state), DECK_TONES[state]);
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
	assert.deepEqual(DECK_UNBLOCK, { noShot: 'review', noDirection: 'direction', emptyPrompts: 'shot', noEngine: 'engine', unavailable: 'engine', no_preset: 'engine', no_model: 'engine', missing_models: 'engine', profile_unsupported: 'engine', quota_unrecorded: 'retry' });
	assert.deepEqual(deckUnblock({ code: 'emptyPrompts', shotId: 's6' }), { action: 'shot', shotId: 's6' });
	assert.deepEqual(deckUnblock({ code: 'emptyPrompts', shotId: null }), { action: 'shot', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'noDirection', shotId: null }), { action: 'direction', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'noShot', shotId: null }), { action: 'review', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'noEngine', shotId: null }), { action: 'engine', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'unavailable', shotId: null }), { action: 'engine', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'missing_models', shotId: null }), { action: 'engine', shotId: null });
	assert.deepEqual(deckUnblock({ code: 'audio_source_missing', shotId: 's2' }), { action: 'shot', shotId: 's2' });
	assert.deepEqual(deckUnblock({ code: 'quota_unrecorded', shotId: 's4' }), { action: 'retry', shotId: null });
	assert.equal(deckUnblock({ code: 'noRange', shotId: null }), null);
	assert.equal(deckUnblock({ code: 'quota_exceeded', shotId: null }), null);
	assert.equal(deckUnblock(null), null);
	assert.equal(deckUnblock(undefined), null);
	assert.equal(deckUnblockLabel('shot', t), 'production.deck.unblock.shot');
	assert.equal(deckUnblockLabel('direction', t), 'production.deck.unblock.direction');
	assert.equal(deckUnblockLabel('review', t), 'production.deck.unblock.review');
	assert.equal(deckUnblockLabel('engine', t), 'production.deck.unblock.engine');
	assert.equal(deckUnblockLabel('retry', t), 'production.deck.unblock.retry');
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

test('deck: a deck without engine is blocked, names what unblocks it and keeps its mark disabled; Storyboard and Director AI are the workspaces that show it', async () => {
	scene();
	ui.me = null;
	const html = await renderComponent(DECK);
	assert.match(html, /class="vp-deck" role="region"[^>]*data-state="blocked"/);
	assert.deepEqual(inlineActions(html), [tr('production.deck.unblock.engine')]);
	assert.match(html, /class="vp-deck-generate"[^>]*disabled=""[^>]*data-generate="start"/);
	assert.match(textOf(html), new RegExp(escaped(tr('production.deck.blocked'))));
	for (const [workspace, shown] of [['storyboard', true], ['director', true], ['player', false], ['references', false]]) {
		ui.workspace = workspace;
		assert.equal(generates(), shown, workspace);
	}
	ui.workspace = 'storyboard';
});

test('deck: a ready deck counts the prompts and the takes, and its mark starts the generation', async () => {
	scene();
	const html = await renderComponent(DECK);
	assert.match(html, /data-state="ready"/);
	assert.deepEqual(inlineActions(html), []);
	assert.match(html, /class="vp-deck-generate"[^>]*data-generate="start"/);
	assert.doesNotMatch(html, /class="vp-deck-generate"[^>]*disabled=""/);
	assert.match(textOf(html), new RegExp(`${tr('production.count.prompts', { count: 1 })} · ${tr('production.count.takes', { count: 1 })}`));
});

test('deck: a running deck shows the progress of the running take, its mark cancels, and the queue can take more', async () => {
	scene([{ id: 'tr', shotId: 's1', status: 'running', variant: 'A', progress: 40, step: 'Step 18/40', createdAt: '2026-10-29T10:00:00Z' }]);
	Object.assign(ui.production, { state: 'running', running: 1, progress: 40, step: 'Step 18/40', startedAt: Date.now() });
	const html = await renderComponent(DECK);
	assert.match(html, /data-state="running"/);
	assert.match(html, /role="progressbar"[^>]*aria-valuenow="40"/);
	assert.match(html, /class="vp-deck-generate is-cancel"[^>]*data-generate="cancel"/);
	assert.equal(inlineActions(html).length, 1);
	assert.match(inlineActions(html)[0], new RegExp(`^${tr('production.enqueue')}`));
	assert.match(textOf(html), /Step 18\/40/);
});

test('deck: a finished batch offers the Review, Compare with two finished takes, and the final render once every shot has a selected take', async () => {
	const done = (id, label, createdAt) => ({ id, shotId: 's1', status: 'done', label, variant: id.toUpperCase(), url: `/${id}.mp4`, createdAt });
	scene([done('a', 'draft', '2026-10-29T10:00:01Z'), done('b', 'draft', '2026-10-29T10:00:02Z')]);
	Object.assign(ui.production, { state: 'done', lastCount: 2 });
	const two = await renderComponent(DECK);
	assert.match(two, /data-state="done"/);
	assert.deepEqual(inlineActions(two), [tr('production.deck.results'), tr('production.deck.compare')]);
	setTakes('p1', [done('a', 'final', '2026-10-29T10:00:01Z')]);
	const one = await renderComponent(DECK);
	assert.deepEqual(inlineActions(one), [tr('production.deck.results'), tr('generation.finalPass.title')]);
});

test('deck: a failed batch carries the plain-language message of the take, Retry and Details, and the Review alone once the take is gone', async () => {
	scene([{ id: 'tf', shotId: 's1', status: 'failed', variant: 'B', errorCode: 'cuda_oom', generationId: 'g-1', createdAt: '2026-10-29T10:00:00Z' }]);
	Object.assign(ui.production, { state: 'failed', failed: 1, failedVariant: 'B', failedTake: 'tf' });
	const html = await renderComponent(DECK);
	assert.match(html, /data-state="failed"/);
	assert.match(textOf(html), new RegExp(escaped(tr('generation.failed.cuda_oom', { id: 'g-1' }))));
	assert.deepEqual(inlineActions(html), [tr('generation.card.retry'), tr('production.deck.details')]);
	setTakes('p1', []);
	const gone = await renderComponent(DECK);
	assert.deepEqual(inlineActions(gone), [tr('production.deck.results')]);
});

test('deck: the memory under the Estimated cell turns amber on cuda_oom and past the limits, the muted rule of the page giving way to text-warning there and nowhere else', async () => {
	const page = readFileSync(new URL('../VideoProducerPage.svelte', import.meta.url), 'utf-8');
	const style = page.slice(page.indexOf('<style>'));
	const rules = [...style.matchAll(/^\t\t(\.vp-root [^{\n]+?) \{ ([^}\n]*) \}$/gm)].map(([, selectors, body]) => ({ selectors: selectors.split(',').map((s) => s.trim()), color: /(?:^|; )color: ([^;]+);/.exec(body)?.[1] ?? null }));
	const colorOf = (classes) => {
		let best = classes.includes('text-warning') ? { weight: 1, color: 'rgb(var(--warning))' } : { weight: 0, color: null };
		for (const rule of rules) {
			for (const selector of rule.selectors) {
				const compound = /^\.vp-root ((?:\.[\w-]+)+)$/.exec(selector);
				if (!compound || !rule.color) continue;
				const needed = compound[1].split('.').filter(Boolean);
				if (needed.every((name) => classes.includes(name)) && needed.length + 1 >= best.weight) best = { weight: needed.length + 1, color: rule.color };
			}
		}
		return best.color;
	};
	assert.equal(colorOf(['vp-deck-cell-sub']), 'rgb(var(--fg-muted))');
	assert.equal(colorOf(['vp-deck-cell-sub', 'text-warning']), 'rgb(var(--warning))');
	assert.equal(colorOf(['vp-deck-cell-label', 'text-warning']), 'rgb(var(--fg-subtle))');
	assert.deepEqual(style.match(/[^\s{};][^{};\n]*text-warning[^{};\n]*(?=\{)/g).map((selector) => selector.trim()), ['.vp-root .vp-deck-cell-sub.text-warning']);
	scene([{ id: 'tf', shotId: 's1', status: 'failed', variant: 'B', errorCode: 'cuda_oom', generationId: 'g-1', createdAt: '2026-10-29T10:00:00Z' }]);
	Object.assign(ui.production, { state: 'failed', failed: 1, failedVariant: 'B', failedTake: 'tf' });
	assert.match(await renderComponent(DECK), /<button[^>]*class="vp-deck-timing"[\s\S]*?<span class="vp-deck-cell-sub text-warning">/);
	setTakes('p1', [{ id: 'tf', shotId: 's1', status: 'failed', variant: 'B', errorCode: 'unclassified', generationId: 'g-1', createdAt: '2026-10-29T10:00:00Z' }]);
	assert.match(await renderComponent(DECK), /<button[^>]*class="vp-deck-timing"[\s\S]*?<span class="vp-deck-cell-sub">/);
});

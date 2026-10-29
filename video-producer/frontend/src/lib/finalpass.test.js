import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { clean, hostUis, renderComponent, textOf } from './svelte-harness.js';
import { emptyDoc, migrate } from './starter.js';
import { normalizePassEstimate, normalizeTake } from './api.js';
import { DEFAULT_RTX_SOURCE, GUIDED_PRESET, PASS_METHODS, PASS_TARGETS, RTX_SOURCES, UPSCALERS, migratePass, passBody, passChoice, passFlying, passPlan, passProgress, passShot, rtxSourceShown, upscalerReady } from './finalpass.js';

const t = (key) => key;
const take = (id, shotId, extra = {}) => ({ id, shotId, status: 'done', url: `/v/${id}.mp4`, label: 'draft', quality: 'draft', kind: 'render', parentTakeId: null, createdAt: id, shotRevision: 0, variant: 'A', ...extra });
const clip = (id, extra = {}) => ({ id, stage: 'draft', take: null, revision: 0, ...extra });

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { commandById } = await import('./commands.js');
const { t: tr } = await import('../i18n/index.svelte.js');

const WAN = '01KX47WANVIDEO0000000000TV';
const FINAL_PASS = new URL('../components/modals/FinalPass.svelte', import.meta.url).href;
const MAKE_FINAL = new URL('../components/modals/MakeFinal.svelte', import.meta.url).href;
const PASS_BUTTON = new URL('../components/production/FinalPassButton.svelte', import.meta.url).href;
const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;
const STORYBOARD = new URL('../components/storyboard/StoryboardView.svelte', import.meta.url).href;
const BAND = new URL('../components/storyboard/BandView.svelte', import.meta.url).href;
const REVIEW = new URL('../components/director/ReviewView.svelte', import.meta.url).href;
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const buttons = (html) => [...clean(html).matchAll(/<host-ui data-host="Button" data-props="([^"]*)">(.*?)<\/host-ui>/g)].map(([, props, inner]) => ({ ...JSON.parse(props.replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&amp;', '&')), text: textOf(inner) }));

after(() => dispose());

function passScene(second = null, extra = []) {
	project.id = 'p1';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }], features: {} };
	ui.workspace = 'storyboard';
	ui.menuOpen = null;
	ui.modal = null;
	doc.engine = { backend: 'native', preset: WAN, model: null };
	doc.clips = [clip('s1', { start: 0, dur: 4, srcIn: 0, label: 'One', take: 't1' }), clip('s2', { start: 4, dur: 4, srcIn: 0, label: 'Two', take: second })];
	setTakes('p1', [take('t1', 's1', { label: 'final', presetId: WAN }), ...(second ? [take(second, 's2', { label: 'final', presetId: WAN })] : []), ...extra]);
}

test('passShot reads each shot from its Final take: ready on a draft, done on a final, running while a final is in flight', () => {
	const draft = take('d1', 's1', { label: 'final' });
	assert.equal(passShot(clip('s1', { take: 'd1' }), [draft]).state, 'ready');
	assert.equal(passShot(clip('s1', { take: 'd1' }), [draft]).source, draft);

	const final = take('f1', 's1', { label: 'final', quality: 'final', kind: 'upscale', parentTakeId: 'd1' });
	const candidate = { ...draft, label: 'candidate' };
	const done = passShot(clip('s1', { take: 'f1', stage: 'final' }), [candidate, final]);
	assert.deepEqual([done.state, done.final.id, done.source.id], ['done', 'f1', 'd1']);

	const flying = take('f2', 's1', { status: 'running', url: null, quality: 'final', kind: 'guided', parentTakeId: 'd1', progress: 40 });
	const running = passShot(clip('s1', { take: 'd1' }), [draft, flying]);
	assert.deepEqual([running.state, running.take.id], ['running', 'f2']);
});

test('passShot leaves out the imported sources and says which shots have no Final take yet', () => {
	assert.equal(passShot(clip('s1', { stage: 'source' }), [take('d1', 's1', { label: 'final' })]).state, 'source');
	assert.equal(passShot(clip('s1', { stage: 'todo' }), []).state, 'missing');
	assert.equal(passShot(clip('s1'), [take('d1', 's1'), take('d2', 's1', { label: 'candidate' })]).state, 'missing');
	assert.equal(passShot(clip('s1'), [take('d1', 's1', { label: 'final', status: 'failed', url: null })]).state, 'missing');
	assert.equal(passShot(clip('s1'), [take('k1', 's1', { label: 'final', kind: 'keyframe' })]).state, 'missing');
});

test('passShot prefers the take the shot plays, marks a stale take and the last final that failed', () => {
	const played = take('d2', 's1', { label: 'final', shotRevision: 1 });
	const other = take('d1', 's1', { label: 'final' });
	const failed = take('f1', 's1', { status: 'failed', url: null, quality: 'final', kind: 'upscale', parentTakeId: 'd2', createdAt: 'z' });
	const shot = passShot(clip('s1', { take: 'd2', revision: 2 }), [other, played, failed]);
	assert.deepEqual([shot.source.id, shot.stale, shot.failed?.id], ['d2', true, 'f1']);
	const retried = take('f2', 's1', { status: 'cancelled', url: null, quality: 'final', kind: 'upscale', parentTakeId: 'd2', createdAt: 'zz' });
	assert.equal(passShot(clip('s1', { take: 'd2', revision: 1 }), [played, failed, retried]).failed.id, 'f2');
	assert.equal(passShot(clip('s1', { take: 'd2', revision: 1 }), [played]).failed, null);
});

test('passPlan sends the ready shots, adds the final ones only when redone, and counts every state', () => {
	const clips = [clip('s1', { take: 'd1' }), clip('s2', { take: 'f2', stage: 'final' }), clip('s3', { stage: 'todo' }), clip('s4', { stage: 'source' }), clip('s5', { take: 'd5' })];
	const takes = [
		take('d1', 's1', { label: 'final' }),
		take('d2', 's2', { label: 'candidate' }),
		take('f2', 's2', { label: 'final', quality: 'final', kind: 'upscale', parentTakeId: 'd2' }),
		take('d5', 's5', { label: 'final' }),
		take('f5', 's5', { status: 'queued', url: null, quality: 'final', kind: 'upscale', parentTakeId: 'd5' })
	];
	const plan = passPlan(clips, takes);
	assert.deepEqual(plan.sources, ['d1']);
	assert.deepEqual(plan.counts, { ready: 1, running: 1, done: 1, missing: 1, source: 1 });
	assert.deepEqual([plan.generated, plan.missing.map((c) => c.id)], [4, ['s3']]);
	assert.deepEqual(passPlan(clips, takes, true).sources, ['d1', 'd2']);
	assert.deepEqual(passProgress(clips, takes), { generated: 4, done: 1, running: 1, ready: 1, missing: 1, complete: false });
	assert.equal(passProgress([clips[1], clips[3]], takes).complete, true);
	assert.equal(passProgress([clips[3]], takes).complete, false);
});

test('a final with no draft behind it is redone from itself', () => {
	const final = take('f1', 's1', { label: 'final', quality: 'final', kind: 'render' });
	assert.deepEqual(passPlan([clip('s1', { take: 'f1' })], [final], true).sources, ['f1']);
});

test('passFlying lists the final takes made from another take that are queued or running, nothing else', () => {
	const list = [
		take('a', 's1', { status: 'running', quality: 'final', kind: 'upscale', parentTakeId: 'd' }),
		take('b', 's1', { status: 'queued', quality: 'final', kind: 'guided', parentTakeId: 'd' }),
		take('c', 's1', { status: 'queued', quality: 'final', kind: 'render', parentTakeId: null }),
		take('d', 's1', { status: 'running', quality: 'draft' }),
		take('e', 's1', { status: 'done', quality: 'final', kind: 'render', parentTakeId: 'd' }),
		take('k', 's1', { status: 'queued', quality: 'final', kind: 'keyframe', parentTakeId: 'd' })
	];
	assert.deepEqual(passFlying(list).map((x) => x.id), ['a', 'b']);
});

test('the choice of the pass keeps what it knows, falls back to upscale and to the first target, Auto', () => {
	assert.deepEqual(passChoice(null), { method: 'upscale', target: 'auto', upscaler: 'auto', rtxSource: 'compressed', interpolator: 'auto', conform: true });
	assert.deepEqual(passChoice({ method: 'render', target: 'uhd2160', upscaler: 'seedvr2' }), { method: 'render', target: 'uhd2160', upscaler: 'seedvr2', rtxSource: 'compressed', interpolator: 'auto', conform: true });
	assert.deepEqual(passChoice({ method: 'guided', target: 'auto', upscaler: 'rtx', rtxSource: 'clean', interpolator: 'rife' }), { method: 'upscale', target: 'auto', upscaler: 'rtx', rtxSource: 'clean', interpolator: 'rife', conform: true });
	assert.equal(passChoice({ rtxSource: 'raw' }).rtxSource, DEFAULT_RTX_SOURCE);
	assert.deepEqual(RTX_SOURCES, ['compressed', 'clean']);
	assert.deepEqual(passChoice({ method: 'guided' }, undefined, true).method, 'guided');
	assert.equal(passChoice({ target: 'uhd2160' }, ['hd720', 'fhd1080']).target, 'hd720');
	assert.deepEqual(PASS_METHODS, ['upscale', 'guided', 'render']);
	assert.deepEqual(UPSCALERS, ['auto', 'rtx', 'seedvr2', 'engine']);
	assert.deepEqual(PASS_TARGETS, ['auto', 'hd720', 'fhd1080', 'qhd1440', 'uhd2160']);
});

test('an upscaler is ready when the server says so, the engine only for takes that upscale themselves', () => {
	const h3 = '01KX47H3MINIMAX000000000VA';
	const me = { features: { upscaler: true, upscalers: { seedvr2: true, rtx: false } } };
	assert.equal(upscalerReady('auto', me, ['wan']), true);
	assert.equal(upscalerReady('seedvr2', me, ['wan']), true);
	assert.equal(upscalerReady('rtx', me, ['wan']), false);
	assert.equal(upscalerReady('rtx', { features: { upscalers: { rtx: true } } }, ['wan']), true);
	assert.equal(upscalerReady('engine', me, ['wan', h3]), false);
	assert.equal(upscalerReady('engine', me, [h3]), true);
	assert.equal(upscalerReady('auto', { features: { upscaler: false } }, [h3]), true);
	assert.equal(upscalerReady('auto', { features: { upscaler: false } }, [h3, 'wan']), false);
	assert.equal(upscalerReady('seedvr2', null, ['wan']), false);
});

test('the body of the pass sends the upscaler only when it is not automatic', () => {
	assert.deepEqual(passBody(['d1', 'd2'], { method: 'upscale', target: 'fhd1080', upscaler: 'auto' }), { takes: ['d1', 'd2'], method: 'upscale', target: 'fhd1080' });
	assert.deepEqual(passBody(['d1'], { method: 'upscale', target: 'hd720', upscaler: 'seedvr2' }), { takes: ['d1'], method: 'upscale', target: 'hd720', upscaler: 'seedvr2' });
	assert.deepEqual(passBody(['d1'], { method: 'guided', target: 'hd720', upscaler: 'seedvr2' }), { takes: ['d1'], method: 'guided', target: 'hd720' });
});

test('the body of the pass asks RTX for a clean source only when chosen, compressed being the default of the server', () => {
	assert.deepEqual(passBody(['d1'], { method: 'upscale', target: 'fhd1080', upscaler: 'rtx', rtxSource: 'compressed' }), { takes: ['d1'], method: 'upscale', target: 'fhd1080', upscaler: 'rtx' });
	assert.deepEqual(passBody(['d1'], { method: 'upscale', target: 'fhd1080', upscaler: 'rtx', rtxSource: 'clean' }), { takes: ['d1'], method: 'upscale', target: 'fhd1080', upscaler: 'rtx', rtx_source: 'clean' });
	assert.deepEqual(passBody(['d1'], { method: 'render', target: 'hd720', upscaler: 'auto', conform: true }), { takes: ['d1'], method: 'render', target: 'hd720', conform: true });
	assert.deepEqual(passBody(['d1'], { method: 'upscale', target: 'hd720', upscaler: 'auto', conform: false }), { takes: ['d1'], method: 'upscale', target: 'hd720' });
	assert.deepEqual(passBody(['d1'], { method: 'render', target: 'fhd1080', upscaler: 'rtx', rtxSource: 'clean' }), { takes: ['d1'], method: 'render', target: 'fhd1080' });
});

test('the kind of source shows for RTX, and for Automatic only when Automatic falls back to RTX', () => {
	const both = { features: { upscalers: { seedvr2: true, rtx: true } } };
	const rtx = { features: { upscalers: { seedvr2: false, rtx: true } } };
	assert.equal(rtxSourceShown('rtx', both), true);
	assert.equal(rtxSourceShown('auto', both), false);
	assert.equal(rtxSourceShown('auto', rtx), true);
	assert.equal(rtxSourceShown('seedvr2', rtx), false);
	assert.equal(rtxSourceShown('auto', null), false);
});

test('migrating keeps the known values of the final pass and drops the key when none is left, as the server does', () => {
	const cases = JSON.parse(readFileSync(new URL('../../../tests/fixtures/final_pass_migration.json', import.meta.url), 'utf8'));
	const doc = emptyDoc(t);
	assert.equal('finalPass' in migrate(doc), false);
	for (const { value, expected } of cases) {
		const next = migrate({ ...doc, finalPass: value });
		assert.deepEqual(next.finalPass ?? null, expected, JSON.stringify(value));
		assert.equal('finalPass' in next, expected !== null, JSON.stringify(value));
		assert.deepEqual(migrate(next), next);
		assert.deepEqual(migratePass(value), expected);
	}
});

test('migrating drops the retired post-processing switches of the engine', () => {
	const doc = emptyDoc(t);
	const next = migrate({ ...doc, engine: { ...doc.engine, post: { upscale: false, interpolation: true, denoise: true } } });
	assert.equal('post' in next.engine, false);
	assert.deepEqual(next.engine, migrate(doc).engine);
});

test('the page reads a guided take and the estimate of a pass shot by shot', () => {
	assert.equal(normalizeTake({ id: 't1', kind: 'guided' }).kind, 'guided');
	assert.equal(normalizeTake({ id: 't1', kind: 'remaster' }).kind, 'render');
	const estimate = normalizePassEstimate({
		shots: [{ shot_id: 's1', take_id: 'd1', method: 'guided', preset_id: GUIDED_PRESET, mode: 'video', resolution: '1280x720', seconds: 5.04, minutes: 8.4, sound: true }, { shot_id: 's2' }],
		vram: { estimate_gb: 10.7, unknown: false },
		time: { seconds: null, samples: 0 },
		quota: { limit: null, needed_minutes: 8.4, applies: true },
		blocks: [],
		warnings: [{ code: 'time_unknown', message: 'No take.' }]
	});
	assert.deepEqual(estimate.shots, [{ shotId: 's1', takeId: 'd1', method: 'guided', presetId: GUIDED_PRESET, mode: 'video', resolution: '1280x720', seconds: 5.04, minutes: 8.4, sound: true }]);
	assert.deepEqual([estimate.vram.estimateGb, estimate.time.seconds, estimate.quota.neededMinutes, estimate.warnings[0].code], [10.7, null, 8.4, 'time_unknown']);
	assert.equal(normalizePassEstimate(null), null);
});



test('the final pass opens from the Production menu and the More menu of the deck, and its button on the Storyboard, the band and the Review counts the shots at final quality', async () => {
	passScene();
	const command = commandById('final-pass');
	assert.equal(command.menuId, 'production');
	command.run();
	assert.deepEqual(ui.modal, { type: 'final-pass' });
	ui.modal = null;
	const button = clean(await renderComponent(PASS_BUTTON));
	assert.match(button, new RegExp(`<button[^>]*aria-label="${escaped(tr('generation.finalPass.tipMissing', { done: 0, total: 2, count: 1 }))}"`));
	assert.equal(textOf(button), `${tr('generation.finalPass.button')} ${tr('generation.finalPass.count', { done: 0, total: 2 })}`);
	assert.equal(textOf(await renderComponent(PASS_BUTTON, { short: true })), tr('generation.finalPass.count', { done: 0, total: 2 }));
	assert.deepEqual(buttons(await renderComponent(PASS_BUTTON, { variant: 'secondary' })).map((b) => [b.variant, b.text]), [['secondary', `${tr('generation.finalPass.button')} · ${tr('generation.finalPass.count', { done: 0, total: 2 })}`]]);
	for (const page of [STORYBOARD, BAND, REVIEW]) assert.match(textOf(await renderComponent(page)), new RegExp(escaped(tr('generation.finalPass.button'))), page);
	ui.menuOpen = 'deck-more';
	const items = [...clean(await renderComponent(DECK)).matchAll(/role="menuitem"[^>]*>(.*?)<\/button>/g)].map((m) => textOf(m[1]));
	assert.ok(items.includes(tr('generation.finalPass.title')), items.join(' | '));
	ui.menuOpen = null;
	doc.clips = [];
	assert.equal(clean(await renderComponent(PASS_BUTTON)), '');
});

test('the window of the pass keeps one primary button, which goes without the missing shots, cancels a running pass from a secondary one, and the per-take window offers the guided render only when its engine is there', async () => {
	passScene();
	const missing = buttons(await renderComponent(FINAL_PASS));
	assert.deepEqual(missing.filter((b) => b.variant === 'primary').map((b) => b.text), [tr('generation.finalPass.startWithout', { count: 1 })]);
	assert.ok(!missing.some((b) => b.text === tr('generation.finalPass.cancelPass', { count: 1 })));
	passScene('t2');
	const whole = buttons(await renderComponent(FINAL_PASS));
	assert.deepEqual(whole.filter((b) => b.variant === 'primary').map((b) => b.text), [tr('generation.finalPass.start', { count: 2 })]);
	passScene('t2', [take('t3', 's1', { quality: 'final', kind: 'upscale', parentTakeId: 't1', status: 'running', url: null, presetId: WAN })]);
	const running = buttons(await renderComponent(FINAL_PASS));
	assert.equal(running.filter((b) => b.variant === 'primary').length, 1);
	assert.deepEqual(running.filter((b) => b.text === tr('generation.finalPass.cancelPass', { count: 1 })).map((b) => b.variant), ['secondary']);
	passScene();
	const plain = buttons(await renderComponent(MAKE_FINAL, { takeId: 't1' }));
	assert.equal(plain.filter((b) => b.variant === 'primary').length, 1);
	assert.ok(!plain.some((b) => b.text === tr('generation.final.guided')));
	ui.me = { ...ui.me, features: { guided: true } };
	const guided = buttons(await renderComponent(MAKE_FINAL, { takeId: 't1' }));
	assert.equal(guided.filter((b) => b.variant === 'primary').length, 1);
	assert.deepEqual(guided.filter((b) => b.text === tr('generation.final.guided')).map((b) => [b.variant, b.class]), [['secondary', 'mr-auto']]);
});

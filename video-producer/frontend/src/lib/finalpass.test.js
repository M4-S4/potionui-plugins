import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { emptyDoc, migrate } from './starter.js';
import { normalizePassEstimate, normalizeTake } from './api.js';
import { DEFAULT_RTX_SOURCE, GUIDED_PRESET, PASS_METHODS, PASS_TARGETS, RTX_SOURCES, UPSCALERS, migratePass, passBody, passChoice, passFlying, passPlan, passProgress, passShot, rtxSourceShown, upscalerReady } from './finalpass.js';

const t = (key) => key;
const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const take = (id, shotId, extra = {}) => ({ id, shotId, status: 'done', url: `/v/${id}.mp4`, label: 'draft', quality: 'draft', kind: 'render', parentTakeId: null, createdAt: id, shotRevision: 0, variant: 'A', ...extra });
const clip = (id, extra = {}) => ({ id, stage: 'draft', take: null, revision: 0, ...extra });

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

test('the final pass opens from the Production menu, the two Storyboard headers, the Review footer and the To produce tab', () => {
	assert.match(source('./commands.js'), /command\('assemble', assembleChosen\), command\('final-pass', openFinalPass\)\]/);
	for (const path of ['../components/storyboard/BandView.svelte', '../components/storyboard/StoryboardView.svelte', '../components/director/ReviewView.svelte']) {
		assert.match(source(path), /<FinalPassButton( room=\{countsEl\})? \/>/, path);
	}
	assert.match(source('../components/storyboard/StoryWindow.svelte'), /<FinalPassButton variant="secondary" \/>/);
	assert.match(source('../components/modals/Modals.svelte'), /m\?\.type === 'final-pass'\}\n\t\t<FinalPass \/>/);
	assert.doesNotMatch(source('../components/production/ProductionBar.svelte'), /FinalPass/);
});

test('the window of the pass keeps one primary button and lets the per-take window offer the guided render', () => {
	const pass = source('../components/modals/FinalPass.svelte');
	assert.equal(pass.match(/variant: 'primary'/g).length, 1);
	assert.match(pass, /plan\.missing\.length \? t\('generation\.finalPass\.startWithout'/);
	assert.match(pass, /onclick: cancelFinalPass/);
	const single = source('../components/modals/MakeFinal.svelte');
	assert.match(single, /\{#if guided\}\n\t\t\t<HostUi name="Button" props=\{\{ variant: 'secondary', size: 'sm', class: 'mr-auto', disabled: sending, onclick: \(\) => send\('guided'\) \}\}>/);
});

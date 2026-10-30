import { test, after, mock } from 'node:test';
import assert from 'node:assert/strict';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';
import enPanels from '../i18n/en/panels.json' with { type: 'json' };
import frPanels from '../i18n/fr/panels.json' with { type: 'json' };
import { CAST_LOW, chainDrifts, chainLook, chainThreshold, DRIFT_LOW, FACE_LOW, FINAL_LOW, IDENTITY_LOW, PLACE_LOW, PUSH_IN_HIGH, SEAM_LOW, bestCandidate, cardThreshold, driftOf, faceChanged, finalLook, identityIssues, issueKey, lowDrift, lowFinal, candidateLook, candidateScore, castIssues, lowCards, lowSeam, normalizeLooks, percent, pushedIn, pushInIssues, seamFaceChanged, seamLook, STATES, takeLook } from './looks.js';

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project, bindClient } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { lookState, measureLooks, startLooks } = await import('./looks.svelte.js');
const { t } = await import('../i18n/index.svelte.js');
const { reanchorImage } = await import('./references.js');

const REVIEW_TAKE = new URL('../components/director/ReviewTake.svelte', import.meta.url).href;
const SUMMARY = new URL('../components/director/DirectorSummary.svelte', import.meta.url).href;
const done = (id, shotId) => ({ id, shotId, status: 'done', label: 'draft', quality: 'draft', variant: 'A', url: `/${id}.mp4`, createdAt: '2026-10-29T10:00:00Z' });

function scene(looks, clips = [{ id: 's1', take: 't1' }]) {
	project.id = 'p1';
	ui.workspace = 'director';
	doc.clips = clips.map((clip, n) => ({ start: n * 4, dur: 4, label: `Shot ${n + 1}`, stage: 'draft', ...clip }));
	setTakes('p1', [...new Set(clips.map((clip) => clip.take).filter(Boolean))].map((id) => done(id, clips.find((clip) => clip.take === id).id)));
	lookState.projectId = 'p1';
	lookState.data = normalizeLooks({ embedder: { available: true }, identity: { available: true }, ...looks });
	return lookState.data;
}

after(() => dispose());

const payload = {
	embedder: { model: 'google/siglip-base-patch16-224', available: true },
	thresholds: { seam: 0.7, cast: 0.6 },
	seams: [
		{ shot_id: 's2', previous_id: 's1', from_take: 't1', to_take: 't2', score: 0.52, status: 'done' },
		{ shot_id: 's3', previous_id: 's2', from_take: 't2', to_take: 't3', score: null, status: 'queued' }
	],
	takes: [
		{ take_id: 't2', shot_id: 's2', status: 'done', cards: [{ card_id: 'c1', label: 'Marin', score: 0.55, status: 'done' }, { card_id: 'c2', label: 'Lina', score: null, status: 'no_images' }, { card_id: 'c3', label: 'Malo', score: 0.81, status: 'done' }] },
		{ take_id: 'bad' },
		{ shot_id: 'x' }
	],
	missing: 3,
	queued: -1
};

test('normalizeLooks keeps the seams and takes the server measured, with its thresholds and counts', () => {
	const looks = normalizeLooks(payload);
	assert.deepEqual(looks.embedder, { model: 'google/siglip-base-patch16-224', available: true });
	assert.deepEqual(looks.thresholds, { seam: 0.7, cast: 0.6, face: FACE_LOW, place: PLACE_LOW, final: FINAL_LOW, drift: DRIFT_LOW, pushIn: PUSH_IN_HIGH, identity: IDENTITY_LOW });
	assert.deepEqual(looks.seams[0], { shotId: 's2', previousId: 's1', fromTake: 't1', toTake: 't2', score: 0.52, identity: null, status: 'done' });
	assert.equal(looks.takes.length, 2);
	assert.deepEqual(looks.takes[1], { takeId: 'bad', shotId: null, status: 'missing', cards: [], pushIn: null, identity: null });
	assert.deepEqual([looks.missing, looks.queued], [3, 0]);
	assert.deepEqual(normalizeLooks(null), { embedder: { model: null, available: false }, faces: { model: null, available: false }, identity: { model: null, available: false }, thresholds: { seam: SEAM_LOW, cast: CAST_LOW, face: FACE_LOW, place: PLACE_LOW, final: FINAL_LOW, drift: DRIFT_LOW, pushIn: PUSH_IN_HIGH, identity: IDENTITY_LOW }, seams: [], takes: [], candidates: [], finals: [], drift: [], chains: [], missing: 0, queued: 0 });
});

test('a start image candidate is scored by the mean of its cast cards, and the closest stands out only among two scored ones or more', () => {
	const looks = normalizeLooks({
		...payload,
		candidates: [
			{ take_id: 'k1', shot_id: 's2', status: 'done', cards: [{ card_id: 'c1', label: 'Marin', score: 0.8, status: 'done' }, { card_id: 'c3', label: 'Malo', score: 0.6, status: 'done' }] },
			{ take_id: 'k2', shot_id: 's2', status: 'done', cards: [{ card_id: 'c1', label: 'Marin', score: 0.75, status: 'done' }, { card_id: 'c2', label: 'Lina', score: null, status: 'no_images' }] },
			{ take_id: 'k3', shot_id: 's2', status: 'queued', cards: [{ card_id: 'c1', label: 'Marin', score: null, status: 'queued' }] }
		]
	});
	assert.equal(candidateLook(looks, 't2'), null);
	assert.equal(Math.round(candidateScore(candidateLook(looks, 'k1')) * 100), 70);
	assert.equal(candidateScore(candidateLook(looks, 'k2')), 0.75);
	assert.equal(candidateScore(candidateLook(looks, 'k3')), null);
	assert.equal(bestCandidate(looks, ['k1', 'k2', 'k3']), 'k2');
	assert.equal(bestCandidate(looks, ['k1', 'k3']), null);
	assert.equal(bestCandidate(null, ['k1', 'k2']), null);
});

test('a card is judged by the threshold of how it was measured, a final by its draft, and a take by the other shots of its character', () => {
	const looks = normalizeLooks({
		thresholds: { seam: 0.7, cast: 0.6, face: 0.72, place: 0.5, final: 0.8, drift: 0.75 },
		takes: [
			{
				take_id: 't1',
				shot_id: 's1',
				status: 'done',
				cards: [
					{ card_id: 'c1', label: 'Marin', kind: 'character', method: 'face', seen: 0.75, score: 0.71, status: 'done' },
					{ card_id: 'c2', label: 'Lina', kind: 'character', method: 'whole', seen: 0, score: 0.65, status: 'done' },
					{ card_id: 'p1', label: 'Quai', kind: 'place', method: 'whole', seen: null, score: 0.52, status: 'done' },
					{ card_id: 'c3', label: 'Malo', kind: 'other', method: 'magic', seen: 2, score: 0.9, status: 'done' }
				]
			}
		],
		finals: [{ take_id: 'f1', parent_id: 't1', shot_id: 's1', score: 0.78, face: null, status: 'done' }, { parent_id: 'x' }],
		drift: [{ card_id: 'c1', shot_id: 's1', take_id: 't1', score: 0.7 }, { card_id: 'c1' }]
	});
	const [marin, lina, quay, malo] = looks.takes[0].cards;
	assert.deepEqual([marin.kind, marin.method, marin.seen], ['character', 'face', 0.75]);
	assert.deepEqual([malo.kind, malo.method, malo.seen], ['character', null, null]);
	assert.deepEqual([cardThreshold(looks, marin), cardThreshold(looks, lina), cardThreshold(looks, quay)], [0.72, 0.6, 0.5]);
	assert.deepEqual(lowCards(looks, looks.takes[0]).map((c) => c.cardId), ['c1']);
	assert.equal(lowFinal(looks, finalLook(looks, 'f1')), true);
	assert.equal(finalLook(looks, 't1'), null);
	assert.equal(lowDrift(looks, driftOf(looks, 't1', 'c1')), true);
	assert.equal(driftOf(looks, 't1', 'c2'), null);
	assert.equal(looks.finals.length, 1);
	assert.equal(looks.drift.length, 1);
});

test('a chain look counts for the take the previous shot plays now, and its drifting cards are a face under the drift threshold or another card under its own threshold', () => {
	const looks = normalizeLooks({
		chains: [
			{
				shot_id: 's2',
				previous_id: 's1',
				from_take: 't1',
				cards: [
					{ card_id: 'c1', label: 'Marin', kind: 'character', method: 'face', seen: 1, score: 0.6, status: 'done' },
					{ card_id: 'c2', label: 'Lina', kind: 'character', method: 'whole', seen: null, score: 0.9, status: 'done' },
					{ card_id: 'c3', label: 'Ana', kind: 'character', method: 'face', seen: 1, score: 0.75, status: 'done' },
					{ card_id: 'c4', label: 'Tom', kind: 'character', method: 'whole', seen: null, score: 0.65, status: 'done' },
					{ card_id: 'c5', label: 'Eva', kind: 'character', method: 'face', seen: 1, score: 0.85, status: 'done' },
					{ card_id: 'c6', label: 'Leo', kind: 'character', method: 'face', seen: 1, score: 0.5, status: 'queued' }
				]
			},
			{ shot_id: 's3' }
		]
	});
	assert.equal(looks.chains.length, 1);
	assert.equal(chainLook(looks, { id: 's1', take: 't1' }, { id: 's2' }).fromTake, 't1');
	assert.equal(chainLook(looks, { id: 's1', take: 't9' }, { id: 's2' }), null);
	assert.deepEqual(chainDrifts(looks, { id: 's1', take: 't1' }, { id: 's2' }).map((c) => c.cardId), ['c1', 'c3']);
	assert.deepEqual(chainDrifts(null, { id: 's1', take: 't1' }, { id: 's2' }), []);
	assert.equal(chainThreshold(looks, { kind: 'character', method: 'face' }), DRIFT_LOW);
	assert.equal(chainThreshold(looks, { kind: 'character', method: 'whole' }), CAST_LOW);
	assert.equal(chainThreshold(looks, { kind: 'place', method: 'whole' }), PLACE_LOW);
});

test('the fix of a drifting chain opens the start images of the next shot, focused on the framing of its current one', () => {
	ui.modal = null;
	reanchorImage({ id: 's2' });
	assert.deepEqual({ ...ui.modal }, { type: 'shot', id: 's2', focus: 'reanchor' });
	ui.modal = null;
	reanchorImage(null);
	assert.equal(ui.modal, null);
});

test('a seam look counts only for the takes placed on its two shots now, and warns under the seam threshold', () => {
	const looks = normalizeLooks(payload);
	const s1 = { id: 's1', take: 't1' };
	const s2 = { id: 's2', take: 't2' };
	const found = seamLook(looks, s1, s2);
	assert.equal(found.score, 0.52);
	assert.equal(lowSeam(looks, found), true);
	assert.equal(seamLook(looks, s1, { id: 's2', take: 't9' }), null);
	assert.equal(seamLook(looks, { id: 's1', take: null }, s2), null);
	assert.equal(lowSeam(looks, seamLook(looks, s2, { id: 's3', take: 't3' })), false);
	assert.equal(lowSeam(looks, { ...found, score: 0.71 }), false);
	assert.equal(percent(0.524), 52);
});

test('a take drifts from each card of its cast under the cast threshold, and the placed takes give the issues', () => {
	const looks = normalizeLooks(payload);
	const look = takeLook(looks, 't2');
	assert.deepEqual(lowCards(looks, look).map((c) => c.label), ['Marin']);
	assert.equal(takeLook(looks, 'nope'), null);
	const issues = castIssues(looks, [{ id: 's1', take: 't1' }, { id: 's2', take: 't2' }, { id: 's3', take: null }]);
	assert.deepEqual(issues.map((i) => [i.clip.id, i.takeId, i.card.cardId]), [['s2', 't2', 'c1']]);
	assert.deepEqual(castIssues(null, [{ id: 's2', take: 't2' }]), []);
});

test('a take whose face grows past the push-in threshold is said in its review and in To check', async () => {
	const looks = normalizeLooks({
		thresholds: { push_in: 1.5 },
		takes: [
			{ take_id: 't1', shot_id: 's1', status: 'done', cards: [], push_in: 2.9 },
			{ take_id: 't2', shot_id: 's2', status: 'done', cards: [], push_in: 1.4 },
			{ take_id: 't3', shot_id: 's3', status: 'done', cards: [], push_in: null },
			{ take_id: 't4', shot_id: 's4', status: 'queued', cards: [], push_in: 3 },
			{ take_id: 't5', shot_id: 's5', status: 'done', cards: [], push_in: -2 }
		]
	});
	assert.deepEqual(looks.takes.map((look) => look.pushIn), [2.9, 1.4, null, 3, null]);
	assert.deepEqual(looks.takes.map((look) => pushedIn(looks, look)), [true, false, false, false, false]);
	assert.equal(pushedIn(null, looks.takes[0]), false);
	const clips = ['t1', 't2', 't3', 't4', 't5', null].map((take, n) => ({ id: `s${n + 1}`, take }));
	assert.deepEqual(pushInIssues(looks, clips).map((i) => [i.clip.id, i.takeId, i.pushIn]), [['s1', 't1', 2.9]]);
	assert.deepEqual(pushInIssues(null, clips), []);
	scene({ thresholds: { push_in: 1.5 }, takes: [{ take_id: 't1', shot_id: 's1', status: 'done', cards: [{ card_id: 'c1', label: 'Lina', status: 'done', score: 0.9 }], push_in: 2.9 }] });
	const review = await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: done('t1', 's1') });
	assert.match(review, /data-look-push-in=""/);
	assert.ok(textOf(review).includes(t('panels.director.pick.lookPushIn', { ratio: '2.9' })));
	assert.match(review, /data-keep-framing-next/);
	const summary = await renderComponent(SUMMARY);
	assert.match(summary, /data-look-push-in="s1"/);
	assert.ok(textOf(summary).includes(t('panels.director.check.pushIn', { shot: '01', ratio: '2.9' })));
	doc.clips[0].keepFraming = true;
	assert.doesNotMatch(await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: done('t1', 's1') }), /data-keep-framing-next/);
});

test('a face that changes within a take or across a chained seam, by face recognition, is said in the review and in To check', async () => {
	const looks = normalizeLooks({
		identity: { model: 'glintr100.onnx', available: true },
		thresholds: { identity: 0.6 },
		takes: [
			{ take_id: 't1', shot_id: 's1', status: 'done', cards: [], identity: { score: 0.29, at: 1.5 } },
			{ take_id: 't2', shot_id: 's2', status: 'done', cards: [], identity: { score: 0.74, at: 2 } },
			{ take_id: 't3', shot_id: 's3', status: 'done', cards: [], identity: null },
			{ take_id: 't4', shot_id: 's4', status: 'queued', cards: [], identity: { score: 0.1, at: 1 } },
			{ take_id: 't5', shot_id: 's5', status: 'done', cards: [], identity: { score: 'low' } }
		],
		seams: [
			{ shot_id: 's2', previous_id: 's1', from_take: 't1', to_take: 't2', score: 0.9, identity: 0.35, status: 'done' },
			{ shot_id: 's3', previous_id: 's2', from_take: 't2', to_take: 't3', score: 0.9, identity: 0.8, status: 'done' },
			{ shot_id: 's4', previous_id: 's3', from_take: 't3', to_take: 't4', score: 0.9, identity: null, status: 'done' }
		]
	});
	assert.deepEqual(looks.identity, { model: 'glintr100.onnx', available: true });
	assert.deepEqual(looks.takes.map((look) => look.identity), [{ score: 0.29, at: 1.5 }, { score: 0.74, at: 2 }, null, { score: 0.1, at: 1 }, null]);
	assert.deepEqual(looks.takes.map((look) => faceChanged(looks, look)), [true, false, false, false, false]);
	assert.deepEqual(looks.seams.map((seam) => seamFaceChanged(looks, seam)), [true, false, false]);
	assert.equal(faceChanged(null, looks.takes[0]), false);
	const clips = ['t1', 't2', 't3', 't4', 't5'].map((take, n) => ({ id: `s${n + 1}`, take }));
	assert.deepEqual(identityIssues(looks, clips).map((i) => [i.kind, i.clip.id, i.previous?.id ?? null, i.score]), [['take', 's1', null, 0.29], ['seam', 's2', 's1', 0.35]]);
	assert.deepEqual(identityIssues(null, clips), []);
	scene(
		{
			thresholds: { identity: 0.6 },
			takes: [{ take_id: 't1', shot_id: 's1', status: 'done', cards: [{ card_id: 'c1', label: 'Lina', status: 'done', score: 0.9 }], identity: { score: 0.29, at: 1.5 } }],
			seams: [{ shot_id: 's2', previous_id: 's1', from_take: 't1', to_take: 't2', score: 0.9, identity: 0.35, status: 'done' }]
		},
		[{ id: 's1', take: 't1' }, { id: 's2', take: 't2' }]
	);
	const review = await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: done('t1', 's1') });
	assert.match(review, /data-look-identity=""/);
	assert.ok(textOf(review).includes(t('panels.director.pick.lookIdentity', { score: percent(0.29) })));
	const summary = textOf(await renderComponent(SUMMARY));
	assert.ok(summary.includes(t('panels.director.check.identity', { shot: '01', score: percent(0.29) })));
	assert.ok(summary.includes(t('panels.director.check.identitySeam', { shot: '02', previous: '01', score: percent(0.35) })));
});

test('a take the embedder has not measured offers Measure in its review, and To check counts the takes still to measure', async () => {
	scene({ missing: 2, takes: [{ take_id: 't1', shot_id: 's1', status: 'missing', cards: [{ card_id: 'c1', label: 'Lina', status: 'missing', score: null }] }] });
	const review = await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: done('t1', 's1') });
	assert.match(review, /data-take-looks/);
	assert.ok(textOf(review).includes(t('panels.director.pick.measure')));
	assert.ok(hostUis(review, 'Button').some((props) => props.variant === 'ghost' && props.disabled === false));
	const summary = await renderComponent(SUMMARY);
	assert.match(summary, /data-looks-missing/);
	assert.ok(textOf(summary).includes(t('panels.director.check.looksMissing', { count: 2 })));
	lookState.data = normalizeLooks({ embedder: { available: false }, missing: 2 });
	assert.doesNotMatch(await renderComponent(SUMMARY), /data-looks-missing/);
});

test('every state a look can have is translated in English and in French', () => {
	for (const [locale, panels] of [['en', enPanels], ['fr', frPanels]]) {
		for (const state of STATES.filter((value) => value !== 'done')) assert.ok(panels[`director.pick.lookState.${state}`], `${locale} director.pick.lookState.${state}`);
	}
	const looks = normalizeLooks({ takes: [{ take_id: 't1', status: 'done', cards: [{ card_id: 'c1', label: 'Lina', score: null, status: 'no_images' }, { card_id: 'c2', label: 'Marin', score: null, status: 'strange' }] }] });
	assert.deepEqual(looks.takes[0].cards.map((card) => card.status), ['no_images', 'missing']);
});

test('the alerts of To check are keyed by shot, so two shots that share a take each keep their alert', async () => {
	const card = { cardId: 'c1' };
	assert.equal(issueKey({ clip: { id: 's1' }, takeId: 't1', card }), 'look:s1:t1:c1');
	assert.equal(issueKey({ clip: { id: 's2' }, takeId: 't1', pushIn: 2 }), 'look:s2:t1');
	assert.equal(issueKey({ kind: 'seam', clip: { id: 's2' }, previous: { id: 's1' }, takeId: 't1', score: 0.3 }), 'seam:s2:t1');
	assert.notEqual(issueKey({ kind: 'take', clip: { id: 's2' }, takeId: 't1' }), issueKey({ kind: 'seam', clip: { id: 's2' }, takeId: 't1' }));
	scene(
		{ thresholds: { cast: 0.6, push_in: 1.5 }, takes: [{ take_id: 't1', shot_id: 's1', status: 'done', cards: [{ card_id: 'c1', label: 'Lina', status: 'done', score: 0.3 }], push_in: 2.9 }] },
		[{ id: 's1', take: 't1' }, { id: 's2', take: 't1' }]
	);
	const summary = await renderComponent(SUMMARY);
	assert.deepEqual([...summary.matchAll(/data-look-issue="([^"]+)"/g)].map((m) => m[1]), ['s1', 's2']);
	assert.deepEqual([...summary.matchAll(/data-look-push-in="([^"]+)"/g)].map((m) => m[1]), ['s1', 's2']);
	assert.ok(textOf(summary).includes(t('panels.director.check.castLook', { shot: '02', name: 'Lina', score: percent(0.3) })));
});

test('an older answer of the looks never replaces a newer one, and the poll goes on after a failed answer while looks are queued', async () => {
	const answers = [];
	const asked = () => new Promise((resolve) => answers.push(resolve));
	const looks = (queued, missing = 0) => ({ ok: true, data: normalizeLooks({ embedder: { available: true }, queued, missing }) });
	const settle = () => new Promise((resolve) => setImmediate(resolve));
	bindClient({ looks: asked, measureLooks: async () => looks(2) });
	Object.assign(project, { id: 'p-poll', version: 1 });
	Object.assign(lookState, { projectId: 'p-poll', data: looks(0).data, asking: false });
	mock.timers.enable({ apis: ['setTimeout'] });
	const stop = startLooks();
	try {
		await settle();
		mock.timers.tick(1500);
		assert.equal(answers.length, 1);
		await measureLooks();
		assert.equal(lookState.data.queued, 2);
		answers[0](looks(0, 2));
		await settle();
		assert.deepEqual([lookState.data.queued, lookState.data.missing], [2, 0]);
		mock.timers.tick(8000);
		assert.equal(answers.length, 2);
		answers[1]({ ok: false, error: { status: 500, code: 'server_error', message: '', data: null } });
		await settle();
		assert.equal(lookState.data.queued, 2);
		mock.timers.tick(8000);
		assert.equal(answers.length, 3);
		answers[2](looks(0));
		await settle();
		assert.equal(lookState.data.queued, 0);
		mock.timers.tick(8000);
		assert.equal(answers.length, 3);
	} finally {
		stop();
		mock.timers.reset();
		bindClient(null);
		project.id = null;
	}
});

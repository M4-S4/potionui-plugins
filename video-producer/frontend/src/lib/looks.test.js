import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CAST_LOW, chainDrifts, chainLook, DRIFT_LOW, FACE_LOW, FINAL_LOW, PLACE_LOW, SEAM_LOW, bestCandidate, cardThreshold, driftOf, finalLook, lowDrift, lowFinal, candidateLook, candidateScore, castIssues, lowCards, lowSeam, normalizeLooks, percent, seamLook, takeLook } from './looks.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

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
	assert.deepEqual(looks.thresholds, { seam: 0.7, cast: 0.6, face: FACE_LOW, place: PLACE_LOW, final: FINAL_LOW, drift: DRIFT_LOW });
	assert.deepEqual(looks.seams[0], { shotId: 's2', previousId: 's1', fromTake: 't1', toTake: 't2', score: 0.52, status: 'done' });
	assert.equal(looks.takes.length, 2);
	assert.deepEqual(looks.takes[1], { takeId: 'bad', shotId: null, status: 'missing', cards: [] });
	assert.deepEqual([looks.missing, looks.queued], [3, 0]);
	assert.deepEqual(normalizeLooks(null), { embedder: { model: null, available: false }, faces: { model: null, available: false }, thresholds: { seam: SEAM_LOW, cast: CAST_LOW, face: FACE_LOW, place: PLACE_LOW, final: FINAL_LOW, drift: DRIFT_LOW }, seams: [], takes: [], candidates: [], finals: [], drift: [], chains: [], missing: 0, queued: 0 });
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

test('the candidate window shows the likeness of each candidate and the closest one, and lets the user choose', () => {
	const window = source('../components/shots/KeyframeCandidates.svelte');
	assert.match(window, /data-candidate-look=\{take\.id\}/);
	assert.match(window, /\{#if best === take\.id\}/);
	assert.match(window, /if \(finished\) untrack\(\(\) => refreshLooks\(\)\)/);
	assert.doesNotMatch(window, /acceptCandidate\(best/);
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

test('a chain look counts for the take the previous shot plays now, and its drifting cards are those under their threshold', () => {
	const looks = normalizeLooks({
		chains: [
			{ shot_id: 's2', previous_id: 's1', from_take: 't1', cards: [{ card_id: 'c1', label: 'Marin', kind: 'character', method: 'face', seen: 1, score: 0.6, status: 'done' }, { card_id: 'c2', label: 'Lina', kind: 'character', method: 'whole', seen: null, score: 0.9, status: 'done' }] },
			{ shot_id: 's3' }
		]
	});
	assert.equal(looks.chains.length, 1);
	assert.equal(chainLook(looks, { id: 's1', take: 't1' }, { id: 's2' }).fromTake, 't1');
	assert.equal(chainLook(looks, { id: 's1', take: 't9' }, { id: 's2' }), null);
	assert.deepEqual(chainDrifts(looks, { id: 's1', take: 't1' }, { id: 's2' }).map((c) => c.cardId), ['c1']);
	assert.deepEqual(chainDrifts(null, { id: 's1', take: 't1' }, { id: 's2' }), []);
});

test('a drifting chain is a seam issue whose fix opens the start images of the next shot with its current one as the framing', () => {
	assert.match(source('./continuity.svelte.js'), /if \(drift\) out\.issues\.push\(\{ kind: 'chain_drift'/);
	assert.match(source('../components/storyboard/SeamFix.svelte'), /\{:else if issue\.kind === 'chain_drift'\}\n\t<button type="button" class=\{link\} data-seam-fix="reanchor" onclick=\{\(e\) => run\(e, reanchorImage\)\}>/);
	assert.match(source('./references.js'), /export function reanchorImage\(clip\) \{\n\tif \(clip\) ui\.modal = \{ type: 'shot', id: clip\.id, focus: 'reanchor' \};/);
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

test('wiring: the measured look feeds the seams, the review, To check and the Storyboard, and is no longer simulated', () => {
	const continuity = source('./continuity.svelte.js');
	assert.doesNotMatch(continuity, /look === rb\.look|0\.94 : 0\.78/);
	assert.match(continuity, /const found = seamLook\(looks, a, b\);/);
	assert.match(continuity, /if \(look\?\.low\) out\.issues\.push\(\{ kind: 'identity'/);
	assert.match(source('./assistant.js'), /const MEASURED_KINDS = \['lum', 'warm', 'identity'\];/);
	assert.doesNotMatch(source('./assistant.js'), /SIMULATED_KINDS|simulated/);
	assert.doesNotMatch(source('../components/modals/Modals.svelte'), /simulations/);
	assert.doesNotMatch(source('../components/director/DirectorSummary.svelte'), /vp-sim|simulatedTip/);
	assert.match(source('../components/storyboard/SeamPanel.svelte'), /\{#if issue\.kind === 'identity'\}<span class="mt-0\.5 block text-2xs text-fg-subtle" data-look-hint>\{t\('lib\.continuity\.lookHint'\)\}/);
	const take = source('../components/director/ReviewTake.svelte');
	assert.match(take, /\{#if look\?\.cards\.length \|\| fromDraft\?\.status === 'done'\}\n\t<section class="space-y-2" data-take-looks>/);
	assert.match(take, /onclick: measureLooks \}\}>\{t\('panels\.director\.pick\.measure'\)\}/);
	const summary = source('../components/director/DirectorSummary.svelte');
	assert.match(summary, /const lookIssues = \$derived\(castIssues\(looks, doc\.clips\)\);/);
	assert.match(summary, /t\('panels\.director\.check\.castLook', \{ shot: num\(item\.clip\), name: item\.card\.label, score: percent\(item\.card\.score\) \}\)/);
	assert.match(summary, /i\.kind === 'identity' \? t\('assistant\.review\.measuredLookTip'\) : seamTip\(s\.toShotId\)/);
	assert.match(summary, /data-looks-missing/);
	const page = source('../VideoProducerPage.svelte');
	assert.match(page, /const stopLooks = startLooks\(\);/);
	assert.match(page, /stopProduction\(\);\n\t\t\tstopLooks\(\);/);
	const store = source('./looks.svelte.js');
	assert.match(store, /onTake\(\(take, live\) => live && take\.status === 'done' && schedule\(\)\)/);
	assert.match(source('./api.js'), /async measureLooks\(projectId\) \{\n\t\t\treturn mapped\(await call\(api, 'post', `\$\{projectPath\(projectId\)\}\/looks`, \{\}\), normalizeLooks\);/);
});

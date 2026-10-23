import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { aggregate, activityStep } from './generation.js';
import { canLabel, labelGroups, labelOf, legacyLabel, marksOf, rejectedCount, relabel, toggledLabel, visibleTakes } from './labels.js';
import {
	MAX_DRAFTS,
	applyShotDraft,
	draftsOf,
	excludedOf,
	generationCounts,
	inputsChanged,
	isStale,
	migrateShots,
	revisionOf,
	sentReferences,
	setDrafts,
	setExcluded,
	sharedDrafts,
	shotDraft,
	shotReferences,
	shotStale,
	takeCount,
	touch
} from './shots.js';
import { migrate } from './starter.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const take = (id, extra = {}) => ({ id, shotId: 's1', status: 'done', url: `/v/${id}.mp4`, label: 'draft', ...extra });

test('labels: the former marks give the label, a stored label wins over them', () => {
	assert.deepEqual([legacyLabel(true, null), legacyLabel(1, 'reject'), legacyLabel(false, 'keep'), legacyLabel(0, 'reject'), legacyLabel(false, null)], ['final', 'final', 'candidate', 'rejected', 'draft']);
	assert.equal(labelOf({ label: 'rejected', chosen: true }), 'rejected');
	assert.equal(labelOf({ label: 'best', flag: 'keep' }), 'candidate');
	assert.equal(labelOf(null), 'draft');
	assert.deepEqual(marksOf('candidate'), { label: 'candidate', chosen: false, flag: 'keep' });
	assert.deepEqual(marksOf('final'), { label: 'final', chosen: true, flag: null });
});

test('labels: one final per shot, the previous final of the shot turns candidate, other shots keep theirs', () => {
	const takes = [take('a', { label: 'final' }), take('b'), take('c', { label: 'rejected' }), take('d', { shotId: 's2', label: 'final' })];

	assert.deepEqual(relabel(takes, 'b', 'final'), { b: 'final', a: 'candidate' });
	assert.deepEqual(relabel(takes, 'c', 'candidate'), { c: 'candidate' });
	assert.deepEqual(relabel(takes, 'x', 'final'), {});
	assert.deepEqual(relabel(takes, 'b', 'keep'), {});
});

test('labels: final needs a finished take with a video, and the final take keeps its label until another one is final', () => {
	assert.equal(canLabel(take('a'), 'final'), true);
	assert.equal(canLabel(take('a', { status: 'running' }), 'final'), false);
	assert.equal(canLabel(take('a', { url: null }), 'final'), false);
	assert.equal(canLabel(take('a', { status: 'failed' }), 'rejected'), true);
	assert.equal(canLabel(take('a', { label: 'final' }), 'rejected'), false);
	assert.equal(canLabel(take('a', { label: 'final' }), 'candidate'), false);
	assert.deepEqual([toggledLabel(take('a'), 'rejected'), toggledLabel(take('a', { label: 'rejected' }), 'rejected'), toggledLabel(take('a', { label: 'candidate' }), 'candidate'), toggledLabel(take('a', { label: 'final' }), 'final')], ['rejected', 'draft', 'draft', 'final']);
});

test('labels: the takes are grouped final, candidates, drafts, rejected, and the rejected ones can be hidden', () => {
	const takes = [take('a'), take('b', { label: 'rejected' }), take('c', { label: 'final' }), take('d', { label: 'candidate' }), take('e', { flag: 'reject', label: undefined })];

	assert.deepEqual(labelGroups(takes).map(([label, list]) => [label, list.map((x) => x.id)]), [['final', ['c']], ['candidate', ['d']], ['draft', ['a']], ['rejected', ['b', 'e']]]);
	assert.deepEqual(labelGroups(takes, true).map(([label]) => label), ['final', 'candidate', 'draft']);
	assert.deepEqual(visibleTakes(takes, true).map((x) => x.id), ['a', 'c', 'd']);
	assert.equal(visibleTakes(takes, false).length, 5);
	assert.equal(rejectedCount(takes), 2);
});

test('drafts: a shot keeps its own number from 1 to 8, else the project number', () => {
	const engine = { variants: 2 };

	assert.deepEqual([draftsOf({}, engine), draftsOf({ drafts: 5 }, engine), draftsOf({ drafts: 12 }, engine), draftsOf({ drafts: 0 }, engine), draftsOf({ drafts: 2.5 }, engine), draftsOf({}, {})], [2, 5, 8, 1, 2, 1]);
	assert.equal(MAX_DRAFTS, 8);
	assert.equal(sharedDrafts([{ drafts: 3 }, { drafts: 3 }], engine), 3);
	assert.equal(sharedDrafts([{ drafts: 3 }, {}], engine), null);
	const clips = [{ id: 's1' }, { id: 's2', drafts: 4 }];
	assert.equal(setDrafts(clips, '6'), true);
	assert.deepEqual(clips.map((c) => c.drafts), [6, 6]);
	assert.equal(setDrafts(clips, 'x'), false);
});

test('drafts: the request gives the project number and only the shots that differ from it, or one forced number', () => {
	const engine = { variants: 2 };
	const clips = [{ id: 's1' }, { id: 's2', drafts: 4 }, { id: 's3', drafts: 2 }];

	assert.deepEqual(generationCounts(clips, engine), { variants: 2, shot_variants: { s2: 4 } });
	assert.deepEqual(generationCounts(clips, engine, 3), { variants: 3, shot_variants: {} });
	assert.deepEqual(generationCounts([{ id: 's1', drafts: 8 }], { variants: 9 }), { variants: 8, shot_variants: {} });
	assert.equal(takeCount(clips, engine), 8);
});

test('drafts: the page sends the counts of the shots in the generate and estimate requests', () => {
	const production = source('./production.svelte.js');

	assert.match(production, /if \(Object\.keys\(counts\.shot_variants\)\.length\) body\.shot_variants = counts\.shot_variants;/);
	assert.match(production, /requestBody\(clips, ui\.production\.quality, generationCounts\(clips, doc\.engine\), option\)/);
	assert.match(production, /const counts = generationCounts\(clips, doc\.engine, opts\.variants\);/);
});

test('references: a shot inherits the global references, may exclude some, and keeps its own', () => {
	const doc = {
		references: [
			{ id: 'g1', scope: { type: 'global' } },
			{ id: 'g2', scope: null },
			{ id: 'o1', scope: { type: 'shot', shotId: 's1' } },
			{ id: 'o2', scope: { type: 'shot', shotId: 's2' } }
		]
	};
	const clip = { id: 's1', referenceOverrides: { exclude: ['g2', 'gone'] } };

	const { inherited, own } = shotReferences(doc, clip);
	assert.deepEqual(inherited.map((x) => [x.reference.id, x.excluded]), [['g1', false], ['g2', true]]);
	assert.deepEqual(own.map((r) => r.id), ['o1']);
	assert.deepEqual(sentReferences(doc, clip).map((r) => r.id), ['o1', 'g1']);
	assert.deepEqual(excludedOf({ referenceOverrides: { exclude: 'g1' } }), []);
});

test('references: the overrides keep their other keys and vanish when nothing is excluded', () => {
	const clip = { id: 's1' };
	setExcluded(clip, ['g1', 'g1', '', 'g2']);
	assert.deepEqual(clip.referenceOverrides, { exclude: ['g1', 'g2'] });
	setExcluded(clip, []);
	assert.equal('referenceOverrides' in clip, false);
	const extended = { id: 's1', referenceOverrides: { exclude: ['g1'], audio: { lane: 'A1' } } };
	setExcluded(extended, []);
	assert.deepEqual(extended.referenceOverrides, { audio: { lane: 'A1' } });
});

test('revision: an edit bumps the revision of the shot, a take older than it is stale', () => {
	const clip = { id: 's1' };
	assert.equal(revisionOf(clip), 0);
	touch(clip);
	touch(clip);
	assert.equal(clip.revision, 2);
	assert.equal(isStale({ shotRevision: 1 }, clip), true);
	assert.equal(isStale({ shotRevision: 2 }, clip), false);
	assert.equal(isStale({}, { revision: 0 }), false);
	assert.equal(isStale({ shotRevision: 3 }, { revision: -1 }), false);
});

test('revision: the card of a shot is stale when its placed take, else every finished take, predates the edit', () => {
	const clip = { id: 's1', take: 'a', revision: 2 };
	const old = take('a', { shotRevision: 1 });
	const fresh = take('b', { shotRevision: 2 });

	assert.equal(shotStale(clip, [old, fresh]), true);
	assert.equal(shotStale({ ...clip, take: 'b' }, [old, fresh]), false);
	assert.equal(shotStale({ ...clip, take: null }, [old, fresh]), false);
	assert.equal(shotStale({ ...clip, take: null }, [old]), true);
	assert.equal(shotStale({ ...clip, take: null }, [take('c', { status: 'running' })]), false);
	assert.equal(shotStale({ ...clip, take: null }, [old, take('f', { label: 'final', shotRevision: 2 })]), false);
});

function editorDoc() {
	return {
		clips: [{ id: 's1', start: 0, dur: 4, srcIn: 0, take: null }, { id: 's2', start: 4, dur: 4, srcIn: 0, take: null }],
		prompts: [{ id: 'p1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'A lighthouse.' }],
		frames: [{ id: 'f1', shotId: 's1', time: 0, assetId: 'img1', role: 'Début', strength: 75, sceneId: 'sc1' }],
		references: [{ id: 'g1', name: 'Hero', space: 'identite', type: 'Personnage', assetId: 'img1', role: 'Identité', scope: { type: 'global' } }, { id: 'o1', name: 'Hat', space: 'identite', type: 'Objet', assetId: 'img2', role: 'Identité', scope: { type: 'shot', shotId: 's1' } }],
		engine: { variants: 2 }
	};
}

test('shot editor: the draft reads the prompt, the frames, the references and the drafts of the shot', () => {
	const doc = editorDoc();

	assert.deepEqual(shotDraft(doc, doc.clips[0], doc.engine), {
		text: 'A lighthouse.',
		dur: 4,
		first: 'img1',
		last: null,
		exclude: [],
		own: [{ id: 'o1', name: 'Hat', space: 'identite', type: 'Objet', assetId: 'img2', role: 'Identité' }],
		drafts: 2,
		engine: {}
	});
});

test('shot editor: saving writes every field and bumps the revision only when what the take was made from changed', () => {
	const doc = editorDoc();
	const clip = doc.clips[0];
	const before = shotDraft(doc, clip, doc.engine);
	let n = 0;
	const makeId = () => `new${++n}`;

	assert.deepEqual(applyShotDraft(doc, clip, before, { ...before, drafts: 4 }, { makeId, engine: doc.engine }), { changed: false, resized: false });
	assert.deepEqual([clip.drafts, revisionOf(clip)], [4, 0]);

	const after = { ...shotDraft(doc, clip, doc.engine), text: ' A lighthouse at dusk. ', dur: 5.01, last: 'img3', exclude: ['g1'], own: [{ id: 'o2', name: 'Cat', space: 'identite', type: 'Personnage', assetId: 'img4', role: 'Identité' }] };
	const result = applyShotDraft(doc, clip, shotDraft(doc, clip, doc.engine), after, { makeId, maxDur: 60, engine: doc.engine });

	assert.deepEqual(result, { changed: true, resized: true });
	assert.equal(revisionOf(clip), 1);
	assert.deepEqual([doc.prompts[0].text, doc.prompts[0].dur, clip.dur], ['A lighthouse at dusk.', 5, 5]);
	assert.deepEqual(doc.frames.map((f) => [f.role, f.assetId, f.time, f.sceneId ?? null]), [['first', 'img1', 0, 'sc1'], ['last', 'img3', 4.96, null]]);
	assert.deepEqual(clip.referenceOverrides, { exclude: ['g1'] });
	assert.deepEqual(doc.references.map((r) => [r.id, r.scope.type]), [['g1', 'global'], ['o2', 'shot']]);
});

test('shot editor: the duration stays within the media, a removed frame goes, an empty shot gets its first prompt', () => {
	const doc = editorDoc();
	const clip = doc.clips[1];
	const before = shotDraft(doc, clip, doc.engine);

	applyShotDraft(doc, clip, before, { ...before, text: 'A storm.', dur: 30 }, { makeId: () => 'p2', maxDur: 6, engine: doc.engine });
	assert.equal(clip.dur, 6);
	assert.deepEqual(doc.prompts.find((p) => p.shotId === 's2'), { id: 'p2', shotId: 's2', start: 4, dur: 6, strength: 75, text: 'A storm.' });

	const first = doc.clips[0];
	const kept = shotDraft(doc, first, doc.engine);
	applyShotDraft(doc, first, kept, { ...kept, first: null }, { makeId: () => 'x', engine: doc.engine });
	assert.deepEqual(doc.frames, []);
});

test('shot editor: a change of prompt, duration, frame, exclusion or own reference counts, a change of drafts does not', () => {
	const base = { text: 'A', dur: 4, first: null, last: null, exclude: ['g1'], own: [{ id: 'o1', assetId: 'i', type: 'Objet' }], drafts: 2 };

	assert.equal(inputsChanged(base, { ...base, text: ' A ', exclude: ['g1'], drafts: 6 }), false);
	for (const change of [{ text: 'B' }, { dur: 4.04 }, { first: 'i' }, { last: 'i' }, { exclude: [] }, { own: [] }, { own: [{ id: 'o1', assetId: 'i', type: 'Style' }] }]) assert.equal(inputsChanged(base, { ...base, ...change }), true, JSON.stringify(change));
});

test('migrate: malformed shot fields are dropped so the document validates, good ones kept', () => {
	const doc = { clips: [{ id: 's1', drafts: 3, revision: 2, referenceOverrides: { exclude: ['g1', 'g1'] } }, { id: 's2', drafts: 40, revision: -1, referenceOverrides: { exclude: [] } }, { id: 's3', drafts: '2', referenceOverrides: null }] };

	assert.deepEqual(migrateShots(doc).clips, [{ id: 's1', drafts: 3, revision: 2, referenceOverrides: { exclude: ['g1'] } }, { id: 's2' }, { id: 's3' }]);
	assert.deepEqual(migrate(doc).clips[1], { id: 's2', mute: false });
	assert.equal(migrateShots(null), null);
});

test('progress: the shot activity averages the takes in flight and names the step of a running take', () => {
	const activity = aggregate([{ status: 'running', progress: 60, step: 'Sampling · 12/20' }, { status: 'queued' }, { status: 'done', progress: 100 }, { status: 'running', progress: 140 }]);

	assert.deepEqual(activity, { state: 'running', progress: 160 / 3, step: 'Sampling · 12/20', count: 3, running: 2 });
	assert.equal(activityStep(activity), 'Sampling · 12/20');
	assert.equal(activityStep(aggregate([{ status: 'queued' }])), '');
	assert.equal(activityStep(aggregate([{ status: 'done' }])), '');
});

test('progress: the timeline block and the storyboard card show the same shot activity', () => {
	const timeline = source('../components/timeline/Timeline.svelte');
	const storyboard = source('../components/storyboard/StoryboardView.svelte');

	assert.match(timeline, /import \{ takesOf, shotActivity, shotEngineText \} from '\.\.\/\.\.\/lib\/production\.svelte\.js';/);
	assert.match(timeline, /\{@const activity = shotActivity\(c\.id\)\}/);
	assert.match(timeline, /\{#if activity\.state === 'running'\}/);
	for (const page of [timeline, storyboard]) assert.match(page, /activityStep\(activity\) \|\| \(activity\.running \? t\('generation\.state\.running'\) : t\('lib\.status\.queued'\)\)/);
});

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent } from './svelte-harness.js';
import { aggregate, activityStep } from './generation.js';
import { canLabel, finalsToSync, labelGroups, labelOf, legacyLabel, marksOf, rejectedCount, relabel, releasedLabel, toggledLabel, visibleTakes } from './labels.js';
import {
	MAX_DRAFTS,
	SHOT_CAP,
	applyShotDraft,
	draftsOf,
	durationLimit,
	excludedOf,
	generationCounts,
	inputsChanged,
	isStale,
	migrateShots,
	overrunsTake,
	releaseOverrun,
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

const take = (id, extra = {}) => ({ id, shotId: 's1', status: 'done', url: `/v/${id}.mp4`, label: 'draft', ...extra });

const { doc, ui, act, undo, dispose } = await import('./state.svelte.js');
const { project, bindClient } = await import('./project.svelte.js');
const { estimateRequest, startGeneration, startProduction } = await import('./production.svelte.js');
const { setTakes, takeStore } = await import('./takes.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

after(() => {
	dispose();
	bindClient(null);
});

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

test('references: a shot sends the pictures of the cards it casts whatever their scope, and not a global picture of a card it leaves out of its cast', () => {
	const doc = {
		references: [
			{ id: 'style', scope: { type: 'global' } },
			{ id: 'c-face', scope: { type: 'global' } },
			{ id: 'f-back', scope: { type: 'shot', shotId: 's2' } },
			{ id: 'f-face', scope: { type: 'global' } },
			{ id: 'quay', scope: { type: 'global' } },
			{ id: 'own', scope: { type: 'shot', shotId: 's1' } }
		],
		bible: {
			characters: [
				{ id: 'cyclist', label: 'Cyclist', references: ['c-face'] },
				{ id: 'fisher', label: 'Fisherman', references: ['f-face', 'f-back', 'gone'] },
				{ id: 'nameless', label: '', references: ['style'] }
			],
			places: [{ id: 'harbour', label: 'Quay', references: ['quay'] }]
		}
	};
	const clip = { id: 's1', cast: { characters: ['fisher'], place: 'harbour' }, referenceOverrides: { exclude: ['f-back'] } };

	const { inherited, cast, own } = shotReferences(doc, clip);
	assert.deepEqual(cast.map((x) => [x.reference.id, x.excluded]), [['f-face', false], ['f-back', true], ['quay', false]]);
	assert.deepEqual(inherited.map((x) => [x.reference.id, x.cast, x.notCast]), [['style', false, false], ['c-face', false, true], ['f-face', true, false], ['quay', true, false]]);
	assert.deepEqual(own.map((r) => r.id), ['own']);
	assert.deepEqual(sentReferences(doc, clip).map((r) => r.id), ['own', 'f-face', 'quay', 'style']);
	assert.deepEqual(sentReferences(doc, { ...clip, cast: { characters: ['cyclist'] } }).map((r) => r.id), ['own', 'c-face', 'style']);
	assert.deepEqual(shotReferences(doc, clip, [], { characters: [] }).cast, []);
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
		frames: [{ id: 'f1', shotId: 's1', time: 0, assetId: 'img1', role: 'Début', strength: 75 }],
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
		excludeLanes: [],
		excludeVrefs: [],
		own: [{ id: 'o1', name: 'Hat', space: 'identite', type: 'Objet', assetId: 'img2', role: 'Identité' }],
		drafts: 2,
		engine: {},
		cast: { characters: [], place: null },
		dialogue: [],
		referencePrompt: null,
		firstFromPrevious: null,
		keepFraming: false,
		speed: 1
	});
});

test('shot editor: saving writes every field and bumps the revision only when what the take was made from changed', () => {
	const doc = editorDoc();
	const clip = doc.clips[0];
	const before = shotDraft(doc, clip, doc.engine);
	let n = 0;
	const makeId = () => `new${++n}`;

	assert.deepEqual(applyShotDraft(doc, clip, before, { ...before, drafts: 4 }, { makeId, engine: doc.engine }), { changed: false, resized: false, released: null });
	assert.deepEqual([clip.drafts, revisionOf(clip)], [4, 0]);

	const after = { ...shotDraft(doc, clip, doc.engine), text: ' A lighthouse at dusk. ', dur: 5.01, last: 'img3', exclude: ['g1'], own: [{ id: 'o2', name: 'Cat', space: 'identite', type: 'Personnage', assetId: 'img4', role: 'Identité' }] };
	const result = applyShotDraft(doc, clip, shotDraft(doc, clip, doc.engine), after, { makeId, maxDur: 60, engine: doc.engine });

	assert.deepEqual(result, { changed: true, resized: true, released: null });
	assert.equal(revisionOf(clip), 1);
	assert.deepEqual([doc.prompts[0].text, doc.prompts[0].dur, clip.dur], ['A lighthouse at dusk.', 5, 5]);
	assert.deepEqual(doc.frames.map((f) => [f.role, f.assetId, f.time]), [['first', 'img1', 0], ['last', 'img3', 4.96]]);
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

function takeDoc() {
	const doc = editorDoc();
	doc.assets = [
		{ id: 'src', kind: 'video', generated: false, srcDur: 6 },
		{ id: 'gen-t1', kind: 'video', generated: true, srcDur: 4.375 },
		{ id: 'still', kind: 'image', generated: false, srcDur: null }
	];
	Object.assign(doc.clips[0], { assetId: 'gen-t1', take: 't1', stage: 'final', dur: 4.4 });
	doc.prompts[0].dur = 4.4;
	Object.assign(doc.clips[1], { assetId: 'src', stage: 'source', srcIn: 1 });
	return doc;
}

test('shot duration: a source bounds the shot, a generated take leaves it free up to the engine of the shot', () => {
	const doc = takeDoc();
	const [shot, source] = doc.clips;

	assert.deepEqual(durationLimit(doc, source, 15), { max: 5, by: 'source', take: null });
	assert.deepEqual(durationLimit(doc, shot, 15), { max: 15, by: 'engine', take: 4.375 });
	assert.deepEqual(durationLimit(doc, shot, null), { max: SHOT_CAP, by: null, take: 4.375 });
	assert.deepEqual(durationLimit(doc, { ...source, assetId: 'still', srcIn: 0 }, 15), { max: SHOT_CAP, by: null, take: null });
	assert.deepEqual(durationLimit(doc, { id: 's3', assetId: null, srcIn: 0 }, 15), { max: SHOT_CAP, by: null, take: null });

	const before = shotDraft(doc, source, doc.engine);
	assert.deepEqual(applyShotDraft(doc, source, before, { ...before, dur: 30 }, { makeId: () => 'p2', maxDur: durationLimit(doc, source, 15).max, engine: doc.engine }).released, null);
	assert.deepEqual([source.dur, source.assetId, source.stage], [5, 'src', 'source']);
});

test('shot duration: past its take a generated shot goes back to be generated, the take staying in the history', () => {
	const doc = takeDoc();
	const shot = doc.clips[0];
	const maxDur = durationLimit(doc, shot, 15).max;
	const before = shotDraft(doc, shot, doc.engine);

	const result = applyShotDraft(doc, shot, before, { ...before, dur: 8 }, { makeId: () => 'x', maxDur, engine: doc.engine });
	assert.deepEqual(result, { changed: true, resized: true, released: { take: 't1' } });
	assert.deepEqual([shot.dur, shot.assetId, shot.take, shot.srcIn, shot.stage], [8, null, null, 0, 'todo']);
	assert.deepEqual([doc.prompts[0].dur, doc.frames[0].time], [8, 0]);
	assert.ok(doc.assets.some((a) => a.id === 'gen-t1'));

	const capped = takeDoc();
	const long = capped.clips[0];
	const draft = shotDraft(capped, long, capped.engine);
	applyShotDraft(capped, long, draft, { ...draft, dur: 30 }, { makeId: () => 'x', maxDur: durationLimit(capped, long, 15).max, engine: capped.engine });
	assert.deepEqual([long.dur, long.stage], [15, 'todo']);
});

test('shot duration: within its take, or by less than a frame step, a generated shot keeps its take', () => {
	for (const dur of [4.2, 2, 4.4]) {
		const doc = takeDoc();
		const shot = doc.clips[0];
		const before = shotDraft(doc, shot, doc.engine);
		const result = applyShotDraft(doc, shot, before, { ...before, text: 'A storm.', dur }, { makeId: () => 'x', maxDur: 15, engine: doc.engine });
		assert.equal(result.released, null, String(dur));
		assert.deepEqual([shot.dur, shot.assetId, shot.take, shot.stage], [dur, 'gen-t1', 't1', 'final']);
	}

	const doc = takeDoc();
	const shot = Object.assign(doc.clips[0], { dur: 4 });
	shot.dur = 4.4;
	assert.equal(releaseOverrun(doc, shot, 4), null);
	shot.dur = 4.44;
	assert.deepEqual(releaseOverrun(doc, shot, 4), { take: 't1' });
	assert.equal(shot.stage, 'todo');

	assert.equal(overrunsTake(4.375, 6, 5), false);
	assert.equal(overrunsTake(null, 4, 8), false);
	assert.equal(overrunsTake(4, 4, 4.08), true);
});

test('shot duration: a released Final or Candidate take turns Draft, the other takes of the shot keep their label', () => {
	assert.deepEqual([take('a', { label: 'final' }), take('b', { label: 'candidate' }), take('c', { chosen: true, label: undefined })].map(releasedLabel), ['draft', 'draft', 'draft']);
	assert.deepEqual([take('d'), take('e', { label: 'rejected' }), null].map(releasedLabel), [null, null, null]);

	const takes = [take('a', { label: 'final' }), take('b', { label: 'candidate' })];
	assert.deepEqual(relabel(takes, 'a', releasedLabel(takes[0])), { a: 'draft' });
	assert.deepEqual(finalsToSync([{ id: 's1', take: null }], [take('a', { label: 'draft' }), take('b', { label: 'candidate' })]), []);
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

const GRID = new URL('../components/storyboard/StoryboardView.svelte', import.meta.url).href;
const TIMELINE = new URL('../components/timeline/Timeline.svelte', import.meta.url).href;
const WAN = '01KX47WANVIDEO0000000000TV';
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function scene(clips) {
	project.id = 'p1';
	project.version = 1;
	project.status = 'saved';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	Object.assign(ui, { workspace: 'storyboard', storyView: 'grid', selection: null, picked: [], dirty: false, modal: null, menuOpen: null, toasts: [], pxPerSec: 60 });
	Object.assign(ui.production, { target: 'sequence', quality: 'draft', state: 'ready', progress: 0, running: 0, step: '', lastCount: 0, startedAt: null, lastSeconds: null, failed: 0, failedVariant: null, failedTake: null });
	doc.engine = { backend: 'native', preset: WAN, model: null, variants: 2 };
	doc.direction.univers = 'A harbour at dawn.';
	doc.clips = clips.map((clip, i) => ({ start: i * 4, dur: 4, label: `Shot ${i + 1}`, stage: 'todo', take: null, assetId: null, ...clip }));
	doc.prompts = doc.clips.map((c, i) => ({ id: `p${i + 1}`, shotId: c.id, start: c.start, dur: 4, strength: 75, text: `Shot ${i + 1} at dawn.` }));
	doc.frames = [];
}

test('labels: after an undo or a redo the final follows the take the shot plays, and a shot that plays none keeps no final', async () => {
	const takes = [take('a', { label: 'final' }), take('b', { label: 'candidate' }), take('c', { shotId: 's2', label: 'final' }), take('d', { shotId: 's3' }), take('e', { shotId: 's4', status: 'running', url: null })];
	const clips = [{ id: 's1', take: 'b' }, { id: 's2', take: null }, { id: 's3', take: 'd' }, { id: 's4', take: 'e' }];

	assert.deepEqual(finalsToSync(clips, takes), [['b', 'final'], ['c', 'candidate'], ['d', 'final']]);
	assert.deepEqual(finalsToSync([{ id: 's1', take: 'a' }], takes), []);

	scene([{ id: 's1', take: 'b', assetId: 'gen-b', stage: 'draft' }]);
	const sent = [];
	bindClient({
		async labelTake(projectId, takeId, label) {
			sent.push([projectId, takeId, label]);
			return { ok: true, data: { ...takeStore.list.find((x) => x.id === takeId), ...marksOf(label) } };
		}
	});
	const stop = startProduction();
	setTakes('p1', [take('a', { label: 'final' }), take('b', { label: 'candidate' })]);
	act(() => (doc.clips[0].label = 'Shot 1 bis'));
	assert.deepEqual(sent, []);
	undo();
	await settle();
	assert.deepEqual(sent, [['p1', 'b', 'final']]);
	assert.deepEqual(takeStore.list.map(labelOf), ['candidate', 'final']);
	stop();
	bindClient(null);
});

test('drafts: the page sends the counts of the shots in the generate and estimate requests', async () => {
	scene([{ id: 's1', drafts: 3 }, { id: 's2' }, { id: 's3', drafts: 1 }]);
	const sent = [];
	bindClient({
		async saveProject(id, next, version) {
			return { ok: true, data: { version: version + 1, updatedAt: '2026-10-29T10:00:00Z' } };
		},
		async generate(id, body) {
			sent.push(body);
			return { ok: true, data: [] };
		}
	});

	const request = estimateRequest();
	assert.deepEqual([request.body.shots, request.body.variants, request.body.shot_variants], [['s1', 's2', 's3'], 2, { s1: 3, s3: 1 }]);

	await startGeneration();
	await startGeneration({ variants: 4 });
	assert.deepEqual(sent.map((body) => [body.shots, body.variants, body.shot_variants]), [[['s1', 's2', 's3'], 2, { s1: 3, s3: 1 }], [['s1', 's2', 's3'], 4, undefined]]);
	assert.ok(!('shot_variants' in sent[1]));
	bindClient(null);
});

test('progress: the timeline block and the storyboard card show the same shot activity', async () => {
	scene([{ id: 's1' }, { id: 's2' }, { id: 's3' }]);
	const flying = (id, shotId, extra = {}) => ({ id, shotId, status: 'queued', label: 'draft', quality: 'draft', variant: 'A', url: null, generationId: null, progress: 0, createdAt: '2026-10-29T10:00:00Z', ...extra });
	setTakes('p1', [flying('r1', 's1', { status: 'running', generationId: 'g1', progress: 40, step: 'Sampling' }), flying('q1', 's1', { variant: 'B' }), flying('q2', 's2'), take('d1', { shotId: 's3' })]);
	assert.deepEqual(doc.clips.map((c) => activityStep(aggregate(takeStore.list.filter((x) => x.shotId === c.id)))), ['Sampling', '', '']);

	const grid = clean(await renderComponent(GRID));
	const cards = grid.split('data-story-shot="').slice(1);
	const gridActivity = cards.map((card) => {
		const text = card.match(/<span class="max-w-\[90%\] truncate text-xs text-white"[^>]*>([^<]*)<\/span>/);
		const bar = card.match(/role="progressbar"[^>]*aria-valuemax="100"( aria-valuenow="(\d+)")?/);
		return [card.slice(0, card.indexOf('"')), text ? text[1] : null, bar ? (bar[2] ? Number(bar[2]) : null) : undefined];
	});

	const timeline = clean(await renderComponent(TIMELINE));
	const blocks = timeline.split('<div class="vp-touch-none group absolute bottom-1 top-1 ').slice(1);
	const timelineActivity = blocks.map((block) => {
		const name = block.match(/aria-label="Shot ([^"]*?), /);
		const text = block.match(/<span class="min-w-0 truncate">([^<]*)<\/span>/);
		const bar = block.match(/role="progressbar"[^>]*aria-valuemax="100"( aria-valuenow="(\d+)")?/);
		return [doc.clips.find((c) => c.label === name[1]).id, text ? text[1] : null, bar ? (bar[2] ? Number(bar[2]) : null) : undefined];
	});

	assert.deepEqual(gridActivity, [['s1', 'Sampling', 20], ['s2', t('lib.status.queued'), null], ['s3', null, undefined]]);
	assert.deepEqual(timelineActivity, gridActivity);
});

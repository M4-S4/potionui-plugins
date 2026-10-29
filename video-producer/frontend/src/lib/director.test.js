import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { clean, hostUis, renderComponent, textOf } from './svelte-harness.js';
import enPanels from '../i18n/en/panels.json' with { type: 'json' };
import frPanels from '../i18n/fr/panels.json' with { type: 'json' };
import enInspector from '../i18n/en/inspector.json' with { type: 'json' };
import frInspector from '../i18n/fr/inspector.json' with { type: 'json' };
import enLib from '../i18n/en/lib.json' with { type: 'json' };
import frLib from '../i18n/fr/lib.json' with { type: 'json' };
import enProduction from '../i18n/en/production.json' with { type: 'json' };
import frProduction from '../i18n/fr/production.json' with { type: 'json' };
import enCommands from '../i18n/en/commands.json' with { type: 'json' };
import frCommands from '../i18n/fr/commands.json' with { type: 'json' };
import { CHARACTERS, PLACES, castOf } from './bible.js';
import { PANEL_KINDS, REVIEW_FILTERS, VIEWS, cardImages, castWhereCited, citedWithout, defaultView, failureFixes, isCast, marked, markedPhrases, missingWords, nextToReview, panelSelection, promptShot, reviewChoice, reviewCounts, reviewFilterOf, reviewPickOf, reviewShots, reviewState, shotNumbers, toggledCast, unnamedIn, viewOf, viewShot, witnessOf } from './director.js';

const { doc, ui, dispose, select, followIssue, allIssues, directorView, secs } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes, takeStore } = await import('./takes.svelte.js');
const { showInReview, chooseShot, chooseTake, chooseSeam } = await import('./band.svelte.js');
const { handleKeydown, commandById, spaceLabel } = await import('./commands.js');
const { reception } = await import('./references.js');
const { stages } = await import('./catalog.js');
const { hostIconName } = await import('./icons.js');
const { t } = await import('../i18n/index.svelte.js');

const take = (id, shotId, fields = {}) => ({ id, shotId, status: 'done', url: `/t/${id}.mp4`, label: 'draft', createdAt: `2026-10-26T10:0${id.slice(-1)}:00Z`, ...fields });

const clips = [
	{ id: 's1', start: 0, dur: 4 },
	{ id: 's2', start: 4, dur: 4 },
	{ id: 's3', start: 8, dur: 4 },
	{ id: 's4', start: 12, dur: 4 },
	{ id: 's5', start: 16, dur: 4 }
];
const takes = [
	take('t1', 's1', { label: 'final' }),
	take('t2', 's1', { label: 'candidate' }),
	take('t3', 's2', { label: 'candidate' }),
	take('t4', 's3', { label: 'rejected' }),
	take('t5', 's3', { status: 'running', url: null }),
	take('t6', 's4', { label: 'draft' }),
	take('t7', 's4', { status: 'failed', url: null })
];

test('director: four views, the Review first, and an unknown or missing choice falls back on the takes of the project', () => {
	assert.deepEqual(VIEWS, ['review', 'direction', 'bible', 'references']);
	assert.equal(defaultView([]), 'direction');
	assert.equal(defaultView(undefined), 'direction');
	assert.equal(defaultView(takes), 'review');
	assert.equal(viewOf(null, takes), 'review');
	assert.equal(viewOf(null, []), 'direction');
	assert.equal(viewOf('bible', []), 'bible');
	assert.equal(viewOf('queue', takes), 'review');
});

test('director: a shot is to review while it has a finished take that is not rejected and no final, or when its latest take failed', () => {
	assert.deepEqual(reviewState(takes.filter((x) => x.shotId === 's1')), { running: false, final: true, failed: false, review: false });
	assert.deepEqual(reviewState(takes.filter((x) => x.shotId === 's2')), { running: false, final: false, failed: false, review: true });
	assert.deepEqual(reviewState(takes.filter((x) => x.shotId === 's3')), { running: true, final: false, failed: false, review: false });
	assert.deepEqual(reviewState(takes.filter((x) => x.shotId === 's4')), { running: false, final: false, failed: true, review: true });
	assert.deepEqual(reviewState([]), { running: false, final: false, failed: false, review: false });
	assert.equal(reviewState([take('a1', 's9', { label: 'final', url: null })]).final, false);
});

test('director: the filters of the Review keep the shots of their state, in the order of the cut', () => {
	assert.deepEqual(REVIEW_FILTERS, ['review', 'running', 'final', 'all']);
	const ids = (filter) => reviewShots(clips, takes, filter).map((c) => c.id);
	assert.deepEqual(ids('review'), ['s2', 's4']);
	assert.deepEqual(ids('running'), ['s3']);
	assert.deepEqual(ids('final'), ['s1']);
	assert.deepEqual(ids('all'), ['s1', 's2', 's3', 's4', 's5']);
	assert.deepEqual(reviewCounts(clips, takes), { review: 2, running: 1, final: 1, all: 5 });
	assert.deepEqual(reviewCounts([], takes), { review: 0, running: 0, final: 0, all: 0 });
});

const bibleDoc = () => ({
	clips: [
		{ id: 's1', start: 0, dur: 4, cast: { characters: ['lina'] } },
		{ id: 's2', start: 4, dur: 4, cast: { characters: ['lina', 'malo'], place: 'quai' } },
		{ id: 's3', start: 8, dur: 4 },
		{ id: 's4', start: 12, dur: 4, cast: { characters: ['malo'] } }
	],
	prompts: [
		{ id: 'p1', shotId: 's1', text: 'A woman climbs the stairs.' },
		{ id: 'p2', shotId: 's2', text: 'Lina and Malo dance on Quai 9.' },
		{ id: 'p3', shotId: 's3', text: 'Malo plays the saxophone on quai 9.' },
		{ id: 'p4', shotId: 's4', text: 'Malo waits.' }
	],
	bible: {
		characters: [
			{ id: 'lina', label: 'Lina', text: '', references: ['r1'] },
			{ id: 'malo', label: 'Malo', text: '', references: [] },
			{ id: 'blank', label: '  ', text: '', references: [] }
		],
		places: [{ id: 'quai', label: 'Quai 9', text: '', references: ['r2', 'gone'] }]
	},
	references: [
		{ id: 'r1', space: 'identite' },
		{ id: 'r2', space: 'decors3d' },
		{ id: 'r3', space: 'identite' }
	]
});

test('director: the Bible finds the shots that name a card without casting it, and the shots that cast a character without naming it', () => {
	const doc = bibleDoc();
	const [lina, malo, blank] = doc.bible.characters;
	const quai = doc.bible.places[0];
	assert.deepEqual(citedWithout(doc, CHARACTERS, malo).map((c) => c.id), ['s3']);
	assert.deepEqual(citedWithout(doc, CHARACTERS, lina).map((c) => c.id), []);
	assert.deepEqual(citedWithout(doc, PLACES, quai).map((c) => c.id), ['s3']);
	assert.deepEqual(citedWithout(doc, CHARACTERS, blank), []);
	assert.deepEqual(unnamedIn(doc, CHARACTERS, lina).map((c) => c.id), ['s1']);
	assert.deepEqual(unnamedIn(doc, CHARACTERS, malo).map((c) => c.id), []);
	assert.deepEqual(unnamedIn(doc, PLACES, quai), []);
});

test('director: a cell of the distribution toggles a character, and sets or clears the single place of a shot', () => {
	const doc = bibleDoc();
	const [s1, s2, s3] = doc.clips;
	assert.deepEqual(toggledCast(s1, CHARACTERS, 'malo'), { characters: ['lina', 'malo'], place: null });
	assert.deepEqual(toggledCast(s2, CHARACTERS, 'lina'), { characters: ['malo'], place: 'quai' });
	assert.deepEqual(toggledCast(s3, PLACES, 'quai'), { characters: [], place: 'quai' });
	assert.deepEqual(toggledCast(s2, PLACES, 'quai'), { characters: ['lina', 'malo'], place: null });
	assert.equal(isCast(s2, PLACES, 'quai'), true);
	assert.equal(isCast(s1, CHARACTERS, 'malo'), false);
	assert.equal(s1.cast.characters.length, 1);
});

test('director: casting a card where it is cited touches only those shots, and the images of a card are its linked references', () => {
	const doc = bibleDoc();
	const malo = doc.bible.characters[1];
	assert.deepEqual(castWhereCited(doc, CHARACTERS, malo).map((c) => c.id), ['s3']);
	assert.deepEqual(castOf(doc.clips[2]), { characters: ['malo'], place: null });
	assert.equal(doc.clips[2].revision, 1);
	assert.equal(doc.clips[0].revision, undefined);
	assert.deepEqual(castOf(doc.clips[0]), { characters: ['lina'], place: null });
	assert.deepEqual(castWhereCited(doc, CHARACTERS, malo), []);
	assert.deepEqual(cardImages(doc, doc.bible.characters[0]).map((r) => r.id), ['r1']);
	assert.deepEqual(cardImages(doc, doc.bible.places[0]).map((r) => r.id), ['r2']);
	assert.deepEqual(cardImages(doc, null), []);
});

test('director: each view of the right panel keeps the kinds it can show, and anything else stays selected elsewhere', () => {
	assert.deepEqual(PANEL_KINDS, { review: ['clip'], direction: ['clip'], bible: [], references: ['reference', 'clip', 'vtrack'] });
	const shot = { kind: 'clip', id: 's2' };
	const sound = { kind: 'audio', id: 'a1' };
	const reference = { kind: 'reference', id: 'r1' };
	assert.deepEqual(panelSelection('review', shot), { shown: shot, elsewhere: null });
	assert.deepEqual(panelSelection('review', sound), { shown: null, elsewhere: sound });
	assert.deepEqual(panelSelection('review', reference), { shown: null, elsewhere: reference });
	assert.deepEqual(panelSelection('references', reference), { shown: reference, elsewhere: null });
	assert.deepEqual(panelSelection('references', shot), { shown: shot, elsewhere: null });
	assert.deepEqual(panelSelection('references', { kind: 'vtrack', id: 't1' }), { shown: { kind: 'vtrack', id: 't1' }, elsewhere: null });
	assert.deepEqual(panelSelection('review', { kind: 'vtrack', id: 't1' }), { shown: null, elsewhere: { kind: 'vtrack', id: 't1' } });
	for (const kind of ['audio', 'title', 'prompt', 'frame', 'marker', 'lane']) assert.equal(panelSelection('references', { kind, id: 'x' }).shown, null, kind);
	assert.deepEqual(panelSelection('bible', shot), { shown: null, elsewhere: shot });
	assert.deepEqual(panelSelection('review', null), { shown: null, elsewhere: null });
});

test('director: the sample shot is the pinned one, else the chosen shot, else the first shot with an instruction, and the view shot follows the panel', () => {
	const doc = { clips: [{ id: 's1', start: 0, dur: 4 }, { id: 's2', start: 4, dur: 4 }, { id: 's3', start: 8, dur: 4 }], prompts: [{ id: 'p2', shotId: 's2', start: 4, dur: 4, text: 'Lina runs.' }] };
	const [s1, s2, s3] = doc.clips;
	assert.deepEqual(witnessOf(doc, { kind: 'clip', id: 's3' }, 's1'), { clip: s1, source: 'pinned' });
	assert.deepEqual(witnessOf(doc, { kind: 'clip', id: 's3' }, 'gone'), { clip: s3, source: 'selection' });
	assert.deepEqual(witnessOf(doc, { kind: 'audio', id: 'a1' }, null), { clip: s2, source: 'first' });
	assert.deepEqual(witnessOf({ clips: [s1], prompts: [] }, null, null), { clip: s1, source: 'first' });
	assert.deepEqual(witnessOf({ clips: [], prompts: [] }, null, null), { clip: null, source: null });
	assert.equal(viewShot('direction', doc, { kind: 'clip', id: 's3' }, null), s3);
	assert.equal(viewShot('direction', doc, null, 's1'), s1);
	assert.equal(viewShot('review', doc, { kind: 'clip', id: 's3' }, 's1'), s3);
	assert.equal(viewShot('review', doc, { kind: 'audio', id: 'a1' }, null), null);
	assert.equal(viewShot('references', doc, { kind: 'reference', id: 'r1' }, null), null);
	assert.equal(viewShot('references', doc, { kind: 'clip', id: 's1' }, null), s1);
	assert.equal(viewShot('bible', doc, { kind: 'clip', id: 's1' }, 's2'), null);
});

test('director: a contradiction belongs to the shot of its prompt, and its two sentences are found and marked', () => {
	const doc = { clips: [{ id: 's1', start: 0, dur: 4 }, { id: 's2', start: 4, dur: 4 }] };
	assert.equal(promptShot(doc, { shotId: 's2', start: 0, dur: 1 }), doc.clips[1]);
	assert.equal(promptShot(doc, { shotId: null, start: 3, dur: 4 }), doc.clips[1]);
	assert.equal(promptShot(doc, { shotId: null, start: 20, dur: 2 }), null);
	assert.equal(promptShot(doc, null), null);
	const text = 'A stable camera. Lina runs with a handheld camera; rain falls.\nNo neon.';
	const parts = marked(text, [/stable camera/i, /handheld/i]);
	assert.equal(parts.map((x) => x.text).join(''), text);
	assert.deepEqual(parts.filter((x) => x.mark).map((x) => x.text), ['A stable camera.', 'Lina runs with a handheld camera;']);
	assert.deepEqual(marked(text, []).filter((x) => x.mark), []);
	assert.deepEqual(markedPhrases(text, [/neon/i]), ['No neon.']);
	assert.deepEqual(marked('', [/x/]), []);
});

test('director: shots are named by their numbers, three at most, and the Review filter falls back on its counts', () => {
	const doc = { clips: [{ id: 's1' }, { id: 's2' }, { id: 's3' }, { id: 's4' }, { id: 's5' }] };
	assert.deepEqual(shotNumbers(doc, [doc.clips[1]]), { list: '02', more: 0 });
	assert.deepEqual(shotNumbers(doc, doc.clips), { list: '01 · 02 · 03', more: 2 });
	assert.deepEqual(shotNumbers(doc, []), { list: '', more: 0 });
	assert.equal(reviewFilterOf('final', { review: 2 }), 'final');
	assert.equal(reviewFilterOf(null, { review: 2 }), 'review');
	assert.equal(reviewFilterOf('gone', { review: 0 }), 'all');
});

test('director: the Review panel shows the chosen take when it is finished or failed, the seam of the chosen shot, else the shot, else nothing', () => {
	const doc = { clips };
	const [s1, s2, s3, s4] = clips;
	const shot = (id) => ({ kind: 'clip', id });
	assert.equal(reviewPickOf(doc, takes, { kind: 'take', id: 't3' }, null), null);
	assert.equal(reviewPickOf(doc, takes, null, { kind: 'audio', id: 'a1' }), null);
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'take', id: 't3' }, shot('s2')), { kind: 'take', clip: s2, take: takes[2] });
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'take', id: 't7' }, shot('s4')), { kind: 'failed', clip: s4, take: takes[6] });
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'take', id: 't5' }, shot('s3')), { kind: 'shot', clip: s3 });
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'take', id: 't3' }, shot('s1')), { kind: 'shot', clip: s1 });
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'take', id: 'gone' }, shot('s1')), { kind: 'shot', clip: s1 });
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'seam', id: 's2' }, shot('s2')), { kind: 'seam', clip: s2, previous: s1 });
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'seam', id: 's1' }, shot('s1')), { kind: 'shot', clip: s1 });
	assert.deepEqual(reviewPickOf(doc, takes, { kind: 'seam', id: 's2' }, shot('s3')), { kind: 'shot', clip: s3 });
	assert.deepEqual(reviewChoice(takes[4], s3), { kind: 'shot', id: 's3' });
	assert.deepEqual(reviewChoice(takes[6], s4), { kind: 'take', id: 't7' });
	assert.deepEqual(reviewChoice(takes[0], s1), { kind: 'take', id: 't1' });
});

test('director: the next take to review is the latest finished one, not rejected, of the first shot left to review', () => {
	assert.deepEqual(nextToReview(clips, takes), { clip: clips[1], take: takes[2] });
	assert.deepEqual(nextToReview(clips, takes.filter((x) => x.id !== 't3')), { clip: clips[3], take: takes[5] });
	assert.equal(nextToReview(clips, []), null);
});

test('director: what a take lacks is every word of the instruction of today that the sent prompt did not carry', () => {
	const text = 'Lina and Malo exchange a glance, handheld, close framing.';
	const parts = missingWords(text, 'Bible: Lina. Lina and Malo exchange a glance under flickering lights, close framing.');
	assert.equal(parts.map((x) => x.text).join(''), text);
	assert.deepEqual(parts.filter((x) => x.mark).map((x) => x.text), ['handheld']);
	assert.deepEqual(missingWords('A slow tracking shot at dusk.', 'A shot.').filter((x) => x.mark).map((x) => x.text), ['slow tracking', 'at dusk']);
	assert.deepEqual(missingWords('Same words.', 'same WORDS'), [{ text: 'Same words.', mark: false }]);
	assert.deepEqual(missingWords('', 'x'), []);
});

test('director: a failed take offers to retry, and the way out that fits its cause', () => {
	assert.deepEqual(failureFixes({ errorCode: 'cuda_oom' }), ['retry', 'engine', 'shorter']);
	assert.deepEqual(failureFixes({ errorCode: 'content_blocked' }), ['instruction', 'retry']);
	assert.deepEqual(failureFixes({ errorCode: 'banned_prompt' }), ['instruction', 'retry']);
	assert.deepEqual(failureFixes({ errorCode: 'previous_take_failed' }), ['previous', 'retry']);
	assert.deepEqual(failureFixes({ errorCode: 'backend_unreachable' }), ['retry']);
	assert.deepEqual(failureFixes(null), ['retry']);
});

const url = (path) => new URL(path, import.meta.url).href;
const RIGHT_PANEL = url('../components/panels/RightPanel.svelte');
const LEFT_PANEL = url('../components/panels/LeftPanel.svelte');
const CENTER = url('../components/director/DirectorCenter.svelte');
const DIRECTOR_VIEWS = url('../components/director/DirectorViews.svelte');
const DIRECTION_VIEW = url('../components/director/DirectionView.svelte');
const DIRECTION_ASIDE = url('../components/director/DirectionAside.svelte');
const SUMMARY = url('../components/director/DirectorSummary.svelte');
const BIBLE_VIEW = url('../components/director/BibleView.svelte');
const BIBLE_ASIDE = url('../components/director/BibleAside.svelte');
const REVIEW_VIEW = url('../components/director/ReviewView.svelte');
const REVIEW_ASIDE = url('../components/director/ReviewAside.svelte');
const REFERENCE_ASIDE = url('../components/director/ReferenceAside.svelte');
const REFERENCE_BOARD = url('../components/references/ReferenceBoard.svelte');
const TAKE_CARD = url('../components/takes/TakeCard.svelte');

const done = (id, shotId, fields = {}) => ({ id, shotId, status: 'done', label: 'draft', quality: 'draft', variant: 'A', url: `/${id}.mp4`, createdAt: `2026-10-29T10:0${id.slice(-1)}:00Z`, ...fields });
const escapeRe = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const has = (html, text) => new RegExp(escapeRe(text)).test(textOf(html));
const label = (id) => commandById(id)?.label ?? '';
const keydown = (fields) => handleKeydown({ target: null, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, preventDefault() {}, ...fields }, null);

function scene({ clips = [], takes = [], prompts = [], references = [], audio = [], assets = [], direction = {}, bible = null, view = 'review' } = {}) {
	project.id = 'p1';
	Object.assign(ui, { workspace: 'director', directorView: view, selection: null, picked: [], preview: null, compare: null, reviewMonitor: false, reviewPick: null, witness: null, issue: null, reveal: null, selectedIn: null, reviewFilter: null, bibleCard: null, sidebarOpen: true, inspectorOpen: true, hideRejected: false, seamCompare: null, modal: null, menuOpen: null, paletteOpen: false, deckDrawer: false, playhead: 0 });
	doc.clips = clips.map((clip, n) => ({ start: n * 4, dur: 4, label: `Shot ${n + 1}`, stage: 'draft', ...clip }));
	doc.prompts = prompts;
	doc.references = references;
	doc.audio = audio;
	doc.assets = assets;
	doc.promptLanguage = 'en';
	for (const key of ['univers', 'personnages', 'photographie', 'palette', 'rythme']) doc.direction[key] = direction[key] ?? '';
	if (bible) doc.bible = bible;
	setTakes('p1', takes);
}

after(() => dispose());

test('director: the Review and References panels show the chosen shot, keep a sound chosen elsewhere behind a note that names it and its space, and References alone shows a reference', async () => {
	const rain = { id: 'a1', assetId: 'au', lane: doc.lanes[0].id, start: 0, dur: 2, srcIn: 0, gain: 0 };
	const poster = { id: 'r1', space: 'identite', type: 'Personnage', role: 'Identité', name: 'Poster', assetId: null, scope: { type: 'global' } };
	scene({ clips: [{ id: 's1' }, { id: 's2' }], audio: [rain], references: [poster], assets: [{ id: 'au', kind: 'audio', name: 'Rain loop', src: '/rain.mp3', origin: null }] });

	select('audio', 'a1');
	assert.equal(ui.selectedIn, 'director:review');
	let review = clean(await renderComponent(RIGHT_PANEL));
	assert.match(review, /data-review-aside="none"/);
	assert.match(review, /data-elsewhere="audio"/);
	assert.ok(has(review, t('inspector.elsewhere.audio', { name: 'Rain loop', space: spaceLabel('director:review') })));
	ui.directorView = 'references';
	select('audio', 'a1');
	assert.equal(ui.selectedIn, 'director:references');
	let references = clean(await renderComponent(RIGHT_PANEL));
	assert.match(references, /data-reference-aside="none"/);
	assert.match(references, /data-elsewhere="audio"/);
	assert.ok(has(references, t('inspector.elsewhere.audio', { name: 'Rain loop', space: spaceLabel('director:references') })));

	select('clip', 's2');
	references = clean(await renderComponent(RIGHT_PANEL));
	assert.match(references, /data-reference-aside="shot"/);
	assert.match(references, /data-reference-shot="s2"/);
	assert.doesNotMatch(references, /data-elsewhere=/);
	assert.ok(!has(references, t('inspector.section.flag')));
	assert.ok(!has(references, secs(4)));
	ui.directorView = 'review';
	review = clean(await renderComponent(RIGHT_PANEL));
	assert.match(review, /data-review-aside="shot"/);
	assert.doesNotMatch(review, /data-elsewhere=/);

	select('reference', 'r1');
	review = clean(await renderComponent(RIGHT_PANEL));
	assert.match(review, /data-review-aside="none"/);
	assert.match(review, /data-elsewhere="reference"/);
	ui.directorView = 'references';
	references = clean(await renderComponent(RIGHT_PANEL));
	assert.match(references, /data-reference-aside="reference"/);
	assert.match(references, /data-reference-chosen="r1"/);

	ui.workspace = 'storyboard';
	select('clip', 's1');
	assert.equal(ui.selectedIn, 'storyboard');
	select(null);
	assert.equal(ui.selectedIn, null);
	for (const [locale, inspector, lib] of [['en', enInspector, enLib], ['fr', frInspector, frLib]]) {
		for (const kind of ['audio', 'title', 'prompt', 'frame', 'marker', 'reference', 'lane']) assert.match(inspector[`elsewhere.${kind}`], /\{name\}.*\{space\}/, `${locale} ${kind}`);
		assert.doesNotMatch(lib['refTag.shotTip'], /\{start\}|\{end\}/, locale);
	}
});

test('director: a contradiction link makes its shot the sample and says so, the summary lists it, and the panel marks the two sentences, edits the instruction and can be unpinned', async () => {
	scene({ clips: [{ id: 's1' }, { id: 's2' }], prompts: [{ id: 'p2', shotId: 's2', start: 4, dur: 4, text: 'Handheld, fast pan.' }], direction: { photographie: 'Slow, steady camera.' }, view: 'direction' });
	const issue = allIssues()[0];
	assert.equal(issue?.id, 'stableCamera');

	let view = clean(await renderComponent(DIRECTION_VIEW));
	assert.match(view, new RegExp(`aria-pressed="false"[^>]*>${escapeRe(t('panels.director.direction.issueLink', { shot: '02' }))}</button>`));
	assert.ok(has(await renderComponent(SUMMARY), `02 · ${issue.text}`));

	followIssue(issue);
	assert.deepEqual([ui.workspace, directorView(), ui.issue, ui.witness, ui.selection, ui.reveal], ['director', 'direction', { prompt: 'p2', rule: 'stableCamera' }, null, { kind: 'clip', id: 's2' }, 's2']);
	view = clean(await renderComponent(DIRECTION_VIEW));
	assert.match(view, new RegExp(`aria-pressed="true"[^>]*>${escapeRe(t('panels.director.direction.issueShown', { shot: '02' }))}</button>`));

	let aside = clean(await renderComponent(DIRECTION_ASIDE));
	assert.match(aside, /data-witness="selection"/);
	assert.ok(has(aside, t('panels.director.aside.followsIssue')));
	const phrases = aside.match(/<dl[^>]*data-issue-phrases[^>]*>([\s\S]*?)<\/dl>/)?.[1] ?? '';
	assert.deepEqual([...phrases.matchAll(/<mark[^>]*>([^<]*)<\/mark>/g)].map((m) => m[1]), ['Slow, steady camera.', 'Handheld, fast pan.']);
	assert.ok(has(aside, t('panels.director.aside.edit', { shot: '02' })));
	assert.doesNotMatch(aside, new RegExp(escapeRe(t('panels.director.aside.unpin'))));

	ui.witness = 's1';
	aside = clean(await renderComponent(DIRECTION_ASIDE));
	assert.match(aside, /data-witness="pinned"/);
	assert.ok(has(aside, t('panels.director.aside.unpin')));
	assert.ok(has(aside, t('panels.director.aside.edit', { shot: '01' })));
	assert.doesNotMatch(aside, /data-issue-phrases/);
	for (const panels of [enPanels, frPanels]) assert.match(panels['director.direction.issueLink'], /^\{shot\} · /);
});

test('director: a shot chip of the Bible names the shot and its takes, and showing a shot in the Review opens that view on it, widening the filter when it hides the shot', async () => {
	scene({ clips: [{ id: 's1', cast: { characters: ['lina'] } }, { id: 's2' }], takes: [done('t2', 's2', { label: 'candidate' })], bible: { characters: [{ id: 'lina', label: 'Lina', text: '', references: [], props: '' }], places: [] }, view: 'bible' });

	const bible = clean(await renderComponent(BIBLE_VIEW));
	assert.match(bible, new RegExp(`<button type="button" class="vp-tc[^"]*" title="${escapeRe(t('panels.director.bible.chipTip', { shot: '01', name: 'Shot 1' }))}">01</button>`));

	showInReview(doc.clips[0]);
	assert.deepEqual([ui.workspace, directorView(), ui.selection, ui.reveal, ui.reviewFilter], ['director', 'review', { kind: 'clip', id: 's1' }, 's1', 'all']);
	const review = clean(await renderComponent(REVIEW_VIEW));
	assert.match(review, /<section class="[^"]*" data-review-shot="s1" aria-label="Shot 1" aria-current="true">/);
	assert.match(review, /<section class="[^"]*" data-review-shot="s2" aria-label="Shot 2">/);

	ui.reviewFilter = 'review';
	showInReview(doc.clips[1]);
	assert.deepEqual([ui.selection, ui.reviewFilter], [{ kind: 'clip', id: 's2' }, 'review']);
});

test('director: the summary leads to the four views and the engine, the view strip appears only without the sidebar, the center shows one view and the right panel follows it', async () => {
	scene({ clips: [{ id: 's1' }], bible: { characters: [{ id: 'lina', label: 'Lina', text: '', references: [], props: '' }], places: [] }, view: 'direction' });

	const left = clean(await renderComponent(LEFT_PANEL));
	assert.match(left, new RegExp(`<nav class="[^"]*" aria-label="${escapeRe(t('panels.director.views'))}">`));
	for (const id of VIEWS) assert.match(left, new RegExp(`<span class="block text-sm font-medium text-fg">${escapeRe(label(`view-${id}`))}</span>`));
	assert.match(left, new RegExp(`aria-current="page"[^>]*>(?:(?!</button>)[\\s\\S])*?<span class="block text-sm font-medium text-fg">${escapeRe(label('view-direction'))}</span>`));
	assert.equal((left.match(/aria-current="page"/g) ?? []).length, 1);
	assert.ok(has(left, t('panels.director.engine')));
	assert.ok(has(left, t('production.editEngine')));

	assert.doesNotMatch(clean(await renderComponent(DIRECTOR_VIEWS)), /role="group"/);
	ui.sidebarOpen = false;
	const strip = clean(await renderComponent(DIRECTOR_VIEWS));
	assert.match(strip, new RegExp(`role="group" aria-label="${escapeRe(t('panels.director.views'))}"`));
	for (const id of VIEWS) assert.match(strip, new RegExp(`aria-pressed="${id === 'direction'}" aria-label="${escapeRe(label(`view-${id}`))}"`));
	ui.sidebarOpen = true;

	const centers = { review: label('view-review'), direction: label('view-direction'), bible: label('view-bible'), references: t('references.title') };
	const asides = { review: /data-review-aside=/, direction: new RegExp(`aria-label="${escapeRe(t('panels.director.aside.prompt'))}"`), bible: new RegExp(`aria-label="${escapeRe(t('panels.director.aside.card'))}"`), references: /data-reference-aside=/ };
	for (const id of VIEWS) {
		ui.directorView = id;
		const center = clean(await renderComponent(CENTER));
		assert.match(center, new RegExp(`^<section class="[^"]*" aria-label="${escapeRe(centers[id])}">`), id);
		const right = clean(await renderComponent(RIGHT_PANEL));
		assert.match(right, asides[id], id);
		for (const other of VIEWS.filter((v) => v !== id)) assert.doesNotMatch(right, asides[other], `${id} shows ${other}`);
	}
	ui.directorView = 'direction';
	assert.ok(has(await renderComponent(DIRECTION_ASIDE), t('modals.shot.composed')));
	ui.bibleCard = 'lina';
	assert.match(clean(await renderComponent(BIBLE_ASIDE)), new RegExp(`aria-label="${escapeRe(t('modals.shot.pickImage', { slot: t('panels.director.aside.addImage') }))}"`));
	ui.workspace = 'storyboard';
	assert.match(clean(await renderComponent(RIGHT_PANEL)), new RegExp(`^<aside class="[^"]*" aria-label="${escapeRe(t('inspector.title'))}"`));
});

test('director: the Review lists the takes of each shot as cards to choose, opens the viewer only to compare or preview, and offers to assemble the finals without generating anything', async () => {
	scene({ clips: [{ id: 's1' }, { id: 's2' }], takes: [done('t1', 's1'), done('t2', 's1', { label: 'candidate', variant: 'B' }), done('t3', 's2')] });
	ui.reviewFilter = 'all';

	let review = clean(await renderComponent(REVIEW_VIEW));
	for (const id of ['t1', 't2', 't3']) assert.match(review, new RegExp(`data-take-card="${id}"`));
	assert.equal((review.match(/<div role="presentation" class="cursor-pointer"/g) ?? []).length, 3);
	assert.doesNotMatch(review, new RegExp(`aria-label="${escapeRe(t('viewer.label'))}"`));
	assert.ok(hostUis(review, 'Button').some((props) => props.disabled === true && props.icon === hostIconName('layers')));
	assert.ok(has(review, t('panels.dock.results.assemble', { count: 0 })));
	assert.ok(!has(review, label('generate')));

	ui.compare = ['t1', 't2'];
	review = clean(await renderComponent(REVIEW_VIEW));
	assert.match(review, new RegExp(`aria-label="${escapeRe(t('viewer.label'))}"`));
	assert.ok(hostUis(review, 'IconButton').some((props) => props.label === t('panels.director.review.closeMonitor')));

	ui.compare = null;
	ui.preview = { kind: 'result', id: 't3' };
	review = clean(await renderComponent(REVIEW_VIEW));
	assert.match(review, new RegExp(`aria-label="${escapeRe(t('viewer.label'))}"`));

	ui.preview = null;
	setTakes('p1', [done('t1', 's1', { label: 'final' }), done('t3', 's2')]);
	review = clean(await renderComponent(REVIEW_VIEW));
	assert.ok(hostUis(review, 'Button').some((props) => props.disabled === false && props.icon === hostIconName('layers')));
	assert.ok(has(review, t('panels.dock.results.assemble', { count: 1 })));
	assert.doesNotMatch(review, new RegExp(`aria-label="${escapeRe(t('viewer.label'))}"`));
	assert.match(clean(await renderComponent(TAKE_CARD, { take: takeStore.list[0], clip: doc.clips[0], onchoose() {} })), /<div role="presentation" class="cursor-pointer"/);
	assert.match(clean(await renderComponent(TAKE_CARD, { take: takeStore.list[0], clip: doc.clips[0] })), /<div role="presentation"><div class="flex gap-2.5 p-1.5">/);
});

test('director: choosing a shot, a take or a seam in the Review marks the shot current and sets the pick, and Escape closes the compare, then the monitor, then the seam compare', async () => {
	scene({ clips: [{ id: 's1' }, { id: 's2' }], takes: [done('t3', 's2'), done('t7', 's2', { status: 'failed', url: null, variant: 'B' })] });
	ui.reviewFilter = 'all';
	ui.playhead = 1;

	chooseShot(doc.clips[1]);
	assert.deepEqual([ui.selection, ui.reviewPick, ui.witness, ui.reveal], [{ kind: 'clip', id: 's2' }, { kind: 'shot', id: 's2' }, null, null]);
	assert.ok(ui.playhead >= 4 && ui.playhead < 8);
	let review = clean(await renderComponent(REVIEW_VIEW));
	assert.match(review, /data-review-shot="s2" aria-label="Shot 2" aria-current="true">\s*<span class="absolute inset-y-0 left-0 w-0\.5 bg-signal" aria-hidden="true"><\/span>/);
	assert.doesNotMatch(review, /data-review-shot="s1" aria-label="Shot 1" aria-current/);

	chooseTake(takeStore.list[0]);
	assert.deepEqual([ui.reviewPick, ui.preview], [{ kind: 'take', id: 't3' }, { kind: 'result', id: 't3' }]);
	review = clean(await renderComponent(REVIEW_VIEW));
	assert.match(review, /aria-current="true" data-take-card="t3"/);
	chooseTake(takeStore.list[1]);
	assert.deepEqual([ui.reviewPick, ui.preview], [{ kind: 'take', id: 't7' }, null]);

	chooseSeam(doc.clips[1]);
	assert.deepEqual(ui.reviewPick, { kind: 'seam', id: 's2' });
	chooseSeam(doc.clips[0]);
	assert.deepEqual(ui.reviewPick, { kind: 'seam', id: 's2' });

	Object.assign(ui, { compare: ['t3', 't7'], reviewMonitor: true, seamCompare: { shotId: 's2' } });
	keydown({ key: 'Escape' });
	assert.deepEqual([ui.compare, ui.reviewMonitor, ui.seamCompare], [null, true, { shotId: 's2' }]);
	keydown({ key: 'Escape' });
	assert.deepEqual([ui.compare, ui.reviewMonitor, ui.seamCompare], [null, false, { shotId: 's2' }]);
	keydown({ key: 'Escape' });
	assert.deepEqual([ui.compare, ui.reviewMonitor, ui.seamCompare], [null, false, null]);
	for (const panels of [enPanels, frPanels]) assert.ok(panels['director.review.closeMonitor']);
});

test('director: the Review panel is about the chosen take, its failure, the seam or the shot, with the project when nothing is chosen, and never edits the shot itself', async () => {
	const instruction = 'Lina runs along the quay, handheld.';
	scene({ clips: [{ id: 's1' }, { id: 's2', revision: 2 }], prompts: [{ id: 'p2', shotId: 's2', start: 4, dur: 4, text: instruction }], takes: [done('t3', 's2', { promptText: 'Lina runs along the quay.', shotRevision: 1, generationId: 'g3' }), done('t7', 's2', { status: 'failed', url: null, variant: 'B', errorCode: 'cuda_oom' })] });
	const fields = [t('inspector.section.flag'), t('inspector.section.duration'), t('inspector.field.name')];
	const clean_ = async () => clean(await renderComponent(REVIEW_ASIDE));

	let aside = await clean_();
	assert.match(aside, /data-review-aside="none"/);
	assert.ok(hostUis(aside, 'Button').length >= 1 && has(aside, t('inspector.projectProps')));
	assert.match(aside, /data-review-counts/);

	select('clip', 's2');
	aside = await clean_();
	assert.match(aside, /data-review-aside="shot"/);
	assert.match(aside, /data-shot-takes="s2"/);
	assert.match(aside, /data-shot-summary="s2"/);
	assert.ok(has(aside, t('modals.shot.composed')));
	assert.ok(has(aside, t('panels.director.pick.generate', { key: commandById('generate')?.key ?? '' })));
	for (const field of fields) assert.ok(!has(aside, field), field);

	ui.reviewPick = { kind: 'take', id: 't3' };
	aside = await clean_();
	assert.match(aside, /data-review-aside="take"/);
	assert.match(aside, /data-take-since/);
	assert.deepEqual([...aside.matchAll(/<mark[^>]*data-take-missing[^>]*>([^<]*)<\/mark>/g)].map((m) => m[1]), ['handheld']);
	assert.match(aside, /data-take-sent/);
	assert.ok(has(aside, 'Lina runs along the quay.'));
	assert.match(aside, /data-shot-summary="s2"/);
	assert.ok(hostUis(aside, 'Button').some((props) => props.icon === 'info'));
	for (const field of fields) assert.ok(!has(aside, field), field);

	ui.reviewPick = { kind: 'take', id: 't7' };
	aside = await clean_();
	assert.match(aside, /data-review-aside="failed"/);
	assert.match(aside, /data-take-failure="cuda_oom"/);
	assert.deepEqual([...aside.matchAll(/data-take-fix="([^"]+)"/g)].map((m) => m[1]), ['retry', 'engine', 'shorter']);
	assert.ok(has(aside, t('panels.director.pick.fix.previous', { shot: '01' })) === false);

	ui.reviewPick = { kind: 'seam', id: 's2' };
	aside = await clean_();
	assert.match(aside, /data-review-aside="seam"/);
	assert.match(aside, /data-seam-pair="s2"/);
	assert.ok(has(aside, t('panels.director.pick.gaps')));
	assert.doesNotMatch(aside, /data-shot-summary/);

	select('audio', 'none');
	aside = await clean_();
	assert.match(aside, /data-review-aside="none"/);
	assert.doesNotMatch(aside, /data-elsewhere/);
});

test('director: Alt+1 to Alt+4 open the views, the old dock and its tabs are gone, Draft is grey and Edit Engine keeps its English name', () => {
	scene({ clips: [{ id: 's1' }], takes: [done('t1', 's1')] });
	ui.workspace = 'storyboard';
	VIEWS.forEach((id, i) => {
		keydown({ key: String(i + 1), code: `Digit${i + 1}`, altKey: true });
		assert.deepEqual([ui.workspace, directorView()], ['director', id], id);
	});
	keydown({ key: '1', code: 'Digit1', altKey: true, shiftKey: true });
	assert.equal(directorView(), 'references');
	assert.ok(!existsSync(new URL('../components/panels/DirectorDock.svelte', import.meta.url)));
	assert.ok(!existsSync(new URL('../components/panels/BibleSection.svelte', import.meta.url)));
	assert.deepEqual([stages.draft.tone, stages.draft.dot], ['text-fg-muted', 'bg-fg-muted']);
	assert.equal(stages.draft.label, t('lib.stage.draft'));
	for (const [production, commands] of [[enProduction, enCommands], [frProduction, frCommands]]) {
		assert.equal(production.editEngine, 'Edit Engine');
		assert.equal(commands['cmd.engine'], 'Edit Engine…');
	}
});

test('director: the References panel is about the reference, the shot or the project, reads what each engine gets, can remove a reference, and the board highlights the chosen shot', async () => {
	const poster = { id: 'r1', space: 'identite', type: 'Personnage', role: 'Identité', name: 'Poster', assetId: null, scope: { type: 'global' } };
	const hat = { id: 'r2', space: 'identite', type: 'Objet', role: 'Objet', name: 'Hat', assetId: null, scope: { type: 'shot', shotId: 's2' } };
	scene({ clips: [{ id: 's1', cast: { characters: ['lina'] } }, { id: 's2' }], references: [poster, hat], bible: { characters: [{ id: 'lina', label: 'Lina', text: '', references: ['r1'], props: '' }], places: [] }, view: 'references' });

	let aside = clean(await renderComponent(REFERENCE_ASIDE));
	assert.match(aside, /data-reference-aside="none"/);
	assert.match(aside, /data-reference-project/);
	assert.match(aside, new RegExp(`<ul class="[^"]*" aria-label="${escapeRe(t('panels.director.refs.byEngine'))}" data-reception="">`));
	assert.equal((aside.match(/data-reception-row=/g) ?? []).length, 1);
	assert.ok(!has(aside, t('inspector.reference.remove')));

	select('reference', 'r1');
	aside = clean(await renderComponent(REFERENCE_ASIDE));
	assert.match(aside, /data-reference-aside="reference"/);
	assert.match(aside, /data-reference-chosen="r1"/);
	const [scope] = hostUis(aside, 'SegmentedControl');
	assert.deepEqual([scope.selected, scope.items.map((item) => item.id)], ['global', ['global', 'shot']]);
	assert.doesNotMatch(aside, /data-reference-shot-pick/);
	assert.match(aside, new RegExp(`<ul class="[^"]*" aria-label="${escapeRe(t('panels.director.refs.received'))}" data-reception="">`));
	assert.ok(has(aside, t('panels.director.refs.cardText', { name: 'Lina', count: 1 })));
	assert.ok(has(aside, t('inspector.reference.remove')));
	const found = reception(poster);
	assert.deepEqual([found.cast.map((c) => c.id), found.linked?.card.id, found.groups.length >= 1], [['s1'], 'lina', true]);

	select('reference', 'r2');
	aside = clean(await renderComponent(REFERENCE_ASIDE));
	assert.equal(hostUis(aside, 'SegmentedControl')[0].selected, 'shot');
	assert.match(aside, /<select class="vp-popup w-full"[^>]*data-reference-shot-pick="true">\s*<option value="s1">01 · Shot 1<\/option><option value="s2" selected="">02 · Shot 2<\/option>/);

	select('clip', 's2');
	aside = clean(await renderComponent(REFERENCE_ASIDE));
	assert.match(aside, /data-reference-aside="shot"/);
	assert.match(aside, /data-reference-shot="s2"/);
	assert.match(aside, /data-reference-notice="/);
	assert.match(aside, /data-reference-globals/);
	assert.match(aside, /data-reference-row="r1"[\s\S]*?data-reference-not-cast[\s\S]*?aria-pressed="true"[^>]*>[^<]*<\/button>\s*<button[^>]*aria-pressed="false"/);
	assert.match(aside, /data-reference-owns[\s\S]*data-reference-row="r2"/);
	assert.ok(has(aside, t('panels.director.refs.addTo', { shot: '02' })));
	const board = clean(await renderComponent(REFERENCE_BOARD));
	assert.match(board, /data-reference-highlight="s2"/);
	select(null);
	assert.doesNotMatch(clean(await renderComponent(REFERENCE_BOARD)), /data-reference-highlight/);

	ui.bibleCard = 'lina';
	const bible = clean(await renderComponent(BIBLE_ASIDE));
	assert.match(bible, /data-card-reception/);
	assert.match(bible, new RegExp(`<ul class="[^"]*" aria-label="${escapeRe(t('panels.director.bible.received'))}" data-reception="">`));
	assert.ok(has(bible, t('panels.director.refs.cardText', { name: 'Lina', count: 1 })));
});

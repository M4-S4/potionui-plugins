import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { CHARACTERS, PLACES, castOf } from './bible.js';
import { PANEL_KINDS, REVIEW_FILTERS, VIEWS, cardImages, castWhereCited, citedWithout, defaultView, failureFixes, isCast, marked, markedPhrases, missingWords, nextToReview, panelSelection, promptShot, reviewChoice, reviewCounts, reviewFilterOf, reviewPickOf, reviewShots, reviewState, shotNumbers, toggledCast, unnamedIn, viewOf, viewShot, witnessOf } from './director.js';

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

const read = (file) => readFileSync(new URL(file, import.meta.url), 'utf-8');

test('director: each view of the right panel keeps the kinds it can show, and anything else stays selected elsewhere', () => {
	assert.deepEqual(PANEL_KINDS, { review: ['clip'], direction: ['clip'], bible: [], references: ['reference', 'clip'] });
	const shot = { kind: 'clip', id: 's2' };
	const sound = { kind: 'audio', id: 'a1' };
	const reference = { kind: 'reference', id: 'r1' };
	assert.deepEqual(panelSelection('review', shot), { shown: shot, elsewhere: null });
	assert.deepEqual(panelSelection('review', sound), { shown: null, elsewhere: sound });
	assert.deepEqual(panelSelection('review', reference), { shown: null, elsewhere: reference });
	assert.deepEqual(panelSelection('references', reference), { shown: reference, elsewhere: null });
	assert.deepEqual(panelSelection('references', shot), { shown: shot, elsewhere: null });
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

test('director: the right panel of Review and References filters the selection, keeps it, says where it stays and leaves the flag and the times out of Director AI', () => {
	const inspector = read('../components/inspector/Inspector.svelte');
	assert.match(inspector, /const s = \$derived\(ui\.selection\);/);
	assert.doesNotMatch(inspector, /directorView|panelSelection|ElsewhereNote|shotNumber/);
	assert.doesNotMatch(inspector, /ui\.selection = null/);
	const note = read('../components/inspector/ElsewhereNote.svelte');
	assert.match(note, /data-elsewhere=\{kind\}/);
	assert.match(note, /space: spaceLabel\(ui\.selectedIn\) \?\? t\('inspector\.elsewhere\.space'\)/);
	const aside = read('../components/director/ReferenceAside.svelte');
	assert.match(aside, /const filtered = \$derived\(panelSelection\('references', ui\.selection\)\);/);
	assert.match(aside, /\{#if filtered\.elsewhere\}<ElsewhereNote kind=\{filtered\.elsewhere\.kind\} \/>\{\/if\}/);
	for (const file of ['ReferenceAside', 'ReferenceChosen', 'ReferenceShot', 'ReferenceProject', 'ReceptionList']) {
		assert.doesNotMatch(read(`../components/director/${file}.svelte`), /secs\(|inspector\.section\.flag|ui\.playhead|shotIdAt/, file);
	}
	assert.match(read('./state.svelte.js'), /ui\.selectedIn = kind \? \(ui\.workspace === 'director' \? `director:\$\{directorView\(\)\}` : ui\.workspace\) : null;/);
	const board = read('../components/references/ReferenceBoard.svelte');
	assert.doesNotMatch(board, /ondblclick|seek\(/);
	for (const locale of ['en', 'fr']) {
		const keys = JSON.parse(read(`../i18n/${locale}/inspector.json`));
		for (const kind of ['audio', 'title', 'prompt', 'frame', 'marker', 'reference', 'lane']) assert.match(keys[`elsewhere.${kind}`], /\{name\}.*\{space\}/, `${locale} ${kind}`);
		assert.doesNotMatch(JSON.parse(read(`../i18n/${locale}/lib.json`))['refTag.shotTip'], /\{start\}|\{end\}/, locale);
	}
});

test('director: a contradiction link makes its shot the sample, names it, and the panel marks the two sentences and edits the instruction', () => {
	const view = read('../components/director/DirectionView.svelte');
	assert.match(view, /onclick=\{\(\) => followIssue\(i\)\}>\{isShown\(i\) \? t\('panels\.director\.direction\.issueShown', \{ shot: num\(clip\) \}\) : t\('panels\.director\.direction\.issueLink', \{ shot: num\(clip\) \}\)\}<\/button>/);
	assert.doesNotMatch(view, /select\('prompt'|seek\(|issuePrompt/);
	const summary = read('../components/director/DirectorSummary.svelte');
	assert.match(summary, /onclick=\{\(\) => followIssue\(i\)\}>/);
	assert.doesNotMatch(summary, /seek\(/);
	const aside = read('../components/director/DirectionAside.svelte');
	assert.match(aside, /const marks = \$derived\(rule \? \[rule\.global, rule\.local\] : \[\]\);/);
	assert.match(aside, /t\('panels\.director\.aside\.edit', \{ shot: num\(shot\) \}\)/);
	assert.match(aside, /onclick=\{\(\) => \(ui\.witness = null\)\}>\{t\('panels\.director\.aside\.unpin'\)\}/);
	assert.match(read('../components/shots/ComposedPrompt.svelte'), /\{#if part\.mark\}<mark /);
	for (const locale of ['en', 'fr']) assert.match(JSON.parse(read(`../i18n/${locale}/panels.json`))['director.direction.issueLink'], /^\{shot\} · /, locale);
});

test('director: a shot chip of the Bible opens the Review on that shot and brings its row on screen', () => {
	const bible = read('../components/director/BibleView.svelte');
	assert.match(bible, /function goTo\(e, clip\) \{\n\t\te\.stopPropagation\(\);\n\t\tshowInReview\(clip\);\n\t\}/);
	assert.match(bible, /title=\{t\('panels\.director\.bible\.chipTip', \{ shot: num\(clip\), name: clipLabel\(clip\) \}\)\}/);
	assert.doesNotMatch(bible, /seek\(/);
	const review = read('../components/director/ReviewView.svelte');
	assert.match(review, /rows\?\.querySelector\(`\[data-review-shot="\$\{id\}"\]`\)\?\.scrollIntoView\(\{ block: 'start' \}\);\n\t\t\tui\.reveal = null;/);
	assert.match(read('./band.svelte.js'), /export function showInReview\(clip\) \{[\s\S]*?openDirector\('review'\);\n\tpickShot\(clip\);\n\tui\.reveal = clip\.id;\n\}/);
});

test('director: the summary leads to the four views and the engine, the center shows one view, the right panel follows it', () => {
	assert.match(read('../components/panels/LeftPanel.svelte'), /\{:else if ui\.workspace === 'director'\}\n\t\t<DirectorSummary \/>/);
	const summary = read('../components/director/DirectorSummary.svelte');
	assert.match(summary, /\{#each VIEWS as id \(id\)\}/);
	assert.match(summary, /onclick=\{\(\) => \(ui\.directorView = id\)\}/);
	assert.match(summary, /citedWithout\(doc, kind, card\)/);
	assert.match(summary, /reviewState\(takesOf\(c\)\)\.failed/);
	const center = read('../components/director/DirectorCenter.svelte');
	for (const view of ['DirectionView', 'BibleView', 'ReferenceBoard', 'ReviewView']) assert.match(center, new RegExp(`<${view} />`));
	const right = read('../components/panels/RightPanel.svelte');
	assert.match(right, /\{#if view === 'review'\}\n\t<ReviewAside \/>\n\{:else if view === 'direction'\}\n\t<DirectionAside \/>\n\{:else if view === 'bible'\}\n\t<BibleAside \/>\n\{:else if view === 'references'\}\n\t<ReferenceAside \/>\n\{:else\}\n\t<Inspector \/>/);
	assert.match(read('../components/director/DirectorViews.svelte'), /\{#if !ui\.sidebarOpen\}/);
	assert.match(read('../components/director/DirectionAside.svelte'), /<ComposedPrompt source=\{doc\} shotId=\{shot\.id\} \{marks\} bind:current=\{composed\} \/>/);
	assert.match(read('../components/director/BibleAside.svelte'), /onpick=\{\(id\) => addCardImage\(card, SPACES\[kind\], id\)\}/);
});

test('director: the Review lists the takes with their cards and compares them in the viewer, never generating by itself', () => {
	const review = read('../components/director/ReviewView.svelte');
	assert.match(review, /const taking = \$derived\(ui\.compare\?\.length === 2 \|\| ui\.preview\?\.kind === 'result'\);\n\tconst watching = \$derived\(ui\.reviewMonitor \|\| taking\);/);
	assert.match(review, /\{#if watching\}\n\t\t<div class="relative grid min-h-0 shrink-0 border-b border-line" style:height="46%">\n\t\t\t<Viewer \/>/);
	assert.match(review, /<TakeCard \{take\} clip=\{c\} onchoose=\{chooseTake\} chosen=\{picked\?\.take\?\.id === take\.id\} \/>/);
	assert.match(review, /onclick: assembleChosen/);
	assert.doesNotMatch(review, /startGeneration/);
	for (const file of ['../components/inspector/Inspector.svelte', '../components/inspector/TakesSection.svelte', '../components/storyboard/ShotQuickEdit.svelte', '../components/storyboard/StoryboardView.svelte', '../components/viewer/Viewer.svelte', '../components/director/ReviewAside.svelte', '../components/director/ReviewTake.svelte', '../components/director/ReviewFailure.svelte', '../components/director/ReviewShot.svelte']) assert.doesNotMatch(read(file), /startGeneration/, file);
});

test('director: in the Review, a click in the block of a shot chooses the shot, a click on a card chooses its take, the seam line chooses the seam, and the monitor stays open on the cut once open', () => {
	const review = read('../components/director/ReviewView.svelte');
	assert.match(read('./band.svelte.js'), /export function chooseShot\(clip\) \{\n\tif \(!clip\) return;\n\tpickShot\(clip, clipAt\(ui\.playhead\)\?\.id !== clip\.id\);\n\tui\.reviewPick = \{ kind: 'shot', id: clip\.id \};\n\}/);
	assert.match(review, /function choose\(e, c\) \{\n\t\tif \(e\.target\.closest\?\.\('button, a, input, select, textarea, label'\)\) return;\n\t\tchooseShot\(c\);\n\t\}/);
	assert.match(review, /<div role="presentation" class="px-4 py-3" onclick=\{\(e\) => choose\(e, c\)\}>/);
	assert.match(review, /<button type="button" class="mb-2 flex min-h-7 cursor-pointer items-center gap-2 rounded px-1\.5 text-left transition-colors hover:bg-surface-2"[^>]*onclick=\{\(\) => chooseShot\(c\)\}>/);
	assert.match(review, /data-review-seam=\{c\.id\}\n\t+aria-current=\{seamOn\(c\) \? 'true' : undefined\}\n\t+onclick=\{\(e\) => chooseAt\(e, c\)\}/);
	assert.match(review, /title=\{t\('panels\.director\.review\.seamTip'\)\} onclick=\{\(\) => chooseSeam\(c\)\}>/);
	assert.match(review, /if \(ui\.selection\?\.kind !== 'clip' \|\| ui\.selection\.id !== id\) return void \(ui\.reveal = null\);\n\t\tif \(!shown\.some\(\(c\) => c\.id === id\)\) return void \(ui\.reviewFilter = 'all'\);/);
	assert.match(review, /aria-current=\{isSel\(c\) \? 'true' : undefined\}>\n\t+\{#if isSel\(c\)\}<span class="absolute inset-y-0 left-0 w-0\.5 bg-signal" aria-hidden="true"><\/span>\{\/if\}/);
	assert.match(review, /\$effect\(\(\) => \{\n\t\tif \(taking\) ui\.reviewMonitor = true;\n\t\}\);\n\t\$effect\(\(\) => \(\) => \(ui\.reviewMonitor = false\)\);/);
	assert.match(review, /function closeMonitor\(\) \{\n\t\tui\.preview = null;\n\t\tui\.compare = null;\n\t\tui\.reviewMonitor = false;\n\t\}/);
	assert.match(review, /label: t\('panels\.director\.review\.closeMonitor'\)[^\n]*onclick: closeMonitor/);
	assert.match(review, /onclick=\{\(\) => openSeam\(c\)\}/);
	assert.doesNotMatch(review, /function openSeam|select\('clip'/);
	const card = read('../components/takes/TakeCard.svelte');
	assert.match(card, /function open\(\) \{\n\t\tif \(onchoose\) onchoose\(take\);\n\t\telse previewTake\(take\);\n\t\}/);
	assert.match(card, /function choose\(e\) \{\n\t\tif \(!onchoose \|\| e\.target\.closest\?\.\('button, a, input, select, textarea, label'\)\) return;\n\t\te\.stopPropagation\(\);\n\t\tonchoose\(take\);\n\t\}/);
	assert.match(card, /<div role="presentation" class=\{onchoose \? 'cursor-pointer' : ''\} onclick=\{choose\}>/);
	assert.match(card, /onclick=\{open\}>/);
	assert.doesNotMatch(card, /ui\.preview = /);
	assert.match(read('../components/storyboard/BandLanes.svelte'), /import \{ previewTake \} from '\.\.\/\.\.\/lib\/monitor\.svelte\.js';/);
	assert.match(read('./commands.js'), /\} else if \(ui\.reviewMonitor\) ui\.reviewMonitor = false;\n\telse if \(ui\.seamCompare\) ui\.seamCompare = null;/);
	for (const locale of ['en', 'fr']) assert.ok(JSON.parse(read(`../i18n/${locale}/panels.json`))['director.review.closeMonitor'], locale);
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

test('director: the Review has its own panel, about the take, its failure, the shot or the seam, with nothing that sets a shot', () => {
	const aside = read('../components/director/ReviewAside.svelte');
	assert.match(aside, /const pick = \$derived\(reviewPick\(\)\);/);
	assert.match(aside, /const elsewhere = \$derived\(panelSelection\('review', ui\.selection\)\.elsewhere\);/);
	assert.match(aside, /\{#if elsewhere\}<ElsewhereNote kind=\{elsewhere\.kind\} \/>\{\/if\}/);
	assert.match(aside, /\{#if pick\?\.kind === 'take'\}\n\t+<ReviewTake clip=\{pick\.clip\} \{take\} \/>\n\t+\{:else if pick\?\.kind === 'failed'\}\n\t+<ReviewFailure clip=\{pick\.clip\} \{take\} \/>\n\t+\{:else if pick\?\.kind === 'seam'\}\n\t+<ReviewSeam clip=\{pick\.clip\} previous=\{pick\.previous\} \/>\n\t+\{:else if pick\}\n\t+<ReviewShot clip=\{pick\.clip\} \/>\n\t+\{:else\}\n\t+<ReviewEmpty \/>/);
	const panel = ['ReviewAside', 'ReviewTake', 'ReviewFailure', 'ReviewShot', 'ReviewSeam', 'ReviewEmpty', 'ShotSummary'].map((name) => read(`../components/director/${name}.svelte`)).join('\n');
	for (const gone of [/labelTake|toggledLabel|rejectShort|candidateShort|finalShort/, /inspector\.field\.|inspector\.section\.(sound|fades|flag|duration|frames)/, /bladeAt|duplicateSelection|deleteSelection|deleteTake/, /TakesSection|TakeCard|inspector\.tab\.video|inspector\.flag/, /secs\(\w+\.start\)/]) assert.doesNotMatch(panel, gone, String(gone));
	const take = read('../components/director/ReviewTake.svelte');
	assert.match(take, /const parts = \$derived\(take\.promptText \? missingWords\(today, take\.promptText\) : \[\{ text: today, mark: false \}\]\);/);
	assert.match(take, /\{#if stale\}\n\t<section class="space-y-2" data-take-since>/);
	assert.match(take, /<p class="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-line-strong p-2\.5 text-xs leading-5 text-fg-muted">\{take\.promptText\}<\/p>/);
	assert.match(take, /<ShotSummary \{clip\} \/>/);
	assert.match(read('../components/director/ShotSummary.svelte'), /onclick: \(\) => showInStoryboard\(clip\)/);
	assert.match(read('../components/director/ReviewFailure.svelte'), /failureFixes\(take\)/);
	assert.match(read('../components/director/ReviewSeam.svelte'), /<SeamPanel \{clip\} title=\{false\} compare=\{false\} \/>/);
	assert.match(read('../components/director/ReviewShot.svelte'), /<ComposedPrompt source=\{doc\} shotId=\{clip\.id\} \/>/);
	assert.match(read('./state.svelte.js'), /\tui\.witness = null;\n\tselect\('clip', clip\.id\);\n\tui\.reveal = clip\.id;\n\}/);
});

test('director: Alt+1 to Alt+4 open the views, the old dock and its tabs are gone, Draft is grey and Edit Engine keeps its English name', () => {
	const commands = read('./commands.js');
	VIEWS.forEach((id, i) => assert.ok(commands.includes(`command('view-${id}', view('${id}'), { keys: 'alt+${i + 1}', check: isView('${id}') })`), id));
	assert.ok(!existsSync(new URL('../components/panels/DirectorDock.svelte', import.meta.url)));
	assert.ok(!existsSync(new URL('../components/panels/BibleSection.svelte', import.meta.url)));
	assert.match(read('./catalog.js'), /return t\('lib\.stage\.draft'\);\n\t\t\},\n\t\ttone: 'text-fg-muted',\n\t\tdot: 'bg-fg-muted'/);
	for (const locale of ['en', 'fr']) {
		assert.equal(JSON.parse(read(`../i18n/${locale}/production.json`)).editEngine, 'Edit Engine');
		assert.equal(JSON.parse(read(`../i18n/${locale}/commands.json`))['cmd.engine'], 'Edit Engine…');
	}
});

test('director: References has its own panel, which reads what each engine gets from the rule the server applies', () => {
	const aside = read('../components/director/ReferenceAside.svelte');
	assert.match(aside, /\{#if reference\}\n\t+<ReferenceChosen \{reference\} \/>\n\t+\{:else if clip\}\n\t+<ReferenceShot \{clip\} \/>\n\t+\{:else\}\n\t+<ReferenceProject \/>/);
	assert.match(aside, /onclick: deleteSelection \}\}>\{t\('inspector\.reference\.remove'\)\}/);
	assert.match(read('./references.js'), /export const reception = \(reference, source = doc\) => receptionOf\(reference, source, \(clip\) => engineOf\(clip, source\), tracksFor\(source\)\);/);
	assert.match(read('./reception.js'), /^import table from '\.\/reception\.json';/);
	const chosen = read('../components/director/ReferenceChosen.svelte');
	assert.match(chosen, /const found = \$derived\(reception\(reference\)\);/);
	assert.match(chosen, /\{ id: 'global', label: t\('inspector\.scope\.global'\) \},\n\t\t\{ id: 'shot', label: t\('inspector\.scope\.shot'\) \}/);
	assert.match(chosen, /\} else if \(isGlobal\(reference\)\) pending = true;/);
	assert.match(chosen, /<option value="" disabled>\{t\('panels\.director\.refs\.pickShot'\)\}<\/option>/);
	assert.match(chosen, /<ReceptionList \{rows\} label=\{t\('panels\.director\.refs\.received'\)\} \/>/);
	assert.match(chosen, /onclick=\{\(\) => showInReview\(c\)\}/);
	assert.match(chosen, /onclick: \(\) => startImage\(target\)/);
	const shot = read('../components/director/ReferenceShot.svelte');
	assert.match(shot, /onclick=\{\(\) => setSent\(clip, r\.id, false\)\}/);
	assert.match(shot, /onclick: \(\) => addShotReference\(clip\)/);
	assert.match(read('../components/director/ReferenceProject.svelte'), /const groups = \$derived\(projectReceptionFor\(\)\);/);
	const board = read('../components/references/ReferenceBoard.svelte');
	assert.match(board, /const going = \$derived\(shot \? new Set\(sentReferences\(doc, shot\)\.map\(\(r\) => r\.id\)\) : null\);/);
	assert.match(board, /data-reference-highlight=\{shot\.id\}/);
	assert.match(board, /takesReferences\(project\.profile\)/);
	assert.doesNotMatch(board, /supportedProfiles/);
	const bible = read('../components/director/BibleAside.svelte');
	assert.match(bible, /const received = \$derived\(card \? cardReceptionFor\(kind, card\) : null\);/);
	assert.match(bible, /<ReceptionList \{rows\} label=\{t\('panels\.director\.bible\.received'\)\} \/>/);
	assert.match(read('../components/modals/Modals.svelte'), /focus=\{m\.focus \?\? null\}/);
	const keyframes = read('../components/shots/KeyframeCandidates.svelte');
	assert.match(keyframes, /tick\(\)\.then\(\(\) => root\?\.scrollIntoView\(\{ block: 'start' \}\)\);/);
	assert.match(keyframes, /aria-controls="\{id\}-body" autofocus=\{focus\}/);
	assert.match(read('../components/modals/ShotEditor.svelte'), /autofocus=\{focus !== 'keyframes'\}/);
});

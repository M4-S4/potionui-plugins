import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { CHARACTERS, PLACES, castOf } from './bible.js';
import { REVIEW_FILTERS, VIEWS, cardImages, castWhereCited, citedWithout, defaultView, isCast, reviewCounts, reviewShots, reviewState, toggledCast, unnamedIn, viewOf } from './director.js';

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
	assert.match(right, /\{#if view === 'direction'\}\n\t<DirectionAside \/>\n\{:else if view === 'bible'\}\n\t<BibleAside \/>\n\{:else\}\n\t<Inspector \/>/);
	assert.match(read('../components/director/DirectorViews.svelte'), /\{#if !ui\.sidebarOpen\}/);
	assert.match(read('../components/director/DirectionAside.svelte'), /<ComposedPrompt source=\{doc\} shotId=\{witness\.id\} \/>/);
	assert.match(read('../components/director/BibleAside.svelte'), /onpick=\{\(id\) => addCardImage\(card, SPACES\[kind\], id\)\}/);
});

test('director: the Review lists the takes with their cards and compares them in the viewer, never generating by itself', () => {
	const review = read('../components/director/ReviewView.svelte');
	assert.match(review, /const taking = \$derived\(ui\.compare\?\.length === 2 \|\| ui\.preview\?\.kind === 'result'\);\n\tconst watching = \$derived\(ui\.reviewMonitor \|\| taking\);/);
	assert.match(review, /\{#if watching\}\n\t\t<div class="relative grid min-h-0 shrink-0 border-b border-line" style:height="46%">\n\t\t\t<Viewer \/>/);
	assert.match(review, /<TakeCard \{take\} clip=\{c\} \/>/);
	assert.match(review, /onclick: assembleChosen/);
	assert.doesNotMatch(review, /startGeneration/);
	for (const file of ['../components/inspector/Inspector.svelte', '../components/inspector/TakesSection.svelte', '../components/storyboard/ShotQuickEdit.svelte', '../components/storyboard/StoryboardView.svelte', '../components/viewer/Viewer.svelte']) assert.doesNotMatch(read(file), /startGeneration/, file);
});

test('director: in the Review, a click in the block of a shot or on one of its takes chooses the shot, which shows plainly, and the monitor stays open on the cut once open', () => {
	const review = read('../components/director/ReviewView.svelte');
	assert.match(review, /const pick = \(c\) => pickShot\(c, clipAt\(ui\.playhead\)\?\.id !== c\.id\);/);
	assert.match(review, /function choose\(e, c\) \{\n\t\tif \(e\.target\.closest\?\.\('button, a, input, select, textarea, label'\)\) return;\n\t\tpick\(c\);\n\t\}/);
	assert.match(review, /<div role="presentation" class="px-4 py-3" onclick=\{\(e\) => choose\(e, c\)\}>/);
	assert.match(review, /<button type="button" class="mb-2 flex min-h-7 cursor-pointer items-center gap-2 rounded px-1\.5 text-left transition-colors hover:bg-surface-2"[^>]*onclick=\{\(\) => pick\(c\)\}>/);
	assert.match(review, /aria-current=\{isSel\(c\) \? 'true' : undefined\}>\n\t+\{#if isSel\(c\)\}<span class="absolute inset-y-0 left-0 w-0\.5 bg-signal" aria-hidden="true"><\/span>\{\/if\}/);
	assert.match(review, /\$effect\(\(\) => \{\n\t\tif \(taking\) ui\.reviewMonitor = true;\n\t\}\);\n\t\$effect\(\(\) => \(\) => \(ui\.reviewMonitor = false\)\);/);
	assert.match(review, /function closeMonitor\(\) \{\n\t\tui\.preview = null;\n\t\tui\.compare = null;\n\t\tui\.reviewMonitor = false;\n\t\}/);
	assert.match(review, /label: t\('panels\.director\.review\.closeMonitor'\)[^\n]*onclick: closeMonitor/);
	assert.match(review, /onclick=\{\(\) => openSeam\(c\)\}/);
	assert.doesNotMatch(review, /function openSeam|select\('clip'/);
	const card = read('../components/takes/TakeCard.svelte');
	assert.match(card, /onclick=\{\(\) => previewTake\(take\)\}/);
	assert.doesNotMatch(card, /ui\.preview = /);
	assert.match(read('../components/storyboard/BandLanes.svelte'), /import \{ previewTake \} from '\.\.\/\.\.\/lib\/monitor\.svelte\.js';/);
	assert.match(read('./commands.js'), /\} else if \(ui\.reviewMonitor\) ui\.reviewMonitor = false;\n\telse if \(ui\.seamCompare\) ui\.seamCompare = null;/);
	for (const locale of ['en', 'fr']) assert.ok(JSON.parse(read(`../i18n/${locale}/panels.json`))['director.review.closeMonitor'], locale);
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

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { placedOn, seamShots, shownShots } from './monitor.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const viewerJson = (locale) => JSON.parse(source(`../i18n/${locale}/viewer.json`));
const shot = (id, start, extra = {}) => ({ id, start, dur: 4, take: null, assetId: null, ...extra });
const clips = [shot('s1', 0, { take: 't1', assetId: 'gen-t1' }), shot('s2', 4, { take: 't2', assetId: 'gen-t2' }), shot('s3', 8, { assetId: 'a3' })];
const takes = { t1: { id: 't1', shotId: 's1' }, t1b: { id: 't1b', shotId: 's1' }, t2: { id: 't2', shotId: 's2' } };
const find = { take: (id) => takes[id] ?? null, asset: (id) => (id === 'a3' ? { id } : null) };
const view = (extra = {}) => ({ clips, playhead: 1, ...extra });

test('monitor: a take is placed on its shot only while the shot plays it, with its own media', () => {
	assert.equal(placedOn(clips, takes.t1), clips[0]);
	assert.equal(placedOn(clips, takes.t2), clips[1]);
	assert.equal(placedOn(clips, takes.t1b), null);
	assert.equal(placedOn([{ ...clips[0], assetId: 'a9' }], takes.t1), null);
	assert.equal(placedOn([{ ...clips[0], assetId: null }], takes.t1), null);
	assert.equal(placedOn([{ ...clips[0], id: 's9' }], takes.t1), null);
	assert.equal(placedOn(clips, null), null);
});

test('monitor: the sequence shows the shot under the playhead, and none past the end of the cut', () => {
	assert.deepEqual(shownShots(view({ playhead: 0 }), find), ['s1']);
	assert.deepEqual(shownShots(view({ playhead: 4 }), find), ['s2']);
	assert.deepEqual(shownShots(view({ playhead: 11.9 }), find), ['s3']);
	assert.deepEqual(shownShots(view({ playhead: 12 }), find), []);
});

test('monitor: a take preview shows its shot only when the take is placed, a source media shows none', () => {
	assert.deepEqual(shownShots(view({ playhead: 5, preview: { kind: 'result', id: 't1' } }), find), ['s1']);
	assert.deepEqual(shownShots(view({ preview: { kind: 'result', id: 't1b' } }), find), []);
	assert.deepEqual(shownShots(view({ preview: { kind: 'asset', id: 'a3' } }), find), []);
	assert.deepEqual(shownShots(view({ preview: { kind: 'asset', id: 'gone' } }), find), ['s1']);
	assert.deepEqual(shownShots(view({ preview: { kind: 'result', id: 'gone' } }), find), ['s1']);
});

test('monitor: a comparison shows the shots of its placed takes, and needs both takes to stay a comparison', () => {
	assert.deepEqual(shownShots(view({ compare: ['t1', 't2'] }), find), ['s1', 's2']);
	assert.deepEqual(shownShots(view({ compare: ['t1b', 't1'] }), find), ['s1']);
	assert.deepEqual(shownShots(view({ compare: ['t1b', 't2'], preview: { kind: 'result', id: 't1' } }), find), ['s2']);
	assert.deepEqual(shownShots(view({ compare: ['t1', 'gone'], preview: { kind: 'result', id: 't2' } }), find), ['s2']);
	assert.deepEqual(shownShots(view({ compare: ['t1b', 'gone'] }), find), ['s1']);
});

test('monitor: the seam of the band shows the shot and the one before it, over any preview', () => {
	assert.deepEqual(seamShots(clips, 's2'), ['s1', 's2']);
	assert.deepEqual(seamShots(clips, 's1'), []);
	assert.deepEqual(seamShots(clips, 'gone'), []);
	assert.deepEqual(shownShots(view({ seam: 's3', preview: { kind: 'result', id: 't1' }, compare: ['t1', 't2'] }), find), ['s2', 's3']);
});

test('monitor: the viewer grades the placed take of a preview and of each side of a comparison, filter and LUT, and leaves the other takes and the media raw', () => {
	const viewer = source('../components/viewer/Viewer.svelte');
	assert.match(viewer, /const resultShot = \$derived\(previewResult \? placedOn\(doc\.clips, previewResult\) : null\);/);
	assert.match(viewer, /const resultLut = \$derived\(resultShot \? lutOf\(resultShot\) : null\);/);
	assert.match(viewer, /\{#key Boolean\(resultLut\)\}\n\t+<video\n\t+bind:this=\{resultVideo\}/);
	assert.match(viewer, /controls=\{!resultLut\}\n\t+autoplay=\{Boolean\(resultLut\)\}\n\t+loop=\{Boolean\(resultLut\)\}/);
	assert.match(viewer, /style:filter=\{resultShot \? clipFilter\(resultShot\) : null\}/);
	assert.match(viewer, /\{#if resultLut && resultVideo\}<MatchCanvas source=\{resultVideo\} lut=\{resultLut\} filter=\{clipFilter\(resultShot\)\} \/>\{\/if\}/);
	assert.match(viewer, /\{#each compareRes as res \(res\.id\)\}\n\t+\{@const shot = placedOn\(doc\.clips, res\)\}\n\t+\{@const look = shot \? lutOf\(shot\) : null\}/);
	assert.match(viewer, /bind:this=\{sides\[res\.id\]\}/);
	assert.match(viewer, /style:filter=\{shot \? clipFilter\(shot\) : null\}/);
	assert.match(viewer, /\{#if look && sides\[res\.id\]\}<MatchCanvas source=\{sides\[res\.id\]\} lut=\{look\} filter=\{clipFilter\(shot\)\} \/>\{\/if\}/);
	assert.match(viewer, /const graded = \(shot\) => Boolean\(shot\) && \(clipFilter\(shot\) !== 'none' \|\| Boolean\(lutOf\(shot\)\)\);/);
	assert.match(viewer, /\{takeLabel\(res\)\}\{#if graded\(shot\)\} <span class="text-white\/60">\{t\('viewer\.graded'\)\}<\/span>\{\/if\}/);
	assert.match(viewer, /\{t\('viewer\.outOfCut'\)\}\{#if graded\(resultShot\)\} \{t\('viewer\.graded'\)\}\{\/if\}/);
	const media = viewer.slice(viewer.indexOf('{:else if previewAsset}'), viewer.indexOf('{:else if clip && !a}'));
	assert.ok(media.length > 0);
	assert.doesNotMatch(media, /filter|MatchCanvas/);
	assert.equal(viewerJson('fr').graded, '· étalonnage du plan');
	assert.equal(viewerJson('en').graded, '· shot grade');
});

test('monitor: the seam of the band and its side thumbnails show each image through the grade of its own shot', () => {
	const band = source('../components/storyboard/BandMonitor.svelte');
	assert.match(band, /\[\[lastSrc, t\('storyboard\.band\.endOf', \{ n: num\(index - 1\) \}\), prev, index - 1\], \[firstSrc, t\('storyboard\.band\.startOf', \{ n: num\(index\) \}\), clip, index\]\] as \[src, caption, shot, at\], k \(caption\)\}\n\t+\{@const look = lutOf\(shot\)\}/);
	assert.match(band, /<img bind:this=\{stills\[k\]\} \{src\} alt="" class="h-full w-full object-cover" style:filter=\{clipFilter\(shot\)\} \/>/);
	assert.match(band, /\{#if src && look && stills\[k\]\}<MatchCanvas source=\{stills\[k\]\} lut=\{look\} filter=\{clipFilter\(shot\)\} cover \/>\{\/if\}/);
	assert.match(band, /\{#if src\}<img \{src\} alt="" class="h-full w-full object-cover" style:filter=\{clipFilter\(shot\)\} \/>\{\/if\}<\/span>/);
	const canvas = source('../components/viewer/MatchCanvas.svelte');
	assert.match(canvas, /let \{ source, lut, filter = 'none', fade = 1, cover = false \} = \$props\(\);/);
	assert.match(canvas, /class="pointer-events-none absolute inset-0 h-full w-full \{cover \? 'object-cover' : 'object-contain'\}"/);
});

test('monitor: the seam of the band carries the color controls of both its shots, folded by default, without the button that applies to every shot', () => {
	const band = source('../components/storyboard/BandMonitor.svelte');
	assert.match(band, /let grading = \$state\(\[false, false\]\);/);
	assert.match(band, /const roomy = \$derived\(w >= 1150\);\n\tconst beside = \$derived\(roomy \|\| grading\.some\(Boolean\)\);\n\tconst gradeColumn = \$derived\(roomy \? '240px' : 'minmax\(180px, 200px\)'\);/);
	assert.match(band, /style:grid-template-columns=\{beside \? `\$\{gradeColumn\} minmax\(0, 300px\) minmax\(0, 300px\) \$\{gradeColumn\}` : 'repeat\(2, minmax\(0, 300px\)\)'\}/);
	assert.match(band, /style:grid-template-areas=\{beside \? '"grade0 still0 still1 grade1" "grade0 seam seam grade1"' : '"still0 still1" "grade0 grade1" "seam seam"'\}/);
	assert.match(band, /<div class="relative aspect-video w-full overflow-hidden rounded [^\n]*style:grid-area="still\{k\}">/);
	assert.match(band, /<div class="min-w-0 \{beside \? 'overflow-y-auto' : ''\}" style:grid-area="grade\{k\}" style:max-height=\{beside \? `\$\{Math\.max\(160, h - 64\)\}px` : null\} data-seam-grade=\{shot\.id\}>/);
	assert.match(band, /<div class="flex min-w-0" style:grid-area="seam"><SeamPanel \{clip\} title=\{false\} compare=\{false\} \/><\/div>/);
	assert.match(band, /aria-expanded=\{grading\[k\]\}\n\t+aria-controls="\{id\}-grade-\{k\}"\n\t+onclick=\{\(\) => \(grading\[k\] = !grading\[k\]\)\}/);
	assert.match(band, /\{t\('storyboard\.band\.grade', \{ n: num\(at\) \}\)\}<\/span>\n\t+<span class="shrink-0 truncate text-fg" style:max-width="50%">\{colorPresetLabel\(shot\.preset\)\}<\/span>/);
	assert.match(band, /\{#if grading\[k\]\}\n\t+<div id="\{id\}-grade-\{k\}" class="mt-1 space-y-3 rounded-lg border border-line-strong bg-surface-1 p-2\.5">\n\t+<ColorControls clip=\{shot\} compact all=\{false\} \/>/);
	assert.match(band, /<div class="flex min-h-0 flex-col overflow-auto bg-canvas p-3">\n\t+<div class="m-auto flex w-full flex-col items-center gap-2">/);
	assert.doesNotMatch(band, /h-\[168px\] w-\[300px\]/);
	const controls = source('../components/inspector/ColorControls.svelte');
	assert.match(controls, /let \{ clip, compact = false, all = true \} = \$props\(\);/);
	assert.match(controls, /<select class="vp-popup min-w-0 flex-1" value=\{clip\.preset\} onchange=\{\(e\) => apply\(e\.currentTarget\.value\)\}>\n\t+\{#if !\(clip\.preset in colorPresets\)\}<option value=\{clip\.preset\} disabled>\{colorPresetLabel\(clip\.preset\)\}<\/option>\{\/if\}/);
	assert.match(controls, /\{#if !compact\}<div class="vp-section-title">\{t\('inspector\.color\.fine'\)\}<\/div>\{\/if\}/);
	assert.match(controls, /onclick: \(\) => apply\('Original'\) \}\}>\{t\('inspector\.color\.reset'\)\}<\/HostUi>\n\t+\{#if all\}<HostUi name="Button"[^\n]*onclick: applyAll \}\}>\{t\('inspector\.color\.applyAll'\)\}<\/HostUi>\{\/if\}/);
	assert.match(source('../components/inspector/ColorSection.svelte'), /\{#key clip\.id\}<MatchSection \{clip\} \/>\{\/key\}\n\n\t<ColorControls \{clip\} \/>\n\{\/if\}/);
	for (const locale of ['en', 'fr']) assert.match(JSON.parse(source(`../i18n/${locale}/storyboard.json`))['band.grade'], /\{n\}/);
});

test('monitor: every color change of a shot brings that shot to the monitor', () => {
	const color = source('../components/inspector/ColorControls.svelte');
	assert.match(color, /function set\(k, v\) \{\n\t\tclip\[k\] = v;\n\t\tshowShot\(clip\);\n\t\}/);
	assert.match(color, /function apply\(name\) \{\n\t\tact\(\(\) => Object\.assign\(clip, colorPresets\[name\], \{ preset: name \}\)\);\n\t\tshowShot\(clip\);\n\t\}/);
	assert.match(color, /act\(\(\) => doc\.clips\.forEach\(\(c\) => Object\.assign\(c, p\)\)\);\n\t\tshowShot\(clip\);/);
	assert.match(source('../components/inspector/ColorSection.svelte'), /onclick=\{\(\) => matchToPrevious\(clip\)\}/);
	const matching = source('../components/inspector/MatchSection.svelte');
	assert.match(matching, /function setStrength\(v\) \{\n\t\tclip\.match\.strength = v;\n\t\tshowShot\(clip\);\n\t\}/);
	assert.match(matching, /format=\{strength\} onchange=\{setStrength\}/);
	const continuity = source('./continuity.svelte.js');
	assert.match(continuity, /clip\.preset = 'Raccord';\n\}/);
	assert.match(continuity, /act\(\(\) => correct\(clip, ca, cb\)\);\n\tshowShot\(clip\);/);
	assert.match(continuity, /for \(const step of plan\) correct\(step\.clip, step\.from, step\.to\);\n\t\}\);\n\tshowShot\(plan\[0\]\.clip\);/);
	const lib = source('./match.svelte.js');
	assert.match(lib, /act\(\(\) => \(live\.match = \{[^\n]+\}\)\);\n\t\tshowShot\(live\);/);
	assert.match(lib, /act\(\(\) => delete clip\.match\);\n\tshowShot\(clip\);/);
});

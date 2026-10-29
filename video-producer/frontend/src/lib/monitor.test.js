import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent, textOf } from './svelte-harness.js';
import enViewer from '../i18n/en/viewer.json' with { type: 'json' };
import frViewer from '../i18n/fr/viewer.json' with { type: 'json' };
import enStoryboard from '../i18n/en/storyboard.json' with { type: 'json' };
import frStoryboard from '../i18n/fr/storyboard.json' with { type: 'json' };
import { placedOn, seamShots, shownShots } from './monitor.js';
import { lutOf } from './match.js';

const shot = (id, start, extra = {}) => ({ id, start, dur: 4, take: null, assetId: null, ...extra });
const clips = [shot('s1', 0, { take: 't1', assetId: 'gen-t1' }), shot('s2', 4, { take: 't2', assetId: 'gen-t2' }), shot('s3', 8, { assetId: 'a3' })];
const takes = { t1: { id: 't1', shotId: 's1' }, t1b: { id: 't1b', shotId: 's1' }, t2: { id: 't2', shotId: 's2' } };
const find = { take: (id) => takes[id] ?? null, asset: (id) => (id === 'a3' ? { id } : null) };
const view = (extra = {}) => ({ clips, playhead: 1, ...extra });

const { doc, ui, dispose } = await import('./state.svelte.js');
const { clipFilter, colorPresetLabel, colorPresets } = await import('./look.js');
const { project } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { showShot } = await import('./monitor.svelte.js');
const { clearMatch } = await import('./match.svelte.js');
const { matchToPrevious } = await import('./continuity.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

globalThis.Image = class {};

after(() => {
	dispose();
	delete globalThis.Image;
});

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

const VIEWER = new URL('../components/viewer/Viewer.svelte', import.meta.url).href;
const BAND_MONITOR = new URL('../components/storyboard/BandMonitor.svelte', import.meta.url).href;
const MATCH_CANVAS = new URL('../components/viewer/MatchCanvas.svelte', import.meta.url).href;
const COLOR_CONTROLS = new URL('../components/inspector/ColorControls.svelte', import.meta.url).href;
const COLOR_SECTION = new URL('../components/inspector/ColorSection.svelte', import.meta.url).href;
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const GRADED = { exposure: 0.3, contrast: 110, saturation: 90, temperature: 20, preset: 'Lumière dorée' };
const RAW = { exposure: 0, contrast: 100, saturation: 100, temperature: 0, preset: 'Original' };
const MATCH = { anchor: 'reference', anchorId: 'r1', assetId: 'gen-t1', strength: 80, source: [50, 0, 0, 10, 5, 5], target: [60, 5, -5, 12, 6, 6] };
const done = (id, shotId, extra = {}) => ({ id, shotId, status: 'done', label: 'draft', quality: 'draft', variant: 'A', url: `/${id}.mp4`, thumbUrl: `/${id}.jpg`, createdAt: `2026-10-29T10:0${id.slice(-1)}:00Z`, ...extra });
const videoTags = (html) => [...clean(html).matchAll(/<video [^>]*>/g)].map((m) => m[0]);

function scene() {
	project.id = 'p1';
	Object.assign(ui, { workspace: 'timeline', preview: null, compare: null, seamCompare: null, selection: null, picked: [], playhead: 1, reviewMonitor: false, toasts: [] });
	doc.clips = [
		{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'draft', take: 't1', assetId: 'gen-t1', srcIn: 0, ...GRADED, match: { ...MATCH } },
		{ id: 's2', start: 4, dur: 4, label: 'Two', stage: 'draft', take: 't2', assetId: 'gen-t2', srcIn: 0, ...RAW },
		{ id: 's3', start: 8, dur: 4, label: 'Three', stage: 'todo', take: null, assetId: null, srcIn: 0, ...RAW }
	];
	doc.assets = [
		{ id: 'gen-t1', kind: 'video', name: 'Take 1', src: null, origin: { kind: 'history', generationId: 'g1', fileId: 'f1' }, srcDur: 4, generated: true, resultId: 't1' },
		{ id: 'gen-t2', kind: 'video', name: 'Take 2', src: null, origin: { kind: 'history', generationId: 'g2', fileId: 'f2' }, srcDur: 4, generated: true, resultId: 't2' },
		{ id: 'lib', kind: 'video', name: 'Rushes', src: '/lib.mp4', origin: { kind: 'library', itemId: 'u1' }, srcDur: 6, generated: false },
		{ id: 'img1', kind: 'image', name: 'End of one', src: '/img1.png', origin: { kind: 'library', itemId: 'u2' }, generated: false },
		{ id: 'img2', kind: 'image', name: 'Start of two', src: '/img2.png', origin: { kind: 'library', itemId: 'u3' }, generated: false }
	];
	doc.frames = [
		{ id: 'f1', shotId: 's1', role: 'last', time: 4, assetId: 'img1' },
		{ id: 'f2', shotId: 's2', role: 'first', time: 4, assetId: 'img2' }
	];
	setTakes('p1', [done('t1', 's1'), done('t2', 's2'), done('t3', 's1', { variant: 'B' })]);
	return doc.clips;
}

function seamScene() {
	const [graded, raw] = scene();
	Object.assign(ui, { workspace: 'storyboard', storyView: 'band', selection: { kind: 'clip', id: 's2' }, seamCompare: 's2' });
	return [graded, raw];
}

test('monitor: the viewer grades the placed take of a preview and of each side of a comparison, filter and LUT, and leaves the other takes and the media raw', async () => {
	const [graded, raw] = scene();
	assert.ok(lutOf(graded) && clipFilter(graded) !== 'none');
	assert.ok(!lutOf(raw) && clipFilter(raw) === 'none');
	const gradedFilter = `style="filter: ${escaped(clipFilter(graded))};"`;

	ui.preview = { kind: 'result', id: 't1' };
	let html = clean(await renderComponent(VIEWER));
	let [tag] = videoTags(html);
	assert.match(tag, new RegExp(gradedFilter));
	assert.match(tag, /autoplay=""/);
	assert.match(tag, /loop=""/);
	assert.doesNotMatch(tag, /controls/);
	assert.match(textOf(html), new RegExp(`${escaped(t('viewer.outOfCut'))}\\s*${escaped(t('viewer.graded'))}`));

	ui.preview = { kind: 'result', id: 't3' };
	html = clean(await renderComponent(VIEWER));
	[tag] = videoTags(html);
	assert.match(tag, /controls=""/);
	assert.doesNotMatch(tag, /style="filter|autoplay|loop/);
	assert.ok(textOf(html).includes(t('viewer.outOfCut')) && !textOf(html).includes(t('viewer.graded')));

	ui.preview = { kind: 'result', id: 't2' };
	html = clean(await renderComponent(VIEWER));
	[tag] = videoTags(html);
	assert.match(tag, /controls=""/);
	assert.match(tag, /style="filter: none;"/);
	assert.ok(!textOf(html).includes(t('viewer.graded')));

	ui.preview = null;
	ui.compare = ['t1', 't2'];
	html = clean(await renderComponent(VIEWER));
	const sides = videoTags(html);
	assert.equal(sides.length, 2);
	assert.match(sides[0], new RegExp(gradedFilter));
	assert.match(sides[1], /style="filter: none;"/);
	assert.match(html, new RegExp(`One · Draft A<span class="text-white/60">${escaped(t('viewer.graded'))}</span></span>`));
	assert.match(html, /Two · Draft A<\/span>/);

	ui.compare = null;
	ui.preview = { kind: 'asset', id: 'lib' };
	html = clean(await renderComponent(VIEWER));
	[tag] = videoTags(html);
	assert.match(tag, /src="\/lib\.mp4"[^>]*controls=""/);
	assert.doesNotMatch(tag, /style=/);
	assert.ok(textOf(html).includes(t('viewer.sourceMedia')) && !textOf(html).includes(t('viewer.graded')));
	assert.equal(frViewer.graded, '· étalonnage du plan');
	assert.equal(enViewer.graded, '· shot grade');
});

test('monitor: the seam of the band shows each still through the grade of its own shot, and the LUT canvas composes the filter, the fade and the fit it is given', async () => {
	const [graded] = seamScene();
	const html = clean(await renderComponent(BAND_MONITOR));
	const stills = [...html.matchAll(/<img src="([^"]*)" alt="" class="h-full w-full object-cover" style="filter: ([^"]*);"/g)].map((m) => [m[1], m[2]]);
	assert.deepEqual(stills, [['/img1.png', clipFilter(graded)], ['/img2.png', 'none']]);
	assert.ok(html.includes(t('storyboard.band.endOf', { n: '01' })) && html.includes(t('storyboard.band.startOf', { n: '02' })));

	const covering = clean(await renderComponent(MATCH_CANVAS, { source: null, lut: null, filter: 'sepia(0.08)', fade: 0.5, cover: true }));
	assert.match(covering, /<canvas class="pointer-events-none absolute inset-0 h-full w-full object-cover" aria-hidden="true" style="filter: sepia\(0\.08\) brightness\(0\.5\); visibility: hidden;">/);
	const plain = clean(await renderComponent(MATCH_CANVAS, { source: null, lut: null }));
	assert.match(plain, /object-contain" aria-hidden="true" style="filter: none; visibility: hidden;"/);
	const faded = clean(await renderComponent(MATCH_CANVAS, { source: null, lut: null, filter: 'none', fade: -1 }));
	assert.match(faded, /style="filter: brightness\(0\); visibility: hidden;"/);
});

test('monitor: the seam of the band carries the color controls of both its shots, folded by default, without the button that applies to every shot', async () => {
	const [graded] = seamScene();
	const html = clean(await renderComponent(BAND_MONITOR));
	assert.deepEqual([...html.matchAll(/data-seam-grade="([^"]*)" style="grid-area: (grade\d);"/g)].map((m) => [m[1], m[2]]), [['s1', 'grade0'], ['s2', 'grade1']]);
	assert.equal((html.match(/aria-expanded="false" aria-controls="[^"]+-grade-\d"/g) ?? []).length, 2);
	assert.match(html, /grid-template-columns: repeat\(2, minmax\(0, 300px\)\); grid-template-areas: &quot;still0 still1&quot; &quot;grade0 grade1&quot; &quot;seam seam&quot;;/);
	assert.match(html, new RegExp(`${escaped(t('storyboard.band.grade', { n: '01' }))}</span> <span class="shrink-0 truncate text-fg" style="max-width: 50%;">${escaped(colorPresetLabel(graded.preset))}</span>`));
	assert.match(html, new RegExp(`${escaped(t('storyboard.band.grade', { n: '02' }))}</span> <span class="shrink-0 truncate text-fg" style="max-width: 50%;">${escaped(colorPresetLabel('Original'))}</span>`));
	assert.match(html, /<div class="flex min-w-0" style="grid-area: seam;"><div class="flex w-full flex-col gap-2\.5" data-seam-panel="s2">/);
	assert.doesNotMatch(html, /<select|vp-section-title/);
	assert.ok(!html.includes(t('inspector.color.applyAll')) && !html.includes(t('inspector.color.reset')));
	for (const dictionary of [enStoryboard, frStoryboard]) assert.match(dictionary['band.grade'], /\{n\}/);

	const compact = clean(await renderComponent(COLOR_CONTROLS, { clip: { ...graded, preset: 'Weird' }, compact: true, all: false }));
	assert.match(compact, /<select class="vp-popup min-w-0 flex-1"><option value="Weird" disabled="" selected="">Weird<\/option>/);
	assert.equal((compact.match(/<option /g) ?? []).length, Object.keys(colorPresets).length + 1);
	assert.doesNotMatch(compact, /vp-section-title|aria-pressed/);
	assert.ok(compact.includes(t('inspector.color.reset')) && !compact.includes(t('inspector.color.fine')) && !compact.includes(t('inspector.color.applyAll')));

	const full = clean(await renderComponent(COLOR_CONTROLS, { clip: graded }));
	assert.equal((full.match(/aria-pressed="true"/g) ?? []).length, 1);
	assert.equal((full.match(/aria-pressed="false"/g) ?? []).length, Object.keys(colorPresets).length - 1);
	assert.doesNotMatch(full, /<select/);
	for (const key of ['inspector.color.presets', 'inspector.color.fine', 'inspector.color.reset', 'inspector.color.applyAll']) assert.ok(full.includes(t(key)), key);

	const section = clean(await renderComponent(COLOR_SECTION, { clip: graded }));
	for (const key of ['inspector.color.scope', 'inspector.match.title', 'inspector.color.presets', 'inspector.color.applyAll']) assert.ok(section.includes(t(key)), key);
	doc.assets.push({ id: 'snd', kind: 'audio', name: 'Voice', src: '/voice.wav', origin: { kind: 'library', itemId: 'u4' }, generated: false });
	const silent = clean(await renderComponent(COLOR_SECTION, { clip: { ...graded, assetId: 'snd' } }));
	assert.equal(textOf(silent), t('inspector.color.pending'));
});

test('monitor: every color change of a shot brings that shot to the monitor', () => {
	const [graded, raw, empty] = scene();
	Object.assign(ui, { selection: { kind: 'clip', id: 's2' }, playhead: 5, preview: { kind: 'result', id: 't3' } });
	clearMatch(graded);
	assert.equal(graded.match, undefined);
	assert.deepEqual([ui.preview, ui.compare, ui.selection, ui.playhead], [null, null, { kind: 'clip', id: 's1' }, 0.01]);

	Object.assign(ui, { selection: { kind: 'clip', id: 's2' }, playhead: 5, preview: { kind: 'result', id: 't1' } });
	showShot(graded);
	assert.deepEqual([ui.preview, ui.selection.id, ui.playhead], [{ kind: 'result', id: 't1' }, 's1', 0.01]);

	Object.assign(ui, { workspace: 'director', directorView: 'review', reviewMonitor: false, compare: ['t1', 't2'], preview: null });
	showShot(empty);
	assert.deepEqual([ui.preview, ui.compare, ui.reviewMonitor, ui.selection.id, ui.playhead], [null, null, true, 's3', 8.01]);

	const before = { ...raw };
	const notes = [];
	const host = window.__potionui.notifications;
	host.toast = (level, message) => notes.push([level, message]);
	matchToPrevious(raw);
	host.toast = () => {};
	assert.deepEqual({ ...raw }, before);
	assert.deepEqual(notes, [['warning', t('lib.continuity.pending')]]);
});

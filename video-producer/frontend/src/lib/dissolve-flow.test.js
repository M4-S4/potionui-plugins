import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { clean, renderComponent } from './svelte-harness.js';
import { DISSOLVE_CHOICES, headTrim, joins, onFrame, playedLengths, setDissolve, tailTrim } from './dissolve.js';

const { doc, ui, act, adopt, checkpoint, relayout, select, bladeAt, bladeTime, duplicateSelection, undo, seqDuration, clipAt, shotIdAt, addPrompt, addFrame, limitNote, dispose } = await import('./state.svelte.js');
const { drag } = await import('./timeline.js');
const { shotTrim, bandTrim, setShotDuration, setShotIn } = await import('./trims.js');
const { nudgeDuration } = await import('./band.svelte.js');
const { commandById } = await import('./commands.js');
const { t } = await import('../i18n/index.svelte.js');

const here = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(readFileSync(join(here, '..', '..', '..', 'tests', 'fixtures', 'dissolve_cases.json'), 'utf-8'));
const VIEWER = new URL('../components/viewer/Viewer.svelte', import.meta.url).href;
const TIMELINE = new URL('../components/timeline/Timeline.svelte', import.meta.url).href;
const SEAM = new URL('../components/storyboard/SeamTransition.svelte', import.meta.url).href;
const INSPECTOR = new URL('../components/inspector/Inspector.svelte', import.meta.url).href;
const shot = (id, start, dur, extra = {}) => ({ id, start, dur, srcIn: 0, label: `Shot ${id}`, stage: 'draft', take: null, assetId: `m${id}`, fadeIn: 0, fadeOut: 0, ...extra });

after(() => dispose());

function project() {
	doc.fps = 25;
	doc.aspect = '16:9';
	doc.assets = ['a', 'b', 'c'].map((id) => ({ id: `m${id}`, kind: 'video', name: `Take ${id}`, src: `/m/${id}.mp4`, width: 1280, height: 720, srcDur: 6 }));
	doc.clips = [shot('a', 0, 2, { fadeOut: 0.4 }), shot('b', 2, 2, { fadeIn: 0.4, fadeOut: 0.4 }), shot('c', 4, 1, { fadeIn: 0.4 })];
	doc.prompts = [];
	doc.frames = [];
	doc.audio = [];
	doc.titles = [];
	doc.markers = [];
	Object.assign(ui, { workspace: 'media', preview: null, compare: null, playhead: 0, selection: null, picked: [], inspectorOpen: true });
}

function dissolveB(seconds = 1) {
	act(() => {
		setDissolve(doc.clips, 1, seconds);
		relayout();
	});
}

for (const c of cases) {
	test(`dissolve flow: the page lays the shared case "${c.name}" out where the assistant does`, () => {
		doc.clips = c.clips.map((clip, i) => ({ id: `c${i}`, start: 99, srcIn: 0, ...clip }));
		relayout();
		assert.ok(
			doc.clips.every((clip, i) => Math.abs(clip.start - c.starts[i]) < 1e-9),
			doc.clips.map((clip) => clip.start).join(', ')
		);
	});
}

test('dissolve flow: a dissolve shortens the film by its length, moves the later shots, and undoes in one step', () => {
	project();
	assert.equal(seqDuration(), 5);
	dissolveB();
	assert.deepEqual(
		doc.clips.map((c) => [c.start, c.fadeIn, c.fadeOut]),
		[
			[0, 0, 0],
			[1, 0, 0.4],
			[3, 0.4, 0]
		]
	);
	assert.equal(seqDuration(), 4);
	undo();
	assert.deepEqual(
		doc.clips.map((c) => [c.start, c.fadeIn, c.fadeOut, 'dissolve' in c]),
		[
			[0, 0, 0.4, false],
			[2, 0.4, 0.4, false],
			[4, 0.4, 0, false]
		]
	);
});

test('dissolve flow: the blade keeps the dissolve on the head of a shot and a duplicate starts with a cut', () => {
	project();
	doc.clips[1].dur = 4;
	dissolveB();
	select('clip', 'b');
	bladeAt(3.5);
	assert.deepEqual(
		doc.clips.map((c) => [c.dur, c.dissolve ?? 0]),
		[
			[2, 0],
			[2.5, 1],
			[1.5, 0],
			[1, 0]
		]
	);
	assert.deepEqual(
		doc.clips.map((c) => c.start),
		[0, 1, 3.5, 5]
	);
	project();
	dissolveB();
	select('clip', 'b');
	duplicateSelection();
	assert.deepEqual(
		doc.clips.map((c) => c.dissolve ?? 0),
		[0, 1, 0, 0]
	);
	assert.deepEqual(
		doc.clips.map((c) => c.start),
		[0, 1, 3, 5]
	);
});

test('dissolve flow: the viewer lays the incoming picture over the outgoing one at the share of the dissolve gone by', async () => {
	project();
	dissolveB();
	ui.playhead = 1.5;
	const middle = clean(await renderComponent(VIEWER));
	assert.match(middle, /<video[^>]*src="\/m\/a\.mp4"[^>]*style="opacity: 1;/);
	assert.match(middle, /<video[^>]*src="\/m\/b\.mp4"[^>]*data-dissolve-layer="b"[^>]*style="opacity: 0\.5;/);
	ui.playhead = 0.5;
	assert.doesNotMatch(clean(await renderComponent(VIEWER)), /data-dissolve-layer/);
	ui.playhead = 2.5;
	const after = clean(await renderComponent(VIEWER));
	assert.doesNotMatch(after, /data-dissolve-layer/);
	assert.match(after, /<video[^>]*src="\/m\/b\.mp4"/);
});

test('dissolve flow: the timeline marks the dissolve on its cut, draws each shot to the middle of it and hides the fade it replaces', async () => {
	project();
	ui.pxPerSec = 100;
	const before = clean(await renderComponent(TIMELINE));
	assert.doesNotMatch(before, /data-dissolve=/);
	const fadesBefore = (before.match(new RegExp(`aria-label="${t('timeline.fade.in')}"`, 'g')) ?? []).length;
	dissolveB();
	const html = clean(await renderComponent(TIMELINE));
	const tip = t('timeline.dissolve.tip', { dur: '1.0 s' });
	assert.match(html, new RegExp(`aria-label="${tip}"[^>]*data-dissolve="b"`));
	assert.match(html, /data-dissolve="b" style="left: 150px; width: 100px;"/);
	assert.match(html, new RegExp(`aria-label="${t('timeline.clip.label', { name: 'Shot a', stage: t('lib.stage.draft'), dur: '2.0 s' })}" style="left: 0px; width: 150px;`));
	assert.match(html, new RegExp(`aria-label="${t('timeline.clip.label', { name: 'Shot b', stage: t('lib.stage.draft'), dur: '2.0 s' })}" style="left: 150px; width: 150px;`));
	assert.match(html, new RegExp(`aria-label="${t('timeline.clip.label', { name: 'Shot c', stage: t('lib.stage.draft'), dur: '1.0 s' })}" style="left: 300px; width: 100px;`));
	assert.equal((html.match(new RegExp(`aria-label="${t('timeline.fade.in')}"`, 'g')) ?? []).length, fadesBefore - 1);
});

test('dissolve flow: the cut offers the dissolve, says how much shorter the film gets, and the inspector greys the fades it replaces', async () => {
	project();
	const cut = clean(await renderComponent(SEAM, { clip: doc.clips[1] }));
	assert.match(cut, /<option value="0" selected/);
	assert.ok(cut.includes(t('timeline.dissolve.hint')));
	assert.equal(clean(await renderComponent(SEAM, { clip: doc.clips[0] })).trim(), '');
	dissolveB();
	const joined = clean(await renderComponent(SEAM, { clip: doc.clips[1] }));
	assert.match(joined, /<option value="1" selected/);
	assert.ok(joined.includes(t('timeline.dissolve.shorter', { dur: '1.0 s' })));
	select('clip', 'b');
	const inspector = clean(await renderComponent(INSPECTOR));
	assert.ok(inspector.includes(t('inspector.fades.dissolved')));
	assert.match(inspector, /data-seam-transition="b"/);
});

test('dissolve flow: the cut window of the Storyboard grid offers the dissolve, the compact cuts of the band and of the review of Director AI do not', async () => {
	project();
	const PANEL = new URL('../components/storyboard/SeamPanel.svelte', import.meta.url).href;
	assert.match(clean(await renderComponent(PANEL, { clip: doc.clips[1] })), /data-seam-transition="b"/);
	assert.doesNotMatch(clean(await renderComponent(PANEL, { clip: doc.clips[1], title: false, compare: false })), /data-seam-transition/);
});

test('dissolve flow: from the middle of a dissolve on, the shot under the playhead is the incoming one, and the blade refuses to cut inside it', () => {
	project();
	dissolveB();
	assert.deepEqual([0.9, 1.2, 1.49, 1.5, 1.8, 2.99, 3].map((time) => clipAt(time)?.id), ['a', 'a', 'a', 'b', 'b', 'b', 'c']);
	assert.equal(shotIdAt(1.8), 'b');
	select('clip', 'b');
	const before = JSON.stringify(doc.clips);
	bladeAt(1.8);
	assert.equal(JSON.stringify(doc.clips), before);
	project();
	doc.clips[1].dur = 4;
	dissolveB();
	select('clip', 'b');
	bladeAt(3);
	assert.deepEqual(
		doc.clips.map((c) => [c.id === 'b' ? 'b' : c.id === 'a' || c.id === 'c' ? c.id : 'new', c.start, c.dur]),
		[
			['a', 0, 2],
			['b', 1, 2],
			['new', 3, 2],
			['c', 5, 1]
		]
	);
});

test('dissolve flow: trimming a dissolved shot from the keyboard keeps its dissolve where it is drawn', () => {
	project();
	dissolveB(0.4);
	select('clip', 'b');
	ui.playhead = 3.2;
	commandById('trim-end').run();
	const expected = [
		[0, 2],
		[1.6, 1.6],
		[3.2, 1]
	];
	assert.ok(
		doc.clips.every((c, i) => Math.abs(c.start - expected[i][0]) < 1e-9 && Math.abs(c.dur - expected[i][1]) < 1e-9),
		JSON.stringify(doc.clips.map((c) => [c.start, c.dur]))
	);
	assert.ok(Math.abs(seqDuration() - 4.2) < 1e-9);
});

test('dissolve flow: an incoming shot without media fades the picture to black, as the export does', async () => {
	project();
	doc.clips[1].assetId = null;
	dissolveB();
	ui.playhead = 1.5;
	const html = clean(await renderComponent(VIEWER));
	assert.match(html, /<div class="pointer-events-none absolute inset-0 bg-black" data-dissolve-layer="b" style="opacity: 0\.5;"><\/div>/);
});

test('dissolve flow: the cut says when a dissolve is rounded to the grid, when it is capped, and when the shot is chained', async () => {
	project();
	doc.fps = 24;
	act(() => {
		setDissolve(doc.clips, 1, 0.5);
		relayout();
	});
	const rounded = clean(await renderComponent(SEAM, { clip: doc.clips[1] }));
	assert.ok(rounded.includes(t('timeline.dissolve.rounded', { dur: '0.48 s' })));
	assert.doesNotMatch(rounded, /data-dissolve-capped/);
	assert.match(rounded, /<option value="0\.4">/);
	assert.match(rounded, /<option value="0\.5" selected/);
	project();
	doc.clips[1].dur = 1;
	doc.clips[2].stage = 'source';
	act(() => {
		setDissolve(doc.clips, 2, 2);
		relayout();
	});
	const capped = clean(await renderComponent(SEAM, { clip: doc.clips[2] }));
	assert.ok(capped.includes(t('timeline.dissolve.capped', { dur: '0.48 s' })));
	assert.doesNotMatch(capped, /data-dissolve-rounded|data-dissolve-chained/);
	doc.clips[2].stage = 'todo';
	assert.ok(clean(await renderComponent(SEAM, { clip: doc.clips[2] })).includes(t('timeline.dissolve.chained')));
	doc.firstFromPrevious = false;
	assert.doesNotMatch(clean(await renderComponent(SEAM, { clip: doc.clips[2] })), /data-dissolve-chained/);
	delete doc.firstFromPrevious;
});

test('dissolve flow: changing the cadence of the project keeps every dissolve and every start', async () => {
	project();
	doc.clips[1].dur = 3.1;
	act(() => {
		setDissolve(doc.clips, 1, 1);
		setDissolve(doc.clips, 2, 0.6);
		relayout();
	});
	const starts = doc.clips.map((c) => c.start);
	const played = joins(doc.clips);
	assert.deepEqual(starts, [0, 1, 3.62]);
	assert.deepEqual(played, [0, 1, 0.48]);
	for (const fps of [24, 25, 30, 48, 50, 60]) {
		doc.fps = fps;
		assert.deepEqual(joins(doc.clips), played, `${fps} fps`);
		relayout();
		assert.deepEqual(
			doc.clips.map((c) => c.start),
			starts,
			`${fps} fps`
		);
		ui.playhead = 1.5;
		assert.match(clean(await renderComponent(VIEWER)), /data-dissolve-layer="b"[^>]*style="opacity: 0\.5;/, `${fps} fps`);
	}
});

test('dissolve flow: at 24 and 48 fps the prompts and frames linked to a shot stay on its start', () => {
	for (const fps of [24, 48]) {
		project();
		doc.fps = fps;
		doc.clips.push(shot('d', 5, 2));
		doc.prompts = doc.clips.map((c, i) => ({ id: `p${i}`, shotId: c.id, start: c.start, dur: c.dur, strength: 75, text: 'x' }));
		doc.frames = doc.clips.map((c, i) => ({ id: `f${i}`, shotId: c.id, time: c.start, assetId: null, role: 'First frame', strength: 75 }));
		act(() => {
			setDissolve(doc.clips, 1, 0.4);
			setDissolve(doc.clips, 2, 0.4);
			setDissolve(doc.clips, 3, 0.4);
			relayout();
		});
		const starts = doc.clips.map((c) => c.start);
		assert.deepEqual(starts, [0, 1.6, 3.2, 3.8], `${fps} fps`);
		assert.deepEqual(
			doc.prompts.map((p) => p.start),
			starts,
			`${fps} fps`
		);
		assert.deepEqual(
			doc.frames.map((f) => f.time),
			starts,
			`${fps} fps`
		);
		assert.deepEqual(
			starts.map((time) => shotIdAt(time)),
			['a', 'b', 'c', 'd'],
			`${fps} fps`
		);
	}
});

test('dissolve flow: trimming the head of a dissolved shot from the keyboard keeps its linked prompt inside it', () => {
	project();
	dissolveB(0.4);
	doc.prompts = [{ id: 'p', shotId: 'b', start: 1.6, dur: 2, strength: 75, text: 'x' }];
	select('clip', 'b');
	ui.playhead = 2;
	commandById('trim-start').run();
	assert.deepEqual(
		doc.clips.map((c) => [c.start, c.dur]),
		[
			[0, 2],
			[1.6, 1.6],
			[3.2, 1]
		]
	);
	assert.equal(doc.prompts[0].start, 1.6);
	assert.equal(shotIdAt(doc.prompts[0].start), 'b');
});

test('dissolve flow: a project whose cuts are all too short for a dissolve trims from the keyboard as before', () => {
	project();
	doc.clips[1].dissolve = 0.03;
	select('clip', 'b');
	ui.playhead = 2.5;
	commandById('trim-start').run();
	assert.deepEqual(
		doc.clips.map((c) => [c.start, c.dur]),
		[
			[0, 2],
			[2.5, 1.5],
			[4, 1]
		]
	);
});

test('dissolve flow: the cut says why a dissolve plays shorter when the starts of a document overlap less than asked, and when its value is too brief', async () => {
	project();
	doc.clips[0].dur = 3.1;
	act(() => {
		setDissolve(doc.clips, 1, 1);
		relayout();
	});
	assert.equal(doc.clips[1].start, 2.1);
	assert.doesNotMatch(clean(await renderComponent(SEAM, { clip: doc.clips[1] })), /data-dissolve-overlap/);
	doc.clips[1].start = 2.12;
	const off = clean(await renderComponent(SEAM, { clip: doc.clips[1] }));
	assert.ok(off.includes(t('timeline.dissolve.shorter', { dur: '0.98 s' })));
	assert.ok(off.includes(t('timeline.dissolve.overlap', { dur: '0.98 s', asked: '1.0 s' })));
	assert.doesNotMatch(off, /data-dissolve-capped|data-dissolve-rounded/);
	project();
	doc.clips[1].dissolve = 0.04;
	const brief = clean(await renderComponent(SEAM, { clip: doc.clips[1] }));
	assert.ok(brief.includes(t('timeline.dissolve.tooBrief')));
	assert.ok(!brief.includes(t('timeline.dissolve.tooShort')));
	project();
	doc.clips[0].dur = 0.12;
	doc.clips[1].dissolve = 1;
	const short = clean(await renderComponent(SEAM, { clip: doc.clips[1] }));
	assert.ok(short.includes(t('timeline.dissolve.tooShort')));
	assert.ok(!short.includes(t('timeline.dissolve.tooBrief')));
});

test('dissolve flow: in a project that dissolves, a prompt and a frame added on the start of a shot off the grid sit on that exact start', () => {
	project();
	doc.clips[0].dur = 2.539;
	dissolveB(1);
	const c = doc.clips[2];
	assert.equal(c.start, 3.539);
	addPrompt(c.start);
	addFrame(null, c.start);
	assert.deepEqual([doc.prompts.at(-1).start, doc.prompts.at(-1).shotId], [3.539, 'c']);
	assert.deepEqual([doc.frames.at(-1).time, doc.frames.at(-1).shotId], [3.539, 'c']);
	addPrompt(3.55);
	assert.deepEqual([doc.prompts.at(-1).start, doc.prompts.at(-1).shotId], [3.539, 'c']);
	addFrame(null, 4.6);
	assert.equal(doc.frames.at(-1).time, 4.6);
	ui.modal = null;
});

test('dissolve flow: the mark of a dissolve is a clickable strip at least 12 px wide on its top, and leaves the rest of its box to the trim handles', async () => {
	const button = (html) => html.match(/<button[^>]*data-dissolve="b"[^>]*>/)?.[0] ?? '';
	const box = (html) => html.match(/<div[^>]*data-dissolve-box="b"[^>]*>/)?.[0] ?? '';
	const width = (tag) => +(tag.match(/width: ([\d.]+)px/)?.[1] ?? NaN);
	for (const [pxPerSec, seconds, wide] of [
		[34, 0.4, 13.6],
		[8, 0.4, 12],
		[8, 1, 12],
		[100, 1, 100]
	]) {
		project();
		ui.pxPerSec = pxPerSec;
		dissolveB(seconds);
		const html = clean(await renderComponent(TIMELINE));
		const tag = button(html);
		assert.ok(tag, `no mark at ${pxPerSec} px/s`);
		const classes = tag.match(/class="([^"]*)"/)[1].split(/\s+/);
		assert.ok(!classes.includes('pointer-events-none'), tag);
		assert.ok(!classes.includes('vp-hit'), tag);
		assert.ok(classes.includes('top-6') && classes.includes('h-3'), tag);
		assert.ok(width(tag) >= 12 && Math.abs(width(tag) - wide) < 1e-9, tag);
		assert.ok(box(html).split('class="')[1].split('"')[0].split(/\s+/).includes('pointer-events-none'), box(html));
		assert.doesNotMatch(html, /data-dissolve-hit/);
	}
});

test('dissolve flow: in a project that dissolves, the blade cuts a shot off the grid exactly at the playhead and keeps its length and its source', () => {
	project();
	doc.clips[0].dur = 3.1;
	doc.clips[1].dur = 4;
	doc.clips[1].srcIn = 0.3;
	dissolveB(1);
	assert.equal(doc.clips[1].start, 2.1);
	select('clip', 'b');
	bladeAt(4.33);
	assert.deepEqual(
		doc.clips.map((c) => [c.start, c.dur, c.srcIn]),
		[
			[0, 3.1, 0],
			[2.1, 2.23, 0.3],
			[4.33, 1.77, 2.53],
			[6.1, 1, 0]
		]
	);
});

test('dissolve flow: in a project that dissolves, trimming the head of a shot from the keyboard leaves round lengths', () => {
	project();
	doc.clips[0].dur = 3.1;
	dissolveB(1);
	select('clip', 'c');
	ui.playhead = 4.43;
	commandById('trim-start').run();
	const c = doc.clips[2];
	assert.deepEqual([c.start, c.dur, c.srcIn], [4.1, 0.67, 0.33]);
});

test('dissolve flow: a reference frame added just before an off-grid shot start sits on that shot and shows its picture', () => {
	project();
	doc.clips[0].dur = 2.539;
	dissolveB(1);
	ui.playhead = 3.52;
	addFrame();
	assert.deepEqual([doc.frames.at(-1).time, doc.frames.at(-1).shotId, doc.frames.at(-1).assetId], [3.539, 'c', 'mc']);
	ui.playhead = 3;
	addFrame();
	assert.deepEqual([doc.frames.at(-1).shotId, doc.frames.at(-1).assetId], ['b', 'mb']);
});

const said = [];
window.__potionui.notifications.toast = (level, message) => said.push(message);
const lastToast = () => said.at(-1) ?? '';
const refusal = (seconds) => t('timeline.dissolve.splitShortens', { dur: seconds });

function lay(durs, dissolves) {
	project();
	doc.clips = durs.map((dur, i) => shot(String.fromCharCode(97 + i), 0, dur, dissolves[i] ? { dissolve: dissolves[i] } : {}));
	relayout();
}

test('dissolve flow: the blade refuses a cut that would shorten the dissolve on the head of the shot, and leaves the document as it was', () => {
	lay([2, 4, 1], [0, 1, 0]);
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 1, 5]);
	select('clip', 'b');
	const before = JSON.stringify(doc.clips);
	bladeAt(2.6);
	assert.equal(JSON.stringify(doc.clips), before);
	assert.equal(lastToast(), refusal('1.0 s'));
});

test('dissolve flow: the blade refuses a cut that would shorten the dissolve into the next shot', () => {
	lay([2, 4, 3], [0, 0, 1.2]);
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 2, 4.8]);
	select('clip', 'b');
	const before = JSON.stringify(doc.clips);
	bladeAt(4.5);
	assert.equal(JSON.stringify(doc.clips), before);
	assert.equal(lastToast(), refusal('1.2 s'));
});

test('dissolve flow: the blade refuses a cut that would remove the only dissolve of the project', () => {
	lay([2, 2], [0, 0.08]);
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 1.92]);
	select('clip', 'a');
	const before = JSON.stringify(doc.clips);
	bladeAt(1.8853);
	assert.equal(JSON.stringify(doc.clips), before);
	assert.equal(lastToast(), refusal('0.08 s'));
});

function seeded(seed) {
	let a = seed >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let x = a;
		x = Math.imul(x ^ (x >>> 15), x | 1);
		x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
		return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
	};
}

test('dissolve flow: on projects drawn at random, every blade the page accepts cuts at the asked time and leaves the later starts and every dissolve length unchanged to the millionth', () => {
	const random = seeded(116);
	const pick = (list) => list[Math.floor(random() * list.length)];
	let accepted = 0;
	let refused = 0;
	let byRule = 0;
	const rule = t('timeline.dissolve.splitShortens', { dur: '@' }).split('@')[0];
	for (let n = 0; n < 80; n++) {
		const count = 2 + Math.floor(random() * 5);
		const durs = Array.from({ length: count }, () => +(0.4 + random() * 5).toFixed(pick([2, 3])));
		const dissolves = durs.map((_, i) => (i > 0 && random() < 0.6 ? pick([...DISSOLVE_CHOICES, 0.08, 0.12]) : 0));
		lay(durs, dissolves);
		doc.fps = pick([24, 25, 30, 50, 60]);
		if (!joins(doc.clips).some(Boolean)) continue;
		const clips = JSON.parse(JSON.stringify(doc.clips));
		const total = seqDuration();
		for (let k = 0; k < 12; k++) {
			doc.clips = JSON.parse(JSON.stringify(clips));
			relayout();
			const time = random() < 0.5 ? onFrame(random() * total, doc.fps) : +(random() * total).toFixed(6);
			const c = clipAt(time);
			if (!c) continue;
			const i = doc.clips.indexOf(c);
			const starts = doc.clips.map((x) => x.start);
			const overlaps = joins(doc.clips);
			const before = JSON.stringify(doc.clips);
			select('clip', c.id);
			const heard = said.length;
			bladeAt(time);
			if (JSON.stringify(doc.clips) === before) {
				refused += 1;
				if (said.length > heard && said.at(-1).startsWith(rule)) byRule += 1;
				continue;
			}
			accepted += 1;
			const label = `${JSON.stringify(clips.map((x) => [x.dur, x.dissolve ?? 0]))} at ${time}`;
			assert.equal(doc.clips.length, clips.length + 1, label);
			assert.ok(Math.abs(doc.clips[i + 1].start - time) <= 1e-6, `${label}: piece at ${doc.clips[i + 1].start}`);
			const after = doc.clips.map((x) => x.start);
			const kept = [...starts.slice(0, i + 1), time, ...starts.slice(i + 1)];
			assert.ok(after.every((start, j) => Math.abs(start - kept[j]) <= 1e-6), `${label}: ${after} against ${kept}`);
			const lengths = joins(doc.clips);
			const want = [...overlaps.slice(0, i + 1), 0, ...overlaps.slice(i + 1)];
			assert.ok(lengths.every((value, j) => Math.abs(value - want[j]) <= 1e-6), `${label}: ${lengths} against ${want}`);
		}
	}
	assert.ok(accepted > 100 && byRule > 50 && refused > byRule, `${accepted} accepted, ${byRule} refused by the rule, ${refused - byRule} by the guards`);
});

test('dissolve flow: in a project that dissolves, a reference frame added away from the playhead, as a double-click does, shows the picture of the shot it lands on', () => {
	project();
	dissolveB(1);
	ui.playhead = 0.5;
	addFrame(undefined, 2.6);
	assert.deepEqual([doc.frames.at(-1).shotId, doc.frames.at(-1).assetId], ['b', 'mb']);
	addFrame(undefined, 3.61);
	assert.deepEqual([doc.frames.at(-1).time, doc.frames.at(-1).shotId, doc.frames.at(-1).assetId], [3.6, 'c', 'mc']);
});

test('dissolve flow: in a project without dissolve, a prompt and a reference frame keep the behaviour of the base', () => {
	project();
	ui.playhead = 4.5;
	addPrompt(1.99);
	assert.deepEqual([doc.prompts.at(-1).start, doc.prompts.at(-1).shotId], [2, 'a']);
	addPrompt(2.37);
	assert.deepEqual([doc.prompts.at(-1).start, doc.prompts.at(-1).shotId], [2.36, 'b']);
	addFrame(undefined, 1.99);
	assert.deepEqual([doc.frames.at(-1).time, doc.frames.at(-1).shotId, doc.frames.at(-1).assetId], [2, 'a', 'mc']);
	addFrame(undefined, 2.6);
	assert.deepEqual([doc.frames.at(-1).time, doc.frames.at(-1).shotId, doc.frames.at(-1).assetId], [2.6, 'b', 'mc']);
	ui.modal = null;
});

test('dissolve flow: in a project that dissolves, the mouse blade cuts on the nearest whole frame counted from zero', () => {
	assert.equal(onFrame(2.137891, 25), 2.12);
	assert.equal(onFrame(2.141, 25), 2.16);
	assert.equal(onFrame(4.33, 30), 4.333333);
	assert.equal(onFrame(1.01, 24), 1);
	project();
	doc.clips[1].dur = 4;
	dissolveB(1);
	select('clip', 'b');
	bladeAt(onFrame(3.137891, doc.fps));
	assert.deepEqual(doc.clips.map((c) => [c.start, c.dur]).slice(1, 3), [
		[1, 2.12],
		[3.12, 1.88]
	]);
	assert.equal(bladeTime(4.337891), 4.32);
	assert.equal(bladeTime(4.351), 4.36);
	doc.fps = 30;
	assert.equal(bladeTime(4.34), 4.333333);
	doc.fps = 25;
	project();
	assert.equal(bladeTime(4.337891), 4.337891);
});

function dragBy(handlers, dx) {
	const fire = (type, x) => window.dispatchEvent(Object.assign(new Event(type), { pointerId: 7, clientX: x, clientY: 0 }));
	drag({ button: 0, pointerId: 7, clientX: 0, clientY: 0, stopPropagation() {}, currentTarget: null }, handlers);
	fire('pointermove', dx / 2);
	fire('pointermove', dx);
	const text = ui.drag?.text ?? '';
	fire('pointerup', dx);
	return text;
}

const settled = () => new Promise((resolve) => queueMicrotask(resolve));

test('dissolve flow: in a project that dissolves, a trim moves one edge on the grid and keeps the source point of the other edge to the millionth', () => {
	project();
	doc.clips[0].dur = 3.1;
	doc.clips[1].dur = 4;
	doc.clips[1].srcIn = 0.3;
	dissolveB(1);
	select('clip', 'b');
	bladeAt(4.33);
	const piece = doc.clips[2];
	assert.deepEqual([piece.start, piece.dur, piece.srcIn], [4.33, 1.77, 2.53]);
	const end = piece.srcIn + piece.dur;
	for (const shift of [0.013, 0.05, -0.05, 0.31, -2.9, 1.5]) {
		const next = headTrim(piece.srcIn, piece.dur, 1, shift);
		assert.ok(Math.abs(next.srcIn + next.dur - end) <= 1e-6, `${shift}: ${JSON.stringify(next)}`);
		assert.ok(next.dur >= 0.4 && next.srcIn >= 0, `${shift}: ${JSON.stringify(next)}`);
		assert.equal(next.srcIn, +next.srcIn.toFixed(6));
	}
	assert.deepEqual(headTrim(2.53, 1.77, 1, 0.05), { srcIn: 2.57, dur: 1.73 });
	assert.deepEqual(headTrim(2.53, 1.77, 0.5, 0.08), { srcIn: 2.57, dur: 1.69 });
	assert.deepEqual(headTrim(0, 0.2, 1, 0.04), { srcIn: 0, dur: 0.2 });
	assert.deepEqual(headTrim(0.3, 0.2, 1, 0.04), { srcIn: 0.3, dur: 0.2 });
	assert.deepEqual(headTrim(0.3, 0.2, 1, -0.08), { srcIn: 0.22, dur: 0.28 });
	assert.equal(tailTrim(4.33, 6.12, 6), 1.79);
	assert.equal(tailTrim(4.33, 4.4, 6), 0.4);
	ui.pxPerSec = 100;
	ui.snapping = false;
	dragBy(shotTrim(piece, 'start'), 5);
	assert.deepEqual([piece.start, piece.dur, piece.srcIn], [4.33, 1.73, 2.57]);
	dragBy(shotTrim(piece, 'end'), 18);
	assert.deepEqual([piece.start, piece.dur, piece.srcIn, +(piece.start + piece.dur).toFixed(6)], [4.33, 1.91, 2.57, 6.24]);
	dragBy(bandTrim(piece), -12);
	assert.deepEqual([piece.dur, +(piece.start + piece.dur).toFixed(6)], [1.79, 6.12]);
	checkpoint();
	setShotIn(piece, 2.6);
	assert.deepEqual([piece.srcIn, piece.dur], [2.6, 1.79]);
	ui.snapping = true;
});

test('dissolve flow: whatever command shortens a shot so that a dissolve plays shorter or stops, the page says it once, and only then', async () => {
	const limited = t('timeline.dissolve.trimLimited', { dur: '0.8 s' });
	const heard = () => said.length;
	const ways = {
		'keyboard end': () => ((ui.playhead = doc.clips[1].start + 1.6), commandById('trim-end').run()),
		'keyboard start': () => ((ui.playhead = doc.clips[1].start + doc.clips[1].dur - 1.6), commandById('trim-start').run()),
		'mouse end': () => dragBy(shotTrim(doc.clips[1], 'end'), (1.6 - doc.clips[1].dur) * ui.pxPerSec),
		'mouse start': () => dragBy(shotTrim(doc.clips[1], 'start'), (doc.clips[1].dur - 1.6) * ui.pxPerSec),
		'band end': () => dragBy(bandTrim(doc.clips[1]), (1.6 - doc.clips[1].dur) * ui.pxPerSec),
		'inspector duration': () => (checkpoint(), setShotDuration(doc.clips[1], 1.6)),
		'inspector in': () => (checkpoint(), setShotIn(doc.clips[1], 4.4)),
		'band nudge': () => ((ui.workspace = 'storyboard'), (ui.storyView = 'band'), select('clip', 'b'), nudgeDuration(-0.5), (ui.workspace = 'media')),
		'any command': () => act(() => ((doc.clips[1].dur = 1.6), relayout()))
	};
	ui.pxPerSec = 100;
	ui.snapping = false;
	for (const [name, run] of Object.entries(ways)) {
		project();
		dissolveB(1);
		if (name === 'band nudge') {
			act(() => ((doc.clips[1].dur = 2.1), relayout()));
			assert.deepEqual(joins(doc.clips), [0, 1, 0], name);
		}
		select('clip', 'b');
		await settled();
		let count = heard();
		run();
		await settled();
		assert.equal(doc.clips[1].dur, 1.6, name);
		assert.deepEqual(joins(doc.clips), [0, 0.8, 0], name);
		assert.equal(doc.clips[1].dissolve, 1, name);
		assert.equal(heard(), count + 1, name);
		assert.equal(said.at(-1), limited, name);
		count = heard();
		undo();
		await settled();
		assert.notEqual(said.at(-1), limited, name);
		assert.ok(said.length <= count + 1, name);
	}

	project();
	dissolveB(1);
	act(() => ((doc.clips[1].dur = 1.2), relayout()));
	assert.deepEqual(joins(doc.clips), [0, 0.6, 0]);
	await settled();
	let count = heard();
	act(() => ((doc.clips[1].dur = 1.6), relayout()));
	await settled();
	assert.deepEqual(joins(doc.clips), [0, 0.8, 0]);
	assert.equal(heard(), count, 'a dissolve that grows back without its full length says nothing');
	act(() => ((doc.clips[1].dur = 2), relayout()));
	await settled();
	assert.equal(heard(), count, 'a dissolve that gets its length back says nothing');

	project();
	dissolveB(1);
	count = heard();
	act(() => ((doc.clips[1].dissolve = 0.6), relayout()));
	await settled();
	assert.equal(heard(), count, 'choosing a shorter dissolve says nothing');

	project();
	dissolveB(1);
	count = heard();
	act(() => ((doc.clips[1].dur = 0.12), relayout()));
	await settled();
	assert.deepEqual(joins(doc.clips), [0, 0, 0]);
	assert.equal(said.at(-1), t('timeline.dissolve.trimStopped'));
	assert.equal(heard(), count + 1);

	project();
	dissolveB(1);
	count = heard();
	const next = JSON.parse(JSON.stringify(doc));
	next.clips[1].dur = 1.6;
	adopt(next);
	await settled();
	assert.equal(heard(), count, 'a server write the page adopts says nothing');

	project();
	count = heard();
	act(() => ((doc.clips[1].dur = 0.5), relayout()));
	await settled();
	assert.equal(heard(), count, 'a project without dissolve says nothing');

	lay([2, 2, 2], [0, 1, 1]);
	count = heard();
	checkpoint();
	setShotDuration(doc.clips[1], 1.6);
	await settled();
	assert.deepEqual(joins(doc.clips), [0, 0.8, 0.8]);
	assert.equal(heard(), count + 1);
	assert.equal(said.at(-1), t('timeline.dissolve.trimLimitedMany', { list: '0.8 s and 0.8 s' }));
});

test('dissolve flow: in a project that dissolves, a keyboard trim stops at 0.4 s, and a shot already shorter is not shortened further', () => {
	project();
	doc.clips[0].dur = 4;
	doc.clips[1].dur = 4;
	doc.clips[2].dur = 2;
	dissolveB(1);
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 3, 7]);
	select('clip', 'b');
	ui.playhead = 3.1;
	commandById('trim-end').run();
	assert.deepEqual([doc.clips[1].start, doc.clips[1].dur, doc.clips[2].start], [3.8, 0.4, 4.2]);
	assert.deepEqual(joins(doc.clips), [0, 0.2, 0]);
	undo();
	ui.playhead = 6.9;
	commandById('trim-start').run();
	assert.deepEqual([doc.clips[1].start, doc.clips[1].dur, doc.clips[1].srcIn], [3.8, 0.4, 3.6]);
	act(() => ((doc.clips[1].dur = 0.2), relayout()));
	ui.playhead = doc.clips[1].start + 0.1;
	commandById('trim-end').run();
	assert.equal(doc.clips[1].dur, 0.2);
	project();
	select('clip', 'b');
	ui.playhead = 2.1;
	commandById('trim-end').run();
	assert.equal(+doc.clips[1].dur.toFixed(6), 0.1);
});

test('dissolve flow: while a trim limits a dissolve, the drag text says so, with one or two dissolves', () => {
	ui.pxPerSec = 100;
	project();
	dissolveB(1);
	ui.snapping = false;
	assert.equal(dragBy(shotTrim(doc.clips[1], 'end'), 10).includes('cross-dissolve'), false);
	project();
	dissolveB(1);
	const text = dragBy(shotTrim(doc.clips[1], 'end'), -40);
	assert.ok(text.endsWith(` · ${t('timeline.drag.dissolveLimited', { dur: '0.8 s' })}`), text);
	lay([2, 2, 2], [0, 1, 1]);
	const two = dragBy(bandTrim(doc.clips[1]), -40);
	assert.ok(two.endsWith(` · ${t('timeline.drag.dissolveLimitedMany', { list: '0.8 s and 0.8 s' })}`), two);
	project();
	assert.equal(dragBy(shotTrim(doc.clips[1], 'end'), -40).includes('cross-dissolve'), false);
	assert.equal(limitNote(playedLengths(doc.clips)), '');
	ui.snapping = true;
});

test('dissolve flow: in a project that dissolves, the trim handles of a narrow shot share it in halves, and a project without dissolve keeps its handles as they were', async () => {
	const reaches = (html) => [...html.matchAll(/--vp-reach: ([\d.]+)px/g)].map((m) => +(+m[1]).toFixed(3));
	project();
	doc.clips[1].dur = 4;
	ui.pxPerSec = 8;
	assert.deepEqual(reaches(clean(await renderComponent(TIMELINE))), []);
	dissolveB(0.4);
	assert.deepEqual(reaches(clean(await renderComponent(TIMELINE))), [0, 0, 7.2, 7.2, 0, 0]);
	ui.pxPerSec = 34;
	assert.deepEqual(reaches(clean(await renderComponent(TIMELINE))), [16, 16, 16, 16, 9, 9]);
});

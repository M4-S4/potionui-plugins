import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import './svelte-harness.js';
import { joins, setDissolve, mixAt } from './dissolve.js';
import { shownShots } from './monitor.js';

globalThis.document ??= { body: {}, querySelector: () => null };

const { doc, ui, act, relayout, select, relink, clipAt, pickClip, entryTime, itemsIn, undo, dispose } = await import('./state.svelte.js');
const { readiness, productionItems, jobClips, sentRange, estimateState } = await import('./production.svelte.js');
const { project } = await import('./project.svelte.js');
const { pickShot, stepShot } = await import('./band.svelte.js');
const { showShot } = await import('./monitor.svelte.js');
const { handleKeydown } = await import('./commands.js');

after(() => dispose());

const WAN = '01KX47WANVIDEO0000000000TV';
const shot = (id, dur, extra = {}) => ({ id, start: 0, dur, srcIn: 0, label: `Shot ${id}`, stage: 'todo', take: null, assetId: `m${id}`, fadeIn: 0, fadeOut: 0, ...extra });
const ids = (list) => list.map((x) => x.id);

function scene(dissolves = [0, 1, 1]) {
	project.id = 'p1';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	ui.workspace = 'media';
	ui.storyView = 'grid';
	ui.production.target = 'clip';
	ui.preview = null;
	ui.compare = null;
	ui.seamCompare = null;
	ui.picked = [];
	ui.range = null;
	doc.fps = 25;
	doc.engine = { backend: 'native', preset: WAN, model: null };
	doc.direction = { ...doc.direction, mode: 'FL2VA', univers: '', personnages: '', photographie: '', palette: '', rythme: '' };
	doc.assets = ['a', 'b', 'c'].map((id) => ({ id: `m${id}`, kind: 'video', name: `Take ${id}`, src: `/m/${id}.mp4`, width: 1280, height: 720, srcDur: 8 }));
	doc.clips = [shot('a', 4), shot('b', 4), shot('c', 4)];
	doc.prompts = [];
	doc.frames = [];
	doc.audio = [];
	doc.titles = [];
	doc.markers = [];
	doc.references = [];
	act(() => {
		dissolves.forEach((seconds, i) => seconds && setDissolve(doc.clips, i, seconds));
		relayout();
	});
	estimateState.data = null;
}

const prompt = (id, shotId, start, text) => ({ id, shotId, start, dur: 4, strength: 75, text });

test('dissolve shots: a shot target keeps only its own prompts, frames and references, never those of the shots it dissolves with', () => {
	scene();
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 3, 6]);
	doc.prompts = [prompt('pa', 'a', 0, ''), prompt('pc', 'c', 6, 'The bars slide in.')];
	doc.frames = [{ id: 'fa', shotId: 'a', time: 3.96, assetId: 'ma', role: 'Fin', strength: 75 }];
	select('clip', 'b');
	assert.deepEqual(ids(jobClips()), ['b']);
	assert.deepEqual(ids(productionItems().prompts), []);
	assert.deepEqual(ids(productionItems().frames), []);
	const codes = readiness().reasons.map((r) => r.code);
	assert.ok(codes.includes('noDirection'), codes.join());
	assert.ok(!codes.includes('emptyPrompts'), codes.join());
	doc.prompts.push(prompt('pb', 'b', 3, 'A walk.'));
	assert.deepEqual(ids(productionItems().prompts), ['pb']);
	assert.ok(!readiness().reasons.some((r) => r.code === 'noDirection' || r.code === 'emptyPrompts'));
	pickClip('b', 'replace');
	assert.deepEqual(ids(productionItems().prompts), ['pb']);
	ui.picked = [];
	ui.production.target = 'sequence';
	assert.deepEqual(ids(productionItems().prompts), ['pa', 'pc', 'pb']);
	assert.ok(readiness().reasons.some((r) => r.code === 'emptyPrompts'));
	ui.production.target = 'clip';
	assert.deepEqual(ids(productionItems(undefined, { clips: [doc.clips[2]] }).prompts), ['pc']);
});

test('dissolve shots: in a project without dissolve, a shot target after a shot off the grid keeps only its own prompts, and the generation sends that shot alone', () => {
	scene([0, 0, 0]);
	doc.clips[0].dur = 4.13;
	relayout();
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 4.12, 8.12]);
	doc.prompts = [prompt('pa', 'a', 0, ''), prompt('pb', 'b', 4.12, 'A walk.')];
	select('clip', 'a');
	assert.deepEqual(ids(readiness().items.prompts), ['pa']);
	select('clip', 'b');
	assert.deepEqual(ids(readiness().items.prompts), ['pb']);
	assert.ok(!readiness().reasons.some((r) => r.code === 'emptyPrompts'));
	doc.prompts[0].text = 'Alpha walks.';
	const { range, items } = readiness();
	assert.deepEqual(items.prompts.map((p) => p.text), ['A walk.']);
	assert.deepEqual(range, [doc.clips[1].start, doc.clips[1].start + doc.clips[1].dur]);
	assert.deepEqual(ids(jobClips(range)), ['b']);
});

test('dissolve shots: in a project without dissolve on the grid, a shot target with a shot selected keeps what its range read by time', () => {
	scene([0, 0, 0]);
	doc.prompts = [prompt('pa', 'a', 0, ''), prompt('pb', 'b', 4, 'A walk.'), { id: 'free', start: 5, dur: 1, strength: 75, text: 'Loose.' }];
	doc.frames = [{ id: 'fb', shotId: 'b', time: 7.96, assetId: 'mb', role: 'Fin', strength: 75 }];
	for (const id of ['a', 'b', 'c']) {
		select('clip', id);
		const range = readiness().range;
		const kept = readiness().items;
		const byTime = itemsIn(range);
		assert.deepEqual([ids(kept.prompts).sort(), ids(kept.frames)], [ids(byTime.prompts).sort(), ids(byTime.frames)], id);
	}
	ui.production.target = 'sequence';
	assert.deepEqual(ids(readiness().items.prompts).sort(), ['free', 'pa', 'pb']);
	ui.production.target = 'clip';
});

test('dissolve shots: shots passed to the generation read only their own prompts and frames, so a shot that does not go never blocks them', () => {
	scene([0, 0, 0]);
	doc.clips[0].dur = 4.13;
	relayout();
	doc.prompts = [prompt('pa', 'a', 0, 'Alpha.'), prompt('pb', 'b', 4.12, ''), prompt('pc', 'c', 8.12, 'Charlie.')];
	doc.frames = [{ id: 'fb', shotId: 'b', time: 4.12, assetId: 'mb', role: 'Début', strength: 75 }];
	const alone = readiness({ clips: [doc.clips[0]] });
	assert.deepEqual([ids(alone.items.prompts), ids(alone.items.frames)], [['pa'], []]);
	assert.ok(!alone.reasons.some((r) => r.code === 'emptyPrompts'));
	const remaining = readiness({ clips: [doc.clips[0], doc.clips[2]] });
	assert.deepEqual(ids(remaining.items.prompts), ['pa', 'pc']);
	assert.ok(!remaining.reasons.some((r) => r.code === 'emptyPrompts'));
	assert.deepEqual(remaining.range, [0, 12.12]);
	assert.ok(readiness({ clips: [doc.clips[1]] }).reasons.some((r) => r.code === 'emptyPrompts'));
	scene([0, 1, 0]);
	doc.prompts = [prompt('pa', 'a', 0, 'Alpha.'), prompt('pb', 'b', 3, ''), prompt('pc', 'c', 7, 'Charlie.')];
	assert.deepEqual(ids(readiness({ clips: [doc.clips[0], doc.clips[2]] }).items.prompts), ['pa', 'pc']);
});

test('dissolve shots: with the shot target and a prompt or a title selected, the checks, the prompts they read and the range sent are those of the shot that goes', () => {
	scene([0, 0, 0]);
	doc.prompts = [prompt('pa', 'a', 0, 'Alpha walks.'), prompt('pc', 'c', 8, 'Charlie jumps.')];
	doc.prompts[0].dur = 1;
	doc.titles = [{ id: 't', text: 'T', sub: '', start: 1, dur: 2 }];
	ui.playhead = 9;
	try {
		for (const [kind, id] of [['prompt', 'pa'], ['title', 't']]) {
			select(kind, id);
			assert.deepEqual(ids(jobClips()), ['c'], kind);
			assert.deepEqual(readiness().range, [8, 12], kind);
			assert.deepEqual(readiness().items.prompts.map((p) => p.text), ['Charlie jumps.'], kind);
			assert.deepEqual(sentRange(), [8, 12], kind);
			assert.deepEqual(ids(jobClips(sentRange())), ['c'], kind);
		}
	} finally {
		ui.playhead = 0;
		doc.titles = [];
	}
});

test('dissolve shots: in a project that dissolves, a last frame dragged into a dissolve stays on the outgoing shot, and a first frame on the incoming one', () => {
	scene([0, 1, 0]);
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 3, 7]);
	const end = { id: 'fa', shotId: 'a', time: 3.96, assetId: 'ma', role: 'Fin', strength: 75 };
	const start = { id: 'fb', shotId: 'b', time: 3.04, assetId: 'mb', role: 'Début', strength: 75 };
	const any = { id: 'ft', shotId: 'a', time: 3.96, assetId: 'ma', role: 'Transition', strength: 75 };
	doc.frames = [end, start, any];
	for (const frame of doc.frames) relink(frame);
	assert.deepEqual(doc.frames.map((f) => [f.id, f.shotId]), [
		['fa', 'a'],
		['fb', 'b'],
		['ft', 'b']
	]);
	doc.frames[0].time = 3.2;
	doc.frames[1].time = 3.9;
	for (const frame of doc.frames) relink(frame);
	assert.deepEqual(doc.frames.map((f) => f.shotId).slice(0, 2), ['a', 'b']);
	doc.frames[0].time = 4.5;
	relink(doc.frames[0]);
	assert.equal(doc.frames[0].shotId, 'b');
	scene([0, 0, 0]);
	doc.frames = [{ id: 'fa', shotId: 'a', time: 4.04, assetId: 'ma', role: 'Fin', strength: 75 }];
	relink(doc.frames[0]);
	assert.equal(doc.frames[0].shotId, 'b');
});

test('dissolve shots: going to a shot in a project that dissolves puts the playhead on its first frame out of the dissolve, where it plays alone', () => {
	const key = (name) => handleKeydown({ key: name, code: name, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, repeat: false, target: null, preventDefault() {} }, null);
	scene([0, 1, 0]);
	const b = doc.clips[1];
	assert.equal(entryTime(b), 4);
	assert.equal(entryTime(doc.clips[0]), 0.01);
	assert.equal(entryTime(doc.clips[2]), 7.01);
	pickShot(b);
	assert.equal(ui.playhead, 4);
	assert.equal(clipAt(ui.playhead).id, 'b');
	assert.equal(mixAt(doc.clips, ui.playhead), null);
	ui.storyView = 'band';
	ui.workspace = 'storyboard';
	select('clip', 'a');
	stepShot(1);
	assert.equal(ui.playhead, 4);
	ui.storyView = 'grid';
	select('clip', 'a');
	ui.playhead = 0;
	key('ArrowRight');
	assert.deepEqual([ui.selection.id, ui.playhead], ['b', 4]);
	ui.workspace = 'media';
	ui.playhead = 3.6;
	assert.equal(clipAt(3.6).id, 'b');
	showShot(b);
	assert.equal(ui.playhead, 4);
	ui.playhead = 5;
	showShot(b);
	assert.equal(ui.playhead, 5);
	scene([0, 0, 0]);
	pickShot(doc.clips[1]);
	assert.equal(ui.playhead, 4.01);
	ui.playhead = 5;
	showShot(doc.clips[1]);
	assert.equal(ui.playhead, 5);
});

test('dissolve shots: during a dissolve the monitor shows both shots, and outside it the one under the playhead', () => {
	scene([0, 1, 0]);
	const view = (playhead) => ({ clips: doc.clips, playhead });
	const find = { take: () => null, asset: () => null };
	assert.deepEqual(shownShots(view(2.5), find), ['a']);
	assert.deepEqual(shownShots(view(3.2), find), ['a', 'b']);
	assert.deepEqual(shownShots(view(3.8), find), ['a', 'b']);
	assert.deepEqual(shownShots(view(4), find), ['b']);
	scene([0, 0, 0]);
	assert.deepEqual(shownShots(view(3.99), find), ['a']);
	assert.deepEqual(shownShots(view(4), find), ['b']);
});

const heard = [];
window.__potionui.notifications.toast = (level, message) => heard.push(message);
const settled = () => new Promise((resolve) => queueMicrotask(resolve));
const { shotsIn, checkpoint, settle, adopt, replaceDoc } = await import('./state.svelte.js');
const { pickTarget } = await import('./production.svelte.js');
const { placement, shownSpans } = await import('./dissolve.js');
const { commandById } = await import('./commands.js');
const { shotTrim } = await import('./trims.js');
const { drag } = await import('./timeline.js');
const { t } = await import('../i18n/index.svelte.js');

test('dissolve shots: a range made from a shot target covers the shot as the timeline draws it, and a range by time keeps the shots it draws', () => {
	scene();
	select('clip', 'b');
	assert.deepEqual(ids(jobClips()), ['b']);
	pickTarget('range');
	assert.deepEqual([ui.range.in, ui.range.out], [3.5, 6.5]);
	assert.deepEqual(ids(jobClips()), ['b']);
	assert.deepEqual(readiness().range, [3.5, 6.5]);
	doc.prompts = [prompt('pa', 'a', 0, ''), prompt('pb', 'b', 3, 'A walk.'), prompt('pc', 'c', 6, '')];
	assert.deepEqual(ids(productionItems().prompts), ['pb']);
	assert.ok(!readiness().reasons.some((r) => r.code === 'emptyPrompts'));
	assert.deepEqual(ids(shotsIn([0, 3.2])), ['a']);
	assert.deepEqual(ids(shotsIn([0, 3.8])), ['a', 'b']);
	assert.deepEqual(ids(shotsIn([6.4, 9])), ['b', 'c']);
	assert.deepEqual(ids(shotsIn([6.6, 9])), ['c']);
	scene([0, 0, 0]);
	select('clip', 'b');
	pickTarget('range');
	assert.deepEqual([ui.range.in, ui.range.out], [4, 8]);
	assert.deepEqual(ids(jobClips()), ['b']);
	assert.deepEqual(ids(shotsIn([0, 4.01])), ['a', 'b']);
});

function length(random, pick) {
	const kind = pick(['grid', 'milli', 'third', 'fine']);
	if (kind === 'grid') return (3 + Math.floor(random() * 120)) * 0.04;
	if (kind === 'milli') return (100 + Math.floor(random() * 4800)) / 1000;
	if (kind === 'third') return (1 + Math.floor(random() * 14)) / 3;
	return (1280 + Math.floor(random() * 60000)) / 12800;
}

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

test('dissolve shots: on projects drawn at random, going to a shot gives a time where it plays alone, or the meeting point of the two dissolves that take it whole', () => {
	scene([0, 0, 0]);
	doc.clips = [shot('a', 3.52), shot('b', 2, { dissolve: 0.56 })];
	relayout();
	assert.equal(doc.clips[1].start, 2.96);
	assert.equal(mixAt(doc.clips, entryTime(doc.clips[1])), null);
	assert.equal(clipAt(entryTime(doc.clips[1])).id, 'b');
	const random = seeded(1110);
	const pick = (list) => list[Math.floor(random() * list.length)];
	let alone = 0;
	let met = 0;
	for (let n = 0; n < 400; n++) {
		const count = 2 + Math.floor(random() * 6);
		doc.clips = Array.from({ length: count }, (_, i) => shot(`s${i}`, length(random, pick), i && random() < 0.7 ? { dissolve: pick([0.08, 0.12, 0.4, 0.6, 1, 1.2, 2]) } : {}));
		relayout();
		if (!joins(doc.clips).some(Boolean)) continue;
		const places = placement(doc.clips);
		doc.clips.forEach((c, i) => {
			const time = entryTime(c);
			const place = places[i];
			const next = places[i + 1];
			const until = next?.overlap > 0 ? next.start : place.end;
			if (place.start + place.overlap < until) {
				alone += 1;
				assert.equal(mixAt(doc.clips, time), null, `${c.id} of ${JSON.stringify(doc.clips.map((x) => [x.dur, x.dissolve ?? 0]))}`);
				assert.equal(clipAt(time)?.id, c.id, `${c.id} at ${time} of ${JSON.stringify(doc.clips.map((x) => [x.start, x.dur, x.dissolve ?? 0]))} spans ${JSON.stringify(shownSpans(doc.clips))}`);
			} else {
				met += 1;
				assert.equal(time, place.start + place.overlap);
				ui.playhead = time;
				showShot(c);
				assert.equal(ui.playhead, time);
			}
		});
	}
	assert.ok(alone > 1000 && met > 0, `${alone} alone, ${met} met`);
});

test('dissolve shots: without dissolve, a head trim from the keyboard writes the playhead as the new start, as the base', () => {
	scene([0, 0, 0]);
	doc.clips = [shot('a', 2, { start: 0.04 })];
	select('clip', 'a');
	ui.playhead = 0.11;
	commandById('trim-start').run();
	assert.equal(doc.clips[0].start, 0.11);
});

test('dissolve shots: a mouse trim reads the zoom of the moment at each move, as before', () => {
	scene();
	doc.engine = { backend: 'native', preset: null, model: null };
	ui.snapping = false;
	ui.pxPerSec = 100;
	const fire = (type, x) => window.dispatchEvent(Object.assign(new Event(type), { pointerId: 9, clientX: x, clientY: 0 }));
	drag({ button: 0, pointerId: 9, clientX: 0, clientY: 0, stopPropagation() {}, currentTarget: null }, shotTrim(doc.clips[1], 'end'));
	fire('pointermove', 20);
	ui.pxPerSec = 50;
	fire('pointermove', 20);
	fire('pointerup', 20);
	assert.equal(doc.clips[1].dur, 4.4);
	ui.pxPerSec = 34;
	ui.snapping = true;
});

test('dissolve shots: a document replaced, or a server write adopted during a drag, never makes the page blame the drag for a limited dissolve', async () => {
	scene([0, 1, 0]);
	await settled();
	let count = heard.length;
	ui.drag = {};
	checkpoint();
	const next = JSON.parse(JSON.stringify(doc));
	next.clips[1].dur = 1.6;
	adopt(next);
	ui.drag = null;
	settle();
	await settled();
	assert.deepEqual(heard.slice(count), []);
	scene([0, 1, 0]);
	await settled();
	count = heard.length;
	ui.drag = {};
	checkpoint();
	replaceDoc({ ...JSON.parse(JSON.stringify(doc)), clips: doc.clips.map((c, i) => ({ ...JSON.parse(JSON.stringify(c)), dur: i === 1 ? 1.6 : c.dur })) });
	ui.drag = null;
	settle();
	await settled();
	assert.deepEqual(heard.slice(count), []);
});

test('dissolve shots: every dissolve a command limits or stops is said, three or more included', async () => {
	scene([0, 0, 0]);
	doc.clips = ['a', 'b', 'c', 'd', 'e'].map((id, i) => shot(id, 2, i ? { dissolve: 1 } : {}));
	relayout();
	await settled();
	let count = heard.length;
	act(() => ((doc.clips[1].dur = 1.6), (doc.clips[3].dur = 1.6), relayout()));
	await settled();
	assert.deepEqual(heard.slice(count), [t('timeline.dissolve.trimLimitedMany', { list: '0.8 s, 0.8 s, 0.8 s, and 0.8 s' })]);
	undo();
	await settled();
	count = heard.length;
	act(() => ((doc.clips[1].dur = 0.12), (doc.clips[3].dur = 1.6), relayout()));
	await settled();
	assert.deepEqual(heard.slice(count), [`${t('timeline.dissolve.trimStoppedMany', { count: 2 })} ${t('timeline.dissolve.trimLimitedMany', { list: '0.8 s and 0.8 s' })}`]);
});

test('dissolve shots: the checks of picked shots read their own prompts over their range, and the generation sends them, with or without dissolve', () => {
	try {
		scene([0, 0, 0]);
		doc.prompts = [prompt('pa', 'a', 0, 'Alpha walks.'), prompt('pb', 'b', 4, 'Bravo runs.'), prompt('pc', 'c', 8, 'Charlie jumps.')];
		select('clip', 'a');
		ui.picked = ['b', 'c'];
		assert.deepEqual(ids(productionItems().prompts), ['pb', 'pc']);
		const picked = readiness();
		assert.deepEqual(picked.items.prompts.map((p) => p.text), ['Bravo runs.', 'Charlie jumps.']);
		assert.deepEqual(picked.range, [4, 12]);
		assert.deepEqual(ids(jobClips(picked.range)), ['b', 'c']);
		ui.picked = [];
		scene([0, 1, 0]);
		doc.prompts = [prompt('pa', 'a', 0, 'Alpha walks.'), prompt('pb', 'b', 3, 'Bravo runs.')];
		select('clip', 'a');
		const dissolving = readiness();
		assert.deepEqual(dissolving.items.prompts.map((p) => p.text), ['Alpha walks.']);
		assert.deepEqual(ids(jobClips(dissolving.range)), ['a']);
	} finally {
		ui.picked = [];
	}
});

test('dissolve shots: with a first shot of 3.14 s, a range made from either shot keeps that shot alone', () => {
	scene([0, 0, 0]);
	doc.clips = [shot('a', 3.14), shot('b', 4, { dissolve: 0.6 }), shot('c', 4)];
	relayout();
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 2.54, 6.54]);
	ui.production.target = 'clip';
	ui.range = null;
	select('clip', 'a');
	pickTarget('range');
	const first = [ui.range.in, ui.range.out];
	assert.deepEqual(ids(jobClips()), ['a']);
	assert.deepEqual(ids(shotsIn(readiness().range)), ['a']);
	ui.production.target = 'clip';
	ui.range = null;
	select('clip', 'b');
	pickTarget('range');
	assert.equal(ui.range.in, first[1]);
	assert.deepEqual(ids(jobClips()), ['b']);
});

test('dissolve shots: on projects drawn at random, Shot then Range keeps that shot alone, and two neighbouring ranges share no shot', () => {
	scene([0, 0, 0]);
	const random = seeded(1111);
	const pick = (list) => list[Math.floor(random() * list.length)];
	let checked = 0;
	let points = 0;
	for (let n = 0; n < 300; n++) {
		const count = 2 + Math.floor(random() * 7);
		doc.clips = Array.from({ length: count }, (_, i) => shot(`s${i}`, random() < 0.1 ? 0.1 : length(random, pick), i && random() < 0.75 ? { dissolve: pick([0.08, 0.12, 0.4, 0.6, 1, 1.2, 2]) } : {}));
		relayout();
		if (!joins(doc.clips).some(Boolean)) continue;
		const ranges = doc.clips.map((c) => {
			ui.production.target = 'clip';
			ui.range = null;
			select('clip', c.id);
			pickTarget('range');
			return [ui.range.in, ui.range.out];
		});
		const label = JSON.stringify(doc.clips.map((x) => [x.dur, x.dissolve ?? 0]));
		doc.clips.forEach((c, i) => {
			const kept = ids(shotsIn(ranges[i]));
			if (ranges[i][1] - ranges[i][0] > 1e-6) {
				checked += 1;
				assert.deepEqual(kept, [c.id], `${c.id} of ${label}: ${ranges[i]}`);
				ui.production.target = 'range';
				ui.range = { in: ranges[i][0], out: ranges[i][1] };
				assert.deepEqual(ids(jobClips()), [c.id]);
			} else {
				points += 1;
				assert.ok(kept.includes(c.id), `${c.id} of ${label}`);
			}
			if (i > 0 && ranges[i - 1][1] - ranges[i - 1][0] > 1e-6 && ranges[i][1] - ranges[i][0] > 1e-6) {
				const before = new Set(ids(shotsIn(ranges[i - 1])));
				assert.ok(!kept.some((id) => before.has(id)), `${label}: ${ranges[i - 1]} and ${ranges[i]}`);
			}
		});
	}
	ui.range = null;
	ui.production.target = 'clip';
	assert.ok(checked > 800, `${checked} checked, ${points} taken whole`);
});

test('dissolve shots: a document whose valid dissolve keys sit on starts end to end plays no dissolve, and the checks of picked shots read their own prompts as any other', () => {
	scene([0, 0, 0]);
	doc.clips = [shot('a', 4, { start: 0 }), shot('b', 4, { start: 4, dissolve: 1 }), shot('c', 4, { start: 8, dissolve: 1 })];
	assert.deepEqual(joins(doc.clips), [0, 0, 0]);
	doc.prompts = [prompt('pa', 'a', 0, 'Alpha walks.'), prompt('pb', 'b', 4, 'Bravo runs.'), prompt('pc', 'c', 8, 'Charlie jumps.')];
	select('clip', 'a');
	ui.picked = ['b', 'c'];
	try {
		const { range, items } = readiness();
		assert.deepEqual(items.prompts.map((p) => p.text), ['Bravo runs.', 'Charlie jumps.']);
		assert.deepEqual(range, [4, 12]);
		assert.deepEqual(ids(jobClips(range)), ['b', 'c']);
	} finally {
		ui.picked = [];
	}
});

const { rangeDraw } = await import('./timeline.js');

function drawRange(from, to) {
	const fire = (type, time) => window.dispatchEvent(Object.assign(new Event(type), { pointerId: 11, clientX: time * ui.pxPerSec, clientY: 0 }));
	ui.range = null;
	drag({ button: 0, pointerId: 11, clientX: from * ui.pxPerSec, clientY: 0, stopPropagation() {}, currentTarget: null }, rangeDraw(from, (ev) => ev.clientX / ui.pxPerSec));
	fire('pointermove', (from + to) / 2);
	fire('pointermove', to);
	fire('pointerup', to);
	return [ui.range.in, ui.range.out];
}

test('dissolve shots: a range drawn with the mouse snaps to the drawn bounds of the shots, so from edge to edge it keeps one shot', () => {
	ui.snapping = true;
	ui.pxPerSec = 34;
	ui.playhead = 0;
	const lay3 = (seconds) => {
		scene([0, 0, 0]);
		doc.clips = [shot('a', 4), shot('b', 4, { dissolve: seconds }), shot('c', 4)];
		relayout();
		ui.playhead = 0;
	};
	const drawn = () => [shownSpans(doc.clips)[1].start, shownSpans(doc.clips)[1].end];
	lay3(0.6);
	assert.deepEqual(doc.clips.map((c) => c.start), [0, 3.4, 7.4]);
	assert.ok(Math.abs(drawn()[0] - 3.7) < 1e-9);
	assert.deepEqual(drawRange(3.7, 7.4), drawn());
	assert.deepEqual(ids(shotsIn([ui.range.in, ui.range.out])), ['b']);
	lay3(1);
	assert.deepEqual(drawRange(3.47, 6.98), drawn());
	assert.deepEqual(drawn(), [3.5, 7]);
	assert.deepEqual(ids(jobClips()), ['b']);
	assert.deepEqual(drawRange(3.5, 7), drawn());
	lay3(0.4);
	assert.ok(Math.abs(drawn()[0] - 3.8) < 1e-9);
	assert.deepEqual(drawRange(3.77, 7.6), drawn());
	assert.deepEqual(ids(shotsIn([ui.range.in, ui.range.out])), ['b']);
	assert.deepEqual(drawRange(3.8, 7.6), drawn());
	scene([0, 0, 0]);
	ui.playhead = 0;
	assert.deepEqual(drawRange(3.95, 8.03), [4, 8]);
	ui.range = null;
	ui.production.target = 'clip';
});

test('dissolve shots: on projects drawn at random, a range drawn between two pointers near the drawn edges of a shot keeps that shot alone', () => {
	scene([0, 0, 0]);
	ui.snapping = true;
	const random = seeded(1112);
	const pick = (list) => list[Math.floor(random() * list.length)];
	let checked = 0;
	for (let n = 0; n < 300; n++) {
		const count = 2 + Math.floor(random() * 7);
		doc.clips = Array.from({ length: count }, (_, i) => shot(`s${i}`, length(random, pick), i && random() < 0.75 ? { dissolve: pick([0.08, 0.12, 0.4, 0.6, 1, 1.2, 2]) } : {}));
		relayout();
		if (!joins(doc.clips).some(Boolean)) continue;
		ui.pxPerSec = pick([8, 20, 34, 60, 100, 220]);
		ui.playhead = 0;
		const tol = 8 / ui.pxPerSec;
		const spans = shownSpans(doc.clips);
		doc.clips.forEach((c, i) => {
			const wide = [i - 1, i, i + 1].every((k) => !spans[k] || spans[k].end - spans[k].start > 2 * tol);
			if (!wide) return;
			const near = (edge) => edge + (random() * 2 - 1) * 0.9 * tol;
			const range = drawRange(near(spans[i].start), near(spans[i].end));
			checked += 1;
			assert.deepEqual(range, [spans[i].start, spans[i].end], `${c.id} at ${ui.pxPerSec} px/s of ${JSON.stringify(doc.clips.map((x) => [x.dur, x.dissolve ?? 0]))}`);
			assert.deepEqual(ids(shotsIn(range)), [c.id]);
		});
	}
	ui.range = null;
	ui.production.target = 'clip';
	ui.pxPerSec = 34;
	assert.ok(checked > 600, `${checked} checked`);
});

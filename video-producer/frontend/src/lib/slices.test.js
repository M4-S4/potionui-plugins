import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, hostUis, renderComponent, textOf } from './svelte-harness.js';
import { JOIN_TOLERANCE, MAX_SLICES, SLICE_MAX, SLICE_MIN, SLICE_SECONDS, continues, joined, shotCuts, shotSlices, sliceChain, sliceCuts, sliceItem, sliceLength } from './tracks.js';
import { isReferenceItem, joinPlan } from './sound.js';

const lane = (id, extra = {}) => ({ id, name: id, role: 'Musique', vol: 0, pan: 0, mute: false, solo: false, ...extra });
const sound = (id, start, dur, extra = {}) => ({ id, assetId: 'stem', lane: 'A1', start, dur, srcIn: 0, fadeIn: 0, fadeOut: 0, gain: -6, ...extra });
const ids = () => {
	let n = 0;
	return () => `new-${++n}`;
};
const shape = (items) => items.map((x) => [x.id, x.start, x.dur, x.srcIn, x.fadeIn, x.fadeOut]);

const { doc, ui, sliceAudio, joinAudio, sliceOnShots, undo, dispose } = await import('./state.svelte.js');
const { commandById } = await import('./commands.js');
const { t } = await import('../i18n/index.svelte.js');

const INSPECTOR = new URL('../components/inspector/Inspector.svelte', import.meta.url).href;
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const buttons = (html) => [...clean(html).matchAll(/<host-ui data-host="Button" data-props="([^"]*)">(.*?)<\/host-ui>/g)].map(([, props, inner]) => ({ ...JSON.parse(props.replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&amp;', '&')), text: textOf(inner) }));

after(() => dispose());

function pageScene(dur = 12) {
	ui.sliceSeconds = SLICE_SECONDS;
	doc.clips = [{ id: 's1', start: 0, dur: 4, srcIn: 0, stage: 'todo', label: 'One' }, { id: 's2', start: 4, dur: 4, srcIn: 0, stage: 'todo', label: 'Two' }];
	doc.assets = [{ id: 'stem', kind: 'audio', name: 'stem.wav', src: '/s.wav', srcDur: 20 }];
	doc.audio = [sound('a1', 0, dur, { lane: doc.lanes[0].id })];
	ui.selection = { kind: 'audio', id: 'a1' };
}

function sliced(item, seconds, doc = { lanes: [lane('A1')], audio: [] }) {
	const parts = sliceItem(item, seconds, ids());
	doc.audio = parts;
	return { doc, parts };
}

test('slice length: 5 s by default, held between 1 and 60 s, to a tenth of a second', () => {
	assert.equal(SLICE_SECONDS, 5);
	assert.deepEqual([SLICE_MIN, SLICE_MAX, MAX_SLICES], [1, 60, 200]);
	assert.equal(sliceLength('abc'), 5);
	assert.equal(sliceLength(0.2), 1);
	assert.equal(sliceLength(90), 60);
	assert.equal(sliceLength('2.46'), 2.5);
});

test('slicing: consecutive clips of N seconds, the last one shorter, each going on from the same place in the file, same gain, track and flag', () => {
	const item = sound('a', 2, 12, { srcIn: 1.5, gain: -4, fadeIn: 0.5, fadeOut: 0.8, reference: false });
	const parts = sliceItem(item, 5, ids());
	assert.deepEqual(shape(parts), [
		['a', 2, 5, 1.5, 0.5, 0],
		['new-1', 7, 5, 6.5, 0, 0],
		['new-2', 12, 2, 11.5, 0, 0.8]
	]);
	for (const part of parts) assert.deepEqual([part.lane, part.assetId, part.gain, part.reference], ['A1', 'stem', -4, false]);
	for (let i = 1; i < parts.length; i++) {
		assert.equal(parts[i].start, parts[i - 1].start + parts[i - 1].dur);
		assert.equal(parts[i].srcIn, parts[i - 1].srcIn + parts[i - 1].dur);
	}
	assert.equal(parts.reduce((sum, x) => sum + x.dur, 0), item.dur);
	assert.equal('reference' in sliceItem(sound('b', 0, 12), 5, ids())[1], false);
});

test('slicing: no sliver is left at the end, a clip no longer than N plus 0.1 s is not sliced, and more than 200 slices are refused', () => {
	assert.deepEqual(sliceCuts(10, 5), [5]);
	assert.deepEqual(sliceCuts(10.05, 5), [5]);
	assert.deepEqual(sliceCuts(10.2, 5), [5, 10]);
	assert.deepEqual(sliceCuts(10, 3.3), [3.3, 6.6]);
	assert.deepEqual(sliceCuts(0.7, 0.1 * 3), [0.3]);
	assert.deepEqual(sliceCuts(5.1, 5), []);
	assert.deepEqual(sliceItem(sound('c', 0, 5.1), 5, ids()), []);
	assert.equal(sliceCuts(200, 1).length, MAX_SLICES - 1);
	assert.equal(sliceCuts(200.2, 1), null);
	assert.equal(sliceItem(sound('d', 0, 400), 1, ids()), null);
	assert.deepEqual(sliceCuts(7.7, 2.5), [2.5, 5, 7.5]);
	const parts = sliceItem(sound('e', 0.3, 7.55, { srcIn: 0.1 }), 2.5, ids());
	assert.deepEqual(
		parts.map((x) => [x.start, x.dur, x.srcIn]),
		[
			[0.3, 2.5, 0.1],
			[2.8, 2.5, 2.6],
			[5.3, 2.55, 5.1]
		]
	);
});

test('joining: the slices of a clip, found from any of them, go back to the very clip they came from', () => {
	const item = sound('a', 2, 12, { srcIn: 1.5, gain: -4, fadeIn: 0.5, fadeOut: 0.8 });
	const { doc, parts } = sliced(item, 5);
	for (const part of parts) {
		const { chain, runs } = joinPlan(doc, part);
		assert.deepEqual(
			chain.map((x) => x.id),
			['a', 'new-1', 'new-2']
		);
		assert.equal(runs.length, 1);
	}
	assert.deepEqual(joined(parts), item);
	const flagged = sliceItem({ ...item, reference: true }, 5, ids());
	assert.deepEqual(joined(flagged), { ...item, reference: true });
});

test('joining keeps what is sent and heard: slices whose Reference setting or gain differs stay apart', () => {
	const { doc, parts } = sliced(sound('a', 0, 60), 5, { lanes: [lane('A1', { reference: true })], audio: [] });
	assert.equal(parts.length, 12);
	for (const n of [3, 7, 8]) parts[n - 1].reference = false;
	parts[10].reference = true;
	const { chain, runs } = joinPlan(doc, parts[5]);
	assert.equal(chain.length, 12);
	assert.deepEqual(
		runs.map((run) => run.map((x) => parts.indexOf(x) + 1)),
		[[1, 2], [3], [4, 5, 6], [7, 8], [9, 10, 11, 12]]
	);
	const merged = runs.map(joined);
	assert.deepEqual(
		merged.map((x) => [x.start, x.dur, x.srcIn, x.reference]),
		[
			[0, 10, 0, undefined],
			[10, 5, 10, false],
			[15, 15, 15, undefined],
			[30, 10, 30, false],
			[40, 20, 40, true]
		]
	);
	for (const [i, run] of runs.entries()) assert.ok(run.every((x) => isReferenceItem(x, doc.lanes[0]) === isReferenceItem(merged[i], doc.lanes[0])));

	parts.forEach((x) => delete x.reference);
	parts[4].gain = -3;
	assert.deepEqual(
		joinPlan(doc, parts[0]).runs.map((run) => run.length),
		[4, 1, 7]
	);
});

test('joining: only clips of the same file on the same track that follow on, on the timeline and in the file, within the tolerance', () => {
	assert.equal(JOIN_TOLERANCE, 0.025);
	const a = sound('a', 1, 2.9, { srcIn: 4 });
	assert.ok(continues(a, sound('b', 3.92, 2, { srcIn: 6.9 })));
	assert.ok(continues(a, sound('b', 3.9, 2, { srcIn: 6.92 })));
	assert.ok(!continues(a, sound('b', 3.95, 2, { srcIn: 6.9 })));
	assert.ok(!continues(a, sound('b', 3.9, 2, { srcIn: 8 })));
	assert.ok(!continues(a, sound('b', 3.9, 2, { srcIn: 6.9, assetId: 'other' })));
	assert.ok(!continues(a, sound('b', 3.9, 2, { srcIn: 6.9, lane: 'A2' })));
	assert.ok(!continues(a, a));
	const doc = { lanes: [lane('A1')], audio: [sound('x', 0, 1), a, sound('b', 3.92, 2, { srcIn: 6.9, fadeOut: 0.4 }), sound('gap', 6, 1, { srcIn: 8.9 })] };
	assert.deepEqual(
		sliceChain(doc, doc.audio[2]).map((x) => x.id),
		['a', 'b']
	);
	assert.deepEqual(
		[joined([a, doc.audio[2]])].map((x) => [x.id, x.start, x.dur, x.srcIn, x.fadeOut]),
		[['a', 1, 4.92, 4, 0.4]]
	);
	assert.deepEqual(
		joinPlan(doc, doc.audio[0]).chain.map((x) => x.id),
		['x']
	);
});


const shot = (id, start, dur) => ({ id, start, dur });
const spans = (parts) => parts.map((x) => [x.start, x.dur, x.srcIn]);

test('slicing on the shots: one slice per shot over the clip, cut exactly at the edges of V1, with the rules of the slices of N seconds', () => {
	const clips = [shot('s1', 0, 4), shot('s2', 4, 5), shot('s3', 9, 3)];
	const item = sound('a', 2, 9, { srcIn: 1, gain: -3, fadeIn: 0.4, fadeOut: 0.6, reference: true });
	assert.deepEqual(shotCuts(item, clips), [2, 7]);
	const parts = shotSlices(item, clips, ids());
	assert.deepEqual(shape(parts), [
		['a', 2, 2, 1, 0.4, 0],
		['new-1', 4, 5, 3, 0, 0],
		['new-2', 9, 2, 8, 0, 0.6]
	]);
	for (const part of parts) assert.deepEqual([part.lane, part.assetId, part.gain, part.reference], ['A1', 'stem', -3, true]);
	assert.deepEqual([parts[1].start, parts[2].start], [clips[1].start, clips[2].start]);
	assert.deepEqual(joined(parts), item);
	const doc = { lanes: [lane('A1', { reference: true })], audio: shotSlices(sound('b', 0, 12), clips, ids()) };
	assert.deepEqual(
		doc.audio.map((x) => ['reference' in x, isReferenceItem(x, doc.lanes[0])]),
		[
			[false, true],
			[false, true],
			[false, true]
		]
	);
	doc.audio[1].reference = false;
	assert.deepEqual(
		joinPlan(doc, doc.audio[0]).runs.map((run) => run.length),
		[1, 1, 1]
	);
});

test('slicing on the shots: edges closer than 0.1 s make one cut at the later one, a gap or what lies past the last shot is a slice of its own', () => {
	assert.deepEqual(shotCuts(sound('a', 0, 7), [shot('s1', 0, 3.98), shot('s2', 4, 3)]), [4]);
	assert.deepEqual(shotCuts(sound('a', 0, 7), [shot('s1', 0, 4.03), shot('s2', 4, 3)]), [4.03]);
	assert.deepEqual(spans(shotSlices(sound('a', 0, 8), [shot('s1', 0, 4), shot('s2', 5, 3)], ids())), [
		[0, 4, 0],
		[4, 1, 4],
		[5, 3, 5]
	]);
	assert.deepEqual(spans(shotSlices(sound('a', 1, 6), [shot('s1', 0, 4), shot('s2', 4, 0.05), shot('s3', 4.05, 4)], ids())), [
		[1, 3.05, 0],
		[4.05, 2.95, 3.05]
	]);
	assert.deepEqual(spans(shotSlices(sound('a', 6, 6), [shot('s1', 0, 4), shot('s2', 4, 4)], ids())), [
		[6, 2, 0],
		[8, 4, 2]
	]);
});

test('slicing on the shots: nothing to cut inside one shot, past the last shot or within 0.1 s of an edge of the clip, and more than 200 slices are refused', () => {
	const clips = [shot('s1', 0, 4), shot('s2', 4, 4)];
	assert.deepEqual(shotCuts(sound('a', 1, 2), clips), []);
	assert.deepEqual(shotCuts(sound('a', 9, 3), clips), []);
	assert.deepEqual(shotCuts(sound('a', 3.95, 3), clips), []);
	assert.deepEqual(shotCuts(sound('a', 1, 3.05), clips), []);
	assert.deepEqual(shotCuts(sound('a', 0, 10), []), []);
	assert.deepEqual(shotSlices(sound('a', 1, 2), clips, ids()), []);
	const many = Array.from({ length: 250 }, (_, i) => shot(`s${i}`, i, 1));
	assert.equal(shotCuts(sound('a', 0, 250), many), null);
	assert.equal(shotSlices(sound('a', 0, 250), many, ids()), null);
	assert.equal(shotCuts(sound('a', 0, 200), many).length, MAX_SLICES - 1);
});


test('the page slices and joins the selected audio clip in one undo step each, from the Inspector buttons, the command search and the keyboard', async () => {
	pageScene();
	assert.equal(ui.sliceSeconds, SLICE_SECONDS);
	const before = JSON.stringify(doc);
	sliceAudio();
	assert.deepEqual(spans(doc.audio), spans(sliceItem(JSON.parse(before).audio[0], SLICE_SECONDS, ids())));
	assert.equal(doc.audio[0].id, 'a1');
	undo();
	assert.equal(JSON.stringify(doc), before);
	sliceAudio();
	const sliced = JSON.stringify(doc);
	ui.selection = { kind: 'audio', id: doc.audio[1].id };
	joinAudio();
	assert.deepEqual(spans(doc.audio), [[0, 12, 0]]);
	assert.deepEqual(ui.selection, { kind: 'audio', id: 'a1' });
	undo();
	assert.equal(JSON.stringify(doc), sliced);
	assert.deepEqual([commandById('audio-slice').keys, commandById('audio-join').keys], ['shift+mod+b', 'alt+mod+b']);
	ui.selection = { kind: 'audio', id: 'a1' };
	ui.sliceSeconds = 2;
	commandById('audio-slice').run();
	assert.deepEqual(spans(doc.audio).slice(0, 3), [[0, 2, 0], [2, 2, 2], [4, 1, 4]]);
	commandById('audio-join').run();
	assert.deepEqual(spans(doc.audio), [[0, 12, 0]]);
	pageScene();
	const html = await renderComponent(INSPECTOR);
	assert.deepEqual(buttons(html).filter((b) => b.text === t('inspector.audio.slice')).map((b) => b.disabled), [false]);
	assert.deepEqual(buttons(html).filter((b) => b.text === t('inspector.audio.join')).map((b) => b.disabled), [true]);
	assert.deepEqual(hostUis(html, 'Switch').filter((item) => item.id === 'vp-audio-reference').map((item) => item.checked), [false]);
	sliceAudio();
	doc.audio[0].reference = true;
	const parts = await renderComponent(INSPECTOR);
	assert.deepEqual(buttons(parts).filter((b) => b.text === t('inspector.audio.join')).map((b) => b.disabled), [false]);
	assert.deepEqual(hostUis(parts, 'Switch').filter((item) => item.id === 'vp-audio-reference').map((item) => item.checked), [true]);
	assert.match(textOf(parts), new RegExp(escaped(t('inspector.section.slices'))));
});

test('the page slices on the shots the selected audio clip, or every clip of the selected track, in one undo step, from the Inspector and the command search', async () => {
	pageScene();
	const before = JSON.stringify(doc);
	sliceOnShots();
	assert.deepEqual(spans(doc.audio), spans(shotSlices(JSON.parse(before).audio[0], doc.clips, ids())));
	undo();
	assert.equal(JSON.stringify(doc), before);
	doc.audio.push(sound('a2', 3, 2, { lane: doc.lanes[0].id }));
	const two = JSON.stringify(doc);
	ui.selection = { kind: 'lane', id: doc.lanes[0].id };
	assert.equal(commandById('audio-slice-shots').menuId, 'edit-timeline');
	commandById('audio-slice-shots').run();
	const planned = JSON.parse(two).audio.map((item) => shotSlices(item, doc.clips, ids()));
	assert.deepEqual(spans(doc.audio), planned.flatMap(spans));
	undo();
	assert.equal(JSON.stringify(doc), two);
	pageScene();
	const shots = (html) => buttons(html).filter((b) => b.text === t('inspector.audio.shots')).map((b) => b.disabled);
	assert.deepEqual(shots(await renderComponent(INSPECTOR)), [false]);
	doc.clips = [];
	assert.deepEqual(shots(await renderComponent(INSPECTOR)), [true]);
	pageScene();
	ui.selection = { kind: 'lane', id: doc.lanes[0].id };
	assert.deepEqual(shots(await renderComponent(INSPECTOR)), [false]);
	doc.audio = [];
	assert.deepEqual(shots(await renderComponent(INSPECTOR)), [true]);
});

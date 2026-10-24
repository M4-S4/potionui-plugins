import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JOIN_TOLERANCE, MAX_SLICES, SLICE_MAX, SLICE_MIN, SLICE_SECONDS, continues, joined, sliceChain, sliceCuts, sliceItem, sliceLength } from './tracks.js';
import { isReferenceItem, joinPlan } from './sound.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const lane = (id, extra = {}) => ({ id, name: id, role: 'Musique', vol: 0, pan: 0, mute: false, solo: false, ...extra });
const sound = (id, start, dur, extra = {}) => ({ id, assetId: 'stem', lane: 'A1', start, dur, srcIn: 0, fadeIn: 0, fadeOut: 0, gain: -6, ...extra });
const ids = () => {
	let n = 0;
	return () => `new-${++n}`;
};
const shape = (items) => items.map((x) => [x.id, x.start, x.dur, x.srcIn, x.fadeIn, x.fadeOut]);

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

test('the page slices and joins the selected audio clip through act(), from the Inspector, the command search and the keyboard', () => {
	const state = source('./state.svelte.js');
	assert.match(state, /sliceAudio\(seconds = ui\.sliceSeconds\)[\s\S]*?act\(\(\) => \{\n\t\tObject\.assign\(a, parts\[0\]\);/);
	assert.match(state, /export function joinAudio\(\)[\s\S]*?act\(\(\) => \{\n\t\tfor \(const run of runs\.filter/);
	assert.match(state, /sliceSeconds: SLICE_SECONDS/);
	const commands = source('./commands.js');
	assert.match(commands, /command\('audio-slice', \(\) => sliceAudio\(\), \{ keys: 'shift\+mod\+b', vars: \(\) => \(\{ dur: secs\(ui\.sliceSeconds\) \}\) \}\)/);
	assert.match(commands, /command\('audio-join', joinAudio, \{ keys: 'alt\+mod\+b' \}\)/);
	const inspector = source('../components/inspector/Inspector.svelte');
	assert.match(inspector, /setReferenceItem\(item, audioLane, v\)/);
	assert.match(inspector, /act\(\(\) => followLane\(item\)\)/);
	assert.match(inspector, /undoable=\{false\} onchange=\{\(v\) => \(ui\.sliceSeconds = sliceLength\(v\)\)\}/);
	assert.match(inspector, /onclick: \(\) => sliceAudio\(\)/);
	assert.match(inspector, /onclick: joinAudio/);
	assert.match(source('../components/inspector/NumField.svelte'), /if \(undoable\) checkpoint\(\);/);
	const timeline = source('../components/timeline/Timeline.svelte');
	assert.match(timeline, /\{@const reference = isReferenceItem\(a, row\.lane\)\}/);
	assert.match(timeline, /\{#if reference\}<span class="flex shrink-0 text-signal" role="img"[^>]*data-reference-item><Icon name="sparkles"/);
});

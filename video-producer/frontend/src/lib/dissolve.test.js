import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DOMAINS, mergeDomains, translate } from '../i18n/core.js';
import { DISSOLVE_CHOICES, MAX_DISSOLVE, cuts, dissolveGain, dissolveMarks, dissolveOf, indexAt, joins, layout, limitOf, lostSeconds, mixAt, placement, setDissolve, shownSpan, shownSpans, startingAt, unfaded } from './dissolve.js';
import { MAKERS } from './exchange.js';
import { ghostLayout } from './band.js';
import { shotsContext } from './assistant.js';
import { shotCuts } from './tracks.js';

const here = dirname(fileURLToPath(import.meta.url));
const tests = join(here, '..', '..', '..', 'tests', 'fixtures');
const cases = JSON.parse(readFileSync(join(tests, 'dissolve_cases.json'), 'utf-8'));
const property = JSON.parse(readFileSync(join(tests, 'dissolve_property.json'), 'utf-8'));
const readDomain = (domain) => JSON.parse(readFileSync(join(here, '..', 'i18n', 'en', `${domain}.json`), 'utf-8'));
const dictionaries = { en: mergeDomains(Object.fromEntries(DOMAINS.map((domain) => [domain, readDomain(domain)]))) };
const close = (actual, expected) => assert.ok(actual.length === expected.length && actual.every((v, i) => Math.abs(v - expected[i]) < 1e-9), `${actual} != ${expected}`);
const snap = (v) => +(Math.round(v / 0.04) * 0.04).toFixed(3);

function laidOut(durations, asks) {
	const clips = durations.map((dur, i) => ({ id: `c${i}`, dur, fadeIn: 0.4, fadeOut: 0.4, ...(asks[i] ? { dissolve: asks[i] } : {}) }));
	layout(clips, snap).forEach((start, i) => (clips[i].start = start));
	return clips;
}

for (const c of cases) {
	test(`dissolve: the shared case "${c.name}" lays out and plays the dissolves the server does`, () => {
		const clips = c.clips.map((clip, i) => ({ id: `c${i}`, ...clip }));
		close(layout(clips, snap), c.starts);
		clips.forEach((clip, i) => (clip.start = c.starts[i]));
		close(joins(clips), c.joins);
	});
}

test('dissolve: seeded documents give on the page the layout, dissolves, drawn spans and exchange cuts of the server, at every cadence', () => {
	for (const [n, c] of property.docs.entries()) {
		const clips = c.clips.map((clip, i) => ({ id: `c${i}`, ...clip }));
		assert.deepEqual(layout(clips, snap), c.laid, `layout of document ${n}`);
		clips.forEach((clip, i) => (clip.start = c.starts[i]));
		assert.deepEqual(joins(clips), c.joins, `dissolves of document ${n}`);
		close(
			shownSpans(clips).flatMap((span) => [span.start, span.start + span.dur]),
			c.spans.flat()
		);
		for (const fps of property.fps) {
			const frames = (s) => Math.round(s * fps);
			assert.deepEqual(
				cuts(clips, frames).map((cut) => (cut ? [cut.start, cut.end, cut.overlap, cut.head] : null)),
				c.cuts[String(fps)],
				`cuts of document ${n} at ${fps} fps`
			);
		}
		clips.forEach((clip, i) => {
			if (i && !(String(i) in c.gaps) && dissolveOf(clips[i - 1], clip) > 0) assert.ok(c.joins[i] > 0, `cut ${i} of document ${n} dissolves`);
			if (i > 1 && c.joins[i - 1] && c.joins[i]) assert.ok(clips[i - 2].start + clips[i - 2].dur <= clip.start + 1e-6, `dissolves around shot ${i - 1} of document ${n}`);
			const places = placement(clips);
			if (i && c.joins.some(Boolean) && !(String(i) in c.gaps) && places[i] && places[i - 1]) assert.ok(places[i].start <= places[i - 1].end + 1e-6, `no black before shot ${i} of document ${n}`);
		});
	}
});

test('dissolve: every choice of the page is on the grid of the document and within the bound, at any cadence', () => {
	for (const v of DISSOLVE_CHOICES) {
		assert.ok(v > 0 && v <= MAX_DISSOLVE);
		const clips = laidOut([10, 10], [0, v]);
		assert.equal(limitOf(clips[0], clips[1]).by, null, String(v));
		assert.equal(joins(clips)[1], v);
	}
});

test('dissolve: the page says why a dissolve is shorter than asked: half of a short shot, or the grid', () => {
	assert.deepEqual(limitOf({ dur: 4 }, { dur: 1, dissolve: 1 }), { seconds: 0.48, by: 'half' });
	assert.deepEqual(limitOf({ dur: 4 }, { dur: 4, dissolve: 0.5 }), { seconds: 0.48, by: 'grid' });
	assert.deepEqual(limitOf({ dur: 4 }, { dur: 4, dissolve: 1 }), { seconds: 1, by: null });
	assert.deepEqual(limitOf({ dur: 0.12 }, { dur: 4, dissolve: 1 }), { seconds: 0, by: 'half' });
	assert.deepEqual(limitOf({ dur: 4 }, { dur: 4, dissolve: 0.04 }), { seconds: 0, by: 'brief' });
	assert.equal(dissolveOf({ dur: 0.16 }, { dur: 4, dissolve: 1 }), 0.08);
});

test('dissolve: after a shot of 3.1 s, a project that dissolves lays every shot end to end exactly, and the dissolve keeps its length', () => {
	const clips = laidOut([3.1, 4, 2], [0, 1, 0]);
	assert.deepEqual(
		clips.map((c) => c.start),
		[0, 2.1, 6.1]
	);
	assert.deepEqual(joins(clips), [0, 1, 0]);
	assert.equal(lostSeconds(clips), 1);
	const cuts = laidOut([3.1, 2, 2], [0, 0, 0]);
	assert.deepEqual(
		cuts.map((c) => c.start),
		[0, 3.12, 5.08]
	);
});

test('dissolve: choosing one clears the fade to black on both sides of its cut, only when the cut really dissolves', () => {
	const clips = laidOut([4, 4, 4], [0, 0, 0]);
	assert.equal(setDissolve(clips, 0, 1), false);
	assert.equal(setDissolve(clips, 1, 1), true);
	assert.deepEqual([clips[0].fadeIn, clips[0].fadeOut, clips[1].fadeIn, clips[1].fadeOut, clips[1].dissolve], [0.4, 0, 0, 0.4, 1]);
	setDissolve(clips, 1, 9);
	assert.equal(clips[1].dissolve, MAX_DISSOLVE);
	setDissolve(clips, 1, 0);
	assert.ok(!('dissolve' in clips[1]));
	const short = laidOut([0.12, 0.12], [0, 0]);
	setDissolve(short, 1, 1);
	assert.deepEqual([short[1].dissolve, short[0].fadeOut, short[1].fadeIn], [1, 0.4, 0.4]);
});

test('dissolve: the fades of a dissolved cut are not played, the others are', () => {
	const clips = laidOut([4, 4, 4], [0, 1, 0]);
	assert.deepEqual([unfaded(clips, 0).fadeIn, unfaded(clips, 0).fadeOut], [0.4, 0]);
	assert.deepEqual([unfaded(clips, 1).fadeIn, unfaded(clips, 1).fadeOut], [0, 0.4]);
	assert.equal(unfaded(clips, 2), clips[2]);
});

test('dissolve: the timeline draws each shot up to the middle of its dissolves and one mark per dissolve', () => {
	const clips = laidOut([4, 4, 4], [0, 1, 0.6]);
	assert.deepEqual(shownSpan(clips, 0), { start: 0, end: 3.5, dur: 3.5, head: 0, tail: 0.5 });
	assert.deepEqual(shownSpan(clips, 1), { start: 3.5, end: 6.7, dur: 3.2, head: 0.5, tail: 0.3 });
	assert.deepEqual(shownSpan(clips, 2), { start: 6.7, end: 10.4, dur: 3.7, head: 0.3, tail: 0 });
	assert.deepEqual(
		dissolveMarks(clips).map((m) => [m.id, m.from.id, m.start, m.dur]),
		[
			['c1', 'c0', 3, 1],
			['c2', 'c1', 6.4, 0.6]
		]
	);
	assert.equal(lostSeconds(clips), 1.6);
	assert.deepEqual(shownSpan(laidOut([4, 3], [0, 0]), 1), { start: 4, end: 7, dur: 3, head: 0, tail: 0 });
});

test('dissolve: the shot at a time is the one the timeline draws there, and an item placed on the start of a shot belongs to it', () => {
	const clips = laidOut([4, 4, 4], [0, 1, 0]);
	assert.deepEqual(
		[0, 3, 3.2, 3.49, 3.5, 3.9, 6.99, 7].map((t) => indexAt(clips, t)),
		[0, 0, 0, 0, 1, 1, 1, 2]
	);
	assert.equal(indexAt(clips, 10.99), 2);
	assert.equal(indexAt(clips, 11), -1);
	assert.deepEqual(
		[0, 3, 3.2, 3.5, 7].map((t) => startingAt(clips, t)),
		[0, 1, 0, 1, 2]
	);
	const cut = laidOut([4, 4], [0, 0]);
	assert.deepEqual(
		[3.99, 4].map((t) => startingAt(cut, t)),
		[0, 1]
	);
});

test('dissolve: the viewer mixes the two pictures across the dissolve and nowhere else', () => {
	const clips = laidOut([2, 2, 1], [0, 1, 0]);
	assert.equal(mixAt(clips, 0.99), null);
	const half = mixAt(clips, 1.5);
	assert.deepEqual([half.from.id, half.to.id, half.index, half.progress], ['c0', 'c1', 1, 0.5]);
	assert.equal(mixAt(clips, 1).progress, 0);
	assert.equal(mixAt(clips, 2), null);
	assert.equal(mixAt(clips, 3.5), null);
});

test('dissolve: the sound of the two shots crosses at equal power over the same span', () => {
	const clips = laidOut([2, 2, 1], [0, 1, 0]);
	for (const time of [1, 1.25, 1.5, 1.75, 1.99]) {
		const out = dissolveGain(clips, 0, time);
		const into = dissolveGain(clips, 1, time);
		assert.ok(Math.abs(out * out + into * into - 1) < 1e-9, `${time}: ${out}, ${into}`);
	}
	assert.equal(dissolveGain(clips, 0, 0.5), 1);
	assert.equal(dissolveGain(clips, 1, 2.5), 1);
	assert.equal(dissolveGain(clips, 2, 3.5), 1);
	assert.ok(dissolveGain(clips, 1, 1.01) < 0.05 && dissolveGain(clips, 0, 1.99) < 0.05);
});

test('dissolve: a document plays the dissolve its starts overlap, and a bare overlap cuts at the later start', () => {
	const clips = [
		{ id: 'a', start: 0, dur: 4 },
		{ id: 'b', start: 4, dur: 4, dissolve: 1 }
	];
	assert.deepEqual(joins(clips), [0, 0]);
	assert.equal(mixAt(clips, 3.9), null);
	assert.deepEqual(dissolveMarks(clips), []);
	clips[1].start = 3.8;
	assert.deepEqual(joins(clips), [0, 0.2]);
	assert.deepEqual(shownSpan(clips, 1), { start: 3.9, end: 7.8, dur: 3.9, head: 0.1, tail: 0 });
	clips.push({ id: 'c', start: 7, dur: 2 });
	assert.deepEqual(
		placement(clips).map((p) => [p.start, p.end]),
		[
			[0, 4],
			[3.8, 7],
			[7, 9]
		]
	);
	assert.equal(indexAt(clips, 7.2), 2);
});

test('dissolve: the exchange cut sits in the middle of the dissolve, in frames', () => {
	const clips = laidOut([5, 4.2, 3], [0, 1, 0.52]);
	const frames = (s) => Math.round(s * 25);
	assert.deepEqual(cuts(clips, frames), [
		{ start: 0, end: 112, overlap: 0, head: 0 },
		{ start: 112, end: 198, overlap: 25, head: 12 },
		{ start: 198, end: 267, overlap: 13, head: 6 }
	]);
	assert.deepEqual(cuts(laidOut([5, 4], [0, 0]), frames), [null, null]);
});

test('dissolve: a sound sliced on the shots is cut at the middle of each dissolve, and a ghost shot lands at the end of the film', () => {
	const clips = laidOut([4, 4, 4], [0, 1, 0]);
	assert.deepEqual(shotCuts({ start: 0, dur: 11 }, clips), [3.5, 7]);
	assert.deepEqual(shotCuts({ start: 0, dur: 12 }, laidOut([4, 4, 4], [0, 0, 0])), [4, 8]);
	assert.equal(ghostLayout(clips, [{ keep: true, dur: 2 }], 3, lostSeconds(clips)).ghosts[0].start, 11);
	assert.equal(ghostLayout(clips, [{ keep: true, dur: 2 }], 3).ghosts[0].start, 12);
});

test('dissolve: the page writes the EDL, OTIO and FCPXML of a project with dissolves as the server does, byte for byte', () => {
	const fixture = JSON.parse(readFileSync(join(tests, 'exports', 'dissolve-project.json'), 'utf-8'));
	const fallback = translate(dictionaries, 'en', 'lib.default.clip');
	const label = (c) => c?.label || fixture.doc.assets?.find((a) => a.id === c?.assetId)?.name || fallback;
	for (const format of ['edl', 'otio', 'fcpxml']) {
		const golden = readFileSync(join(tests, 'exports', `dissolve.${format}`));
		assert.ok(Buffer.from(MAKERS[format](fixture.doc, { label }), 'utf-8').equals(golden), `${format} differs from dissolve.${format}`);
	}
	const edl = MAKERS.edl(fixture.doc, { label }).split('\r\n');
	assert.ok(edl.includes('002  VP002    V     D    025 00:00:00:10 00:00:02:06 00:00:04:00 00:00:07:17'));
	assert.ok(edl.includes('004  VP004    V     D    037 00:00:00:06 00:00:03:19 00:00:09:05 00:00:12:18'));
});

test('dissolve: the page writes a dissolve the starts overlap and a bare overlap in the EDL as the server does', () => {
	const doc = {
		name: 'Overlap',
		fps: 25,
		assets: [],
		lanes: [],
		audio: [],
		titles: [],
		clips: [
			{ id: 'a', start: 0, dur: 4, srcIn: 0 },
			{ id: 'b', start: 3.8, dur: 4, srcIn: 0, dissolve: 1 },
			{ id: 'c', start: 7, dur: 2, srcIn: 0 }
		]
	};
	const edl = MAKERS.edl(doc, { label: (c) => c.id }).split('\r\n');
	assert.ok(edl.includes('002  BL       V     D    005 00:00:00:00 00:00:03:05 00:00:03:20 00:00:07:00'), edl.join('\n'));
});

test('dissolve: the page never plays a dissolve longer than the rule, as the server', () => {
	const shot = (id, start, dur, extra = {}) => ({ id, start, dur, ...extra });
	assert.deepEqual(joins([shot('a', 0, 150), shot('b', 80, 150, { dissolve: 0.08 })]), [0, 0]);
	const run = [shot('a', 0, 4), shot('b', 3, 4, { dissolve: 1 }), shot('c', 5.5, 4, { dissolve: 1 })];
	assert.deepEqual(joins(run), [0, 1, 0]);
	assert.deepEqual(placement(run).map((place) => [place.start, place.end]), [[0, 4], [3, 5.5], [5.5, 9.5]]);
	run[2].start = 6.4;
	assert.deepEqual(joins(run), [0, 1, 0.6]);
	run[2].start = 6;
	assert.deepEqual(joins(run), [0, 1, 1]);
});

test('dissolve: in a project that dissolves, the assistant gets the exact times, so it measures the dissolves the page plays', () => {
	const doc = { clips: [{ id: 'a', dur: 1.048 }, { id: 'b', dur: 1.226, dissolve: 1 }, { id: 'c', dur: 0.411, dissolve: 1 }], prompts: [], frames: [] };
	layout(doc.clips, snap).forEach((start, i) => (doc.clips[i].start = start));
	const shots = shotsContext(doc, (c) => c.id);
	assert.deepEqual(shots.map((s) => [s.start, s.dur]), [[0, 1.048], [0.528, 1.226], [1.554, 0.411]]);
	assert.deepEqual(joins(shots), joins(doc.clips));
	assert.deepEqual(joins(shots), [0, 0.52, 0.2]);
	const plain = { clips: [{ id: 'a', start: 0, dur: 1.048 }, { id: 'b', start: 1.04, dur: 1.226 }], prompts: [], frames: [] };
	assert.deepEqual(shotsContext(plain, (c) => c.id).map((s) => [s.start, s.dur]), [[0, 1.05], [1.04, 1.23]]);
});

test('dissolve: a tie at the millionth rounds away from zero on the page, as on the server', () => {
	assert.deepEqual([2.0078125, 0.0234375, -2.0078125, 1.5, 10 / 3].map((value) => +value.toFixed(6)), [2.007813, 0.023438, -2.007813, 1.5, 3.333333]);
	const clips = [{ id: 'a', dur: 3.0078125 }, { id: 'b', dur: 2.0234375, dissolve: 1 }];
	assert.deepEqual(layout(clips, snap), [0, 2.007813]);
});

test('dissolve: the sound of a shot reads the placement it is given, so the playback lays the shots once per update', () => {
	const clips = Array.from({ length: 40 }, (_, i) => ({ id: `c${i}`, dur: 1 + (i % 5) * 0.21, fadeIn: 0.2, fadeOut: 0.2, ...(i % 3 ? { dissolve: 0.4 } : {}) }));
	layout(clips, snap).forEach((start, i) => (clips[i].start = start));
	const places = placement(clips);
	for (let i = 0; i < clips.length; i++) {
		assert.deepEqual(unfaded(clips, i, places), unfaded(clips, i));
		for (const at of [clips[i].start, clips[i].start + 0.1, clips[i].start + clips[i].dur / 2, clips[i].start + clips[i].dur - 0.05]) assert.equal(dissolveGain(clips, i, at, places), dissolveGain(clips, i, at));
	}
	const busy = Array.from({ length: 500 }, (_, i) => ({ id: `c${i}`, dur: 1 + (i % 7) * 0.13, ...(i ? { dissolve: 0.4 } : {}) }));
	layout(busy, snap).forEach((start, i) => (busy[i].start = start));
	const laid = placement(busy);
	const t0 = performance.now();
	for (let k = 0; k < 200; k++) dissolveGain(busy, 250, busy[250].start + 0.1, laid);
	const given = performance.now() - t0;
	const t1 = performance.now();
	for (let k = 0; k < 200; k++) dissolveGain(busy, 250, busy[250].start + 0.1);
	assert.ok(given * 5 < performance.now() - t1, `${given} ms given, ${performance.now() - t1} ms laid each time`);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { merge3, mergeDocs, same } from './merge.js';
import { chained, joins, layout } from './dissolve.js';
import { onGrid } from './grid.js';

const clone = (value) => JSON.parse(JSON.stringify(value));

function baseDoc() {
	return {
		name: 'Night ride',
		synopsis: 'A courier crosses the city.',
		engine: { quality: 'draft', variants: 2, preset: 'wan' },
		clips: [
			{ id: 's1', label: 'Arrival', start: 0, dur: 4 },
			{ id: 's2', label: 'Bridge', start: 4, dur: 5 },
			{ id: 's3', label: 'Exit', start: 9, dur: 3 }
		],
		prompts: [{ id: 'p1', shotId: 's1', start: 0, dur: 4, text: 'Wide shot' }],
		removedTakes: ['t9']
	};
}

test('same compares values whatever the key order, and numbers by value', () => {
	assert.equal(same({ a: 1, b: [1, { c: 4 }] }, { b: [1, { c: 4.0 }], a: 1 }), true);
	assert.equal(same({ a: 1 }, { a: 1, b: undefined }), false);
	assert.equal(same([1, 2], [2, 1]), false);
	assert.equal(same(null, {}), false);
});

test('nothing changed on the page takes the server document as it is', () => {
	const base = baseDoc();
	const theirs = clone(base);
	theirs.clips.splice(1, 0, { id: 'n1', label: 'Close-up', start: 4, dur: 2 });
	theirs.clips[2].start = 6;
	theirs.clips[3].start = 11;

	const { value, conflicts } = merge3(base, clone(base), theirs);

	assert.deepEqual(value, theirs);
	assert.equal(conflicts, 0);
});

test('an edit on the page and a change of the server on other fields both land', () => {
	const base = baseDoc();
	const mine = clone(base);
	mine.synopsis = 'A courier crosses the city at night.';
	mine.clips[2].label = 'Last exit';
	const theirs = clone(base);
	theirs.clips[0].cast = { characters: ['c1'] };
	theirs.engine.variants = 3;

	const { value, conflicts } = merge3(base, mine, theirs);

	assert.equal(value.synopsis, 'A courier crosses the city at night.');
	assert.equal(value.clips[2].label, 'Last exit');
	assert.deepEqual(value.clips[0].cast, { characters: ['c1'] });
	assert.equal(value.engine.variants, 3);
	assert.equal(conflicts, 0);
});

test('the same field changed on both sides keeps the page and counts a conflict', () => {
	const base = baseDoc();
	const mine = clone(base);
	mine.clips[1].label = 'Typed on the page';
	const theirs = clone(base);
	theirs.clips[1].label = 'Written by the assistant';

	const { value, conflicts } = merge3(base, mine, theirs);

	assert.equal(value.clips[1].label, 'Typed on the page');
	assert.equal(conflicts, 1);
});

test('shots added on both sides are all kept, each next to its neighbour', () => {
	const base = baseDoc();
	const mine = clone(base);
	mine.clips.push({ id: 'm1', label: 'Mine', start: 12, dur: 2 });
	const theirs = clone(base);
	theirs.clips.splice(1, 0, { id: 't1', label: 'Theirs', start: 4, dur: 2 });

	const { value } = merge3(base, mine, theirs);

	assert.deepEqual(
		value.clips.map((c) => c.id),
		['s1', 't1', 's2', 's3', 'm1']
	);
});

test('an item deleted on one side and edited on the other comes back as the edit, with a conflict', () => {
	const base = { references: [{ id: 'r1', name: 'Look' }, { id: 'r2', name: 'Gate' }] };
	const theirs = clone(base);
	theirs.references.pop();
	const untouched = merge3(base, clone(base), theirs);
	const mine = clone(base);
	mine.references[1].name = 'Old gate';
	const edited = merge3(base, mine, theirs);

	assert.deepEqual(
		untouched.value.references.map((r) => r.id),
		['r1']
	);
	assert.equal(untouched.conflicts, 0);
	assert.deepEqual(edited.value.references[1], { id: 'r2', name: 'Old gate' });
	assert.equal(edited.conflicts, 1);
});

test('a reorder on one side keeps that order and places the other side additions', () => {
	const base = baseDoc();
	const theirs = clone(base);
	theirs.clips = [theirs.clips[2], theirs.clips[0], theirs.clips[1]];
	const mine = clone(base);
	mine.clips.splice(1, 0, { id: 'm1', label: 'Mine', start: 4, dur: 1 });

	const { value, conflicts } = merge3(base, mine, theirs);

	assert.deepEqual(
		value.clips.map((c) => c.id),
		['s3', 's1', 'm1', 's2']
	);
	assert.equal(conflicts, 0);
});

test('a key removed by the server is removed, a key the page added stays', () => {
	const base = baseDoc();
	const theirs = clone(base);
	delete theirs.removedTakes;
	const mine = clone(base);
	mine.dialogueLanguage = 'fr';

	const { value } = merge3(base, mine, theirs);

	assert.equal('removedTakes' in value, false);
	assert.equal(value.dialogueLanguage, 'fr');
});

test('lists without ids are merged as one value', () => {
	const base = { lanes: [{ inserts: [{ type: 'eq', on: true }] }].map((x, i) => ({ id: `A${i}`, ...x })), tags: ['a'] };
	const mine = clone(base);
	mine.tags = ['a', 'b'];
	const theirs = clone(base);
	theirs.tags = ['c'];
	theirs.lanes[0].inserts[0].on = false;

	const { value, conflicts } = merge3(base, mine, theirs);

	assert.deepEqual(value.tags, ['a', 'b']);
	assert.equal(value.lanes[0].inserts[0].on, false);
	assert.equal(conflicts, 1);
});

function timedDoc() {
	return {
		name: 'Night ride',
		clips: [
			{ id: 's1', label: 'Arrival', start: 0, dur: 4 },
			{ id: 's2', label: 'Bridge', start: 4, dur: 4 }
		],
		prompts: [
			{ id: 'p1', shotId: 's1', start: 0, dur: 4, text: 'Wide shot' },
			{ id: 'p2', shotId: 's2', start: 4, dur: 4, text: 'The bridge' }
		],
		frames: [{ id: 'f2', shotId: 's2', time: 4.5, assetId: 'img', role: 'first', strength: 100 }],
		references: [
			{ id: 'r-look', name: 'Look', scope: { type: 'global' } },
			{ id: 'r-own', name: 'Gate', scope: { type: 'shot', shotId: 's2' } }
		]
	};
}

const spans = (doc) => doc.clips.map((c) => [c.id, c.start, c.dur]);

test('a shot the assistant adds at the start and one the page adds at the end are laid out end to end, each prompt with its shot', () => {
	const base = timedDoc();
	const theirs = clone(base);
	theirs.clips = [{ id: 'a0', label: 'Opening', start: 0, dur: 3 }, { ...theirs.clips[0], start: 3 }, { ...theirs.clips[1], start: 7 }];
	theirs.prompts = [{ ...theirs.prompts[0], start: 3 }, { ...theirs.prompts[1], start: 7 }, { id: 'pa', shotId: 'a0', start: 0, dur: 3, text: 'Dawn' }];
	theirs.frames[0].time = 7.5;
	const mine = clone(base);
	mine.clips.push({ id: 'm3', label: 'Exit', start: 8, dur: 2 });
	mine.prompts.push({ id: 'pm', shotId: 'm3', start: 8, dur: 2, text: 'The rider leaves' });

	const { value, conflicts } = mergeDocs(base, mine, theirs);

	assert.deepEqual(spans(value), [
		['a0', 0, 3],
		['s1', 3, 4],
		['s2', 7, 4],
		['m3', 11, 2]
	]);
	assert.deepEqual(
		value.prompts.map((p) => [p.id, p.start]),
		[
			['p1', 3],
			['p2', 7],
			['pm', 11],
			['pa', 0]
		]
	);
	assert.equal(value.frames[0].time, 7.5);
	assert.equal(conflicts, 0);
});

test('a frame moved inside its shot on the page keeps its place in the shot when the assistant moves the shot', () => {
	const base = timedDoc();
	const mine = clone(base);
	mine.frames[0].time = 5;
	const theirs = clone(base);
	theirs.clips = [{ id: 'a0', label: 'Opening', start: 0, dur: 2 }, { ...theirs.clips[0], start: 2 }, { ...theirs.clips[1], start: 6 }];
	theirs.prompts = [{ ...theirs.prompts[0], start: 2 }, { ...theirs.prompts[1], start: 6 }];
	theirs.frames[0].time = 6.5;

	const { value, conflicts } = mergeDocs(base, mine, theirs);

	assert.equal(value.frames[0].time, 7);
	assert.deepEqual(spans(value), spans(theirs));
	assert.equal(conflicts, 0);
});

test('a change that moves nothing keeps every time exactly as the server saved it', () => {
	const base = timedDoc();
	const mine = clone(base);
	mine.name = 'Night ride, cut 2';
	const theirs = clone(base);
	theirs.clips[1].label = 'Old bridge';

	const { value } = mergeDocs(base, mine, theirs);

	assert.equal(same(value, { ...theirs, name: 'Night ride, cut 2' }), true);
});

test('a shot the assistant deleted while the page edited it goes whole, prompt, frames and own references with it, and is counted as dropped', () => {
	const base = timedDoc();
	const theirs = clone(base);
	theirs.clips.pop();
	theirs.prompts.pop();
	theirs.frames = [];
	theirs.references.pop();
	const mine = clone(base);
	mine.clips[1].label = 'Bridge at dawn';
	mine.prompts.push({ id: 'p2b', shotId: 's2', start: 6, dur: 2, text: 'A second prompt' });

	const edited = mergeDocs(base, mine, theirs);
	const untouched = mergeDocs(base, clone(base), theirs);

	assert.equal(same(edited.value, theirs), true);
	assert.deepEqual([edited.dropped, edited.conflicts], [1, 0]);
	assert.deepEqual([untouched.dropped, untouched.conflicts], [0, 0]);
});

test('a shot the page deleted stays deleted with everything linked to it, and a change of the assistant to it counts as a conflict', () => {
	const base = timedDoc();
	const mine = clone(base);
	mine.clips = [{ ...mine.clips[1], start: 0 }];
	mine.prompts = [{ ...mine.prompts[1], start: 0 }];
	mine.frames[0].time = 0.5;
	const theirs = clone(base);
	theirs.clips[0].label = 'Arrival at night';
	theirs.prompts[0].text = 'Wide shot at night';

	const { value, conflicts, dropped } = mergeDocs(base, mine, theirs);

	assert.deepEqual(spans(value), [['s2', 0, 4]]);
	assert.deepEqual(
		value.prompts.map((p) => p.id),
		['p2']
	);
	assert.equal(value.frames[0].time, 0.5);
	assert.deepEqual([conflicts, dropped], [1, 0]);
});

test('lists of ids changed on both sides keep the additions and the removals of each side', () => {
	const base = timedDoc();
	base.removedTakes = ['t1', 't2'];
	base.clips[0].cast = { characters: ['mara', 'ivo'], place: 'dock' };
	base.clips[1].referenceOverrides = { exclude: ['r-look'] };
	const mine = clone(base);
	mine.removedTakes = ['t2', 't3'];
	mine.clips[0].cast.characters = ['mara', 'lea'];
	delete mine.clips[1].referenceOverrides;
	const theirs = clone(base);
	theirs.removedTakes = ['t1', 't2', 't4'];
	theirs.clips[0].cast.characters = ['ivo', 'mara', 'sam'];
	theirs.clips[1].referenceOverrides = { exclude: ['r-look', 'r-rain'] };

	const { value, conflicts } = mergeDocs(base, mine, theirs);

	assert.deepEqual(value.removedTakes, ['t2', 't3', 't4']);
	assert.deepEqual(value.clips[0].cast, { characters: ['mara', 'lea', 'sam'], place: 'dock' });
	assert.deepEqual(value.clips[1].referenceOverrides, { exclude: ['r-rain'] });
	assert.equal(conflicts, 0);
});

test('a list of ids emptied by both sides leaves the key out, as the page stores it', () => {
	const base = timedDoc();
	base.removedTakes = ['t1', 't2'];
	const mine = clone(base);
	mine.removedTakes = ['t1'];
	const theirs = clone(base);
	theirs.removedTakes = ['t2'];

	const { value } = mergeDocs(base, mine, theirs);

	assert.equal('removedTakes' in value, false);
});

const fixtures = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');
const placed = (doc) => {
	const at = new Map(doc.clips.map((c) => [c.id, c.start]));
	const items = [...doc.prompts.map((p) => [p, p.start]), ...doc.frames.map((f) => [f, f.time])];
	return new Map(items.map(([item, time]) => [item.id, at.has(item.shotId) ? +(time - at.get(item.shotId)).toFixed(6) : time]));
};
const laidOut = (doc) => {
	const starts = layout(doc.clips, onGrid);
	return { ...doc, clips: doc.clips.map((c, i) => ({ ...c, start: starts[i] })) };
};

function dissolving(clips, mineEdit, theirsEdit) {
	const base = laidOut({ clips });
	base.prompts = [{ id: 'p', shotId: 'c', start: base.clips[2].start, dur: 1, text: 'Harbour' }];
	const side = (change) => {
		const doc = laidOut({ clips: base.clips.map(change) });
		return { ...doc, prompts: [{ ...base.prompts[0], start: doc.clips[2].start }] };
	};
	return mergeDocs(base, side(mineEdit), side(theirsEdit)).value;
}

test('merge: in a project that dissolves, the merged shots start where the layout of the page puts them, so the dissolves still play and the linked items follow', () => {
	const lengthened = dissolving(
		[{ id: 'a', dur: 2 }, { id: 'b', dur: 2, dissolve: 0.4 }, { id: 'c', dur: 2 }],
		(c) => (c.id === 'a' ? { ...c, dur: 2.4 } : c),
		(c) => (c.id === 'c' ? { ...c, dur: 3 } : c)
	);
	assert.deepEqual(lengthened.clips.map((c) => c.start), [0, 2, 4]);
	assert.deepEqual(joins(lengthened.clips), [0, 0.4, 0]);
	assert.equal(lengthened.prompts[0].start, 4);
	const both = dissolving(
		[{ id: 'a', dur: 2 }, { id: 'b', dur: 1.8, dissolve: 0.4 }, { id: 'c', dur: 2, dissolve: 0.4 }],
		(c) => (c.id === 'a' ? { ...c, dur: 2.4 } : c),
		(c) => (c.id === 'b' ? { ...c, dur: 2 } : c)
	);
	assert.deepEqual(both.clips.map((c) => [c.dur, c.start]), [[2.4, 0], [2, 2], [2, 3.6]]);
	assert.deepEqual(joins(both.clips), [0, 0.4, 0.4]);
	const chosen = dissolving(
		[{ id: 'a', dur: 2 }, { id: 'b', dur: 2 }, { id: 'c', dur: 2 }],
		(c) => (c.id === 'b' ? { ...c, dissolve: 0.4 } : c),
		(c) => (c.id === 'c' ? { ...c, dissolve: 0.4 } : c)
	);
	assert.deepEqual(chosen.clips.map((c) => c.start), [0, 1.6, 3.2]);
	assert.deepEqual(joins(chosen.clips), [0, 0.4, 0.4]);
	assert.equal(chosen.prompts[0].start, 3.2);
	const removed = dissolving(
		[{ id: 'a', dur: 2 }, { id: 'b', dur: 2, dissolve: 0.4 }, { id: 'c', dur: 2 }],
		(c) => c,
		(c) => (c.id === 'b' ? { ...c, dissolve: 0 } : c)
	);
	assert.deepEqual(removed.clips.map((c) => c.start), [0, 2, 4]);
	assert.equal(removed.prompts[0].start, 4);
});

test('merge: when no input dissolves but the merge does, the merge keeps, drops and counts what version 0.5.1 did, and lays the shots out so that the dissolve plays', () => {
	const base = laidOut({ clips: [{ id: 'a', dur: 0.1 }, { id: 'b', dur: 2 }, { id: 'c', dur: 2 }], frames: [] });
	base.prompts = [{ id: 'p', shotId: 'c', start: +(base.clips[2].start + 0.3203).toFixed(6), dur: 1, text: 'Harbour' }];
	const mine = laidOut({ ...base, clips: base.clips.map((c) => (c.id === 'a' ? { ...c, dur: 2 } : c)) });
	mine.prompts = [{ ...base.prompts[0], start: 4.32 }];
	const keyed = (doc) => laidOut({ ...doc, clips: doc.clips.map((c) => (c.id === 'b' ? { ...c, dissolve: 0.4 } : c)) });
	const deleted = mergeDocs(base, mine, keyed({ ...base, prompts: [] }));
	assert.deepEqual([deleted.value.prompts, deleted.conflicts, deleted.dropped], [[], 0, 0]);
	const gone = mergeDocs(base, mine, keyed({ ...base, clips: base.clips.filter((c) => c.id !== 'c'), prompts: [] }));
	assert.deepEqual([gone.value.clips.map((c) => c.id), gone.value.prompts, gone.conflicts, gone.dropped], [['a', 'b'], [], 0, 0]);
	const kept = mergeDocs(base, mine, keyed(base));
	assert.deepEqual(kept.value.clips.map((c) => c.start), [0, 1.6, 3.6]);
	assert.deepEqual(joins(kept.value.clips), [0, 0.4, 0]);
	assert.deepEqual([kept.value.prompts.map((p) => p.start), kept.conflicts, kept.dropped], [[3.92], 0, 0]);
});

test('merge: at seeded concurrent edits of shots off the grid with dissolves, the merged starts are those of the layout of the page and of the server, and each prompt or frame stays in its shot at its offset, to the millionth when a cut of an input and of the merge dissolves', () => {
	const cases = JSON.parse(readFileSync(join(fixtures, 'merge_dissolve_cases.json'), 'utf-8'));
	assert.ok(cases.length >= 100);
	for (const [n, { base, mine, theirs, merged, starts }] of cases.entries()) {
		const value = mergeDocs(base, mine, theirs).value;
		assert.deepEqual(value.clips.map(({ id, dur, dissolve }) => ({ id, dur, ...(dissolve === undefined ? {} : { dissolve }) })), merged, `case ${n}`);
		assert.deepEqual(value.clips.map((c) => c.start), starts, `case ${n}`);
		assert.deepEqual(layout(value.clips, onGrid), starts, `case ${n}`);
		const [b, m, t, v] = [base, mine, theirs, value].map(placed);
		const exact = [base, mine, theirs].some((doc) => chained(doc.clips)) && chained(value.clips);
		for (const [id, offset] of v) {
			const wanted = m.get(id) === b.get(id) ? t.get(id) : m.get(id);
			if (exact) assert.equal(offset, wanted, `case ${n} ${id}`);
			else assert.ok(Math.abs(offset - wanted) < 0.0005 + 1e-9, `case ${n} ${id}`);
		}
	}
});

test('merge: at seeded concurrent edits of shots without a dissolve, the merge gives the document of version 0.5.1 byte for byte', () => {
	const cases = JSON.parse(readFileSync(join(fixtures, 'merge_no_dissolve_cases.json'), 'utf-8'));
	assert.ok(cases.length >= 100);
	for (const [n, { base, mine, theirs, merged }] of cases.entries()) assert.equal(JSON.stringify(mergeDocs(base, mine, theirs).value), JSON.stringify(merged), `case ${n}`);
});

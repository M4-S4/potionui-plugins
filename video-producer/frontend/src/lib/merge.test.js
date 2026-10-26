import { test } from 'node:test';
import assert from 'node:assert/strict';
import { merge3, same } from './merge.js';

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

test('a shot deleted by the server goes, unless the page edited it meanwhile', () => {
	const base = baseDoc();
	const theirs = clone(base);
	theirs.clips = theirs.clips.filter((c) => c.id !== 's2');
	const untouched = merge3(base, clone(base), theirs);
	const mine = clone(base);
	mine.clips[1].dur = 6;
	const edited = merge3(base, mine, theirs);

	assert.deepEqual(
		untouched.value.clips.map((c) => c.id),
		['s1', 's3']
	);
	assert.equal(untouched.conflicts, 0);
	assert.deepEqual(
		edited.value.clips.map((c) => c.id),
		['s1', 's2', 's3']
	);
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

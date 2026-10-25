import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	byPhrases,
	castFor,
	displayStart,
	ghostLayout,
	headOf,
	insertIndex,
	lastFailure,
	mergeItem,
	moveItem,
	musicEnd,
	musicParts,
	onMusic,
	previewable,
	removeItem,
	seamStatus,
	sections,
	splitItem,
	stackOrder
} from './band.js';

const ids = () => {
	let n = 0;
	return () => `id${++n}`;
};

const bible = {
	characters: [
		{ id: 'c-lina', label: 'Lina' },
		{ id: 'c-malo', label: 'Malo' }
	],
	places: [{ id: 'p-quai', label: 'Quai 9' }]
};

const synopsis = 'Minuit, la ville se noie sous la pluie. Lina regarde les lumières depuis son balcon. Elle croise Malo dans le métro. Le dernier métro quitte le quai 9.';

test('the parts of the song come from the plain markers, in time order, each ending at the next one', () => {
	const markers = [
		{ id: 'b', time: 8, label: 'Couplet', kind: 'marker' },
		{ id: 'f', time: 4, label: 'Favori', kind: 'favori' },
		{ id: 'a', time: 0, label: 'Intro', kind: 'marker' },
		{ id: 'c', time: 24, label: 'Refrain', kind: 'marker' }
	];
	assert.deepEqual(sections(markers, 40), [
		{ id: 'a', label: 'Intro', start: 0, end: 8 },
		{ id: 'b', label: 'Couplet', start: 8, end: 24 },
		{ id: 'c', label: 'Refrain', start: 24, end: 40 }
	]);
	assert.deepEqual(sections([], 40), []);
});

test('the song ends with the last clip of a Music track, and other tracks do not count', () => {
	const doc = {
		lanes: [
			{ id: 'l1', role: 'Dialogue' },
			{ id: 'l2', role: 'Musique' }
		],
		audio: [
			{ lane: 'l1', start: 0, dur: 90 },
			{ lane: 'l2', start: 2, dur: 58 }
		],
		markers: []
	};
	assert.equal(musicEnd(doc), 60);
	assert.deepEqual(musicParts(doc), [{ id: null, label: '', start: 0, end: 60 }]);
	assert.deepEqual(musicParts({ lanes: [], audio: [], markers: [] }), []);
});

test('by sentence keeps the former breakdown: one shot per sentence, 3 to 7 s, the head of the sentence as its name', () => {
	const items = byPhrases(synopsis, bible, ids());
	assert.equal(items.length, 4);
	assert.equal(items[0].label, 'Minuit');
	assert.equal(items[0].prompt, 'Minuit, la ville se noie sous la pluie.');
	assert.ok(items.every((x) => x.dur >= 3 && x.dur <= 7 && x.keep));
	assert.deepEqual(
		items.map((x) => x.n),
		[1, 2, 3, 4]
	);
	assert.equal(headOf('A'.repeat(40) + '.'), 'A'.repeat(32) + '…');
});

test('the cast of a proposed shot is the bible characters and the first place its sentence names', () => {
	assert.deepEqual(castFor('Elle croise Malo et Lina.', bible), { characters: ['c-lina', 'c-malo'] });
	assert.deepEqual(castFor('Le dernier métro quitte le quai 9.', bible), { place: 'p-quai' });
	assert.equal(castFor('Personne.', bible), null);
	assert.equal(castFor('Lina.', null), null);
});

test('on the song fills every part with shots snapped to the step, and spreads the sentences in order', () => {
	const parts = [
		{ id: 'a', label: 'Intro', start: 0, end: 8 },
		{ id: 'b', label: 'Couplet', start: 8, end: 24 },
		{ id: 'c', label: 'Outro', start: 24, end: 30 }
	];
	const items = onMusic(synopsis, parts, { avg: 4, step: 0.5 }, bible, ids());
	const total = items.reduce((sum, x) => sum + x.dur, 0);
	assert.equal(total, 30);
	assert.equal(items.filter((x) => x.part === 'Intro').length, 2);
	assert.equal(items.filter((x) => x.part === 'Couplet').length, 4);
	assert.ok(items.every((x) => Math.abs(x.dur * 2 - Math.round(x.dur * 2)) < 1e-9));
	const order = items.map((x) => synopsis.indexOf(x.prompt));
	assert.deepEqual(
		order,
		[...order].sort((a, b) => a - b)
	);
	assert.ok(items.some((x) => / \(2\)$/.test(x.label)));
	assert.deepEqual(onMusic(synopsis, [], {}, bible, ids()), []);
	assert.deepEqual(onMusic('', parts, {}, bible, ids()), []);
});

test('a proposed shot can be split, merged, moved and removed, and the numbers follow', () => {
	const make = ids();
	const items = [
		{ id: 'a', n: 1, keep: true, label: 'A', prompt: 'Lina.', dur: 5, cast: { characters: ['c-lina'] } },
		{ id: 'b', n: 2, keep: true, label: 'B', prompt: 'Malo.', dur: 3, cast: { characters: ['c-malo'] } }
	];
	splitItem(items, 0, make);
	assert.deepEqual(
		items.map((x) => [x.label, x.dur, x.n]),
		[
			['A', 2.5, 1],
			['A', 2.5, 2],
			['B', 3, 3]
		]
	);
	mergeItem(items, 1);
	assert.deepEqual(
		items.map((x) => [x.dur, x.n]),
		[
			[2.5, 1],
			[5.5, 2]
		]
	);
	assert.equal(items[1].prompt, 'Lina. Malo.');
	assert.deepEqual(items[1].cast, { characters: ['c-lina', 'c-malo'] });
	moveItem(items, 1, -1);
	assert.equal(items[0].dur, 5.5);
	assert.equal(items[0].n, 1);
	removeItem(items, 0);
	assert.deepEqual(
		items.map((x) => x.n),
		[1]
	);
});

test('the proposed shots go at the end or after the selected shot, and the shots after them shift by their length', () => {
	const clips = [
		{ id: 's1', start: 0, dur: 4 },
		{ id: 's2', start: 4, dur: 2 },
		{ id: 's3', start: 6, dur: 3 }
	];
	assert.equal(insertIndex(clips, 'end', 's1'), 3);
	assert.equal(insertIndex(clips, 'after', 's1'), 1);
	assert.equal(insertIndex(clips, 'after', 'missing'), 3);
	const items = [
		{ id: 'g1', keep: true, dur: 2 },
		{ id: 'g2', keep: false, dur: 9 },
		{ id: 'g3', keep: true, dur: 1.5 }
	];
	const layout = ghostLayout(clips, items, 1);
	assert.deepEqual(
		layout.ghosts.map((g) => [g.id, g.start, g.n]),
		[
			['g1', 4, 2],
			['g3', 6, 3]
		]
	);
	assert.equal(layout.shift, 3.5);
	assert.equal(displayStart(clips[0], 0, layout), 0);
	assert.equal(displayStart(clips[1], 1, layout), 7.5);
	assert.equal(displayStart(clips[2], 2, null), 6);
});

test('the takes stack the final first, then the candidates, drafts and rejected, then the running, queued and failed ones', () => {
	const takes = [
		{ id: '1', variant: 'A', status: 'done', label: 'rejected', url: 'a' },
		{ id: '2', variant: 'B', status: 'failed' },
		{ id: '3', variant: 'C', status: 'done', label: 'draft', url: 'c' },
		{ id: '4', variant: 'D', status: 'queued' },
		{ id: '5', variant: 'E', status: 'done', label: 'final', url: 'e' },
		{ id: '6', variant: 'F', status: 'running' },
		{ id: '7', variant: 'G', status: 'done', label: 'candidate' }
	];
	assert.deepEqual(
		stackOrder(takes).map((x) => x.variant),
		['E', 'G', 'C', 'A', 'F', 'D', 'B']
	);
	assert.deepEqual(
		stackOrder(takes, true).map((x) => x.variant),
		['E', 'G', 'C', 'F', 'D', 'B']
	);
	assert.deepEqual(
		previewable(takes).map((x) => x.variant),
		['E', 'C', 'A']
	);
});

test('a shot shows a failure only when its latest take failed', () => {
	assert.equal(lastFailure([{ status: 'failed', createdAt: '2026-10-25T10:00' }, { status: 'done', createdAt: '2026-10-25T11:00' }]), null);
	assert.equal(lastFailure([{ status: 'done', createdAt: '2026-10-25T10:00' }, { id: 'x', status: 'failed', createdAt: '2026-10-25T11:00' }]).id, 'x');
	assert.equal(lastFailure([]), null);
});

test('a seam marker shows the issues first, then a measured seam, and nothing for an unmeasured one', () => {
	assert.equal(seamStatus({ issues: [{ kind: 'warm' }], measured: true, pending: false }), 'issue');
	assert.equal(seamStatus({ issues: [], measured: true, pending: false }), 'ok');
	assert.equal(seamStatus({ issues: [], measured: false, pending: true }), null);
	assert.equal(seamStatus(null), null);
});

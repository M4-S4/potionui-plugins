import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { MAX_VREF_TRACKS, VREF_ITEMS, VREF_ROLES, VREF_TRACKS, migrateVrefs, trackItemsOf, videoTracksOf } from './vrefs.js';
import { emptyDoc, migrate } from './starter.js';
import { mergeDocs } from './merge.js';
import { excludedVrefsOf, migrateShots, setExcludedVrefs } from './shots.js';

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const { cases } = read('../../../tests/fixtures/vref_migration.json');
const table = read('./reception.json');
const pick = (doc) => Object.fromEntries([VREF_TRACKS, VREF_ITEMS].filter((key) => key in doc).map((key) => [key, doc[key]]));

test('the page knows the slots and roles of the shared table', () => {
	assert.equal(MAX_VREF_TRACKS, table.videoTracks.max);
	assert.deepEqual(VREF_ROLES, Object.keys(table.videoTracks.roles));
});

for (const c of cases) {
	test(`shared migration: ${c.name}`, () => {
		const doc = structuredClone(c.doc);
		const before = structuredClone(doc);
		assert.deepEqual(pick(migrateVrefs(doc)), c.expected);
		assert.deepEqual(doc, before);
	});
}

test('migrate reads the tracks of a whole document as the server does', () => {
	const doc = { ...emptyDoc((key) => key), ...structuredClone(cases[3].doc) };
	assert.deepEqual(pick(migrate(doc)), cases[3].expected);
	const plain = emptyDoc((key) => key);
	assert.deepEqual(pick(migrate(plain)), {});
});

test('the tracks come in slot order and the items of a track in time order', () => {
	const doc = {
		vrefTracks: [
			{ id: 'b', slot: 3 },
			{ id: 'a', slot: 1 },
			{ id: 'x', slot: 'two' }
		],
		vrefItems: [
			{ id: 'i2', track: 'a', start: 6 },
			{ id: 'i1', track: 'a', start: 2 },
			{ id: 'i3', track: 'b', start: 0 }
		]
	};
	assert.deepEqual(videoTracksOf(doc).map((track) => track.id), ['a', 'b']);
	assert.deepEqual(trackItemsOf(doc, 'a').map((item) => item.id), ['i1', 'i2']);
	assert.deepEqual(videoTracksOf({}), []);
});

test('a shot keeps the reference video tracks it leaves out, as distinct ids, next to its other exclusions', () => {
	const clip = { id: 's1' };
	setExcludedVrefs(clip, ['t1', 't1', '', 't2']);
	assert.deepEqual(clip.referenceOverrides, { excludeVrefs: ['t1', 't2'] });
	const [migrated] = migrateShots({ clips: [{ id: 's2', referenceOverrides: { exclude: ['g1'], excludeVrefs: ['t1', 4, 't1'] } }] }).clips;
	assert.deepEqual(migrated.referenceOverrides, { exclude: ['g1'], excludeVrefs: ['t1'] });
	setExcludedVrefs(clip, []);
	assert.equal('referenceOverrides' in clip, false);
	assert.deepEqual(excludedVrefsOf(null), []);
});

test('mergeDocs merges the tracks and items by id, the exclusions of a shot as a set, and drops what would break the slots', () => {
	const base = { clips: [{ id: 's1', start: 0, dur: 4 }], vrefTracks: [{ id: 't1', slot: 1, name: 'Walk', role: 'motion' }], vrefItems: [] };
	const mine = structuredClone(base);
	mine.vrefItems.push({ id: 'i1', track: 't1', assetId: null, start: 0, dur: 4, srcIn: 0 });
	mine.clips[0].referenceOverrides = { excludeVrefs: ['t1'] };
	const theirs = structuredClone(base);
	theirs.vrefTracks.push({ id: 't2', slot: 2, name: 'Sea', role: 'continuation' });
	theirs.clips[0].referenceOverrides = { excludeVrefs: ['t2'] };
	const merged = mergeDocs(base, mine, theirs);
	assert.equal(merged.conflicts, 0);
	assert.deepEqual(merged.value.vrefTracks.map((track) => track.id), ['t1', 't2']);
	assert.deepEqual(merged.value.vrefItems.map((item) => item.id), ['i1']);
	assert.deepEqual(merged.value.clips[0].referenceOverrides.excludeVrefs, ['t1', 't2']);

	const both = structuredClone(base);
	both.vrefTracks.push({ id: 't3', slot: 2, name: 'Mine', role: 'motion' });
	const other = structuredClone(base);
	other.vrefTracks.push({ id: 't4', slot: 2, name: 'Theirs', role: 'motion' });
	const clash = mergeDocs(base, both, other);
	assert.deepEqual(clash.value.vrefTracks.map((track) => [track.id, track.slot]), [
		['t1', 1],
		['t3', 2]
	]);
	assert.equal(clash.conflicts, 1);
});

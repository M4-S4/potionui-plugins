import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { emptyDoc, migrate, newAsset, newClip } from './starter.js';
import { removeAsset } from './usage.js';
import { clearRemoved, isRemoved, markRemoved, pruneRemoved, removedIds, takeOfAsset } from './removedtakes.js';

const t = (key) => key;
const takeAsset = (takeId, extra = {}) => newAsset({ id: `gen-${takeId}`, kind: 'video', generated: true, quality: 'draft', resultId: takeId, src: `/media/${takeId}.mp4`, ...extra });

test('removedIds keeps the distinct non-empty ids in order and reads anything else as none', () => {
	assert.deepEqual(removedIds(['t1', 't2', 't1', '', 3, null, { id: 't3' }, 't3']), ['t1', 't2', 't3']);
	assert.deepEqual(removedIds([]), []);
	assert.deepEqual(removedIds('t1'), []);
	assert.deepEqual(removedIds(undefined), []);
	assert.deepEqual(removedIds({ 0: 't1' }), []);
});

test('takeOfAsset names the take of a generated video only, never an imported media, a start image candidate or a renamed asset', () => {
	assert.equal(takeOfAsset(takeAsset('t1')), 't1');
	assert.equal(takeOfAsset(takeAsset('t1', { quality: 'final' })), 't1');
	assert.equal(takeOfAsset(newAsset({ id: 'pic', kind: 'image' })), null);
	assert.equal(takeOfAsset(newAsset({ id: 'clip', kind: 'video', src: '/media/clip.mp4' })), null);
	assert.equal(takeOfAsset(takeAsset('k1', { kind: 'image' })), null);
	assert.equal(takeOfAsset(takeAsset('t1', { id: 'copy' })), null);
	assert.equal(takeOfAsset(takeAsset('t1', { generated: false })), null);
	assert.equal(takeOfAsset(takeAsset('t1', { resultId: null })), null);
	assert.equal(takeOfAsset(newAsset({ kind: 'audio', generated: true, role: 'Ambiance' })), null);
	assert.equal(takeOfAsset(null), null);
});

test('markRemoved adds a take once, clearRemoved takes it out and drops the key with the last one', () => {
	const doc = {};
	assert.equal(isRemoved(doc, 't1'), false);
	assert.equal(markRemoved(doc, 't1'), true);
	assert.equal(markRemoved(doc, 't1'), false);
	assert.equal(markRemoved(doc, 't2'), true);
	assert.equal(markRemoved(doc, null), false);
	assert.equal(markRemoved(doc, ''), false);
	assert.deepEqual(doc.removedTakes, ['t1', 't2']);
	assert.equal(isRemoved(doc, 't1'), true);
	assert.equal(clearRemoved(doc, 'missing'), false);
	assert.equal(clearRemoved(doc, 't1'), true);
	assert.deepEqual(doc.removedTakes, ['t2']);
	assert.equal(clearRemoved(doc, 't2'), true);
	assert.equal('removedTakes' in doc, false);
	assert.equal(clearRemoved(doc, 't2'), false);
});

test('pruneRemoved forgets the takes the server no longer lists and leaves the list alone otherwise', () => {
	const doc = { removedTakes: ['t1', 't2', 't3'] };
	assert.equal(pruneRemoved(doc, [{ id: 't1' }, { id: 't2' }, { id: 't3' }, { id: 't4' }]), false);
	assert.deepEqual(doc.removedTakes, ['t1', 't2', 't3']);
	assert.equal(pruneRemoved(doc, [{ id: 't3' }, { id: 't1' }]), true);
	assert.deepEqual(doc.removedTakes, ['t1', 't3']);
	assert.equal(pruneRemoved(doc, []), true);
	assert.equal('removedTakes' in doc, false);
	assert.equal(pruneRemoved(doc, [{ id: 't1' }]), false);
	assert.equal('removedTakes' in doc, false);
});

test('removing the video of a take from the project records the take; removing any other media records nothing', () => {
	const shot = newClip({ id: 's1', assetId: 'gen-t1', take: 't1', stage: 'draft' });
	const doc = { assets: [takeAsset('t1'), takeAsset('t2'), newAsset({ id: 'pic', kind: 'image' }), takeAsset('k1', { kind: 'image' })], clips: [shot], audio: [], references: [], frames: [] };
	const result = removeAsset(doc, 'gen-t1');
	assert.deepEqual(result.released, [{ take: 't1' }]);
	assert.deepEqual(doc.removedTakes, ['t1']);
	assert.equal(doc.clips[0].stage, 'todo');
	removeAsset(doc, 'pic');
	removeAsset(doc, 'gen-k1');
	assert.deepEqual(doc.removedTakes, ['t1']);
	removeAsset(doc, 'gen-t2');
	assert.deepEqual(doc.removedTakes, ['t1', 't2']);
	assert.equal(removeAsset(doc, 'gen-t1'), null);
	assert.deepEqual(doc.removedTakes, ['t1', 't2']);
});

test('the page migration keeps the removed takes as distinct ids and drops the key when none is left, as the server does', () => {
	const cases = JSON.parse(readFileSync(new URL('../../../tests/fixtures/removed_takes_migration.json', import.meta.url), 'utf8'));
	const doc = emptyDoc(t);
	assert.equal('removedTakes' in migrate(doc), false);
	for (const { value, expected } of cases) {
		const next = migrate({ ...doc, removedTakes: value });
		assert.deepEqual(next.removedTakes ?? null, expected, JSON.stringify(value));
		assert.equal('removedTakes' in next, expected !== null, JSON.stringify(value));
		assert.deepEqual(migrate(next), next);
	}
});

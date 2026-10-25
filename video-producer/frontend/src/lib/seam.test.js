import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PREVIOUS_LAST, framesOf, frameTime, normalizeSeamMedia, placeSeamFrame, playheadPick, previousShot, requestBody, roleKind, seamAsset, seamImage } from './seam.js';

function sampleDoc() {
	return {
		clips: [
			{ id: 'c1', start: 0, dur: 4, srcIn: 0 },
			{ id: 'c2', start: 4, dur: 3, srcIn: 1.5 },
			{ id: 'c3', start: 7, dur: 5, srcIn: 0 }
		],
		frames: [
			{ id: 'f1', shotId: 'c1', time: 3.96, assetId: 'img1', role: 'Fin', strength: 75 },
			{ id: 'f2', shotId: 'c2', time: 4, assetId: 'img2', role: 'Début', strength: 75 },
			{ id: 'f3', shotId: 'c2', time: 4, assetId: null, role: 'first', strength: 75 },
			{ id: 'f4', shotId: 'c3', time: 8, assetId: 'img3', role: 'Transition', strength: 75 }
		],
		assets: [
			{ id: 'img1', kind: 'image', src: '/api/media/uploads/last.png' },
			{ id: 'img2', kind: 'image', src: null },
			{ id: 'img3', kind: 'image', src: '/api/media/uploads/t.png' }
		]
	};
}

test('roleKind: the first and last roles of every era, any case', () => {
	assert.equal(roleKind('first'), 'first');
	assert.equal(roleKind(' Début '), 'first');
	assert.equal(roleKind('debut'), 'first');
	assert.equal(roleKind('LAST'), 'last');
	assert.equal(roleKind('Fin'), 'last');
	assert.equal(roleKind('Transition'), null);
	assert.equal(roleKind(null), null);
});

test('shots and frames around a seam', () => {
	const doc = sampleDoc();
	assert.equal(previousShot(doc, 'c2').id, 'c1');
	assert.equal(previousShot(doc, 'c1'), null);
	assert.equal(previousShot(doc, 'nope'), null);
	assert.deepEqual(framesOf(doc, 'c2', 'first').map((f) => f.id), ['f2', 'f3']);
	assert.deepEqual(framesOf(doc, 'c1', 'last').map((f) => f.id), ['f1']);
	assert.equal(seamImage(doc, 'c1', 'last').id, 'img1');
	assert.equal(seamImage(doc, 'c2', 'first'), null);
	assert.equal(seamImage(doc, 'c3', 'first'), null);
});

test('requestBody: previous_last by default, a take and a time otherwise', () => {
	assert.deepEqual(requestBody(), { source: 'previous_last' });
	assert.deepEqual(requestBody(PREVIOUS_LAST), { source: 'previous_last' });
	assert.deepEqual(requestBody({ takeId: 't1', at: 2.5, kind: 'last' }), { source: { take_id: 't1', at: 2.5 } });
	assert.deepEqual(requestBody({ takeId: 't1', at: 'last' }), { source: { take_id: 't1', at: 'last' } });
});

test('playhead: first half gives the first frame, second half the last, time inside the take', () => {
	const clip = { start: 4, dur: 3, srcIn: 1.5 };
	assert.deepEqual(playheadPick(clip, 4.5, true), { kind: 'first', at: 2 });
	assert.deepEqual(playheadPick(clip, 6.2, true), { kind: 'last', at: 3.7 });
	assert.deepEqual(playheadPick(clip, 6.2, false), { kind: 'last', at: 2.2 });
	assert.deepEqual(playheadPick(clip, 1, true), { kind: 'first', at: 1.5 });
	assert.deepEqual(playheadPick(clip, 20, false), { kind: 'last', at: 3 });
	assert.equal(frameTime(clip, 'first'), 4);
	assert.equal(frameTime(clip, 'last'), 6.96);
});

test('normalizeSeamMedia: a library image with its item id, nothing else', () => {
	const media = normalizeSeamMedia({ kind: 'library', item_id: 'i9', url: '/api/media/uploads/seam.png', filename: 'seam.png', width: 1280, height: 720, media_type: 'image' });
	assert.deepEqual(media, { itemId: 'i9', url: '/api/media/uploads/seam.png', filename: 'seam.png', width: 1280, height: 720 });
	assert.equal(normalizeSeamMedia({ item_id: 12, url: '/u.png', media_type: 'image' }).itemId, '12');
	assert.equal(normalizeSeamMedia({ url: '/u.png', origin: { kind: 'library', itemId: 'i3' } }).itemId, 'i3');
	assert.equal(normalizeSeamMedia({ item_id: 'i1', url: '/v.mp4', media_type: 'video' }), null);
	assert.equal(normalizeSeamMedia({ item_id: 'i1', url: '' }), null);
	assert.equal(normalizeSeamMedia({ url: '/u.png' }), null);
	assert.equal(normalizeSeamMedia(null), null);
});

test('seamAsset: an image asset bound to the library item', () => {
	const a = seamAsset({ itemId: 'i9', url: '/api/media/uploads/seam.png', filename: '', width: 1280, height: 720 }, 'Seam frame');
	assert.equal(a.kind, 'image');
	assert.equal(a.name, 'Seam frame');
	assert.equal(a.src, '/api/media/uploads/seam.png');
	assert.deepEqual(a.origin, { kind: 'library', itemId: 'i9' });
	assert.equal(a.res, '1280×720');
	assert.equal(a.generated, false);
	assert.equal(seamAsset({ itemId: 'i9', url: '/x.png', filename: 'x.png', width: null, height: null }, 'n').res, null);
});

test('placeSeamFrame: adds the frame, or replaces the frames of the same role in place', () => {
	const doc = sampleDoc();
	const fresh = placeSeamFrame(doc, doc.clips[2], 'first', { id: 'new1', kind: 'image' }, () => 'fid');
	assert.deepEqual(fresh, { id: 'fid', shotId: 'c3', time: 7, assetId: 'new1', role: 'first', strength: 100 });
	assert.equal(doc.assets.at(-1).id, 'new1');
	const replaced = placeSeamFrame(doc, doc.clips[1], 'first', { id: 'new2', kind: 'image' }, () => 'unused');
	assert.equal(replaced.id, 'f2');
	assert.deepEqual(replaced, { id: 'f2', shotId: 'c2', time: 4, assetId: 'new2', role: 'first', strength: 100 });
	assert.deepEqual(framesOf(doc, 'c2', 'first').map((f) => f.id), ['f2']);
	assert.ok(!doc.frames.some((f) => f.id === 'f3'));
	const last = placeSeamFrame(doc, doc.clips[0], 'last', { id: 'new3', kind: 'image' });
	assert.deepEqual([last.id, last.time, last.role], ['f1', 3.96, 'last']);
});

test('placeSeamFrame: a frame captured in a 3D scene carries its sceneId, a later seam frame drops it', () => {
	const doc = sampleDoc();
	const captured = placeSeamFrame(doc, doc.clips[2], 'last', { id: 'cap', kind: 'image' }, () => 'fc', 's1');
	assert.deepEqual(captured, { id: 'fc', shotId: 'c3', time: 11.96, assetId: 'cap', role: 'last', strength: 100, sceneId: 's1' });
	const seam = placeSeamFrame(doc, doc.clips[2], 'last', { id: 'seam', kind: 'image' });
	assert.equal(seam.id, 'fc');
	assert.ok(!('sceneId' in seam));
	const again = placeSeamFrame(doc, doc.clips[2], 'last', { id: 'cap2', kind: 'image' }, () => 'x', 's2');
	assert.equal(again.sceneId, 's2');
});

test('placeSeamFrame: an image already in the project is placed again without a second copy of its asset', () => {
	const doc = sampleDoc();
	const picture = { id: 'kept', kind: 'image' };
	doc.assets.push(picture);
	const count = doc.assets.length;
	placeSeamFrame(doc, doc.clips[2], 'first', picture, () => 'fk', 's1');
	assert.equal(doc.assets.length, count);
	assert.equal(framesOf(doc, 'c3', 'first')[0].assetId, 'kept');
});

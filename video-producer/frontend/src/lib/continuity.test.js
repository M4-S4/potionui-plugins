import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileStem, frameStem, seamPick, seamSourceOf, takeStems } from './continuity.js';

const takeUrl = (gen, file) => `/api/media/generations/${gen}/${file}`;

function sampleDoc() {
	return {
		clips: [
			{ id: 'c1', assetId: 'gen-t1', start: 0, dur: 4 },
			{ id: 'c2', assetId: 'gen-t2', start: 4, dur: 3 },
			{ id: 'c3', assetId: 'src', start: 7, dur: 5 }
		],
		frames: [],
		assets: [
			{ id: 'gen-t1', kind: 'video', src: takeUrl('g1', 'wan_00001.mp4'), origin: { kind: 'history', generationId: 'g1', fileId: 'f1' }, generated: true },
			{ id: 'gen-t2', kind: 'video', src: takeUrl('g2', 'wan_00002.mp4'), origin: { kind: 'history', generationId: 'g2', fileId: 'f2' }, generated: true },
			{ id: 'src', kind: 'video', src: '/api/media/uploads/harbour.mp4', origin: { kind: 'library', itemId: 'u1' }, generated: false }
		]
	};
}

const takes = [
	{ id: 't1', shotId: 'c1', url: takeUrl('g1', 'wan_00001.mp4') },
	{ id: 't1b', shotId: 'c1', url: takeUrl('g3', 'wan_00003.mp4') },
	{ id: 't2', shotId: 'c2', url: takeUrl('g2', 'wan_00002.mp4') },
	{ id: 't2b', shotId: 'c2', url: takeUrl('g4', 'wan 00004.mp4') },
	{ id: 'legacy', shotId: 'c2', url: null }
];

function withFrame(doc, shotId, role, image) {
	doc.assets.push({ kind: 'image', ...image });
	doc.frames.push({ id: `f-${image.id}`, shotId, time: 0, assetId: image.id, role, strength: 100 });
	return doc;
}

test('fileStem and frameStem: the take file a frame was extracted from', () => {
	assert.equal(fileStem(takeUrl('g1', 'wan_00001.mp4')), 'wan_00001');
	assert.equal(fileStem('/api/media/generations/g/a.b.mp4?size=medium'), 'a.b');
	assert.equal(fileStem('/x/wan%2000004.mp4'), 'wan 00004');
	assert.equal(fileStem('/x/%E0%A4%A.mp4'), '%E0%A4%A');
	assert.equal(fileStem(null), '');
	assert.equal(frameStem('wan_00001-frame-last.png'), 'wan_00001');
	assert.equal(frameStem('wan_00001-frame-1.24s.png'), 'wan_00001');
	assert.equal(frameStem('wan_00001-frame-0s.PNG'), 'wan_00001');
	assert.equal(frameStem('a-frame-b-frame-1e+06s.png'), 'a-frame-b');
	assert.equal(frameStem('poster.png'), null);
	assert.equal(frameStem(undefined), null);
});

test('takeStems: every take of the shot, and its own generated asset when the takes are not loaded', () => {
	const doc = sampleDoc();
	assert.deepEqual([...takeStems(doc, doc.clips[1], takes)].sort(), ['wan 00004', 'wan_00002']);
	assert.deepEqual([...takeStems(doc, doc.clips[0], [])], ['wan_00001']);
	assert.deepEqual([...takeStems(doc, doc.clips[2], takes)], []);
});

test('seamPick: a first frame copied from the previous shot never measures the current shot', () => {
	const doc = withFrame(sampleDoc(), 'c2', 'first', { id: 'copy', name: 'wan_00001-frame-last.png', src: '/api/media/uploads/copy.png' });
	const pick = seamPick(doc, 1, takes);
	assert.deepEqual(pick, { last: null, first: null });
	assert.equal(seamSourceOf(pick), 'thumbs');
	assert.deepEqual(seamPick(doc, 1, []), { last: null, first: null });
});

test('seamPick: the previous shot’s own last frame, and the same asset reused as first frame is ignored', () => {
	const doc = withFrame(sampleDoc(), 'c1', 'last', { id: 'end1', name: 'wan_00003-frame-3.96s.png', src: '/api/media/uploads/end1.png' });
	doc.frames.push({ id: 'f-shared', shotId: 'c2', time: 4, assetId: 'end1', role: 'first', strength: 100 });
	withFrame(doc, 'c2', 'Début', { id: 'same-src', name: 'wan_00002-frame-0s.png', src: '/api/media/uploads/end1.png' });
	const pick = seamPick(doc, 1, takes);
	assert.equal(pick.last.id, 'end1');
	assert.equal(pick.first, null);
	assert.equal(seamSourceOf(pick), 'last');
});

test('seamPick: a first frame extracted from a take of the shot itself measures it', () => {
	const doc = withFrame(sampleDoc(), 'c2', 'first', { id: 'copy', name: 'wan_00001-frame-last.png', src: '/api/media/uploads/copy.png' });
	withFrame(doc, 'c2', 'first', { id: 'head2', name: 'wan 00004-frame-0.4s.png', src: '/api/media/uploads/head2.png' });
	assert.equal(seamSourceOf(seamPick(doc, 1, takes)), 'first');
	assert.equal(seamPick(doc, 1, takes).first.id, 'head2');
	withFrame(doc, 'c1', 'Fin', { id: 'end1', name: 'wan_00001-frame-3.96s.png', src: '/api/media/uploads/end1.png' });
	const pick = seamPick(doc, 1, takes);
	assert.deepEqual([pick.last.id, pick.first.id], ['end1', 'head2']);
	assert.equal(seamSourceOf(pick), 'frames');
});

test('seamPick: imported images, frames without a file and frames of another take are not seam images', () => {
	const doc = withFrame(sampleDoc(), 'c1', 'last', { id: 'ref', name: 'reference.png', src: '/api/media/uploads/ref.png' });
	withFrame(doc, 'c1', 'last', { id: 'nofile', name: 'wan_00001-frame-last.png', src: null });
	withFrame(doc, 'c2', 'first', { id: 'other', name: 'wan_00009-frame-0s.png', src: '/api/media/uploads/other.png' });
	doc.frames.push({ id: 'f-none', shotId: 'c2', time: 4, assetId: null, role: 'first', strength: 100 });
	assert.deepEqual(seamPick(doc, 1, takes), { last: null, first: null });
});

test('seamPick: a take file shared by both shots counts as the previous shot’s', () => {
	const shared = [...takes, { id: 't2c', shotId: 'c2', url: takeUrl('g1', 'wan_00001.mp4') }];
	const doc = withFrame(sampleDoc(), 'c2', 'first', { id: 'head', name: 'wan_00001-frame-0s.png', src: '/api/media/uploads/head.png' });
	assert.equal(seamPick(doc, 1, shared).first, null);
});

test('seamPick: no seam before the first shot or past the last one', () => {
	const doc = sampleDoc();
	assert.equal(seamPick(doc, 0, takes), null);
	assert.equal(seamPick(doc, 3, takes), null);
	assert.equal(seamSourceOf(null), 'thumbs');
	assert.deepEqual(seamPick(doc, 2, takes), { last: null, first: null });
});

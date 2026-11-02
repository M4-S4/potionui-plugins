import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mediaFailure, mediaFormat } from './playable.js';

test('mediaFormat: the extension of the name or of the address, upper case, null when there is none', () => {
	assert.equal(mediaFormat('clip.mov'), 'MOV');
	assert.equal(mediaFormat('Interview.ProRes.MOV'), 'MOV');
	assert.equal(mediaFormat('Shot 2 · Draft A', '/api/media/uploads/take.mp4?size=medium'), 'MP4');
	assert.equal(mediaFormat(null, '/api/media/uploads/a.webm#t=2'), 'WEBM');
	assert.equal(mediaFormat('Shot 2 · Draft A'), null);
	assert.equal(mediaFormat('Mr. Smith'), null);
	assert.equal(mediaFormat(undefined, null, ''), null);
});

test('mediaFailure: unsupported or undecodable media, a missing file, nothing for an abort', () => {
	assert.equal(mediaFailure({ error: { code: 4 } }), 'unsupported');
	assert.equal(mediaFailure({ error: { code: 3 } }), 'unsupported');
	assert.equal(mediaFailure({ error: { code: 2 } }), 'offline');
	assert.equal(mediaFailure({ error: { code: 1 } }), null);
	assert.equal(mediaFailure({ error: null }), null);
	assert.equal(mediaFailure(null), null);
});

test('mediaFailure: a video that loads with no picture (an unsupported codec next to a playable audio track) is unsupported', () => {
	assert.equal(mediaFailure({ error: null, videoWidth: 0, videoHeight: 0 }, { video: true }), 'unsupported');
	assert.equal(mediaFailure({ error: null, videoWidth: 0, videoHeight: 0 }), null);
	assert.equal(mediaFailure({ error: null, videoWidth: 1920, videoHeight: 1080 }, { video: true }), null);
	assert.equal(mediaFailure({ error: null }, { video: true }), null);
});

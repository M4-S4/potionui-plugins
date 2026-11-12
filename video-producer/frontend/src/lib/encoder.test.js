import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LIMIT_12GB, MAX_PIXELS, imageTokens, maxPixels, videoTokens, visionTokens } from './encoder.js';

const PICTURES = [[1024, 1024], [1344, 768]];

test('the page counts the vision tokens of the text encoder as the server does', () => {
	const small = maxPixels(1, [832, 480]);
	const large = maxPixels(1, [960, 544]);
	assert.deepEqual([small, large], [399360, 522240]);
	assert.deepEqual(PICTURES.map((picture) => imageTokens(picture, small)), [361, 364]);
	assert.deepEqual(PICTURES.map((picture) => imageTokens(picture, large)), [484, 493]);
	assert.equal(videoTokens(56, [832, 480], small), 1170);
	assert.equal(videoTokens(56, [960, 544], large), 1530);
	assert.equal(visionTokens(PICTURES, [[56, [832, 480]]], small), 1895);
	assert.equal(visionTokens(PICTURES, [[56, [960, 544]]], large), 2507);
	assert.equal(visionTokens([...PICTURES, [1024, 1024]], [[56, [832, 480]]], small), 2256);
	assert.equal(imageTokens(null, small), 390);
	assert.equal(imageTokens([1024, 1024], maxPixels(0, [832, 480])), 1024);
	assert.equal(maxPixels(null, [832, 480]), MAX_PIXELS);
	assert.equal(visionTokens(PICTURES, [[56, [960, 544]]], maxPixels(0, [960, 544])), 3562);
	assert.equal(LIMIT_12GB, 2200);
});

test('a reference picture far from the 1:4 to 4:1 range is padded into it before it is counted', () => {
	const limit = maxPixels(1, [832, 480]);
	assert.equal(imageTokens([4000, 500], limit), imageTokens([4000, 1000], limit));
	assert.equal(imageTokens([300, 2000], limit), imageTokens([500, 2000], limit));
});

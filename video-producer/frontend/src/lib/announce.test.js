import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ANNOUNCE_GAP_MS, ANNOUNCE_STEP, announcer } from './announce.js';

test('announcer: speaks in steps of 10 % or on a new step, never twice within 3 s', () => {
	assert.equal(ANNOUNCE_STEP, 10);
	assert.equal(ANNOUNCE_GAP_MS, 3000);
	const voice = announcer();
	assert.deepEqual(voice.next('Assembling', 3, 0), { label: 'Assembling', value: 0 });
	assert.equal(voice.next('Assembling', 8, 1000), null);
	assert.equal(voice.next('Assembling', 14, 2000), null);
	assert.deepEqual(voice.next('Assembling', 14, 3000), { label: 'Assembling', value: 10 });
	assert.equal(voice.next('Assembling', 19, 7000), null);
	assert.deepEqual(voice.next('Mixing', 19, 8000), { label: 'Mixing', value: 10 });
	assert.equal(voice.next('Storing', 20, 9000), null);
});

test('announcer: a reset speaks again at once, and progress is clamped to 0–100', () => {
	const voice = announcer();
	assert.deepEqual(voice.next('Rendering', 250, 0), { label: 'Rendering', value: 100 });
	assert.equal(voice.next('Rendering', 99, 100), null);
	voice.reset();
	assert.deepEqual(voice.next('Rendering', -5, 200), { label: 'Rendering', value: 0 });
	assert.equal(voice.next('Rendering', Number.NaN, 4000), null);
});

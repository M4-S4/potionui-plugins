import { test } from 'node:test';
import assert from 'node:assert/strict';
import { removalMessage } from './modes.js';

const REMOVED = 'Its folder leaves the draft and the mode is removed from preset.yml.';

test('a removal that adds no lint error says only what goes away', () => {
	assert.equal(removalMessage({ allowed: true, errors: [] }), REMOVED);
	assert.equal(removalMessage(null), REMOVED);
});

test('a removal that adds lint errors names them before it is confirmed', () => {
	assert.equal(
		removalMessage({ errors: ['[ERROR] preset.yml: prompt_syntax.loop: \'loop\' is not a mode of this preset'] }),
		`${REMOVED} The lint then reports one new error, and publishing waits until it is fixed: preset.yml: prompt_syntax.loop: 'loop' is not a mode of this preset.`
	);
	assert.equal(
		removalMessage({ errors: ['[ERROR] a: 1', '[ERROR] b: 2', 'c: 3', '[ERROR] d: 4', '[ERROR] e: 5'] }),
		`${REMOVED} The lint then reports 5 new errors, and publishing waits until they are fixed: a: 1; b: 2; c: 3; and 2 more.`
	);
});

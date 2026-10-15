import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isAdmin, pageIntent } from './access.js';

test('only an ADMIN account type counts as admin', () => {
	assert.equal(isAdmin({ account_type: 'ADMIN' }), true);
	assert.equal(isAdmin({ account_type: 'USER' }), false);
	assert.equal(isAdmin({ account_type: 'admin' }), false);
	assert.equal(isAdmin(null), false);
	assert.equal(isAdmin(undefined), false);
});

test('the page intent follows the query string, a draft or a preset winning over new', () => {
	assert.deepEqual(pageIntent(''), { kind: 'list', id: null });
	assert.deepEqual(pageIntent(undefined), { kind: 'list', id: null });
	assert.deepEqual(pageIntent('?new=1'), { kind: 'new', id: null });
	assert.deepEqual(pageIntent('?new=0'), { kind: 'list', id: null });
	assert.deepEqual(pageIntent('?draft=01ABC'), { kind: 'draft', id: '01ABC' });
	assert.deepEqual(pageIntent('?preset=my-preset&new=1'), { kind: 'preset', id: 'my-preset' });
	assert.deepEqual(pageIntent('?draft=d1&preset=p1'), { kind: 'draft', id: 'd1' });
});

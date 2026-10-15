import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readToken, standaloneApi } from './hostApi.js';

function fakeFetch(payload) {
	const calls = [];
	const fetchImpl = async (url, init) => {
		calls.push([url, init]);
		return { json: async () => payload };
	};
	return { calls, fetchImpl };
}

test('the standalone api mirrors the host api: plugin prefix, bearer token, JSON body', async () => {
	const { calls, fetchImpl } = fakeFetch({ success: true, data: { ok: 1 } });
	const api = standaloneApi('preset-editor', { fetchImpl, token: () => 'tok' });

	assert.deepEqual(await api.get('/drafts'), { success: true, data: { ok: 1 } });
	await api.post('/drafts', { mode: 'copy' });
	await api.post('/drafts/x/lint');
	await api.delete('/drafts/x');

	assert.equal(api.getToken(), 'tok');
	assert.deepEqual(
		calls.map(([url, init]) => [url, init.method, init.body]),
		[
			['/api/plugins/preset-editor/drafts', 'GET', undefined],
			['/api/plugins/preset-editor/drafts', 'POST', '{"mode":"copy"}'],
			['/api/plugins/preset-editor/drafts/x/lint', 'POST', '{}'],
			['/api/plugins/preset-editor/drafts/x', 'DELETE', undefined]
		]
	);
	assert.deepEqual(calls[0][1].headers, { 'Content-Type': 'application/json', Accept: 'application/json', Authorization: 'Bearer tok' });
	assert.equal(calls[0][1].credentials, 'include');
});

test('without a token the request carries no Authorization header', async () => {
	const { calls, fetchImpl } = fakeFetch({});
	const api = standaloneApi('preset-editor', { fetchImpl, token: () => null });

	await api.get('/me');

	assert.equal(api.getToken(), null);
	assert.equal('Authorization' in calls[0][1].headers, false);
});

test('readToken reads localStorage and survives its absence', () => {
	const previous = globalThis.localStorage;
	try {
		globalThis.localStorage = { getItem: (key) => (key === 'auth_token' ? 'stored' : null) };
		assert.equal(readToken(), 'stored');
		globalThis.localStorage = {
			getItem() {
				throw new Error('blocked');
			}
		};
		assert.equal(readToken(), null);
		globalThis.localStorage = undefined;
		assert.equal(readToken(), null);
	} finally {
		globalThis.localStorage = previous;
	}
});

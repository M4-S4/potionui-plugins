import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filenameFrom, hostPluginApi } from './hostApi.js';

function fakeHost(answer = { success: true, data: {} }) {
	const calls = [];
	return {
		calls,
		json: async (path, init) => {
			calls.push(['json', path, init]);
			return answer;
		},
		fetch: async (path, init) => {
			calls.push(['fetch', path, init]);
			return new Response('{}', { status: 200 });
		}
	};
}

test('the slot api goes through the host client with the plugin prefix and JSON bodies', async () => {
	const host = fakeHost({ success: true, data: { ok: 1 } });
	const api = hostPluginApi('preset-editor', host);

	assert.deepEqual(await api.get('/drafts'), { success: true, data: { ok: 1 } });
	await api.post('/drafts', { mode: 'copy' });
	await api.post('/drafts/x/lint');
	await api.put('/drafts/x', { a: 1 });
	await api.delete('/drafts/x');

	assert.deepEqual(host.calls, [
		['json', '/api/plugins/preset-editor/drafts', { method: 'GET' }],
		['json', '/api/plugins/preset-editor/drafts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"mode":"copy"}' }],
		['json', '/api/plugins/preset-editor/drafts/x/lint', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }],
		['json', '/api/plugins/preset-editor/drafts/x', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: '{"a":1}' }],
		['json', '/api/plugins/preset-editor/drafts/x', { method: 'DELETE' }]
	]);
	assert.equal('getToken' in api, false);
});

test('raw requests go to the plugin routes or to an app path, without a timeout', async () => {
	const host = fakeHost();
	const api = hostPluginApi('preset-editor', host);

	await api.fetchRaw('/drafts/x/public/public/cover.webp');
	await api.fetchRawFromApp('/api/presets?include_uninstalled=true', { method: 'GET', headers: { Accept: 'application/json' } });

	assert.deepEqual(host.calls, [
		['fetch', '/api/plugins/preset-editor/drafts/x/public/public/cover.webp', { timeout: 0 }],
		['fetch', '/api/presets?include_uninstalled=true', { timeout: 0, method: 'GET', headers: { Accept: 'application/json' } }]
	]);
});

test('without the host client there is no api', () => {
	assert.equal(hostPluginApi('preset-editor', undefined), null);
	assert.equal(hostPluginApi('preset-editor', { json: async () => null }), null);
});

test('a refused download throws with the status and the parsed body', async () => {
	const host = {
		json: async () => null,
		fetch: async () => new Response(JSON.stringify({ detail: { error: 'not_found', message: 'No draft' } }), { status: 404 })
	};
	const api = hostPluginApi('preset-editor', host);

	await assert.rejects(api.download('/drafts/x/export'), (error) => error.status === 404 && error.body.detail.message === 'No draft');
});

test('the download name comes from Content-Disposition, else from the path', () => {
	const named = (value) => new Response('', { headers: { 'Content-Disposition': value } });

	assert.equal(filenameFrom(named('attachment; filename="copy-one-draft.zip"'), '/drafts/x/export'), 'copy-one-draft.zip');
	assert.equal(filenameFrom(named("attachment; filename*=UTF-8''caf%C3%A9.zip"), '/x'), 'café.zip');
	assert.equal(filenameFrom(new Response(''), '/presets/copy-one/export?x=1'), 'export');
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { callPlugin, downloadDraft, downloadPreset, fetchMedia, getMe, importDraft, listCatalog, normalizeError, unwrap, writeFile } from './client.js';

function fakeHostApi(handler) {
	const calls = [];
	return {
		calls,
		get: async (path) => {
			calls.push(['get', path]);
			return handler('get', path);
		}
	};
}

test('getMe asks the plugin route and unwraps the envelope', async () => {
	const api = fakeHostApi(() => ({ success: true, data: { is_admin: true, user_id: 'u1' } }));

	const result = await getMe(api);

	assert.deepEqual(api.calls, [['get', '/me']]);
	assert.deepEqual(result, { ok: true, data: { is_admin: true, user_id: 'u1' } });
});

test('an admin refusal from the core becomes a 403 even though the host drops the status', async () => {
	const api = fakeHostApi(() => ({ detail: 'Admin access required' }));

	const result = await getMe(api);

	assert.equal(result.ok, false);
	assert.deepEqual(result.error, { status: 403, code: 'forbidden', message: 'Admin access required' });
});

test('an expired session becomes a 401', () => {
	assert.equal(normalizeError({ detail: 'Could not validate credentials' }).status, 401);
	assert.equal(normalizeError({ detail: 'Token has expired' }).code, 'unauthorized');
});

test('a plugin error envelope keeps its code and message', () => {
	assert.deepEqual(normalizeError({ success: false, error: 'conflict', message: 'Id already used' }), {
		status: 409,
		code: 'conflict',
		message: 'Id already used'
	});
	assert.deepEqual(normalizeError({ error: 'precondition_failed', message: 'Stale' }), {
		status: 412,
		code: 'precondition_failed',
		message: 'Stale'
	});
});

test('a refusal carries the loader errors, and a stale write carries the current etag and content', () => {
	const refused = normalizeError({ detail: { success: false, error: 'load_failed', message: 'refused', errors: ["field 'note': unregistered field type 'text'", 3] } });
	assert.deepEqual(refused, { status: 409, code: 'load_failed', message: 'refused', errors: ["field 'note': unregistered field type 'text'"] });
	const stale = normalizeError({ detail: { success: false, error: 'precondition_failed', message: 'changed', etag: 'abc', content: 'schema: 1\n' } }, 412);
	assert.deepEqual(stale, { status: 412, code: 'precondition_failed', message: 'changed', etag: 'abc', content: 'schema: 1\n' });
	assert.equal('errors' in normalizeError({ error: 'conflict', message: 'x' }), false);
});

test('a validation error from FastAPI lists the field messages', () => {
	const error = normalizeError({ detail: [{ msg: 'field required' }, { msg: 'value is not a valid integer' }, 'junk'] });

	assert.deepEqual(error, { status: 422, code: 'invalid_request', message: 'field required; value is not a valid integer' });
});

test('an unknown status gets a default message and code', () => {
	assert.deepEqual(normalizeError({}, 500), {
		status: 500,
		code: 'internal_error',
		message: 'The server could not complete the request'
	});
	assert.deepEqual(normalizeError('nonsense'), { status: 0, code: 'error', message: 'Request failed' });
});

test('unwrap rejects anything that is not a success envelope', () => {
	assert.deepEqual(unwrap({ success: true, data: [1] }), { ok: true, data: [1] });
	assert.equal(unwrap(null).error.code, 'invalid_response');
	assert.equal(unwrap({ success: false, error: 'not_found', message: 'Gone' }).error.status, 404);
});

test('callPlugin reports a missing host api, a network failure and a non-JSON body', async () => {
	assert.equal((await callPlugin(null, 'get', '/me')).error.code, 'no_api');
	const offline = fakeHostApi(() => {
		throw new TypeError('Failed to fetch');
	});
	assert.deepEqual((await callPlugin(offline, 'get', '/me')).error, {
		status: 0,
		code: 'network_error',
		message: 'Could not reach the server'
	});
	const html = fakeHostApi(() => {
		throw new SyntaxError('Unexpected token <');
	});
	assert.equal((await callPlugin(html, 'get', '/me')).error.code, 'invalid_response');
});

function rawApi(respond) {
	const calls = [];
	return {
		calls,
		fetchRawFromApp: async (path, init) => {
			calls.push([path, init]);
			return respond(path, init);
		},
		fetchRaw: async (path, init) => {
			calls.push([path, init]);
			return respond(path, init);
		}
	};
}

test('core calls go through the host client, with a JSON body, a form or extra headers', async () => {
	const api = rawApi(() => new Response(JSON.stringify({ success: true, data: [1] }), { status: 200 }));
	const form = new FormData();

	assert.deepEqual(await listCatalog(api), { ok: true, data: [1] });
	await writeFile(api, 'D', 'modes/txt2img/form.yml', 'fields: []\n', 'etag-1');
	await importDraft(api, form);

	assert.deepEqual(api.calls[0], ['/api/presets?include_uninstalled=true', { method: 'GET', headers: { Accept: 'application/json' } }]);
	assert.deepEqual(api.calls[1], [
		'/api/plugins/preset-editor/drafts/D/files/modes/txt2img/form.yml',
		{ method: 'PUT', headers: { Accept: 'application/json', 'If-Match': 'etag-1', 'Content-Type': 'application/json' }, body: JSON.stringify({ content: 'fields: []\n' }) }
	]);
	assert.equal(api.calls[2][1].body, form);
	assert.equal('Content-Type' in api.calls[2][1].headers, false);
});

test('a core refusal keeps its status, and a page without the host client says so', async () => {
	const api = rawApi(() => new Response(JSON.stringify({ detail: { error: 'precondition_failed', message: 'changed', etag: 'e2' } }), { status: 412 }));

	const result = await writeFile(api, 'D', 'preset.yml', 'x', 'e1');

	assert.deepEqual(result, { ok: false, error: { status: 412, code: 'precondition_failed', message: 'changed', etag: 'e2' } });
	assert.equal((await listCatalog({ get: async () => null })).error.code, 'no_api');
});

test('draft media is read as a blob through the plugin routes', async () => {
	const api = rawApi((path) =>
		path.endsWith('missing.webp')
			? new Response(JSON.stringify({ detail: { error: 'not_found', message: 'no media file' } }), { status: 404 })
			: new Response(new Blob(['RIFF']), { status: 200 })
	);

	const found = await fetchMedia(api, 'D', 'public/examples/a b.webp');
	const missing = await fetchMedia(api, 'D', 'public/missing.webp');

	assert.equal(api.calls[0][0], '/drafts/D/public/public/examples/a%20b.webp');
	assert.equal(found.ok, true);
	assert.equal(await found.data.text(), 'RIFF');
	assert.deepEqual(missing, { ok: false, error: { status: 404, code: 'not_found', message: 'no media file' } });
});

test('zip downloads go through the host download and report its refusal', async () => {
	const asked = [];
	const api = {
		download: async (path, filename) => {
			asked.push([path, filename]);
			if (path.startsWith('/presets/')) {
				const error = new Error('Request failed with status 409');
				error.status = 409;
				error.body = { detail: { error: 'not_local', message: 'only a local preset' } };
				throw error;
			}
		}
	};

	assert.deepEqual(await downloadDraft(api, 'D'), { ok: true, data: null });
	assert.deepEqual(await downloadPreset(api, 'market one'), { ok: false, error: { status: 409, code: 'not_local', message: 'only a local preset' } });
	assert.deepEqual(asked, [['/drafts/D/export', undefined], ['/presets/market%20one/export', undefined]]);
	assert.equal((await downloadDraft({}, 'D')).error.code, 'no_api');
});

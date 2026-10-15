import { test } from 'node:test';
import assert from 'node:assert/strict';
import { callPlugin, getMe, normalizeError, unwrap } from './client.js';

function fakeHostApi(handler) {
	const calls = [];
	return {
		calls,
		getToken: () => 'secret-token',
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

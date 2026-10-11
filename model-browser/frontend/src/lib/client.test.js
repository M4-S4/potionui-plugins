import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchHealth, healthLabel } from './client.js';

/** Fake host `api`: records the requested paths and answers (or throws) from `handler`. */
function fakeApi(handler) {
	const calls = [];
	return {
		calls,
		get: async (path) => {
			calls.push(path);
			return handler(path);
		}
	};
}

test('fetchHealth reads status and version from the success envelope', async () => {
	// Same shape as backend/api.py's GET /health.
	const api = fakeApi(() => ({ success: true, data: { status: 'ok', plugin: 'model-browser', version: '0.1.0' } }));
	assert.deepEqual(await fetchHealth(api), { ok: true, version: '0.1.0' });
	assert.deepEqual(api.calls, ['/health']);
});

test('fetchHealth accepts a flat body', async () => {
	const api = fakeApi(() => ({ status: 'ok', version: '0.1.0' }));
	assert.deepEqual(await fetchHealth(api), { ok: true, version: '0.1.0' });
});

test('fetchHealth accepts a success envelope without a status field, and omits a missing version', async () => {
	assert.deepEqual(await fetchHealth(fakeApi(() => ({ success: true, data: {} }))), { ok: true });
	assert.deepEqual(await fetchHealth(fakeApi(() => ({ success: true, data: { ok: true } }))), { ok: true });
});

test('fetchHealth ignores a version that is not a string', async () => {
	const api = fakeApi(() => ({ success: true, data: { status: 'ok', version: 1 } }));
	assert.deepEqual(await fetchHealth(api), { ok: true });
});

test('fetchHealth reports the message of a failure envelope', async () => {
	const withMessage = fakeApi(() => ({ success: false, error: 'boom', message: 'Backend exploded' }));
	assert.deepEqual(await fetchHealth(withMessage), { ok: false, error: 'Backend exploded' });

	const codeOnly = fakeApi(() => ({ success: false, error: 'boom' }));
	assert.deepEqual(await fetchHealth(codeOnly), { ok: false, error: 'boom' });

	const bare = fakeApi(() => ({ success: false }));
	assert.deepEqual(await fetchHealth(bare), { ok: false, error: 'Request failed' });
});

test('fetchHealth reports FastAPI error bodies', async () => {
	const text = fakeApi(() => ({ detail: 'Not Found' }));
	assert.deepEqual(await fetchHealth(text), { ok: false, error: 'Not Found' });

	const nested = fakeApi(() => ({ detail: { success: false, error: 'plugin_disabled', message: 'Plugin is disabled' } }));
	assert.deepEqual(await fetchHealth(nested), { ok: false, error: 'Plugin is disabled' });
});

test('fetchHealth reports a status other than ok', async () => {
	const api = fakeApi(() => ({ success: true, data: { status: 'degraded', version: '0.1.0' } }));
	assert.deepEqual(await fetchHealth(api), { ok: false, error: 'Backend status: degraded' });
});

test('fetchHealth turns a rejected request into an error result', async () => {
	const api = fakeApi(() => {
		throw new TypeError('Failed to fetch');
	});
	assert.deepEqual(await fetchHealth(api), { ok: false, error: 'Failed to fetch' });
});

test('fetchHealth explains a body that is not JSON', async () => {
	const api = fakeApi(() => {
		throw new SyntaxError('Unexpected token I in JSON at position 0');
	});
	const result = await fetchHealth(api);
	assert.equal(result.ok, false);
	assert.match(result.error, /not valid JSON/);
});

test('fetchHealth copes with rejections that are not Error objects', async () => {
	const text = fakeApi(() => {
		throw 'offline';
	});
	assert.deepEqual(await fetchHealth(text), { ok: false, error: 'offline' });

	const nothing = fakeApi(() => {
		throw undefined;
	});
	assert.deepEqual(await fetchHealth(nothing), { ok: false, error: 'Request failed' });
});

test('fetchHealth rejects bodies it cannot interpret', async () => {
	for (const body of [null, undefined, 'ok', 42, [], {}, { ok: false }]) {
		const result = await fetchHealth(fakeApi(() => body));
		assert.deepEqual(result, { ok: false, error: 'Unexpected response from /health' }, JSON.stringify(body));
	}
});

test('fetchHealth does not throw when there is no api object', async () => {
	const result = await fetchHealth(undefined);
	assert.equal(result.ok, false);
	assert.equal(typeof result.error, 'string');
});

test('healthLabel covers checking, healthy and failed states', () => {
	assert.equal(healthLabel(null), 'Backend: checking\u2026');
	assert.equal(healthLabel({ ok: true, version: '0.1.0' }), 'Backend: ok (v0.1.0)');
	assert.equal(healthLabel({ ok: true }), 'Backend: ok');
	assert.equal(healthLabel({ ok: false, error: 'Not Found' }), 'Backend error: Not Found');
	assert.equal(healthLabel({ ok: false }), 'Backend error: unknown error');
});

test('healthLabel does not double the v of a version that already has one', () => {
	assert.equal(healthLabel({ ok: true, version: 'v0.1.0' }), 'Backend: ok (v0.1.0)');
});

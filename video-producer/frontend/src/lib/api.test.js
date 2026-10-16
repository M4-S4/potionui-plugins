import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createClient, normalizeError, normalizeMe, normalizeMedia, normalizeOrigin, normalizeProject, normalizeProjectSummary, normalizeVersion } from './api.js';

test('normalizeError: the plugin error envelope keeps its code, message and data', () => {
	const conflict = { detail: { success: false, error: 'version_conflict', message: 'stale', data: { version: 7 } } };
	assert.deepEqual(normalizeError(conflict, 409), { status: 409, code: 'version_conflict', message: 'stale', data: { version: 7 } });
	assert.deepEqual(normalizeError({ detail: { success: false, error: 'invalid_doc', message: 'clips.0.dur: must be a number' } }, 422), {
		status: 422,
		code: 'invalid_doc',
		message: 'clips.0.dur: must be a number',
		data: null
	});
	assert.deepEqual(normalizeError({ detail: 'Not Found' }, 404), { status: 404, code: 'not_found', message: 'Not Found', data: null });
	assert.deepEqual(normalizeError(null, 0), { status: 0, code: 'unknown', message: '', data: null });
});

test('normalizeMe: last_project_id becomes lastProjectId, null when absent or empty', () => {
	assert.equal(normalizeMe({ last_project_id: '01JABC' }).lastProjectId, '01JABC');
	assert.equal(normalizeMe({ last_project_id: '' }).lastProjectId, null);
	assert.equal(normalizeMe({}).lastProjectId, null);
	assert.equal(normalizeMe(null).lastProjectId, null);
});

test('project payloads: summaries, full projects and versions are camelCased and checked', () => {
	assert.deepEqual(normalizeProjectSummary({ id: 'p1', name: 'Dawn', version: 3, created_at: '2026-10-16T10:00:00Z', updated_at: '2026-10-16T11:00:00Z', shots: 5, duration_s: 25 }), {
		id: 'p1',
		name: 'Dawn',
		version: 3,
		createdAt: '2026-10-16T10:00:00Z',
		updatedAt: '2026-10-16T11:00:00Z',
		shots: 5,
		duration: 25
	});
	assert.equal(normalizeProjectSummary({ name: 'no id' }), null);
	const doc = { name: 'Dawn', clips: [] };
	assert.deepEqual(normalizeProject({ id: 'p1', user_id: 'u', name: 'Dawn', version: 1, doc, created_at: 'a', updated_at: 'b' }), {
		id: 'p1',
		name: 'Dawn',
		version: 1,
		doc,
		createdAt: 'a',
		updatedAt: 'b',
		unchanged: false
	});
	assert.equal(normalizeProject({ id: 'p1', version: 4, unchanged: true }).doc, null);
	assert.equal(normalizeProject({ id: 'p1', version: 4, unchanged: true }).unchanged, true);
	assert.deepEqual(normalizeVersion({ id: 'v9', version: 9, label: null, source_version: 4, created_at: 'c', shots: 2 }), {
		id: 'v9',
		version: 9,
		label: null,
		sourceVersion: 4,
		createdAt: 'c',
		shots: 2
	});
	assert.equal(normalizeVersion({ id: 'v2', version: 2 }).sourceVersion, null);
	assert.equal(normalizeVersion({ id: 'v' }), null);
});

test('media payloads: only the two picker origins and three media types pass', () => {
	assert.deepEqual(normalizeOrigin({ kind: 'history', generationId: 'g1', fileId: 'f3', extra: true }), { kind: 'history', generationId: 'g1', fileId: 'f3' });
	assert.deepEqual(normalizeOrigin({ kind: 'history', generationId: 'g1', fileId: 3 }), { kind: 'history', generationId: 'g1', fileId: 3 });
	assert.equal(normalizeOrigin({ kind: 'history', generationId: 'g1', fileId: '' }), null);
	assert.deepEqual(normalizeOrigin({ kind: 'library', itemId: 'i1' }), { kind: 'library', itemId: 'i1' });
	assert.equal(normalizeOrigin({ kind: 'history', generationId: 'g1', fileId: NaN }), null);
	assert.equal(normalizeOrigin({ kind: 'upload' }), null);
	const origin = { kind: 'library', itemId: 'i1' };
	assert.deepEqual(normalizeMedia({ kind: 'library', media_type: 'video', url: '/api/media/uploads/a.mp4', filename: 'a.mp4', origin }), {
		kind: 'library',
		mediaType: 'video',
		url: '/api/media/uploads/a.mp4',
		filename: 'a.mp4',
		origin
	});
	assert.equal(normalizeMedia({ kind: 'library', media_type: 'mesh', url: '/x', filename: 'x.glb', origin }), null);
	assert.equal(normalizeMedia({ kind: 'library', media_type: 'image', url: '', origin }), null);
});

function hostApi(responses) {
	const calls = [];
	return {
		calls,
		async request(method, path, data) {
			calls.push([method, path, data]);
			const next = responses.shift();
			if (next instanceof Error) throw next;
			return next;
		}
	};
}

function httpError(status, body) {
	return Object.assign(new Error('failed'), { status, body, detail: body?.detail });
}

test('client: routes, bodies and envelopes of the project and media calls', async () => {
	const api = hostApi([
		{ success: true, data: { projects: [{ id: 'p1', name: 'A', version: 2, shots: 1, duration_s: 4 }, { bad: true }] } },
		{ success: true, data: { project: { id: 'p2', version: 1, doc: { name: 'B' } } } },
		{ success: true, data: { project: { id: 'p2', version: 2, updated_at: 'u' } } },
		httpError(409, { detail: { success: false, error: 'version_conflict', message: 'stale', data: { version: 5 } } }),
		{ success: true, data: { versions: [{ id: 'v1', version: 1, shots: 0 }] } },
		{ success: true, data: { project: { id: 'p2', version: 3, doc: { name: 'B' } } } },
		{ success: true, data: { media: { kind: 'history', media_type: 'image', url: '/api/media/generations/g/f.png', filename: 'f.png', origin: { kind: 'history', generationId: 'g', fileId: 1 } } } },
		{ success: true, data: { locale: 'fr', last_project_id: null } },
		{ success: true, data: { deleted: 'p2' } },
		httpError(404, { detail: 'Not Found' })
	]);
	const client = createClient(api);
	const listed = await client.listProjects();
	assert.deepEqual(listed.data.map((p) => p.id), ['p1']);
	assert.equal((await client.createProject({ name: 'B' }, 'B')).data.id, 'p2');
	assert.equal((await client.saveProject('p2', { name: 'B' }, 1)).data.version, 2);
	const conflict = await client.saveProject('p2', { name: 'B' }, 1);
	assert.equal(conflict.ok, false);
	assert.deepEqual([conflict.error.status, conflict.error.code, conflict.error.data], [409, 'version_conflict', { version: 5 }]);
	assert.equal((await client.listVersions('p2')).data[0].version, 1);
	assert.equal((await client.restoreVersion('p2', 1)).data.version, 3);
	assert.equal((await client.resolveMedia({ kind: 'history', generationId: 'g', fileId: 1 })).data.mediaType, 'image');
	assert.equal((await client.saveLastProject(null)).ok, true);
	assert.deepEqual((await client.deleteProject('p2')).data, { deleted: 'p2' });
	const missing = await client.getProject('gone');
	assert.deepEqual([missing.ok, missing.error.status, missing.error.code], [false, 404, 'not_found']);
	assert.deepEqual(api.calls, [
		['GET', '/projects', undefined],
		['POST', '/projects', { doc: { name: 'B' }, name: 'B' }],
		['PUT', '/projects/p2', { doc: { name: 'B' }, version: 1 }],
		['PUT', '/projects/p2', { doc: { name: 'B' }, version: 1 }],
		['GET', '/projects/p2/versions', undefined],
		['POST', '/projects/p2/versions/1/restore', {}],
		['POST', '/media/resolve', { origin: { kind: 'history', generationId: 'g', fileId: 1 } }],
		['PUT', '/me', { last_project_id: null }],
		['DELETE', '/projects/p2', undefined],
		['GET', '/projects/gone', undefined]
	]);
});

test('client: hosts without request fall back to get/post/put/delete', async () => {
	const seen = [];
	const api = {
		get: async (path) => (seen.push(['get', path]), { success: true, data: { projects: [] } }),
		put: async (path, body) => (seen.push(['put', path, body]), { detail: { success: false, error: 'invalid_doc', message: 'x' } })
	};
	const client = createClient(api);
	assert.deepEqual((await client.listProjects()).data, []);
	const saved = await client.saveProject('p', {}, 1);
	assert.equal(saved.error.code, 'invalid_doc');
	assert.equal((await createClient({}).listProjects()).error.code, 'no_api');
	assert.deepEqual(seen, [
		['get', '/projects'],
		['put', '/projects/p', { doc: {}, version: 1 }]
	]);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createClient, downloadFrom, fetchBytes, normalizeError, normalizeMe, normalizeMedia, normalizeOrigin, normalizeProject, normalizeProjectSummary, normalizeSavedMedia, normalizeSceneFile, normalizeSceneJob, normalizeVersion, upload } from './api.js';

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

test('normalizeMe: ffmpeg is true, false, or null when the server does not say', () => {
	assert.equal(normalizeMe({ ffmpeg: true }).ffmpeg, true);
	assert.equal(normalizeMe({ ffmpeg: false }).ffmpeg, false);
	assert.equal(normalizeMe({ ffmpeg: 'yes' }).ffmpeg, null);
	assert.equal(normalizeMe({}).ffmpeg, null);
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

test('client: export and seam frame routes, bodies and normalized payloads', async () => {
	const job = { id: 'j1', project_id: 'p1', format: 'web', resolution: '720p', status: 'queued', progress: 0, step: null, file: null, media: null, error: null, created_at: 'c', finished_at: null };
	const api = hostApi([
		{ success: true, data: { job } },
		{ success: true, data: { job: { ...job, status: 'running', progress: 42, step: 'mix' } } },
		{ success: true, data: { jobs: [job, { nope: true }] } },
		{ success: true, data: { job: { ...job, status: 'cancelled' } } },
		{ success: true, data: { deleted: 'j1' } },
		httpError(409, { detail: { success: false, error: 'ffmpeg_unavailable', message: 'no ffmpeg' } }),
		{ success: true, data: { media: { kind: 'library', item_id: 'i5', url: '/api/media/uploads/s.png', filename: 's.png', width: 640, height: 360, media_type: 'image' } } },
		httpError(409, { detail: { success: false, error: 'no_previous_take', message: 'none' } })
	]);
	const client = createClient(api);
	assert.equal((await client.exportVideo('p1', { format: 'web', resolution: '720p' })).data.status, 'queued');
	const polled = await client.exportJob('j1');
	assert.deepEqual([polled.data.status, polled.data.progress, polled.data.step], ['running', 42, 'mix']);
	assert.deepEqual((await client.listExports('p1')).data.map((j) => j.id), ['j1']);
	assert.equal((await client.cancelExport('j1')).data.status, 'cancelled');
	assert.deepEqual(await client.cancelExport('j1'), { ok: true, data: null });
	const refused = await client.exportVideo('p1', { format: 'social', resolution: '1080p' });
	assert.deepEqual([refused.ok, refused.error.status, refused.error.code], [false, 409, 'ffmpeg_unavailable']);
	assert.deepEqual((await client.seamFrame('p1', 'c2', 'previous_last')).data, { itemId: 'i5', url: '/api/media/uploads/s.png', filename: 's.png', width: 640, height: 360 });
	const none = await client.seamFrame('p1', 'c 2', { takeId: 't1', at: 1.5 });
	assert.equal(none.error.code, 'no_previous_take');
	assert.deepEqual(api.calls, [
		['POST', '/projects/p1/exports/video', { format: 'web', resolution: '720p' }],
		['GET', '/exports/j1', undefined],
		['GET', '/projects/p1/exports', undefined],
		['DELETE', '/exports/j1', undefined],
		['DELETE', '/exports/j1', undefined],
		['POST', '/projects/p1/exports/video', { format: 'social', resolution: '1080p' }],
		['POST', '/projects/p1/shots/c2/seam-frame', { source: 'previous_last' }],
		['POST', '/projects/p1/shots/c%202/seam-frame', { source: { take_id: 't1', at: 1.5 } }]
	]);
});

test('downloadFrom: the host download first, its HTTP errors normalized', async () => {
	const asked = [];
	const ok = await downloadFrom({ download: async (path, name) => asked.push([path, name]) }, '/projects/p1/exports/edl', 'Aube.edl', () => assert.fail('no fallback'));
	assert.deepEqual(ok, { ok: true, data: { filename: 'Aube.edl' } });
	assert.deepEqual(asked, [['/projects/p1/exports/edl', 'Aube.edl']]);
	const failed = await downloadFrom({ download: async () => Promise.reject(httpError(409, { detail: { success: false, error: 'not_ready', message: 'wait' } })) }, '/exports/j1/file', 'a.mp4');
	assert.deepEqual([failed.ok, failed.error.status, failed.error.code], [false, 409, 'not_ready']);
	const offline = await downloadFrom({ download: async () => Promise.reject(new TypeError('Failed to fetch')) }, '/x', 'x');
	assert.equal(offline.error.code, 'network_error');
	assert.equal((await downloadFrom({}, '/x', 'x')).error.code, 'no_api');
});

test('downloadFrom: without host download, fetchRaw and a Blob saved under the best name', async () => {
	const saved = [];
	const save = (name, blob) => saved.push([name, blob]);
	const response = (body, init) => new Response(body, init);
	const named = await downloadFrom({ fetchRaw: async () => response('EDL', { status: 200, headers: { 'Content-Disposition': `attachment; filename="Aube.edl"; filename*=UTF-8''Aube%20%C3%A9t%C3%A9.edl` } }) }, '/projects/p1/exports/edl', null, save);
	assert.deepEqual(named, { ok: true, data: { filename: 'Aube été.edl' } });
	assert.equal(await saved[0][1].text(), 'EDL');
	const given = await downloadFrom({ fetchRaw: async () => response('X', { status: 200 }) }, '/exports/j1/file', 'Aube_720p.mp4', save);
	assert.equal(given.data.filename, 'Aube_720p.mp4');
	const bare = await downloadFrom({ fetchRaw: async () => response('Y', { status: 200 }) }, '/projects/p1/exports/srt?media=name', null, save);
	assert.equal(bare.data.filename, 'srt');
	const refused = await downloadFrom({ fetchRaw: async () => response(JSON.stringify({ detail: { success: false, error: 'project_not_found', message: 'gone' } }), { status: 404 }) }, '/projects/p9/exports/otio', 'x.otio', save);
	assert.deepEqual([refused.ok, refused.error.status, refused.error.code], [false, 404, 'project_not_found']);
	const broken = await downloadFrom({ fetchRaw: async () => Promise.reject(new TypeError('offline')) }, '/x', 'x', save);
	assert.equal(broken.error.code, 'network_error');
	assert.equal(saved.length, 3);
});

test('scene payloads: jobs, stored files and saved media are checked and camelCased', () => {
	assert.deepEqual(normalizeSceneJob({ id: 'j1', sceneId: 's1', status: 'running', progress: 140, error: null, fileId: null, count: null, view: null }), {
		id: 'j1',
		sceneId: 's1',
		status: 'running',
		progress: 100,
		error: null,
		fileId: null,
		count: null,
		view: null
	});
	const done = normalizeSceneJob({ id: 7, scene_id: 's2', status: 'done', progress: 100, file_id: 'f9', count: 120000, view: { fov: 55, aspect: 1.5, depth: 4 } });
	assert.deepEqual([done.id, done.sceneId, done.fileId, done.count, done.view], ['7', 's2', 'f9', 120000, { fov: 55, aspect: 1.5, depth: 4 }]);
	assert.equal(normalizeSceneJob({ id: 'j', status: 'weird', view: { fov: 0, aspect: 1, depth: 1 } }).status, 'queued');
	assert.equal(normalizeSceneJob({ id: 'j', status: 'failed', error: { code: 'quota_exceeded' } }).error, 'quota_exceeded');
	assert.equal(normalizeSceneJob({ status: 'done' }), null);
	assert.deepEqual(normalizeSceneFile({ id: 'f1', format: 'spz', size: 1024, view: null }), { id: 'f1', format: 'spz', size: 1024, view: null });
	assert.equal(normalizeSceneFile({ id: 'f1', format: 'obj' }).format, null);
	const media = { kind: 'library', item_id: 'i3', media_type: 'video', url: '/api/media/uploads/r.mp4', filename: 'r.mp4', width: 1920, height: 1056 };
	assert.deepEqual(normalizeSavedMedia(media, 'video'), { itemId: 'i3', url: '/api/media/uploads/r.mp4', filename: 'r.mp4', width: 1920, height: 1056 });
	assert.equal(normalizeSavedMedia(media, 'image'), null);
	assert.equal(normalizeSavedMedia({ ...media, item_id: null, origin: { itemId: 'i4' } }, 'video').itemId, 'i4');
	assert.equal(normalizeSavedMedia({ url: '/x.png' }, 'image'), null);
});

test('client: scene, capture and render routes with their bodies', async () => {
	const job = { id: 'j1', sceneId: 's1', status: 'queued', progress: 0, error: null, fileId: null, count: null, view: null };
	const media = (type, name) => ({ kind: 'library', item_id: 'i1', media_type: type, url: `/api/media/uploads/${name}`, filename: name, width: 1920, height: 1080 });
	const api = hostApi([
		{ success: true, data: { job } },
		{ success: true, data: { jobs: [{ ...job, status: 'done', fileId: 'f1', count: 10 }, { bad: true }] } },
		{ success: true, data: { job: { ...job, status: 'cancelled' } } },
		{ success: true, data: { media: media('image', 'c.png') } },
		{ success: true, data: { render: { id: 'r1' } } },
		{ success: true, data: { received: 2 } },
		{ success: true, data: { media: media('video', 'r.mp4') } },
		{ success: true, data: {} },
		httpError(409, { detail: { success: false, error: 'quota_exceeded', message: 'no minutes' } })
	]);
	const client = createClient(api);
	assert.equal((await client.sceneFromImage('p1', { sceneId: 's1', assetId: 'a1', time: 2.5, name: 'Harbour' })).data.status, 'queued');
	assert.deepEqual((await client.sceneJobs('p1')).data.map((j) => [j.id, j.status, j.fileId]), [['j1', 'done', 'f1']]);
	assert.equal((await client.cancelSceneJob('p1', 'j1')).data.status, 'cancelled');
	assert.equal((await client.capture('p1', 'data:image/png;base64,AAA', 'Capture')).data.filename, 'c.png');
	assert.deepEqual((await client.createRender('p1', { width: 1920, height: 1056, fps: 24, frames: 48, name: 'Orbit' })).data, { id: 'r1' });
	assert.deepEqual((await client.renderFrames('p1', 'r1', 0, ['data:image/jpeg;base64,A', 'data:image/jpeg;base64,B'])).data, { received: 2 });
	assert.equal((await client.finishRender('p1', 'r1')).data.url, '/api/media/uploads/r.mp4');
	assert.equal((await client.deleteRender('p1', 'r1')).ok, true);
	const refused = await client.sceneFromImage('p1', { sceneId: 's2', assetId: 'a2', time: null, name: 'Still' });
	assert.deepEqual([refused.ok, refused.error.status, refused.error.code], [false, 409, 'quota_exceeded']);
	assert.deepEqual(api.calls, [
		['POST', '/projects/p1/scenes/from-image', { sceneId: 's1', assetId: 'a1', time: 2.5, name: 'Harbour' }],
		['GET', '/projects/p1/scenes/jobs', undefined],
		['POST', '/projects/p1/scenes/jobs/j1/cancel', {}],
		['POST', '/projects/p1/captures', { png: 'data:image/png;base64,AAA', name: 'Capture' }],
		['POST', '/projects/p1/renders', { width: 1920, height: 1056, fps: 24, frames: 48, name: 'Orbit' }],
		['POST', '/projects/p1/renders/r1/frames', { start: 0, images: ['data:image/jpeg;base64,A', 'data:image/jpeg;base64,B'] }],
		['POST', '/projects/p1/renders/r1/finish', {}],
		['DELETE', '/projects/p1/renders/r1', undefined],
		['POST', '/projects/p1/scenes/from-image', { sceneId: 's2', assetId: 'a2', time: null, name: 'Still' }]
	]);
});

test('client: a scene file goes up as multipart through fetchRaw and comes back as bytes', async () => {
	const seen = [];
	const api = {
		fetchRaw: async (path, init) => {
			seen.push([path, init.method, init.body instanceof FormData ? [...init.body.keys()] : null, init.headers]);
			if (init.method === 'POST') return new Response(JSON.stringify({ success: true, data: { file: { id: 'f1', format: 'glb', size: 4, view: null } } }), { status: 200 });
			if (path.endsWith('/gone')) return new Response(JSON.stringify({ detail: { success: false, error: 'file_not_found', message: 'gone' } }), { status: 404 });
			return new Response(new Uint8Array([1, 2, 3]), { status: 200 });
		}
	};
	const client = createClient(api);
	const file = new File([new Uint8Array([0, 1, 2, 3])], 'set.glb');
	assert.deepEqual((await client.uploadSceneFile('p1', file, 'glb')).data, { id: 'f1', format: 'glb', size: 4, view: null });
	const bytes = await client.sceneFile('p1', 'f1');
	assert.deepEqual([...new Uint8Array(bytes.data)], [1, 2, 3]);
	const missing = await client.sceneFile('p1', 'gone');
	assert.deepEqual([missing.ok, missing.error.status, missing.error.code], [false, 404, 'file_not_found']);
	assert.deepEqual(seen, [
		['/projects/p1/scene-files', 'POST', ['file', 'kind'], undefined],
		['/projects/p1/scene-files/f1', 'GET', null, undefined],
		['/projects/p1/scene-files/gone', 'GET', null, undefined]
	]);
	const tooBig = await upload({ fetchRaw: async () => new Response(JSON.stringify({ detail: 'Request Entity Too Large' }), { status: 413 }) }, '/x', new FormData());
	assert.deepEqual([tooBig.ok, tooBig.error.status], [false, 413]);
	const fallback = await upload({ uploadFile: async (path, form) => ({ success: true, data: { path, keys: [...form.keys()] } }) }, '/y', new FormData());
	assert.deepEqual(fallback.data, { path: '/y', keys: [] });
	assert.equal((await upload({}, '/z', new FormData())).error.code, 'no_api');
	assert.equal((await fetchBytes({}, '/z')).error.code, 'no_api');
	assert.equal((await fetchBytes({ fetchRaw: async () => Promise.reject(new TypeError('offline')) }, '/z')).error.code, 'network_error');
});

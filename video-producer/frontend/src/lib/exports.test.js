import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	BACKGROUND_POLL_EVERY,
	POLL_EVERY,
	README_HREF,
	currentJob,
	exchangeFile,
	exchangePath,
	filenameFrom,
	finishedNow,
	historyOf,
	isJobActive,
	isRealFormat,
	jobFilePath,
	jobPath,
	lastSegment,
	mergeJob,
	normalizeJob,
	pollDelay,
	slugify,
	sortJobs,
	videoFile
} from './exports.js';

test('slugify: the backend slug, spaces to underscores, accents folded, never empty', () => {
	assert.equal(slugify('Aube sur le port'), 'Aube_sur_le_port');
	assert.equal(slugify('  Été — à Montréal !  '), 'Ete__a_Montreal');
	assert.equal(slugify('Œuvre n°2'), 'uvre_n2');
	assert.equal(slugify('v1.2 final-cut'), 'v1.2_final-cut');
	assert.equal(slugify('.hidden_'), 'hidden');
	assert.equal(slugify('日本'), 'video-producer');
	assert.equal(slugify(''), 'video-producer');
	assert.equal(slugify(null), 'video-producer');
	assert.equal(videoFile('x'.repeat(120), '1080p'), `${'x'.repeat(80)}_1080p.mp4`);
	assert.equal(videoFile('a'.repeat(79) + '._', '720p'), `${'a'.repeat(79)}_720p.mp4`);
});

test('file names and routes follow the contract', () => {
	assert.equal(exchangeFile('Aube sur le port', 'fcpxml'), 'Aube_sur_le_port.fcpxml');
	assert.equal(exchangeFile('Aube', 'otio'), 'Aube.otio');
	assert.equal(exchangeFile('Aube', 'edl'), 'Aube.edl');
	assert.equal(exchangeFile('Aube', 'srt'), 'Aube.srt');
	assert.equal(videoFile('Aube sur le port', '1080p'), 'Aube_sur_le_port_1080p.mp4');
	assert.equal(exchangePath('01J/X', 'edl'), '/projects/01J%2FX/exports/edl');
	assert.equal(exchangePath('p1', 'otio', 'name'), '/projects/p1/exports/otio?media=name');
	assert.equal(jobPath('j 1'), '/exports/j%201');
	assert.equal(jobFilePath('j1'), '/exports/j1/file');
	assert.equal(README_HREF, '/admin?tab=docs&doc=plugin%2Fvideo-producer%2FREADME');
	assert.ok(isRealFormat('web') && isRealFormat('social'));
	assert.ok(!isRealFormat('master') && !isRealFormat('archive'));
});

test('normalizeJob: camelCase, bounded progress, known states and steps only', () => {
	const job = normalizeJob({
		id: 'j1',
		project_id: 'p1',
		format: 'web',
		resolution: '1080p',
		status: 'done',
		progress: 140,
		step: 'store',
		file: { name: 'Aube_1080p.mp4', size: 1024, url: '/api/plugins/video-producer/exports/j1/file' },
		media: { kind: 'library', item_id: 42, url: '/api/media/uploads/a.mp4' },
		error: null,
		created_at: '2026-10-17T10:00:00Z',
		finished_at: '2026-10-17T10:01:00Z'
	});
	assert.deepEqual(job, {
		id: 'j1',
		projectId: 'p1',
		format: 'web',
		resolution: '1080p',
		status: 'done',
		progress: 100,
		step: 'store',
		file: { name: 'Aube_1080p.mp4', size: 1024, url: '/api/plugins/video-producer/exports/j1/file' },
		media: { kind: 'library', itemId: '42', url: '/api/media/uploads/a.mp4' },
		error: null,
		createdAt: '2026-10-17T10:00:00Z',
		finishedAt: '2026-10-17T10:01:00Z'
	});
	const odd = normalizeJob({ id: 7, status: 'exploded', step: 'paint', progress: null, error: { code: 'ffmpeg_failed', message: 'x' }, file: { size: 3 } });
	assert.deepEqual([odd.id, odd.status, odd.step, odd.progress, odd.file], ['7', 'queued', null, 0, null]);
	assert.deepEqual(odd.error, { code: 'ffmpeg_failed', message: 'x' });
	assert.equal(normalizeJob({}), null);
	assert.equal(normalizeJob(null), null);
});

test('job lists: newest first, the running job found, a job merged in place', () => {
	const a = normalizeJob({ id: 'a', status: 'done', created_at: '2026-10-17T09:00:00Z' });
	const b = normalizeJob({ id: 'b', status: 'running', created_at: '2026-10-17T10:00:00Z' });
	const c = normalizeJob({ id: 'c', status: 'failed', created_at: '2026-10-17T08:00:00Z' });
	assert.deepEqual(sortJobs([a, c, b]).map((j) => j.id), ['b', 'a', 'c']);
	assert.equal(currentJob([a, b, c]).id, 'b');
	assert.equal(currentJob([a, c]), null);
	assert.ok(isJobActive(b) && isJobActive({ status: 'queued' }));
	assert.ok(!isJobActive(a) && !isJobActive(null));
	const merged = mergeJob([a, b, c], { ...b, status: 'done', progress: 100 });
	assert.deepEqual(merged.map((j) => [j.id, j.status]), [
		['b', 'done'],
		['a', 'done'],
		['c', 'failed']
	]);
});

test('filenameFrom: RFC 5987 name first, then the quoted name, else null', () => {
	assert.equal(filenameFrom(`attachment; filename="Aube_sur_le_port.edl"; filename*=UTF-8''Aube%20sur%20le%20port.edl`), 'Aube sur le port.edl');
	assert.equal(filenameFrom('attachment; filename="Aube.fcpxml"'), 'Aube.fcpxml');
	assert.equal(filenameFrom('attachment; filename=plain.srt'), 'plain.srt');
	assert.equal(filenameFrom("attachment; filename*=UTF-8''%E0%A4%A"), '%E0%A4%A');
	assert.equal(filenameFrom(''), null);
	assert.equal(filenameFrom(null), null);
	assert.equal(lastSegment('/exports/j1/file?x=1'), 'file');
	assert.equal(lastSegment(''), null);
});

test('historyOf: the export in progress heads the list with its own state, the others keep their order', () => {
	const done = normalizeJob({ id: 'a', status: 'done', created_at: '2026-10-17T09:00:00Z' });
	const old = normalizeJob({ id: 'c', status: 'failed', created_at: '2026-10-17T08:00:00Z' });
	const running = normalizeJob({ id: 'b', status: 'running', progress: 40, created_at: '2026-10-17T07:00:00Z' });
	const fresher = { ...running, progress: 65, step: 'mix' };
	const list = historyOf([done, running, old], fresher);
	assert.deepEqual(list.map((j) => [j.id, j.status, j.progress]), [
		['b', 'running', 65],
		['a', 'done', 0],
		['c', 'failed', 0]
	]);
	const ready = { ...running, status: 'done', progress: 100 };
	assert.deepEqual(historyOf([ready], ready).map((j) => j.id), ['b']);
	assert.deepEqual(historyOf([], ready).map((j) => j.id), ['b']);
	assert.deepEqual(historyOf([done, old], null), [done, old]);
});

test('pollDelay: every second in the window, every three seconds once it is closed, never without an export in progress', () => {
	assert.equal(POLL_EVERY, 1000);
	assert.equal(BACKGROUND_POLL_EVERY, 3000);
	assert.equal(pollDelay({ followed: true, shown: true }), POLL_EVERY);
	assert.equal(pollDelay({ followed: true, shown: false }), BACKGROUND_POLL_EVERY);
	assert.equal(pollDelay({ followed: false, shown: true }), 0);
	assert.equal(pollDelay({ followed: false, shown: false }), 0);
});

test('finishedNow: only the export that was in progress and is now ready', () => {
	const running = normalizeJob({ id: 'j', status: 'running' });
	const queued = normalizeJob({ id: 'j', status: 'queued' });
	assert.ok(finishedNow(running, { ...running, status: 'done' }));
	assert.ok(finishedNow(queued, { ...queued, status: 'done' }));
	assert.ok(!finishedNow(running, { ...running, status: 'failed' }));
	assert.ok(!finishedNow(running, { ...running, status: 'cancelled' }));
	assert.ok(!finishedNow({ ...running, status: 'done' }, { ...running, status: 'done' }));
	assert.ok(!finishedNow(running, { ...running, id: 'other', status: 'done' }));
	assert.ok(!finishedNow(null, { ...running, status: 'done' }));
});

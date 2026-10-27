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
	jobFilePath,
	keptInLibrary,
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
	assert.equal(slugify('  Été — à Montréal !  '), 'Ete_a_Montreal');
	assert.equal(slugify('Œuvre n°2'), 'Oeuvre_n2');
	assert.equal(slugify('Cœur'), 'Coeur');
	assert.equal(slugify('Le cœur de l’œuvre'), 'Le_coeur_de_loeuvre');
	assert.equal(slugify('Æon'), 'Aeon');
	assert.equal(slugify('Straße'), 'Strasse');
	assert.equal(slugify('Søren'), 'Soren');
	assert.equal(slugify('ŒÆØ'), 'OeAeO');
	assert.equal(slugify('v1.2 final-mix'), 'v1.2_final-mix');
	assert.equal(slugify('.hidden_'), 'hidden');
	assert.equal(slugify('日本'), 'video-producer');
	assert.equal(slugify(''), 'video-producer');
	assert.equal(slugify(null), 'video-producer');
	assert.equal(videoFile('x'.repeat(120), '1080p'), `${'x'.repeat(80)}_1080p.mp4`);
	assert.equal(videoFile('a'.repeat(79) + '._', '720p'), `${'a'.repeat(79)}_720p.mp4`);
});

const FILE_NAMES = [
	['Cœur', 'Coeur'],
	['Æther', 'Aether'],
	['Straße', 'Strasse'],
	['Søren', 'Soren'],
	['nul.v2', '_nul.v2'],
	['CON', '_CON'],
	['com1.final', '_com1.final'],
	['Concert', 'Concert'],
	['Prn.final', '_Prn.final'],
	['lpt9', '_lpt9'],
	['com10', 'com10'],
	['v2.con', 'v2.con'],
	['STRAẞE', 'STRASSE'],
	['Aube & marée / v2', 'Aube_maree_v2'],
	['a__b', 'a_b'],
	['a\ufeffb', 'a_b'],
	['a\x85b', 'a_b']
];

for (const [name, expected] of FILE_NAMES) {
	test(`a name gets the file name the server gives it: ${JSON.stringify(name)}`, () => {
		assert.equal(slugify(name), expected);
		assert.equal(videoFile(name, '1080p'), `${expected}_1080p.mp4`);
		assert.equal(exchangeFile(name, 'edl'), `${expected}.edl`);
	});
}

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
	assert.ok(keptInLibrary('web') && keptInLibrary('social'));
	assert.ok(!keptInLibrary('master') && !keptInLibrary('archive'));
});

test('videoFile: the name the server gives each format, the stems in a ZIP named after the video', () => {
	assert.equal(videoFile('Aube sur le port', '4K', 'social'), 'Aube_sur_le_port_4K.mp4');
	assert.equal(videoFile('Aube sur le port', '1080p', 'master'), 'Aube_sur_le_port_1080p.mov');
	assert.equal(videoFile('Aube sur le port', '720p', 'archive'), 'Aube_sur_le_port_720p_archive.mp4');
	assert.equal(videoFile('Aube sur le port', '1080p', 'master', true), 'Aube_sur_le_port_1080p_master_stems.zip');
	assert.equal(videoFile('Aube sur le port', '1080p', 'archive', true), 'Aube_sur_le_port_1080p_archive_stems.zip');
	assert.equal(videoFile('Aube sur le port', '1080p', 'web', true), 'Aube_sur_le_port_1080p_web_stems.zip');
	assert.equal(videoFile('x'.repeat(120), '1080p', 'archive'), `${'x'.repeat(80)}_1080p_archive.mp4`);
});

test('normalizeJob: camelCase, bounded progress, known states and steps only', () => {
	const job = normalizeJob({
		id: 'j1',
		project_id: 'p1',
		format: 'web',
		resolution: '1080p',
		stems: true,
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
		stems: true,
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

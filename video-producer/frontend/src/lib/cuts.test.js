import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MEDIA_RUNS, createClient, normalizeRun } from './api.js';
import { CUT_TOOL, SENSITIVITY, SHORTEST, bounded, buildCuts, cutFailure, cutInput, cutName, cutRequest, cuttable, shotLength } from './cuts.js';

const library = { kind: 'library', itemId: 'u1' };
const history = { kind: 'history', generationId: 'g1', fileId: 'f1' };

function piece(i, extra = {}) {
	return { id: `p${i}`, name: `clip-shot ${i}.mp4`, mediaType: 'video', url: `/api/media/uploads/p${i}.mp4`, duration: 1.979, width: 640, height: 360, fps: 24, ...extra };
}

function counter() {
	let n = 0;
	return () => `id${++n}`;
}

function recorder(answers) {
	const calls = [];
	const api = {
		async fetchRawFromApp(path, init) {
			calls.push({ path, method: init.method, body: init.body === undefined ? undefined : JSON.parse(init.body), headers: init.headers });
			const [status, payload] = answers.shift();
			return { ok: status < 400, status, json: async () => payload };
		}
	};
	return { calls, client: createClient(api, () => {}) };
}

test('cuts: a library video is sent by item id, a gallery video by its file id, anything else not at all', () => {
	assert.deepEqual(cutInput(library), { item_id: 'u1' });
	assert.deepEqual(cutInput(history), { generation_file_id: 'f1' });
	assert.equal(cutInput({ kind: 'history', generationId: 'g1', fileId: 0 }), null);
	assert.equal(cutInput(null), null);
	assert.equal(cuttable({ kind: 'video', origin: library }), true);
	assert.equal(cuttable({ kind: 'image', origin: library }), false);
	assert.equal(cuttable({ kind: 'video', origin: null }), false);
});

test('cuts: the request runs cut_finder alone, makes new library items, and keeps the settings inside its bounds', () => {
	assert.deepEqual(cutRequest(library, { sensitivity: 65, shortest: 1.2 }), {
		steps: [{ tool: CUT_TOOL, params: { sensitivity: 65, min_shot_seconds: 1.2 } }],
		inputs: [{ item_id: 'u1' }],
		output: { mode: 'new' }
	});
	assert.deepEqual(cutRequest(history).steps[0].params, { sensitivity: SENSITIVITY.value, min_shot_seconds: SHORTEST.value });
	assert.deepEqual(cutRequest(library, { sensitivity: 140, shortest: 0 }).steps[0].params, { sensitivity: 100, min_shot_seconds: 0.1 });
	assert.deepEqual(cutRequest(library, { sensitivity: -5, shortest: 99 }).steps[0].params, { sensitivity: 0, min_shot_seconds: 30 });
	assert.equal(bounded('', SHORTEST), SHORTEST.value);
	assert.equal(bounded('abc', SENSITIVITY), SENSITIVITY.value);
	assert.equal(cutRequest({ kind: 'library' }), null);
	assert.equal('collection_id' in cutRequest(library).output, false);
});

test('cuts: a shot lasts its piece, rounded down to 0.04 s, never zero', () => {
	assert.equal(shotLength(1.979), 1.96);
	assert.equal(shotLength(2), 2);
	assert.equal(shotLength(0.01), 0.04);
	assert.equal(shotLength(null), null);
	assert.equal(shotLength(0), null);
	assert.equal(cutName('trailer.final.mp4', 'Cut'), 'trailer.final');
	assert.equal(cutName('', 'Cut'), 'Cut');
	assert.equal(cutName('x'.repeat(90), 'Cut').length, 60);
});

test('cuts: the core failures read as no cut, too many shots, a full queue or another failure', () => {
	assert.equal(cutFailure({ code: 'tool_failed', message: 'No cuts were found; try a higher sensitivity' }), 'none');
	assert.equal(cutFailure({ code: 'invalid_params', message: 'Found 230 shots, over the 200-shot limit; lower the sensitivity' }), 'tooMany');
	assert.equal(cutFailure({ status: 429, code: 'too_many_queued', message: 'You already have 8 runs waiting; let some finish first' }), 'busy');
	assert.equal(cutFailure({ code: 'ffmpeg_unavailable', message: 'ffmpeg is missing' }), 'failed');
	assert.equal(cutFailure({ code: 'tool_failed', message: 'Could not read the video' }), 'failed');
	assert.equal(cutFailure(null), null);
});

test('cuts: as sources, each piece becomes the media of its own shot, cut apart from the previous one', () => {
	const built = buildCuts([piece(1), piece(2, { duration: 3.5 }), { id: 'x', mediaType: 'image', url: '/a.png' }], { mode: 'source', label: (n) => `Trailer ${n}`, makeId: counter() });
	assert.equal(built.clips.length, 2);
	assert.deepEqual(built.references, []);
	assert.deepEqual(
		built.clips.map((c) => [c.label, c.dur, c.stage, c.assetId, c.firstFromPrevious, c.srcIn]),
		[
			['Trailer 1', 1.96, 'source', built.assets[0].id, false, 0],
			['Trailer 2', 3.48, 'source', built.assets[1].id, false, 0]
		]
	);
	assert.deepEqual(
		built.assets.map((a) => [a.kind, a.name, a.src, a.origin, a.srcDur, a.res, a.fps, a.generated]),
		[
			['video', 'clip-shot 1.mp4', '/api/media/uploads/p1.mp4', { kind: 'library', itemId: 'p1' }, 1.979, '640×360', 24, false],
			['video', 'clip-shot 2.mp4', '/api/media/uploads/p2.mp4', { kind: 'library', itemId: 'p2' }, 3.5, '640×360', 24, false]
		]
	);
});

test('cuts: as motion references, each shot is left to generate and its piece is its own Motion reference', () => {
	const built = buildCuts([piece(1), piece(2)], { mode: 'motion', label: (n) => `Trailer ${n}`, makeId: counter() });
	assert.deepEqual(
		built.clips.map((c) => [c.label, c.dur, c.stage, c.assetId, c.firstFromPrevious]),
		[
			['Trailer 1', 1.96, 'todo', null, false],
			['Trailer 2', 1.96, 'todo', null, false]
		]
	);
	assert.deepEqual(
		built.references,
		built.clips.map((c, i) => ({ id: built.references[i].id, name: c.label, space: 'mouvement', type: 'Control video', assetId: built.assets[i].id, role: 'Mouvement', scope: { type: 'shot', shotId: c.id } }))
	);
	assert.equal(new Set([...built.clips, ...built.assets, ...built.references].map((x) => x.id)).size, 6);
});

test('cuts: a piece without a known length still makes a 4 s shot', () => {
	const built = buildCuts([piece(1, { duration: null, width: null, height: null })], { mode: 'source', label: (n) => `C ${n}`, makeId: counter() });
	assert.equal(built.clips[0].dur, 4);
	assert.equal(built.assets[0].srcDur, null);
	assert.equal(built.assets[0].res, null);
});

test('cuts: a run reads its state, progress, pieces and error', () => {
	const run = normalizeRun({
		run_id: 'r1',
		status: 'completed',
		progress: 1.4,
		label: 'Find cuts',
		items: [{ id: 'p1', filename: 'a.mp4', original_filename: 'clip-shot 1.mp4', media_type: 'video', url: '/api/media/uploads/a.mp4', duration_seconds: 2.5, width: 640, height: 360, fps: 24 }, { id: 'bad' }],
		error: null
	});
	assert.deepEqual(run, { id: 'r1', status: 'completed', progress: 1, label: 'Find cuts', items: [{ id: 'p1', name: 'clip-shot 1.mp4', mediaType: 'video', url: '/api/media/uploads/a.mp4', duration: 2.5, width: 640, height: 360, fps: 24 }], error: null });
	assert.deepEqual(normalizeRun({ run_id: 'r2', status: 'failed', error: { code: 'tool_failed', message: 'No cuts were found' } }).error, { code: 'tool_failed', message: 'No cuts were found' });
	assert.equal(normalizeRun({ run_id: 'r3', status: 'exploded' }), null);
});

test('cuts: the page starts, reads and cancels the run on the core media tools API, through the host client', async () => {
	const body = cutRequest(library, { sensitivity: 55, shortest: 0.8 });
	const { calls, client } = recorder([
		[202, { success: true, data: { run_id: 'r/1' } }],
		[200, { success: true, data: { run_id: 'r/1', status: 'running', progress: 0.4, items: [] } }],
		[200, { success: true, data: { run_id: 'r/1', status: 'cancelled', progress: 0.4, items: [] } }]
	]);
	assert.deepEqual(await client.startMediaRun(body), { ok: true, data: { id: 'r/1' } });
	assert.equal((await client.mediaRun('r/1')).data.progress, 0.4);
	assert.equal((await client.cancelMediaRun('r/1')).data.status, 'cancelled');
	assert.deepEqual(
		calls.map((c) => [c.method, c.path]),
		[
			['POST', MEDIA_RUNS],
			['GET', '/api/media-tools/runs/r%2F1'],
			['DELETE', '/api/media-tools/runs/r%2F1']
		]
	);
	assert.equal(MEDIA_RUNS, '/api/media-tools/runs');
	assert.deepEqual(calls[0].body, { steps: [{ tool: 'cut_finder', params: { sensitivity: 55, min_shot_seconds: 0.8 } }], inputs: [{ item_id: 'u1' }], output: { mode: 'new' } });
	assert.deepEqual(calls[0].headers, { 'Content-Type': 'application/json' });
	assert.equal(calls[1].body, undefined);
});

test('cuts: a full queue answers with its code, whether the core puts it at the top or under detail', async () => {
	const { client } = recorder([
		[429, { success: false, error: 'too_many_queued', message: 'You already have 8 runs waiting; let some finish first' }],
		[429, { detail: { success: false, error: 'too_many_queued', message: 'You already have 8 runs waiting' } }]
	]);
	for (let i = 0; i < 2; i++) {
		const result = await client.startMediaRun(cutRequest(library));
		assert.equal(result.ok, false);
		assert.equal(result.error.status, 429);
		assert.equal(cutFailure(result.error), 'busy');
	}
});

test('cuts: without the host client the page asks nothing', async () => {
	const client = createClient({}, () => {});
	assert.deepEqual((await client.startMediaRun(cutRequest(library))).error.code, 'no_api');
});

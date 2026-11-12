import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

const hooks = `
import { readFile } from 'node:fs/promises';
import { compileModule } from ${JSON.stringify(import.meta.resolve('svelte/compiler'))};
export async function load(url, context, next) {
	if (url.endsWith('.svelte.js')) return { format: 'module', shortCircuit: true, source: compileModule(await readFile(new URL(url), 'utf8'), { generate: 'client', filename: url }).js.code };
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

const hostToasts = [];
const hostLevels = [];
globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast: (level, message) => (hostToasts.push(message), hostLevels.push([level, message])) } } };

const { doc, ui, undo, dispose } = await import('./state.svelte.js');
const { bindClient, openProject, project } = await import('./project.svelte.js');
const { exportState, startVideoExport, pollJob, listJobs, cancelJob, resumeExports, disposeExports } = await import('./exports.svelte.js');
const { finishState, finishTiming, finishJob, cancelFinish, loadFinishing, setFinish, downloadFinished, resetFinishing, finishShown, finishFailureText } = await import('./finishing.svelte.js');
const { finishSteps, finishingOf, toolsById } = await import('./finishing.js');
const { normalizeTool } = await import('./api.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { setLocale } = await import('../i18n/index.svelte.js');

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const copy = (value) => JSON.parse(JSON.stringify(value));
const FINISHED = { status: 'completed', progress: 1, items: [{ id: 'item-fin', name: 'Film_720p-grain.mp4', mediaType: 'video', url: '/api/media/uploads/fin.mp4' }] };

const TOOLS = [
	{ id: 'film_grain', params: [{ name: 'amount', default: 30, min: 0, max: 100, step: 1 }, { name: 'size', default: 1.5, min: 1, max: 3, step: 0.1 }] },
	{ id: 'vignette', params: [{ name: 'amount', default: 40, min: 0, max: 100, step: 1 }, { name: 'radius', default: 50, min: 0, max: 100, step: 1 }] },
	{ id: 'fix_colors', params: [{ name: 'strength', default: 100, min: 0, max: 100, step: 5 }] },
	{ id: 'lut', params: [{ name: 'lut', type: 'lut', options: [{ label: 'None', value: '' }, { label: 'warm', value: 'warm.cube' }] }, { name: 'strength', default: 1, min: 0, max: 1, step: 0.05 }] }
].map(normalizeTool);

function makeServer(script = {}) {
	const calls = [];
	const docs = new Map();
	const versions = new Map();
	const exported = new Set();
	const server = { calls, docs, status: script.exportEnds ?? 'done', pollAnswer: script.pollAnswer ?? null, cancelAnswer: script.cancelAnswer ?? null, runs: 0 };
	const exportJob = (projectId, status) => ({ id: `job-${projectId}`, projectId, format: script.format ?? 'web', resolution: '720p', ratio: null, stems: false, status, progress: status === 'done' ? 100 : 10, step: null, file: status === 'done' ? { name: 'Film_720p.mp4', size: 10, url: null } : null, media: status === 'done' && (script.format ?? 'web') !== 'master' ? { kind: 'library', itemId: `item-raw-${projectId}`, url: '/api/media/uploads/raw.mp4' } : null, error: null, createdAt: '2026-11-12T10:00:00Z', finishedAt: null });
	const nextRead = (id) => {
		const queue = typeof script.reads === 'function' ? script.reads(id) : script.reads;
		const next = queue?.shift();
		if (next?.fail) return { ok: false, error: next.fail };
		return { ok: true, data: { id, label: '', items: [], error: null, progress: 0, ...(next ?? FINISHED) } };
	};
	server.client = {
		async getProject(id) {
			return { ok: true, data: { id, name: 'Film', version: versions.get(id) ?? 1, doc: copy(docs.get(id)), createdAt: null, updatedAt: null, unchanged: false } };
		},
		async saveProject(id, next) {
			docs.set(id, copy(next));
			versions.set(id, (versions.get(id) ?? 1) + 1);
			calls.push(['save', id]);
			return { ok: true, data: { id, name: 'Film', version: versions.get(id), doc: null, createdAt: null, updatedAt: null, unchanged: false } };
		},
		saveLastProject() {},
		async listTakes() {
			return { ok: true, data: [] };
		},
		async listRenditions() {
			return { ok: true, data: [] };
		},
		async listExports(projectId) {
			calls.push(['list', projectId]);
			return { ok: true, data: exported.has(projectId) ? [exportJob(projectId, server.status)] : [] };
		},
		async exportVideo(projectId, body) {
			calls.push(['export', body]);
			exported.add(projectId);
			return { ok: true, data: exportJob(projectId, 'queued') };
		},
		async exportJob(jobId) {
			calls.push(['poll', jobId]);
			return server.pollAnswer ?? { ok: true, data: exportJob(jobId.slice(4), server.status) };
		},
		async cancelExport(jobId) {
			calls.push(['cancel-export', jobId]);
			return server.cancelAnswer ?? { ok: true, data: exportJob(jobId.slice(4), 'cancelled') };
		},
		async mediaTools(kind) {
			calls.push(['tools', kind]);
			const answer = typeof script.tools === 'function' ? script.tools() : script.tools;
			return answer === false ? { ok: false, error: { status: 500, code: 'server_error', message: '' } } : { ok: true, data: answer ?? TOOLS };
		},
		async startMediaRun(body) {
			calls.push(['run', body]);
			server.runs += 1;
			if (script.startHeld) await script.startHeld;
			return script.start ?? { ok: true, data: { id: `run${server.runs}` } };
		},
		async mediaRun(id) {
			calls.push(['read', id]);
			return nextRead(id);
		},
		async cancelMediaRun(id) {
			calls.push(['cancel', id]);
			return typeof script.cancelRun === 'function' ? script.cancelRun(id) : { ok: true, data: { id, status: 'cancelled', progress: 0, label: '', items: [], error: null } };
		},
		async downloadCore(path, filename) {
			calls.push(['download', path, filename]);
			return { ok: true, data: { filename } };
		}
	};
	return server;
}

let server = null;

function projectDoc(script) {
	const start = emptyDoc((key) => key);
	start.clips = [newClip({ id: 's1', label: 'One', start: 0, dur: 4 })];
	if (script?.finishing) start.master.finishing = script.finishing;
	return start;
}

async function open(script = {}) {
	server = makeServer(script);
	server.docs.set('p1', projectDoc(script));
	server.docs.set('p2', projectDoc(script));
	bindClient(server.client);
	resetFinishing();
	await openProject('p1');
	await resumeExports();
	await loadFinishing();
}

const stepsNow = () => finishSteps(finishingOf(doc), toolsById(finishState.tools));
const runs = () => server.calls.filter(([kind]) => kind === 'run');

async function drain() {
	for (let i = 0; i < 100 && finishState.runs.some((run) => run.status === 'running'); i++) await settle();
}

async function exportAndFinish(format = 'web') {
	const steps = stepsNow();
	await startVideoExport({ format, resolution: '720p', finish: steps });
	await pollJob();
	await drain();
	return steps;
}

beforeEach(() => {
	setLocale('en');
	finishTiming.wait = () => settle();
	ui.modal = null;
});

after(() => {
	disposeExports();
	dispose();
	delete globalThis.window;
});

test('finishing flow: a web export with grain and vignette is finished by one run on its library item', async () => {
	await open({ finishing: { grain: { on: true, amount: 50, size: 2 }, vignette: { on: true } } });
	const steps = await exportAndFinish();
	assert.deepEqual(steps.map((x) => x.tool), ['vignette', 'film_grain']);
	assert.deepEqual(runs()[0][1], { steps: [{ tool: 'vignette', params: { amount: 40, radius: 50 } }, { tool: 'film_grain', params: { amount: 50, size: 2 } }], inputs: [{ item_id: 'item-raw-p1' }], output: { mode: 'new' } });
	assert.deepEqual(server.calls.find(([kind]) => kind === 'export')[1], { format: 'web', resolution: '720p', stems: false });
	const run = finishShown();
	assert.equal(run.status, 'done');
	assert.equal(run.item.id, 'item-fin');
	assert.equal(run.fileName, 'Film_720p.mp4');
	assert.equal(exportState.job.status, 'done');
	assert.equal(exportState.job.media.itemId, 'item-raw-p1');
	await downloadFinished();
	assert.deepEqual(server.calls.at(-1), ['download', '/api/media/uploads/fin.mp4', 'Film_720p_finished.mp4']);
	assert.equal(ui.toasts.at(-1).message, 'Finished film ready: Film_720p_finished.mp4');
});

test('finishing flow: nothing switched on means a plain export and no run', async () => {
	await open({});
	const steps = await exportAndFinish();
	assert.deepEqual(steps, []);
	assert.equal(runs().length, 0);
	assert.equal(finishShown(), null);
});

test('finishing flow: a master export is never finished, whatever is switched on', async () => {
	await open({ format: 'master', finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'master', resolution: '720p', finish: stepsNow() });
	await pollJob();
	await settle();
	assert.equal(runs().length, 0);
	assert.equal(finishShown(), null);
});

test('finishing flow: a failed export starts no finishing', async () => {
	await open({ exportEnds: 'failed', finishing: { grain: { on: true } } });
	await exportAndFinish();
	assert.equal(runs().length, 0);
	assert.equal(finishShown(), null);
});

test('finishing flow: a cancelled export starts no finishing', async () => {
	await open({ exportEnds: 'cancelled', finishing: { grain: { on: true } } });
	await exportAndFinish();
	assert.equal(runs().length, 0);
	assert.equal(finishShown(), null);
});

test('finishing flow: the export seen done by the list of exports, not by the follow-up, is finished', async () => {
	await open({ exportEnds: 'running', finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	server.status = 'done';
	await listJobs();
	await drain();
	assert.equal(runs().length, 1);
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: a round trip to another project during the export still finishes it on the way back', async () => {
	await open({ exportEnds: 'running', finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await openProject('p2');
	await listJobs();
	server.status = 'done';
	await openProject('p1');
	await listJobs();
	await drain();
	assert.equal(runs().length, 1);
	assert.deepEqual(runs()[0][1].inputs, [{ item_id: 'item-raw-p1' }]);
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: a follow-up lost in a 404 hands over to the list, which finishes the export', async () => {
	await open({ finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	server.pollAnswer = { ok: false, error: { status: 404, code: 'job_not_found', message: '' } };
	await pollJob();
	await drain();
	assert.equal(runs().length, 1);
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: cancelling the export just as it ends starts no finishing', async () => {
	await open({ exportEnds: 'running', finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	server.status = 'done';
	server.cancelAnswer = { ok: true, data: { ...exportState.job, status: 'done', media: { kind: 'library', itemId: 'item-raw-p1', url: '/u.mp4' }, file: { name: 'Film_720p.mp4', size: 1, url: null } } };
	await cancelJob(exportState.job);
	await drain();
	assert.equal(runs().length, 0);
	assert.equal(finishShown(), null);
});

test('finishing flow: a cancel answered 409 then listed done starts no finishing', async () => {
	await open({ exportEnds: 'running', finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	server.status = 'done';
	server.cancelAnswer = { ok: false, error: { status: 409, code: 'conflict', message: '' } };
	await cancelJob(exportState.job);
	await drain();
	assert.equal(runs().length, 0);
});

test('finishing flow: a cancel of the export that fails keeps its finishing, which starts when the export ends', async () => {
	await open({ exportEnds: 'running', finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	server.cancelAnswer = { ok: false, error: { status: 0, code: 'network_error', message: '' } };
	await cancelJob(exportState.job);
	assert.equal(runs().length, 0);
	server.status = 'done';
	await pollJob();
	await drain();
	assert.equal(runs().length, 1);
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: an export seen done while its cancel fails is still finished', async () => {
	await open({ exportEnds: 'running', finishing: { grain: { on: true } } });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	server.client.cancelExport = async (jobId) => {
		server.calls.push(['cancel-export', jobId]);
		server.status = 'done';
		await pollJob();
		return { ok: false, error: { status: 500, code: 'server_error', message: '' } };
	};
	await cancelJob(exportState.job);
	await drain();
	assert.equal(exportState.job.status, 'done');
	assert.equal(runs().length, 1);
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: a finishing that fails leaves the plain export done and says why', async () => {
	await open({ finishing: { lut: { on: true, ref: 'warm.cube', strength: 0.7 } }, reads: [{ status: 'failed', error: { code: 'tool_failed', message: 'ffmpeg failed' } }] });
	await exportAndFinish();
	assert.deepEqual(runs()[0][1].steps, [{ tool: 'lut', params: { strength: 0.7, lut: 'warm.cube' } }]);
	const run = finishShown();
	assert.deepEqual([run.status, run.failure, run.message], ['failed', 'failed', 'ffmpeg failed']);
	assert.equal(exportState.job.status, 'done');
});

test('finishing flow: a full queue at the start is told as such', async () => {
	await open({ finishing: { grain: { on: true } }, start: { ok: false, error: { status: 429, code: 'too_many_queued', message: 'You already have 8 runs waiting' } } });
	await exportAndFinish();
	assert.deepEqual([finishShown().status, finishShown().failure], ['failed', 'busy']);
});

test('finishing flow: cancelling the finishing cancels the core run and keeps the plain export', async () => {
	let reads = 0;
	await open({ finishing: { grain: { on: true } }, reads: [{ status: 'running', progress: 0.3 }, { status: 'running', progress: 0.6 }] });
	finishTiming.wait = async () => {
		reads += 1;
		if (reads === 2) await cancelFinish();
		await settle();
	};
	await exportAndFinish();
	assert.equal(finishShown().status, 'cancelled');
	assert.ok(server.calls.some(([kind, id]) => kind === 'cancel' && id === 'run1'));
	assert.equal(exportState.job.status, 'done');
});

test('finishing flow: a read that fails once is tried again, and the finishing still ends', async () => {
	await open({ finishing: { grain: { on: true } }, reads: [{ status: 'running', progress: 0.2 }, { fail: { status: 0, code: 'network_error', message: 'offline' } }, { status: 'running', progress: 0.7 }] });
	await exportAndFinish();
	assert.equal(finishShown().status, 'done');
	assert.equal(server.calls.filter(([kind]) => kind === 'read').length, 4);
});

test('finishing flow: a run PotionUI no longer knows, or reads failing again and again, say the page lost track of it', async () => {
	await open({ finishing: { grain: { on: true } }, reads: [{ fail: { status: 404, code: 'not_found', message: 'Run not found' } }] });
	await exportAndFinish();
	assert.deepEqual([finishShown().status, finishShown().failure], ['failed', 'lost']);
	assert.equal(finishFailureText(finishShown()), 'The page lost track of the finishing. It may still end in PotionUI: look for the finished film in your library.');
	const offline = { fail: { status: 0, code: 'network_error', message: '' } };
	await open({ finishing: { grain: { on: true } }, reads: [offline, offline, offline, offline, offline] });
	await exportAndFinish();
	assert.deepEqual([finishShown().status, finishShown().failure], ['failed', 'lost']);
	assert.equal(server.calls.filter(([kind]) => kind === 'read').length, 5);
});

test('finishing flow: a missed read is tried again after a wait doubled each time, so the page rides out half a minute without PotionUI', async () => {
	const offline = { fail: { status: 0, code: 'network_error', message: '' } };
	const waits = [];
	await open({ finishing: { grain: { on: true } }, reads: [offline, offline, { status: 'running', progress: 0.5 }, offline] });
	finishTiming.wait = (ms) => (waits.push(ms), settle());
	await exportAndFinish();
	assert.equal(finishShown().status, 'done');
	assert.deepEqual(waits, [1000, 2000, 4000, 1000, 2000]);
	waits.length = 0;
	await open({ finishing: { grain: { on: true } }, reads: [offline, offline, offline, offline, offline] });
	finishTiming.wait = (ms) => (waits.push(ms), settle());
	await exportAndFinish();
	assert.deepEqual([finishShown().status, finishShown().failure], ['failed', 'lost']);
	assert.deepEqual(waits, [1000, 2000, 4000, 8000, 16000]);
});

test('finishing flow: with the window closed, a finishing the page lost track of is told as a warning, not as a failure', async () => {
	const offline = { fail: { status: 0, code: 'network_error', message: '' } };
	await open({ finishing: { grain: { on: true } }, reads: [offline, offline, offline, offline, offline] });
	hostLevels.length = 0;
	await exportAndFinish();
	assert.deepEqual([finishShown().status, finishShown().failure], ['failed', 'lost']);
	assert.deepEqual(hostLevels.at(-1), ['warning', 'The page lost track of the finishing. It may still end in PotionUI: look for the finished film in your library. The plain export is still available.']);
});

test('finishing flow: a finishing in a second project leaves the first one running to its end', async () => {
	let held = true;
	await open({ exportEnds: 'done', finishing: { grain: { on: true } }, reads: (id) => (id === 'run1' && held ? [{ status: 'running', progress: 0.5 }] : []) });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	await settle();
	await openProject('p2');
	await resumeExports();
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	for (let i = 0; i < 20; i++) await settle();
	assert.equal(finishShown().status, 'done');
	assert.equal(finishShown().projectId, 'p2');
	held = false;
	await drain();
	const first = finishState.runs.find((run) => run.projectId === 'p1');
	assert.equal(first.status, 'done');
	assert.equal(server.calls.some(([kind]) => kind === 'cancel'), false);
	assert.deepEqual(runs().map(([, body]) => body.inputs[0].item_id), ['item-raw-p1', 'item-raw-p2']);
	assert.ok(ui.toasts.some((x) => x.message === 'Finished film ready: Film_720p_finished.mp4'));
});

test('finishing flow: closing the page stops following a finishing, with no read and no message after, and the page opened again is not held by it', async () => {
	await open({ finishing: { grain: { on: true } }, reads: (id) => (id === 'run1' ? [{ status: 'running', progress: 0.4 }] : []) });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	for (let i = 0; i < 5; i++) await settle();
	const toasts = ui.toasts.length;
	disposeExports();
	const reads = server.calls.filter(([kind]) => kind === 'read').length;
	for (let i = 0; i < 10; i++) await settle();
	assert.equal(server.calls.filter(([kind]) => kind === 'read').length, reads);
	assert.equal(ui.toasts.length, toasts);
	assert.deepEqual([finishShown().status, finishShown().failure, finishShown().cancelling], ['failed', 'lost', false]);
	await resumeExports();
	await loadFinishing();
	await cancelFinish();
	assert.equal(finishShown().cancelling, false);
	assert.equal(server.calls.some(([kind]) => kind === 'cancel'), false);
	await exportAndFinish();
	assert.deepEqual(runs().map(([, body]) => body.inputs[0].item_id), ['item-raw-p1', 'item-raw-p1']);
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: closing the page while the run is being started leaves the started run going on in PotionUI', async () => {
	let release;
	const held = new Promise((resolve) => (release = resolve));
	await open({ finishing: { grain: { on: true } }, startHeld: held });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	await settle();
	assert.equal(runs().length, 1);
	disposeExports();
	release();
	for (let i = 0; i < 10; i++) await settle();
	assert.equal(server.calls.some(([kind]) => kind === 'cancel'), false);
	assert.equal(server.calls.some(([kind]) => kind === 'read'), false);
	assert.deepEqual([finishShown().status, finishShown().failure], ['failed', 'lost']);
});

test('finishing flow: the list of finishings keeps the last eight, but never drops one still running', async () => {
	await open({ finishing: { grain: { on: true } } });
	const old = (key, status) => ({ key, jobId: key, projectId: 'p0', runId: null, status, cancelling: false, progress: 0, item: null, failure: null, message: '', fileName: 'Old.mp4' });
	finishState.runs = [old('old0', 'running'), ...Array.from({ length: 7 }, (_, i) => old(`old${i + 1}`, 'done'))];
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	for (let i = 0; i < 20; i++) await settle();
	assert.equal(finishShown().status, 'done');
	assert.deepEqual(finishState.runs.map((run) => run.key), ['old0', 'old2', 'old3', 'old4', 'old5', 'old6', 'old7', 'job-p1']);
	finishState.runs = Array.from({ length: 8 }, (_, i) => old(`busy${i}`, 'running'));
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	for (let i = 0; i < 20; i++) await settle();
	assert.equal(finishState.runs.length, 9);
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: a cancel answered by a finished run shows the finished film, not a cancellation', async () => {
	let asked = 0;
	await open({ finishing: { grain: { on: true } }, reads: () => [{ status: 'running', progress: 0.9 }], cancelRun: (id) => ({ ok: true, data: { id, status: 'completed', progress: 1, label: '', items: [FINISHED.items[0]], error: null } }) });
	finishTiming.wait = async () => {
		asked += 1;
		if (asked === 2) await cancelFinish();
		await settle();
	};
	await exportAndFinish();
	assert.deepEqual([finishShown().status, finishShown().item.id], ['done', 'item-fin']);
});

test('finishing flow: a cancel that fails leaves the finishing running, says so, and the finishing still ends', async () => {
	let asked = 0;
	const reads = [{ status: 'running', progress: 0.2 }, { status: 'running', progress: 0.5 }];
	await open({ finishing: { grain: { on: true } }, reads, cancelRun: () => ({ ok: false, error: { status: 0, code: 'network_error', message: 'offline' } }) });
	finishTiming.wait = async () => {
		asked += 1;
		if (asked === 2) {
			await cancelFinish();
			assert.deepEqual([finishShown().status, finishShown().cancelling], ['running', false]);
		}
		await settle();
	};
	await exportAndFinish();
	assert.ok(hostToasts.includes('Could not cancel the finishing: it goes on.'));
	assert.equal(finishShown().status, 'done');
});

test('finishing flow: the window says Cancelling until PotionUI answers', async () => {
	let answer = null;
	await open({ finishing: { grain: { on: true } }, reads: () => [{ status: 'running', progress: 0.3 }], cancelRun: (id) => new Promise((resolve) => (answer = () => resolve({ ok: true, data: { id, status: 'cancelled', progress: 0.3, label: '', items: [], error: null } }))) });
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	for (let i = 0; i < 5; i++) await settle();
	const pending = cancelFinish();
	await settle();
	assert.deepEqual([finishShown().status, finishShown().cancelling], ['running', true]);
	answer();
	await pending;
	assert.deepEqual([finishShown().status, finishShown().cancelling], ['cancelled', false]);
});

test('finishing flow: a cancel asked before PotionUI gave the run its id is sent as soon as the id comes', async () => {
	let started = null;
	await open({ finishing: { grain: { on: true } } });
	server.client.startMediaRun = (body) => {
		server.calls.push(['run', body]);
		return new Promise((resolve) => (started = () => resolve({ ok: true, data: { id: 'late' } })));
	};
	await startVideoExport({ format: 'web', resolution: '720p', finish: stepsNow() });
	await pollJob();
	await settle();
	await cancelFinish();
	assert.equal(finishShown().cancelling, true);
	started();
	await drain();
	assert.ok(server.calls.some(([kind, id]) => kind === 'cancel' && id === 'late'));
	assert.equal(finishShown().status, 'cancelled');
});

test('finishing flow: with the window closed, a failed finishing says so and that the plain export is kept', async () => {
	hostToasts.length = 0;
	await open({ finishing: { grain: { on: true } }, reads: [{ status: 'failed', error: { code: 'tool_failed', message: 'ffmpeg failed' } }] });
	await exportAndFinish();
	assert.ok(hostToasts.includes('The finishing failed: ffmpeg failed The plain export is still available.'));
});

test('finishing flow: with the window closed, a finishing cancelled in PotionUI says so', async () => {
	hostToasts.length = 0;
	await open({ finishing: { grain: { on: true } }, reads: [{ status: 'cancelled' }] });
	await exportAndFinish();
	assert.ok(hostToasts.includes('Finishing cancelled. The plain export is still available.'));
});

test('finishing flow: with the window open, the card tells and no toast is added', async () => {
	hostToasts.length = 0;
	await open({ finishing: { grain: { on: true } }, reads: [{ status: 'failed', error: { code: 'tool_failed', message: 'ffmpeg failed' } }] });
	ui.modal = { type: 'export' };
	await exportAndFinish();
	ui.modal = null;
	assert.equal(finishShown().status, 'failed');
	assert.deepEqual(hostToasts, []);
});

test('finishing flow: a refused limit shows the words of PotionUI, not a guess about storage', async () => {
	await open({ finishing: { grain: { on: true } }, start: { ok: false, error: { status: 403, code: 'limit_exceeded', message: 'Your plan allows 20 media tool runs a day' } } });
	await exportAndFinish();
	assert.equal(finishFailureText(finishShown()), 'The finishing failed: Your plan allows 20 media tool runs a day');
});

test('finishing flow: the choices are kept in the project, one undo step each, and a project without them stays as it was', async () => {
	await open({});
	assert.equal('finishing' in doc.master, false);
	setFinish('grain', { on: true });
	assert.deepEqual(doc.master.finishing, { grain: { on: true, amount: 30, size: 1.5 } });
	setFinish('grain', { amount: 70 });
	setFinish('grain', { on: false });
	assert.deepEqual(doc.master.finishing, { grain: { on: false, amount: 70, size: 1.5 } });
	undo();
	assert.deepEqual(doc.master.finishing.grain.on, true);
	undo();
	undo();
	assert.equal('finishing' in doc.master, false);
});

test('finishing flow: without the core catalog nothing is offered and an export stays plain', async () => {
	await open({ tools: false, finishing: { grain: { on: true } } });
	assert.deepEqual([finishState.tools, finishState.toolsFailed], [null, true]);
	const steps = await exportAndFinish();
	assert.deepEqual(steps, []);
	assert.equal(runs().length, 0);
});

test('finishing flow: a catalog that failed at the first opening is read again at the next one', async () => {
	let answers = [false];
	await open({ tools: () => answers.shift() });
	assert.deepEqual([finishState.tools, finishState.toolsFailed], [null, true]);
	await loadFinishing();
	assert.equal(finishState.toolsFailed, false);
	assert.deepEqual(finishState.tools.map((tool) => tool.id), ['film_grain', 'vignette', 'fix_colors', 'lut']);
});

test('finishing flow: a LUT installed after the first opening is offered at the next one', async () => {
	const more = [...TOOLS.slice(0, 3), normalizeTool({ id: 'lut', params: [{ name: 'lut', type: 'lut', options: [{ label: 'None', value: '' }, { label: 'warm', value: 'warm.cube' }, { label: 'cold', value: 'cold.cube' }] }, { name: 'strength', min: 0, max: 1 }] })];
	let answers = [TOOLS, more];
	await open({ tools: () => answers.shift() });
	const lutOptions = () => finishState.tools.find((tool) => tool.id === 'lut').params[0].options.map((option) => option.value);
	assert.deepEqual(lutOptions(), ['', 'warm.cube']);
	await loadFinishing();
	assert.deepEqual(lutOptions(), ['', 'warm.cube', 'cold.cube']);
	assert.equal(server.calls.filter(([kind]) => kind === 'tools').length, 2);
});

test('finishing flow: a job finished without a plan is left alone', async () => {
	await open({});
	assert.equal(await finishJob({ id: 'other', status: 'done', format: 'web', media: { itemId: 'x' } }), null);
	assert.equal(project.id, 'p1');
});

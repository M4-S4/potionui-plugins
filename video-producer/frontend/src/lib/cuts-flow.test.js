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

globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast() {} } } };

const { doc, ui, history, replaceDoc, undo, redo, select, dispose } = await import('./state.svelte.js');
const { bindClient, project } = await import('./project.svelte.js');
const { cuts, findCuts, cancelCuts } = await import('./cuts.svelte.js');
await import('./chain.svelte.js');
const { emptyDoc, newClip, newAsset } = await import('./starter.js');
const { setLocale } = await import('../i18n/index.svelte.js');

after(() => {
	dispose();
	delete globalThis.window;
});

const snapshot = () => JSON.parse(JSON.stringify(doc));

function piece(i, duration = 2) {
	return { id: `p${i}`, name: `trailer-shot ${i}.mp4`, mediaType: 'video', url: `/api/media/uploads/x${i}.mp4`, duration, width: 640, height: 360, fps: 24 };
}

function server(script) {
	const calls = [];
	const client = {
		async startMediaRun(body) {
			calls.push(['start', body]);
			return script.start ?? { ok: true, data: { id: 'run1' } };
		},
		async mediaRun(id) {
			calls.push(['read', id]);
			const next = script.reads.shift();
			return { ok: true, data: { id, status: next.status, progress: next.progress ?? 0, label: 'Find cuts', items: next.items ?? [], error: next.error ?? null } };
		},
		async cancelMediaRun(id) {
			calls.push(['cancel', id]);
			return { ok: true, data: { id, status: 'cancelled', progress: 0, label: '', items: [], error: null } };
		}
	};
	bindClient(client);
	return calls;
}

function setup() {
	const start = emptyDoc((key) => key);
	start.assets = [newAsset({ id: 'src', kind: 'video', name: 'trailer.mp4', src: '/api/media/uploads/t.mp4', origin: { kind: 'library', itemId: 'u-trailer' }, srcDur: 6 })];
	start.clips = [newClip({ id: 'a', label: 'Opening', start: 0, dur: 4 }), newClip({ id: 'b', label: 'Ending', start: 4, dur: 3 })];
	start.prompts = [{ id: 'pb', shotId: 'b', start: 4, dur: 3, strength: 75, text: 'the end' }];
	replaceDoc(start);
	project.id = 'p1';
	ui.selection = null;
	ui.toasts.length = 0;
}

const done = (items) => ({ status: 'completed', progress: 1, items });
const ticks = (fn = () => {}) => async () => fn();

beforeEach(() => {
	setLocale('en');
	setup();
});

test('cut import: as sources, the pieces become new shots at the end, in one undo step, with the request the core expects', async () => {
	const calls = server({ reads: [{ status: 'running', progress: 0.4 }, done([piece(1, 1.5), piece(2, 2.979), piece(3, 1)])] });
	const before = snapshot();
	const progress = [];
	const built = await findCuts({ assetId: 'src', sensitivity: 60, shortest: 0.8, mode: 'source' }, { wait: ticks(() => progress.push(cuts.progress)) });
	assert.equal(built.clips.length, 3);
	assert.deepEqual(calls[0], ['start', { steps: [{ tool: 'cut_finder', params: { sensitivity: 60, min_shot_seconds: 0.8 } }], inputs: [{ item_id: 'u-trailer' }], output: { mode: 'new' } }]);
	assert.deepEqual(progress, [0, 0.4]);
	assert.deepEqual(
		doc.clips.map((c) => [c.label, c.start, c.dur, c.stage]),
		[
			['Opening', 0, 4, 'todo'],
			['Ending', 4, 3, 'todo'],
			['trailer 1', 7, 1.48, 'source'],
			['trailer 2', 8.48, 2.96, 'source'],
			['trailer 3', 11.44, 1, 'source']
		]
	);
	const added = doc.clips.slice(2);
	assert.deepEqual(
		added.map((c) => doc.assets.find((a) => a.id === c.assetId)?.origin),
		[1, 2, 3].map((i) => ({ kind: 'library', itemId: `p${i}` }))
	);
	assert.ok(added.every((c) => c.firstFromPrevious === false));
	assert.deepEqual(doc.frames, []);
	assert.deepEqual(doc.references, before.references);
	assert.equal(ui.workspace, 'storyboard');
	assert.deepEqual(ui.selection, { kind: 'clip', id: added[0].id });
	assert.equal(ui.toasts.at(-1).message, '3 shots added from “trailer”, each with its piece.');
	assert.equal(cuts.status, 'idle');

	undo();
	assert.deepEqual(snapshot(), before);
	redo();
	assert.equal(doc.clips.length, 5);
	assert.equal(doc.assets.length, 4);
});

test('cut import: as motion references, the shots to generate go after the selected shot, and the later shot keeps its prompt', async () => {
	server({ reads: [done([piece(1), piece(2)])] });
	select('clip', 'a');
	const before = snapshot();
	await findCuts({ assetId: 'src', mode: 'motion', at: 'after' }, { wait: ticks() });
	assert.deepEqual(
		doc.clips.map((c) => [c.label, c.start, c.stage, c.assetId]),
		[
			['Opening', 0, 'todo', null],
			['trailer 1', 4, 'todo', null],
			['trailer 2', 6, 'todo', null],
			['Ending', 8, 'todo', null]
		]
	);
	assert.deepEqual(doc.prompts.find((p) => p.id === 'pb').start, 8);
	const refs = doc.references.filter((r) => r.scope?.type === 'shot');
	assert.deepEqual(
		refs.map((r) => [r.space, r.type, r.role, r.scope.shotId, doc.assets.find((a) => a.id === r.assetId)?.origin.itemId]),
		[
			['mouvement', 'Control video', 'Mouvement', doc.clips[1].id, 'p1'],
			['mouvement', 'Control video', 'Mouvement', doc.clips[2].id, 'p2']
		]
	);
	assert.equal(ui.toasts.at(-1).message, '2 shots to generate added from “trailer”, each with its piece as motion reference.');
	undo();
	assert.deepEqual(snapshot(), before);
});

test('cut import: the French page names its shots and says so in French', async () => {
	setLocale('fr');
	server({ reads: [done([piece(1), piece(2)])] });
	await findCuts({ assetId: 'src', mode: 'source' }, { wait: ticks() });
	assert.deepEqual(doc.clips.slice(2).map((c) => c.label), ['trailer 1', 'trailer 2']);
	assert.equal(ui.toasts.at(-1).message, '2 plans ajoutés depuis « trailer », chacun avec son morceau.');
});

test('cut import: no cut found, too many shots or a full queue leave the project untouched and say why', async () => {
	const before = snapshot();
	server({ reads: [{ status: 'failed', error: { code: 'tool_failed', message: 'No cuts were found; try a higher sensitivity' } }] });
	assert.equal(await findCuts({ assetId: 'src' }, { wait: ticks() }), null);
	assert.deepEqual([cuts.status, cuts.failure], ['failed', 'none']);

	server({ reads: [{ status: 'failed', error: { code: 'invalid_params', message: 'Found 230 shots, over the 200-shot limit; lower the sensitivity' } }] });
	await findCuts({ assetId: 'src' }, { wait: ticks() });
	assert.equal(cuts.failure, 'tooMany');

	const calls = server({ start: { ok: false, error: { status: 429, code: 'too_many_queued', message: 'You already have 8 runs waiting' } }, reads: [] });
	await findCuts({ assetId: 'src' }, { wait: ticks() });
	assert.deepEqual([cuts.failure, cuts.message], ['busy', 'You already have 8 runs waiting']);
	assert.deepEqual(calls.map(([kind]) => kind), ['start']);

	assert.deepEqual(snapshot(), before);
	assert.equal(history.canUndo, false);
});

test('cut import: stopping while the core cuts cancels the run and places nothing', async () => {
	let calls = null;
	let reads = 0;
	calls = server({ reads: [{ status: 'running', progress: 0.2 }, done([piece(1), piece(2)])] });
	const before = snapshot();
	const result = await findCuts(
		{ assetId: 'src' },
		{
			wait: async () => {
				reads += 1;
				if (reads === 2) await cancelCuts();
			}
		}
	);
	assert.equal(result, null);
	assert.deepEqual(calls.map(([kind, arg]) => [kind, typeof arg === 'string' ? arg : null]), [
		['start', null],
		['read', 'run1'],
		['cancel', 'run1']
	]);
	assert.equal(cuts.status, 'idle');
	assert.deepEqual(snapshot(), before);
});

test('cut import: a run the core cancels on its side ends quietly', async () => {
	server({ reads: [{ status: 'cancelled' }] });
	assert.equal(await findCuts({ assetId: 'src' }, { wait: ticks() }), null);
	assert.equal(cuts.status, 'idle');
	assert.equal(doc.clips.length, 2);
});

test('cut import: a run that ends after another project opened places nothing there', async () => {
	server({ reads: [done([piece(1), piece(2)])] });
	await findCuts({ assetId: 'src' }, { wait: ticks(() => (project.id = 'p2')) });
	assert.equal(doc.clips.length, 2);
	assert.equal(history.canUndo, false);
});

test('cut import: a gallery video goes by its file id, and a video the core cannot read is never sent', async () => {
	const calls = server({ reads: [done([piece(1), piece(2)])] });
	doc.assets.push(newAsset({ id: 'take', kind: 'video', name: 'take', src: '/m/t.mp4', origin: { kind: 'history', generationId: 'g1', fileId: 'f9' } }));
	doc.assets.push(newAsset({ id: 'local', kind: 'video', name: 'local', src: '/m/l.mp4', origin: null }));
	await findCuts({ assetId: 'take' }, { wait: ticks() });
	assert.deepEqual(calls[0][1].inputs, [{ generation_file_id: 'f9' }]);
	const again = server({ reads: [] });
	assert.equal(await findCuts({ assetId: 'local' }, { wait: ticks() }), null);
	assert.deepEqual(again, []);
});

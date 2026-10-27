import { test, after } from 'node:test';
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

globalThis.window = Object.assign(new EventTarget(), { __potionui: { confirm: async () => true, notifications: { toast() {} } } });

const { doc, ui, act, undo, history, dispose, addShot, onShotsAdded } = await import('./state.svelte.js');
const { project, bindClient, openProject, flushSave } = await import('./project.svelte.js');
const { startAssistant, applyChangeResult, applyPromptResult, contextSnapshot } = await import('./assistant.svelte.js');
const { emptyDoc, newClip } = await import('./starter.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = async () => {
	for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};

const server = { projects: new Map(), saves: [], gets: 0, gate: null };
bindClient({
	async getProject(id) {
		server.gets += 1;
		const p = server.projects.get(id);
		const read = { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null } };
		if (server.gate) await server.gate;
		return read;
	},
	async saveProject(id, next, version) {
		const p = server.projects.get(id);
		if (version !== p.version) return { ok: false, error: { status: 409, code: 'version_conflict', message: '', data: null } };
		p.doc = copy(next);
		p.version += 1;
		server.saves.push(version);
		return { ok: true, data: { id, name: p.doc.name, version: p.version, updatedAt: null } };
	},
	async listTakes() {
		return { ok: true, data: [] };
	},
	saveLastProject() {}
});
const stop = startAssistant();

after(() => {
	stop();
	dispose();
	delete globalThis.window;
});

async function opened(id) {
	const start = emptyDoc((key) => key);
	start.clips = ['Arrival', 'Bridge'].map((label, i) => newClip({ id: `s${i + 1}`, label, start: i * 4, dur: 4 }));
	server.projects.set(id, { doc: start, version: 1 });
	const result = await openProject(id);
	assert.equal(result.ok, true);
	return server.projects.get(id);
}

function assistantAdds(stored, label) {
	stored.doc.clips.push(newClip({ id: `a-${label}`, label, start: 8, dur: 3 }));
	stored.version += 1;
	return { project_id: project.id, version: stored.version, added: [{ id: `a-${label}` }] };
}

const labels = () => doc.clips.map((c) => c.label);

test('a change the assistant saved shows on the page, and Ctrl+Z takes it back and saves that', async () => {
	const stored = await opened('p-undo');

	const outcome = applyChangeResult('vp_add_shots', assistantAdds(stored, 'Close-up'));
	await settle();

	assert.deepEqual(outcome, { status: 'applied' });
	assert.deepEqual(labels(), ['Arrival', 'Bridge', 'Close-up']);
	assert.equal(project.version, 2);
	assert.equal(ui.dirty, false);
	assert.equal(history.canUndo, true);

	undo();
	await flushSave();

	assert.deepEqual(labels(), ['Arrival', 'Bridge']);
	assert.deepEqual(
		stored.doc.clips.map((c) => c.label),
		['Arrival', 'Bridge']
	);
	assert.equal(stored.version, 3);
});

test('an edit made on the page while the assistant worked is kept next to its change', async () => {
	const stored = await opened('p-both');
	act(() => (doc.clips[0].label = 'Arrival at night'));

	applyChangeResult('vp_add_shots', assistantAdds(stored, 'Close-up'));
	await settle();
	await flushSave();

	assert.deepEqual(labels(), ['Arrival at night', 'Bridge', 'Close-up']);
	assert.deepEqual(
		stored.doc.clips.map((c) => c.label),
		['Arrival at night', 'Bridge', 'Close-up']
	);
	assert.equal(stored.version, 3);
});

test('a save refused for an older version merges the server document instead of dropping the page edits', async () => {
	const stored = await opened('p-conflict');
	assistantAdds(stored, 'Close-up');
	act(() => (doc.clips[1].label = 'Bridge at dawn'));

	await flushSave();
	await flushSave();

	assert.deepEqual(labels(), ['Arrival', 'Bridge at dawn', 'Close-up']);
	assert.deepEqual(
		stored.doc.clips.map((c) => c.label),
		['Arrival', 'Bridge at dawn', 'Close-up']
	);
	assert.equal(project.version, stored.version);
});

test('the end of a tool the page follows live pulls the project before the turn ends', async () => {
	const stored = await opened('p-live');
	assistantAdds(stored, 'Insert');
	const before = server.gets;

	window.dispatchEvent(new CustomEvent('potionui:tool-end', { detail: { tool_name: 'vp_add_shots', success: true } }));
	window.dispatchEvent(new CustomEvent('potionui:tool-end', { detail: { tool_name: 'vp_get_project', success: true } }));
	await settle();

	assert.deepEqual(labels(), ['Arrival', 'Bridge', 'Insert']);
	assert.equal(server.gets - before, 1);
	assert.deepEqual(applyChangeResult('vp_add_shots', { project_id: project.id, version: stored.version }), { status: 'noop' });
});

test('a result for another project changes nothing here', async () => {
	await opened('p-other');

	assert.equal(applyChangeResult('vp_update_shots', { project_id: 'elsewhere', version: 9 }).status, 'stale');
	assert.deepEqual(labels(), ['Arrival', 'Bridge']);
});

test('sending a message saves the pending edits first, so the tools read what the page shows', async () => {
	const stored = await opened('p-flush');
	act(() => (doc.clips[0].label = 'Renamed'));
	ui.dirty = true;

	const snapshot = contextSnapshot();
	await settle();

	assert.equal(snapshot.projectId, 'p-flush');
	assert.equal(stored.doc.clips[0].label, 'Renamed');
});

test('an approved prompt that comes two versions ahead is merged, not reloaded, so the page keeps its edits and its undo', async () => {
	const stored = await opened('p-prompt');
	act(() => (doc.clips[1].label = 'Bridge at dawn'));
	assistantAdds(stored, 'Insert');
	stored.doc.prompts.push({ id: 'pr-1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'Wide shot of the dock' });
	stored.version += 1;

	const outcome = applyPromptResult('vp_write_shot_prompt', { project_id: project.id, shot_id: 's1', prompt_id: 'pr-1', text: 'Wide shot of the dock', version: stored.version });
	await settle();
	await flushSave();

	assert.deepEqual(outcome, { status: 'applied' });
	assert.deepEqual(labels(), ['Arrival', 'Bridge at dawn', 'Insert']);
	assert.equal(doc.prompts.find((p) => p.shotId === 's1')?.text, 'Wide shot of the dock');
	assert.equal(history.canUndo, true);
	assert.deepEqual(
		stored.doc.clips.map((c) => c.label),
		['Arrival', 'Bridge at dawn', 'Insert']
	);
});

const spans = (clips) => clips.map((c) => [c.label, c.start, c.dur]);

function assistantOpens(stored) {
	const opening = newClip({ id: 'a-open', label: 'Opening', start: 0, dur: 3 });
	stored.doc.clips = [opening, ...stored.doc.clips.map((c) => ({ ...c, start: c.start + 3 }))];
	stored.version += 1;
	return { project_id: project.id, version: stored.version, added: [{ id: 'a-open' }] };
}

test('a shot the assistant adds at the start and one added at the end on the page are laid out end to end, on the page and on the server', async () => {
	const stored = await opened('p-layout');
	addShot('Exit', '', 2);
	assert.deepEqual(spans(doc.clips), [
		['Arrival', 0, 4],
		['Bridge', 4, 4],
		['Exit', 8, 2]
	]);

	applyChangeResult('vp_add_shots', assistantOpens(stored));
	await settle();
	await flushSave();

	const laid = [
		['Opening', 0, 3],
		['Arrival', 3, 4],
		['Bridge', 7, 4],
		['Exit', 11, 2]
	];
	assert.deepEqual(spans(doc.clips), laid);
	assert.deepEqual(spans(stored.doc.clips), laid);
	assert.equal(ui.dirty, false);
});

test('an image a merged shot gets as it lands is saved, not taken for saved', async () => {
	const stored = await opened('p-chain');
	const off = onShotsAdded((clips) => {
		for (const clip of clips) doc.frames.push({ id: `chain-${clip.id}`, shotId: clip.id, time: clip.start, assetId: 'still', role: 'first', strength: 100 });
	});

	applyChangeResult('vp_add_shots', assistantAdds(stored, 'Close-up'));
	await settle();
	off();

	assert.equal(ui.dirty, true);
	await flushSave();
	assert.deepEqual(
		stored.doc.frames.map((f) => f.id),
		['chain-a-Close-up']
	);
	assert.equal(ui.dirty, false);
});

test('the end of a tool that comes while the page is still reading the project is read after it', async () => {
	const stored = await opened('p-queue');
	let open;
	server.gate = new Promise((resolve) => (open = resolve));
	assistantAdds(stored, 'Insert');
	window.dispatchEvent(new CustomEvent('potionui:tool-end', { detail: { tool_name: 'vp_add_shots', success: true } }));
	await settle();
	server.gate = null;
	stored.doc.clips[0].label = 'Arrival at night';
	stored.version += 1;
	window.dispatchEvent(new CustomEvent('potionui:tool-end', { detail: { tool_name: 'vp_update_shots', success: true } }));
	open();
	await settle();

	assert.deepEqual(labels(), ['Arrival at night', 'Bridge', 'Insert']);
	assert.equal(project.version, stored.version);
});

test('a shot the assistant deleted while the page edited it goes whole with a warning, and Ctrl+Z brings it back with the edit', async () => {
	const stored = await opened('p-delete');
	stored.doc.prompts = [{ id: 'pb', shotId: 's2', start: 4, dur: 4, strength: 75, text: 'The bridge at dawn' }];
	stored.version += 1;
	await openProject('p-delete');
	act(() => (doc.clips[1].label = 'Bridge at dawn'));
	stored.doc.clips = stored.doc.clips.slice(0, 1);
	stored.doc.prompts = [];
	stored.version += 1;
	ui.toasts.length = 0;

	applyChangeResult('vp_delete_shots', { project_id: project.id, version: stored.version, deleted: ['s2'] });
	await settle();

	assert.deepEqual(labels(), ['Arrival']);
	assert.deepEqual(doc.prompts, []);
	assert.match(ui.toasts.at(-1).message, /deleted 1 shot you had edited/);

	undo();
	await flushSave();

	assert.deepEqual(labels(), ['Arrival', 'Bridge at dawn']);
	assert.equal(doc.prompts[0].text, 'The bridge at dawn');
	assert.deepEqual(
		stored.doc.clips.map((c) => c.label),
		['Arrival', 'Bridge at dawn']
	);
});

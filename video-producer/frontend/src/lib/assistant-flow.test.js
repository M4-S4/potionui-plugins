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

const { doc, ui, act, undo, history, dispose } = await import('./state.svelte.js');
const { project, bindClient, openProject, flushSave } = await import('./project.svelte.js');
const { startAssistant, applyChangeResult, applyPromptResult, contextSnapshot } = await import('./assistant.svelte.js');
const { emptyDoc, newClip } = await import('./starter.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = async () => {
	for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};

const server = { projects: new Map(), saves: [], gets: 0 };
bindClient({
	async getProject(id) {
		server.gets += 1;
		const p = server.projects.get(id);
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null } };
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

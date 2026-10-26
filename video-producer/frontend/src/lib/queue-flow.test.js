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

const notes = [];
globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast: (level, message) => notes.push(message) } } };
globalThis.document = { body: {}, querySelector: () => null };

const { doc, ui, applyMe, select, pickClip, pickedClips, undo, dispose, deleteSelection } = await import('./state.svelte.js');
const { bindClient, openProject } = await import('./project.svelte.js');
const { startProduction, busy, jobClips, readiness } = await import('./production.svelte.js');
const { takeStore } = await import('./takes.svelte.js');
const { IS_MAC, handleKeydown } = await import('./commands.js');
const { normalizeTake } = await import('./api.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { t } = await import('../i18n/index.svelte.js');

const WAN = '01KX47WANVIDEO0000000000TV';
const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const projects = new Map();
const sent = { generate: [], cancel: [] };
let made = 0;

function row(projectId, shotId, extra = {}) {
	made += 1;
	return normalizeTake({ id: `t${made}`, project_id: projectId, shot_id: shotId, generation_id: null, kind: 'render', quality: 'draft', status: 'queued', variant: 'A', label: 'draft', created_at: '2026-10-26T10:00:00Z', ...extra });
}

bindClient({
	async getProject(id) {
		const p = projects.get(id);
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null, unchanged: false } };
	},
	async saveProject(id, next) {
		const p = projects.get(id);
		p.doc = copy(next);
		p.version += 1;
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: null, createdAt: null, updatedAt: null, unchanged: false } };
	},
	async listTakes(id) {
		return { ok: true, data: projects.get(id).takes.map((x) => copy(x)) };
	},
	async queue(id) {
		const active = projects.get(id).takes.filter((x) => x.status === 'queued' || x.status === 'running');
		return { ok: true, data: { takes: active.map((x) => copy(x)), keyframes: [], slots: null, elsewhere: null, positions: {} } };
	},
	async generate(id, body) {
		sent.generate.push(copy(body));
		const created = body.shots.map((shotId) => row(id, shotId));
		projects.get(id).takes.push(...created);
		return { ok: true, data: created.map((x) => copy(x)) };
	},
	async cancelTake(takeId) {
		sent.cancel.push(takeId);
		for (const p of projects.values()) {
			const take = p.takes.find((x) => x.id === takeId);
			if (take) take.status = 'cancelled';
			if (take) return { ok: true, data: copy(take) };
		}
		return { ok: false, error: { status: 404 } };
	},
	saveLastProject() {}
});
const stop = startProduction();
applyMe({
	engines: [{ id: 'native', name: 'Local Generation', kind: 'local' }],
	presets: [{ id: WAN, name: 'Wan', video: true, cloud: false, profiles: ['FL2VA'], limits: { maxDuration: 10 } }]
});

after(() => {
	stop();
	dispose();
	delete globalThis.window;
	delete globalThis.document;
});

async function open(id, takes = []) {
	const start = emptyDoc((key) => key);
	start.direction.univers = 'A harbour at dawn.';
	start.engine = { ...start.engine, preset: WAN, model: null, backend: 'native' };
	start.clips = ['s1', 's2', 's3', 's4'].map((shotId, i) => newClip({ id: shotId, label: `Shot ${i + 1}`, start: i * 4, dur: 4 }));
	start.prompts = start.clips.map((c, i) => ({ id: `p${i + 1}`, shotId: c.id, start: c.start, dur: 4, strength: 75, text: `Shot ${i + 1} at dawn.` }));
	projects.set(id, { doc: start, version: 1, takes });
	const result = await openProject(id);
	assert.equal(result.ok, true);
	while (!takeStore.loaded) await settle();
	await settle();
	Object.assign(ui, { workspace: 'storyboard', modal: null, paletteOpen: false, hostModal: false, toasts: [] });
	ui.production.target = 'clip';
	sent.generate.length = 0;
	sent.cancel.length = 0;
}

function press(key, { target = undefined } = {}) {
	let prevented = false;
	handleKeydown({ key, code: `Key${key.toUpperCase()}`, ctrlKey: !IS_MAC, metaKey: IS_MAC, altKey: false, shiftKey: false, repeat: false, target, preventDefault: () => (prevented = true) }, { contains: (el) => el !== OUTSIDE });
	return prevented;
}
const OUTSIDE = { tagName: 'BUTTON' };

async function drained() {
	for (let i = 0; i < 20; i++) await settle();
}

test('queue flow: Ctrl+G while a take runs adds the target to the queue instead of refusing it', async () => {
	await open('p-run', [row('p-run', 's1', { status: 'running', generation_id: 'g-1', progress: 30 })]);
	assert.equal(busy(), true);
	select('clip', 's2');
	assert.ok(press('g'));
	await drained();
	assert.deepEqual(sent.generate.map((b) => b.shots), [['s2']]);
	const toast = ui.toasts.at(-1);
	assert.equal(toast.message, t('generation.toast.queued', { count: 1 }));
	assert.equal(toast.action.label, t('shell.toast.undo'));
	assert.ok(!notes.includes('A generation is already running.'));
});

test('queue flow: Annuler on the message cancels only the takes it just queued', async () => {
	await open('p-undo', [row('p-undo', 's1', { status: 'running', generation_id: 'g-9' })]);
	select('clip', 's3');
	press('g');
	await drained();
	const created = projects.get('p-undo').takes.filter((x) => x.shotId === 's3').map((x) => x.id);
	await ui.toasts.at(-1).action.run();
	assert.deepEqual(sent.cancel, created);
	assert.equal(projects.get('p-undo').takes.find((x) => x.shotId === 's1').status, 'running');
	assert.equal(notes.at(-1), t('generation.toast.queueUndone', { count: 1 }));
});

test('queue flow: a shot that already has a take on its way gets one more, and the message says so', async () => {
	await open('p-again', [row('p-again', 's2', { status: 'queued' })]);
	select('clip', 's2');
	press('g');
	await drained();
	assert.deepEqual(sent.generate.map((b) => b.shots), [['s2']]);
	assert.equal(ui.toasts.at(-1).message, t('generation.toast.queuedAgain', { count: 1, again: 1 }));
});

test('queue flow: two quick Ctrl+G go out one after the other, in the order they were pressed', async () => {
	await open('p-twice');
	select('clip', 's1');
	press('g');
	select('clip', 's2');
	press('g');
	await drained();
	assert.deepEqual(sent.generate.map((b) => b.shots), [['s1'], ['s2']]);
});

test('queue flow: the picked shots are the target, in the order of the edit, whatever the target of the bar', async () => {
	await open('p-picked');
	ui.production.target = 'sequence';
	select('clip', 's4');
	pickClip('s1', 'toggle');
	pickClip('s3', 'toggle');
	assert.deepEqual(pickedClips().map((c) => c.id), ['s1', 's3', 's4']);
	assert.deepEqual(jobClips().map((c) => c.id), ['s1', 's3', 's4']);
	assert.deepEqual(readiness().items.prompts.map((p) => p.id), ['p1', 'p3', 'p4']);
	press('g');
	await drained();
	assert.deepEqual(sent.generate.map((b) => b.shots), [['s1', 's3', 's4']]);
	pickClip('s2', 'range');
	assert.deepEqual(pickedClips().map((c) => c.id), ['s2', 's3']);
	select('clip', 's1');
	assert.deepEqual(pickedClips(), []);
	assert.deepEqual(jobClips().map((c) => c.id), ['s1', 's2', 's3', 's4']);
});

test('queue flow: Delete removes every picked shot in one step that Ctrl+Z brings back', async () => {
	await open('p-delete');
	select('clip', 's2');
	pickClip('s3', 'toggle');
	deleteSelection();
	assert.deepEqual(doc.clips.map((c) => c.id), ['s1', 's4']);
	assert.deepEqual([ui.selection, pickedClips()], [null, []]);
	undo();
	assert.deepEqual(doc.clips.map((c) => c.id), ['s1', 's2', 's3', 's4']);
});

test('queue flow: Esc clears the picked shots with the selection', async () => {
	await open('p-escape');
	select('clip', 's1');
	pickClip('s2', 'toggle');
	handleKeydown({ key: 'Escape', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, target: undefined, preventDefault() {} }, null);
	assert.deepEqual([ui.selection, pickedClips()], [null, []]);
});

test('queue flow: Ctrl+G from a text field of the page leaves the field first, the browser never gets it, an open window keeps it', async () => {
	await open('p-field');
	select('clip', 's1');
	let left = false;
	assert.ok(press('g', { target: { tagName: 'TEXTAREA', blur: () => (left = true) } }));
	await drained();
	assert.equal(left, true);
	assert.deepEqual(sent.generate.map((b) => b.shots), [['s1']]);
	ui.modal = { type: 'shot', id: 's1' };
	assert.ok(press('g'));
	await drained();
	assert.equal(sent.generate.length, 1);
	ui.modal = null;
	assert.ok(press('g', { target: OUTSIDE }));
	await drained();
	assert.equal(sent.generate.length, 1);
	assert.equal(press('y', { target: { tagName: 'INPUT', blur() {} } }), false);
});

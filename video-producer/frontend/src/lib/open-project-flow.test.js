import { test } from 'node:test';
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

const { doc, ui } = await import('./state.svelte.js');
const { project, bindClient, openProject, deleteProject } = await import('./project.svelte.js');
const { emptyDoc } = await import('./starter.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const t = (key) => key;

const server = { projects: new Map(), deleted: [], created: 0, saves: 0 };
const put = (id, name) => server.projects.set(id, { version: 1, doc: { ...emptyDoc(t), name } });
bindClient({
	async getProject(id) {
		const p = server.projects.get(id);
		if (!p) return { ok: false, error: { status: 404, code: 'project_not_found', message: '', data: null } };
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null } };
	},
	async saveProject(id, next, version) {
		const p = server.projects.get(id);
		if (!p) return { ok: false, error: { status: 404, code: 'project_not_found', message: '', data: null } };
		if (version !== p.version) return { ok: false, error: { status: 409, code: 'version_conflict', message: '', data: null } };
		server.saves += 1;
		p.doc = copy(next);
		p.version += 1;
		return { ok: true, data: { version: p.version, updatedAt: null } };
	},
	async deleteProject(id) {
		server.deleted.push(id);
		server.projects.delete(id);
		return { ok: true, data: { deleted: id } };
	},
	async createProject(source) {
		server.created += 1;
		const id = `new${server.created}`;
		server.projects.set(id, { version: 1, doc: copy(source) });
		return { ok: true, data: { id, version: 1, doc: copy(source), createdAt: null, updatedAt: null } };
	},
	async listProjects() {
		return { ok: true, data: [...server.projects.keys()].map((id) => ({ id, name: server.projects.get(id).doc.name })) };
	},
	saveLastProject() {}
});

test('deleting another project leaves the open one alone', async () => {
	put('p1', 'One');
	put('p2', 'Two');
	put('p3', 'Three');
	assert.ok((await openProject('p1')).ok);
	assert.equal(project.id, 'p1');
	const result = await deleteProject('p3');
	assert.ok(result.ok);
	assert.deepEqual(server.deleted, ['p3']);
	assert.equal(project.id, 'p1');
	assert.equal(doc.name, 'One');
});

test('deleting the open project opens the previous one, without saving the deleted one again', async () => {
	doc.name = 'One edited';
	const result = await deleteProject('p1', 'p2');
	assert.ok(result.ok);
	assert.deepEqual(server.deleted, ['p3', 'p1']);
	assert.equal(project.id, 'p2');
	assert.equal(doc.name, 'Two');
	assert.equal(ui.dirty, false);
	await new Promise((resolve) => setTimeout(resolve, 900));
	assert.ok(!server.deleted.includes('p2'));
	assert.equal(server.projects.has('p1'), false);
});

test('deleting the only project puts an empty project in its place', async () => {
	const result = await deleteProject('p2', null);
	assert.ok(result.ok);
	assert.equal(server.created, 1);
	assert.equal(project.id, 'new1');
	assert.equal(doc.clips.length, 0);
	assert.equal(project.fatal, null);
});

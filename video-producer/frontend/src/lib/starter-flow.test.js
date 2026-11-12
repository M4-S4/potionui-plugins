import { test, beforeEach } from 'node:test';
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

const toasts = [];
globalThis.window = Object.assign(new EventTarget(), { __potionui: { confirm: async () => true, notifications: { toast: (...args) => (toasts.push(args), true) } } });

const { doc, ui } = await import('./state.svelte.js');
const { project, bindClient, openLatestOrStarter, projectGone } = await import('./project.svelte.js');
const { emptyDoc } = await import('./starter.js');
const { t } = await import('../i18n/index.svelte.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const image = (name, itemId) => ({ itemId, url: `/api/media/uploads/${itemId}.jpg`, filename: `${name}.jpg`, width: 1024, height: 1024 });
const server = { projects: new Map(), created: 0, asked: 0, images: null };

bindClient({
	async getProject(id) {
		const p = server.projects.get(id);
		if (!p) return { ok: false, error: { status: 404, code: 'project_not_found', message: '', data: null } };
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null } };
	},
	async saveProject(id, next, version) {
		const p = server.projects.get(id);
		if (!p) return { ok: false, error: { status: 404, code: 'project_not_found', message: '', data: null } };
		p.doc = copy(next);
		p.version = version + 1;
		return { ok: true, data: { version: p.version, updatedAt: null } };
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
	async starterImages() {
		server.asked += 1;
		return server.images();
	},
	saveLastProject() {}
});

const stored = () => ({ ok: true, data: { lumi: image('lumi', 'i1'), bottle: image('bottle', 'i2'), 'bottle-gold': image('bottle-gold', 'i3') } });
const refused = () => ({ ok: false, error: { status: 502, code: 'starter_images_failed', message: 'full', data: { image: 'bottle', code: 'limit_exceeded' } } });
const unreachable = () => {
	throw new Error('network down');
};
const warned = () => toasts.filter(([level, message]) => level === 'warning' && message === t('project.toast.starterImages')).length;

beforeEach(() => {
	server.projects.clear();
	toasts.length = 0;
	ui.me = { lastProjectId: null };
	Object.assign(project, { id: null, version: 0, status: 'idle', error: null });
});

test('a first visit asks the server for the three images and opens Lumi with them, without a warning', async () => {
	server.images = stored;
	const asked = server.asked;
	const result = await openLatestOrStarter();
	assert.ok(result.ok);
	assert.equal(server.asked, asked + 1);
	const saved = server.projects.get(project.id).doc;
	assert.deepEqual(
		saved.assets.map((a) => [a.name, a.origin]),
		[
			['lumi.jpg', { kind: 'library', itemId: 'i1' }],
			['bottle.jpg', { kind: 'library', itemId: 'i2' }],
			['bottle-gold.jpg', { kind: 'library', itemId: 'i3' }]
		]
	);
	assert.deepEqual(saved.bible.characters[0].references, [saved.references[0].id]);
	assert.deepEqual(
		saved.frames.map((f) => [f.shotId, f.role, saved.assets.find((a) => a.id === f.assetId).name]),
		[
			[saved.clips[3].id, 'first', 'bottle.jpg'],
			[saved.clips[3].id, 'last', 'bottle-gold.jpg']
		]
	);
	assert.equal(doc.assets.length, 3);
	assert.equal(warned(), 0);
});

for (const [why, answer] of [
	['the server refuses them', refused],
	['the server cannot be reached', unreachable]
]) {
	test(`when ${why}, the starter project still opens, whole but without images, and the user is warned once`, async () => {
		server.images = answer;
		const created = server.created;
		const result = await openLatestOrStarter();
		assert.ok(result.ok);
		assert.equal(server.created, created + 1);
		const saved = server.projects.get(project.id).doc;
		assert.equal(saved.clips.length, 4);
		assert.equal(saved.bible.characters.length, 1);
		for (const key of ['assets', 'references', 'frames']) assert.deepEqual(saved[key], [], key);
		assert.deepEqual(saved.bible.characters[0].references, []);
		assert.equal(project.status, 'saved');
		assert.equal(warned(), 1);
	});
}

test('the images are asked only when the starter project is made: never for a user who still has a project', async () => {
	server.images = stored;
	server.projects.set('kept', { version: 3, doc: { ...emptyDoc(t), name: 'Kept' } });
	const asked = server.asked;
	assert.ok((await openLatestOrStarter()).ok);
	assert.equal(project.id, 'kept');
	assert.equal(server.asked, asked);
	server.projects.clear();
	ui.me = { lastProjectId: null };
	assert.ok((await openLatestOrStarter()).ok);
	assert.notEqual(project.id, 'kept');
	assert.equal(server.asked, asked + 1);
});

test('a user who deleted everything gets the starter again, built on the images the server answers that time', async () => {
	server.images = stored;
	await openLatestOrStarter();
	const first = project.id;
	const before = server.projects.get(first).doc;
	server.projects.delete(first);
	const asked = server.asked;
	await projectGone(first);
	assert.notEqual(project.id, first);
	assert.equal(server.asked, asked + 1);
	const again = server.projects.get(project.id).doc;
	assert.deepEqual(
		again.assets.map((a) => a.origin.itemId),
		before.assets.map((a) => a.origin.itemId)
	);
	assert.notDeepEqual(
		again.assets.map((a) => a.id),
		before.assets.map((a) => a.id)
	);
});

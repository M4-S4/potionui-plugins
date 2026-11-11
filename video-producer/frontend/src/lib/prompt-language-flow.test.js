import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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

globalThis.window = Object.assign(new EventTarget(), { __potionui: { confirm: async () => true, notifications: { toast: () => true } } });

const { doc, ui } = await import('./state.svelte.js');
const { project, bindClient, openLatestOrStarter, openProject, createProject } = await import('./project.svelte.js');
const { emptyDoc } = await import('./starter.js');
const { templates, tplText, defaultVars, varToken } = await import('./library.svelte.js');
const { t, setLocale } = await import('../i18n/index.svelte.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const image = (name, itemId, height) => ({ itemId, url: `/api/media/uploads/${itemId}.jpg`, filename: `${name}.jpg`, width: 1024, height });
const server = { projects: new Map(), created: 0 };

bindClient({
	async getProject(id) {
		const p = server.projects.get(id);
		if (!p) return { ok: false, error: { status: 404, code: 'project_not_found', message: '', data: null } };
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null } };
	},
	async saveProject(id, next, version) {
		const p = server.projects.get(id);
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
		return { ok: true, data: { lumi: image('lumi', 'i1', 1024), bottle: image('bottle', 'i2', 576), 'bottle-gold': image('bottle-gold', 'i3', 576) } };
	},
	saveLastProject() {}
});

beforeEach(() => {
	server.projects.clear();
	setLocale('fr');
	ui.me = { lastProjectId: null };
	Object.assign(project, { id: null, version: 0, status: 'idle', error: null });
});

test('the project properties and the preferences no longer offer a prompt language, in either interface language', () => {
	const modals = readFileSync(new URL('../components/modals/Modals.svelte', import.meta.url), 'utf8');
	assert.doesNotMatch(modals, /promptLanguage|setPromptLanguage/);
	for (const locale of ['en', 'fr']) {
		const strings = readFileSync(new URL(`../i18n/${locale}/project.json`, import.meta.url), 'utf8');
		assert.doesNotMatch(strings, /promptLanguage/, locale);
	}
});

test('with the interface in French, the starter project keeps French names but writes its direction, cards and prompts in English', async () => {
	const result = await openLatestOrStarter();
	assert.ok(result.ok);
	const saved = server.projects.get(project.id).doc;
	assert.equal(saved.promptLanguage, 'en');
	assert.equal(saved.name, 'La potion de Lumi');
	assert.deepEqual(
		saved.clips.map((c) => c.label),
		['L’atelier', 'La potion', 'Lumi', 'Du violet à l’or']
	);
	assert.match(saved.prompts[0].text, /^Wide establishing shot of the empty workshop at night/);
	assert.match(saved.bible.characters[0].text, /^a woman in her thirties/);
	assert.match(saved.direction.univers, /^A witch's cottage workshop at night/);
	assert.deepEqual(saved.references.map((r) => r.name), ['Lumi', 'Potion bottle']);
});

test('with the interface in French, a new project is an English prompt project', async () => {
	const result = await createProject();
	assert.ok(result.ok);
	assert.equal(server.projects.get(project.id).doc.promptLanguage, 'en');
	assert.equal(emptyDoc(t, 'fr').promptLanguage, 'en');
});

test('a project an earlier version set to French opens unchanged, and what the page composes for it afterwards is English', async () => {
	const old = { ...emptyDoc(t), promptLanguage: 'fr' };
	old.direction = { ...old.direction, univers: 'Un port au petit matin.' };
	server.projects.set('old', { version: 3, doc: old });
	const result = await openProject('old');
	assert.ok(result.ok);
	assert.equal(doc.promptLanguage, 'fr');
	assert.equal(doc.direction.univers, 'Un port au petit matin.');
	assert.equal(tplText(templates[0]), 'Slow dolly in toward {subject} in {place}, steady continuous movement over {duration}.');
	assert.equal(varToken('subject'), 'subject');
	assert.equal(defaultVars().light, 'low golden light');
});

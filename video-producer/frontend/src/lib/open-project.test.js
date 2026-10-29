import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import './svelte-harness.js';
import enCommands from '../i18n/en/commands.json' with { type: 'json' };
import frCommands from '../i18n/fr/commands.json' with { type: 'json' };
import enProject from '../i18n/en/project.json' with { type: 'json' };
import frProject from '../i18n/fr/project.json' with { type: 'json' };
import enLib from '../i18n/en/lib.json' with { type: 'json' };
import frLib from '../i18n/fr/lib.json' with { type: 'json' };

const asked = [];
globalThis.window.__potionui.confirm = async (options) => (asked.push(options), true);

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project, bindClient } = await import('./project.svelte.js');
const { commandById } = await import('./commands.js');
const { confirm } = await import('./host.js');
const { t } = await import('../i18n/index.svelte.js');

const copy = (value) => JSON.parse(JSON.stringify(value));
const server = { projects: new Map(), created: 0 };
bindClient({
	async getProject(id) {
		const p = server.projects.get(id);
		return p ? { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null } } : { ok: false, error: { status: 404, code: 'project_not_found', message: '', data: null } };
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
	saveLastProject() {}
});

after(() => dispose());

test('projects: New project creates at once without asking anything when nothing waits to be saved, so its label carries no ellipsis in either language', async () => {
	assert.equal(frCommands['cmd.new-project'], 'Nouveau projet');
	assert.equal(enCommands['cmd.new-project'], 'New project');
	ui.dirty = false;
	await commandById('new-project').run();
	assert.equal(server.created, 1);
	assert.equal(project.id, 'new1');
	assert.equal(doc.name, t('lib.default.project'));
	assert.deepEqual(asked, []);
});

test('projects: a confirmation always offers Cancel in the current language, and the texts of a deletion name the project', async () => {
	await confirm({ title: 'Delete', message: 'Sure?', confirmLabel: 'Delete' });
	assert.equal(asked.at(-1).cancelLabel, t('lib.cancel'));
	assert.equal(asked.at(-1).confirmLabel, 'Delete');
	assert.equal(frLib.cancel, 'Annuler');
	assert.equal(enLib.cancel, 'Cancel');
	for (const [locale, texts] of [['en', enProject], ['fr', frProject]]) {
		assert.equal(texts['delete.cancel'], undefined, locale);
		assert.match(texts['delete.message'], /\{name\}/, locale);
		assert.match(texts['delete.messageCurrent'], /\{name\}/, locale);
		assert.match(texts['delete.messageLast'], /\{name\}/, locale);
		assert.ok(texts['delete.confirm'], locale);
	}
});

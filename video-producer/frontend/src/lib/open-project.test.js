import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const json = (locale, domain) => JSON.parse(read(`../i18n/${locale}/${domain}.json`));

test('projects: New project creates at once, so its label carries no ellipsis in either language', () => {
	assert.equal(json('fr', 'commands')['cmd.new-project'], 'Nouveau projet');
	assert.equal(json('en', 'commands')['cmd.new-project'], 'New project');
	assert.match(read('commands.js'), /command\('new-project', \(\) => createProject\(\)\)/);
});

test('projects: Open a project lets the open project be deleted too, after a confirmation in the current language, and switches to the previous project or to an empty one', () => {
	const modal = read('../components/modals/OpenProject.svelte');
	assert.doesNotMatch(modal, /\{#if p\.id !== project\.id\}\s*<HostUi name="IconButton" props=\{\{ icon: 'trash'/);
	assert.match(modal, /<HostUi name="IconButton" props=\{\{ icon: 'trash', label: t\('project\.delete\.label', \{ name: nameOf\(p\) \}\), tooltip: t\('project\.delete\.title'\), size: 'sm', class: 'vp-h7', disabled: busy, onclick: \(\) => remove\(p\) \}\} \/>/);
	assert.match(modal, /const current = p\.id === project\.id;\n\t\tconst next = current \? \(projects\.find\(\(x\) => x\.id !== p\.id\)\?\.id \?\? null\) : null;/);
	assert.match(modal, /confirmLabel: t\('project\.delete\.confirm'\) \}\);/);
	assert.doesNotMatch(modal, /cancelLabel/);
	assert.match(modal, /const result = await deleteProject\(p\.id, next\);/);
	assert.match(modal, /if \(current\) return load\(\);/);
	for (const locale of ['en', 'fr']) {
		const project = json(locale, 'project');
		assert.equal(project['delete.cancel'], undefined, locale);
		assert.match(project['delete.messageCurrent'], /\{name\}/, locale);
		assert.match(project['delete.messageLast'], /\{name\}/, locale);
	}
	assert.equal(json('fr', 'lib').cancel, 'Annuler');
	assert.equal(json('en', 'lib').cancel, 'Cancel');
	assert.match(read('host.js'), /return Boolean\(await host\(\{ cancelLabel: t\('lib\.cancel'\), \.\.\.options \}\)\);/);
	const store = read('project.svelte.js');
	assert.match(store, /export async function deleteProject\(id, nextId = null\) \{\n\tconst current = id === project\.id;/);
	assert.match(store, /const opened = nextId \? await openProject\(nextId\) : await openCreated\(emptyDoc\(t\)\);\n\tif \(!opened\.ok\) project\.fatal = opened\.error;/);
});

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
globalThis.document = { body: {}, querySelector: () => null };

const { doc, replaceDoc, itemsOf, itemsIn, dispose } = await import('./state.svelte.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { isGlobal, ownsReference } = await import('./shots.js');
const { referenceTags } = await import('./reftags.js');

after(() => {
	dispose();
	delete globalThis.window;
	delete globalThis.document;
});

const reference = (id, scope) => ({ id, name: id, space: 'identite', type: 'image', assetId: null, role: 'Identité', scope });

function project() {
	replaceDoc({
		...emptyDoc((key) => key),
		clips: [newClip({ id: 's1', start: 0, dur: 4 }), newClip({ id: 's2', start: 4, dur: 4 })],
		references: [reference('loose', null), reference('global', { type: 'global' }), reference('own', { type: 'shot', shotId: 's2' })]
	});
}

test('a reference whose scope is null, as the schema allows, is read as a reference of the project', () => {
	project();
	const [loose, global, own] = doc.references;
	assert.deepEqual([isGlobal(loose), isGlobal(global), isGlobal(own)], [true, true, false]);
	assert.equal(ownsReference(doc.clips[1], loose), false);
	assert.deepEqual(itemsOf([doc.clips[0]]).references.map((r) => r.id), ['loose', 'global']);
	assert.deepEqual(itemsIn([4, 8]).references.map((r) => r.id), ['loose', 'global', 'own']);
	assert.deepEqual(referenceTags(doc, loose).find((tag) => tag.kind === 'scope'), { kind: 'scope', global: true, shot: null, number: null });
});

test('no part of the page reads the type of a scope without allowing for a null one', () => {
	const src = join(fileURLToPath(new URL('.', import.meta.url)), '..');
	const files = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => (entry.isDirectory() ? files(join(dir, entry.name)) : [join(dir, entry.name)]));
	const unsafe = [];
	for (const file of files(src).filter((path) => /\.(svelte|js)$/.test(path) && !path.endsWith('.test.js'))) {
		const lines = readFileSync(file, 'utf8').split('\n');
		lines.forEach((line, index) => {
			if (/\.scope\.type\b/.test(line) && !/isObject\(reference\?\.scope\)/.test(line)) unsafe.push(`${file.slice(src.length + 1)}:${index + 1}`);
		});
	}
	assert.deepEqual(unsafe, []);
});

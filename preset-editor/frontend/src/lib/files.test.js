import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTree, fileKind, flattenTree, insertAt, isEditable, isMedia, lineCount, modeOf, snippetsFor } from './files.js';

test('fileKind classifies the canonical layout', () => {
	assert.equal(fileKind('preset.yml'), 'manifest');
	assert.equal(fileKind('description.md'), 'description');
	assert.equal(fileKind('tests.yml'), 'tests');
	assert.equal(fileKind('styles.yml'), 'styles');
	assert.equal(fileKind('modes/txt2img/pipeline.yml'), 'pipeline');
	assert.equal(fileKind('modes/txt2img/form.yml'), 'form');
	assert.equal(fileKind('modes/txt2img/variants/fast/form.yml'), 'form');
	assert.equal(fileKind('modes/txt2img/tabs/main.yml'), 'tab');
	assert.equal(fileKind('modes/txt2img/files/workflows/a.json'), 'options');
	assert.equal(fileKind('files/form/samplers.yml'), 'fragment');
	assert.equal(fileKind('modes/video/files/form/models.yml'), 'fragment');
	assert.equal(fileKind('public/cover.png'), 'media');
	assert.equal(fileKind('notes.txt'), 'text');
	assert.equal(fileKind('weird.bin'), 'other');
});

test('isEditable and isMedia follow the backend rules', () => {
	assert.equal(isEditable('preset.yml'), true);
	assert.equal(isEditable('public/notes.md'), false);
	assert.equal(isEditable('public/cover.png'), false);
	assert.equal(isEditable('modes/x/files/w.json'), true);
	assert.equal(isMedia('public/examples/a.webp'), true);
	assert.equal(isMedia('public/readme.md'), false);
	assert.equal(isMedia('cover.png'), false);
	assert.equal(modeOf('modes/txt2img/form.yml'), 'txt2img');
	assert.equal(modeOf('preset.yml'), null);
});

test('buildTree nests folders first and keeps file sizes', () => {
	const tree = buildTree([
		{ path: 'preset.yml', size: 10 },
		{ path: 'modes/txt2img/form.yml', size: 20 },
		{ path: 'modes/txt2img/tabs/main.yml', size: 30 },
		{ path: 'description.md', size: 5 },
		'junk'
	]);
	assert.deepEqual(tree.map((node) => [node.name, node.kind]), [['modes', 'dir'], ['description.md', 'file'], ['preset.yml', 'file']]);
	const txt2img = tree[0].children[0];
	assert.deepEqual(txt2img.children.map((node) => node.path), ['modes/txt2img/tabs', 'modes/txt2img/form.yml']);
	assert.deepEqual(flattenTree(tree).map((node) => [node.depth, node.path]), [
		[0, 'modes'], [1, 'modes/txt2img'], [2, 'modes/txt2img/tabs'], [3, 'modes/txt2img/tabs/main.yml'], [2, 'modes/txt2img/form.yml'],
		[0, 'description.md'], [0, 'preset.yml']
	]);
	assert.equal(flattenTree(tree).find((node) => node.path === 'preset.yml').fileKind, 'manifest');
	assert.deepEqual(buildTree(null), []);
});

test('lineCount and insertAt keep the text well formed', () => {
	assert.equal(lineCount(''), 1);
	assert.equal(lineCount('a\nb\n'), 3);
	assert.equal(lineCount(null), 1);
	assert.deepEqual(insertAt('a: 1\nb: 2', 4, 'x: 0'), { text: 'a: 1\nx: 0\nb: 2', cursor: 9 });
	assert.deepEqual(insertAt('', 0, 'x'), { text: 'x', cursor: 1 });
	assert.deepEqual(insertAt('a: 1\n', 99, 'z'), { text: 'a: 1\nz', cursor: 6 });
	assert.deepEqual(insertAt('a: 1', 4, 'z'), { text: 'a: 1\nz', cursor: 6 });
});

test('snippets are offered by file kind and reference the shared tree', () => {
	assert.deepEqual(snippetsFor('pipeline').map((s) => s.id), ['native-chain', 'loop-block', 'cloud-chain']);
	assert.deepEqual(snippetsFor('tab').map((s) => s.id), ['shared-options', 'field']);
	assert.deepEqual(snippetsFor('manifest'), []);
	assert.ok(snippetsFor('tab')[0].build('resolutions/flux.yml').includes('{{ paths._shared }}/resolutions/flux.yml'));
});

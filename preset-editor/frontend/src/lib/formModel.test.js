import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cloneNode, duplicateNames, externalChildrenPath, fieldNames, findNode, fromNode, insertNode, metaProblems, moveNode, newField, newTabReference, nodeTitle, orderedAttrs, parseFormDocument, removeNode, serializeFormDocument, toNode, withIncludeVars } from './formModel.js';
import { parseYaml } from './yaml.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures', 'forms');

function* yamlFiles(root) {
	for (const entry of readdirSync(root)) {
		const path = join(root, entry);
		if (statSync(path).isDirectory()) yield* yamlFiles(path);
		else if (entry.endsWith('.yml')) yield path;
	}
}

test('every marketplace form and tab fixture survives a parse and serialize round trip', () => {
	const files = [...yamlFiles(FIXTURES)];
	assert.ok(files.length >= 40, `found ${files.length} fixtures`);
	for (const file of files) {
		const text = readFileSync(file, 'utf8');
		const kind = file.endsWith('form.yml') ? 'form' : 'tab';
		const doc = parseFormDocument(text, { kind });
		assert.equal(doc.ok, true, `${file}: ${doc.ok ? '' : doc.error.message}`);
		const again = parseFormDocument(serializeFormDocument(doc), { kind });
		assert.equal(again.ok, true, file);
		assert.deepEqual(parseYaml(serializeFormDocument(doc)).data, parseYaml(text).data, file);
		assert.deepEqual(Object.keys(parseYaml(serializeFormDocument(doc)).data), Object.keys(parseYaml(text).data), `${file}: top-level key order`);
	}
});

test('parseFormDocument keeps unknown keys, raw sections and meta apart', () => {
	const doc = parseFormDocument('name: quick\nlabel: Quick\nexamples:\n  - public/a.webp\nnegative_prompt:\n  applies_when: true\nfuture_key: 1\nfields:\n  - name: prompt\n    type: textbox\n    default: ""\n', { kind: 'form' });
	assert.equal(doc.ok, true);
	assert.deepEqual(doc.meta, { name: 'quick', label: 'Quick', examples: ['public/a.webp'] });
	assert.deepEqual(doc.raw, { negative_prompt: 'applies_when: true' });
	assert.deepEqual(doc.unknown, { future_key: 1 });
	assert.deepEqual(doc.keyOrder, ['name', 'label', 'examples', 'negative_prompt', 'future_key', 'fields']);
	assert.equal(doc.fields.length, 1);
	assert.deepEqual(doc.fields[0].attrs, { name: 'prompt', type: 'textbox', default: '' });
	assert.equal(doc.fields[0].children, null);
	doc.meta.label = '';
	doc.raw.negative_prompt = '';
	const data = parseYaml(serializeFormDocument(doc)).data;
	assert.deepEqual(Object.keys(data), ['name', 'examples', 'future_key', 'fields']);
	assert.equal(parseFormDocument('- a\n').ok, false);
	assert.equal(parseFormDocument('fields: x\n').ok, false);
	assert.equal(parseFormDocument('fields:\n  - 3\n').ok, false);
	assert.deepEqual(parseFormDocument('', { kind: 'tab' }).fields, []);
});

test('nodes keep their attribute order and emit children last', () => {
	const node = toNode({ type: 'row', label: 'Pair', children: [{ name: 'a', type: 'string' }, { type: 'section', children: [] }], width: 2 });
	assert.deepEqual(Object.keys(node.attrs), ['type', 'label', 'width']);
	assert.equal(node.children.length, 2);
	assert.deepEqual(node.children[1].children, []);
	assert.deepEqual(Object.keys(fromNode(node)), ['type', 'label', 'width', 'children']);
	assert.deepEqual(fromNode(node).children[0], { name: 'a', type: 'string' });
	const copy = cloneNode(node);
	assert.notEqual(copy.id, node.id);
	assert.deepEqual(fromNode(copy), fromNode(node));
	assert.deepEqual(orderedAttrs({ zzz: 1, children: [], label: 'x', type: 't' }), ['type', 'label', 'children', 'zzz']);
});

test('tree operations find, insert, move and remove by id', () => {
	const doc = parseFormDocument('fields:\n  - type: tabs\n    children:\n      - type: tab\n        label: One\n        children:\n          - name: a\n            type: string\n      - type: tab\n        label: Two\n        children: "{{ paths.preset }}/modes/txt2img/tabs/two.yml"\n');
	const [tabs] = doc.fields;
	const [one, two] = tabs.children;
	const a = one.children[0];
	assert.equal(findNode(doc.fields, a.id).parent, one);
	assert.equal(findNode(doc.fields, 'nope'), null);
	assert.deepEqual(externalChildrenPath(two), { scope: 'preset', path: 'modes/txt2img/tabs/two.yml', file: '{{ paths.preset }}/modes/txt2img/tabs/two.yml', vars: null });
	assert.equal(externalChildrenPath(one), null);
	assert.deepEqual(externalChildrenPath({ children: '{{ paths._shared }}/tabs/x.yml' }), { scope: 'shared', path: 'tabs/x.yml', file: '{{ paths._shared }}/tabs/x.yml', vars: null });

	const b = newField('slider', { name: 'b', label: 'B' });
	assert.equal(insertNode(doc.fields, b, { parentId: one.id, index: 0 }), true);
	assert.deepEqual(fieldNames(doc.fields), ['b', 'a']);
	assert.equal(moveNode(doc.fields, a.id, { parentId: null, index: 0 }), true);
	assert.equal(doc.fields[0], a);
	assert.equal(moveNode(doc.fields, tabs.id, { parentId: one.id, index: 0 }), false);
	assert.equal(moveNode(doc.fields, one.id, { parentId: one.id, index: 0 }), false);
	assert.equal(removeNode(doc.fields, b.id), b);
	assert.equal(removeNode(doc.fields, b.id), null);
	assert.deepEqual(fieldNames(doc.fields), ['a']);
	insertNode(doc.fields, newField('string', { name: 'a' }));
	assert.deepEqual(duplicateNames(doc.fields), ['a']);
	assert.equal(nodeTitle(a), 'a · string');
	assert.equal(nodeTitle(one), 'One · tab');
	assert.equal(nodeTitle(tabs), 'tabs');
	const reference = newTabReference('txt2img', 'advanced', 'Advanced');
	assert.deepEqual(fromNode(reference), { type: 'tab', label: 'Advanced', children: '{{ paths.preset }}/modes/txt2img/tabs/advanced.yml' });
	assert.deepEqual(fromNode(newField('row')), { type: 'row', children: [] });
	assert.deepEqual(fromNode(newField('seed', { name: 'seed' })), { name: 'seed', type: 'seed' });
});

test('the prompt keys of a mode form are form settings, its requirements and segment templates raw YAML', () => {
	const text = 'prompt: optional\nprompt_label: Image\nprompt_placeholder: Describe the change\nllm_guide: Ask for one change at a time\nrequirements:\n  - type: python_package\n    package: foo\nsegment_templates: []\nfields: []\n';
	const doc = parseFormDocument(text, { kind: 'form' });

	assert.deepEqual(doc.meta, { prompt: 'optional', prompt_label: 'Image', prompt_placeholder: 'Describe the change', llm_guide: 'Ask for one change at a time' });
	assert.deepEqual(Object.keys(doc.raw), ['requirements', 'segment_templates']);
	assert.deepEqual(doc.unknown, {});
	assert.deepEqual(parseYaml(serializeFormDocument(doc)).data, parseYaml(text).data);
	assert.deepEqual(metaProblems({ prompt: 'sometimes', prompt_label: '  ' }), { prompt: 'required, optional or none', prompt_label: 'a text, or nothing' });
	assert.deepEqual(metaProblems({ prompt: 'none', prompt_placeholder: 'x' }), {});
});

test('a children include with vars is kept, described and can lose or gain its vars', () => {
	const include = { file: '{{ paths.preset }}/files/form/sampling.yml', vars: { steps: 8, cfg: 1 } };
	const node = toNode({ type: 'section', label: 'Sampling', children: include });

	assert.deepEqual(externalChildrenPath(node), { scope: 'preset', path: 'files/form/sampling.yml', file: include.file, vars: include.vars });
	assert.deepEqual(fromNode(node), { type: 'section', label: 'Sampling', children: include });
	assert.notEqual(fromNode(node).children, node.children);
	assert.equal(withIncludeVars(node.children, {}), include.file);
	assert.equal(withIncludeVars(node.children, null), include.file);
	assert.deepEqual(withIncludeVars('{{ paths._shared }}/native/step_cache.yml', { cache: true }), { file: '{{ paths._shared }}/native/step_cache.yml', vars: { cache: true } });
	assert.deepEqual(externalChildrenPath(toNode({ type: 'tab', children: '{{ paths._shared }}/native/seed_quantity.yml' })), { scope: 'shared', path: 'native/seed_quantity.yml', file: '{{ paths._shared }}/native/seed_quantity.yml', vars: null });
	assert.equal(externalChildrenPath(toNode({ type: 'row', children: [] })), null);
});

test('an option list opened in the form builder points to the YAML view', () => {
	const doc = parseFormDocument('- { label: "From above", value: "from above" }\n', { kind: 'tab' });

	assert.equal(doc.ok, false);
	assert.match(doc.error.message, /option list/);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyManifestForm, fieldProblems, formSnapshot, manifestForm, sectionProblems } from './manifest.js';
import { parseYaml, replaceTopLevelBlock, topLevelBlockSpan } from './yaml.js';

const SOURCE = [
	'schema: 1',
	'id: "fixture-minimal-native"',
	'name: "Minimal native"',
	'category: "image"',
	'version: "1.0.0"',
	'engine: "native"',
	'tags: []',
	'',
	'# shared values',
	'vars:',
	'  default_steps: 30   # the sampler default',
	'',
	'formulas:',
	'  groups: {}',
	'',
	'modes:',
	'  - txt2img',
	''
].join('\n');

test('topLevelBlockSpan finds a key with its indented block and nothing else', () => {
	assert.deepEqual(topLevelBlockSpan('a: 1\n# vars: 2\nvars:\n  x: 1\n', 'vars'), { start: 15, end: 28 });
	assert.equal(topLevelBlockSpan('a: 1\n  vars: 2\n', 'vars'), null);
	assert.deepEqual(topLevelBlockSpan('vars: {}', 'vars'), { start: 0, end: 8 });
	assert.deepEqual(topLevelBlockSpan('vars: {}\n\n# about modes\nmodes: []\n', 'vars'), { start: 0, end: 9 });
});

test('replaceTopLevelBlock swaps, removes or appends one block and keeps the rest byte for byte', () => {
	const replaced = replaceTopLevelBlock(SOURCE, 'vars', 'vars:\n  default_steps: 20');
	assert.equal(replaced, SOURCE.replace('vars:\n  default_steps: 30   # the sampler default\n', 'vars:\n  default_steps: 20\n'));
	const removed = replaceTopLevelBlock(SOURCE, 'formulas', null);
	assert.equal(removed, SOURCE.replace('formulas:\n  groups: {}\n\n', ''));
	assert.equal(replaceTopLevelBlock('schema: 1', 'llm', 'llm:\n  form: full'), 'schema: 1\nllm:\n  form: full\n');
	assert.equal(replaceTopLevelBlock(SOURCE, 'llm', null), SOURCE);
});

test('manifestForm splits the manifest into fields, raw sections and read-only keys', () => {
	const form = manifestForm(SOURCE);
	assert.equal(form.ok, true);
	assert.deepEqual(form.fields, { name: 'Minimal native', version: '1.0.0', category: 'image', engine: 'native', driver: '', tags: '' });
	assert.equal(form.sections.vars, 'default_steps: 30');
	assert.equal(form.sections.formulas, 'groups: {}');
	assert.equal(form.sections.llm, '');
	assert.deepEqual(form.readOnly, { schema: '1', id: 'fixture-minimal-native' });
	assert.deepEqual(form.modes, ['txt2img']);
	assert.deepEqual(form.unknownKeys, []);
	assert.equal(manifestForm('- a\n').ok, false);
	assert.equal(manifestForm('a: [\n').ok, false);
});

test('fieldProblems and sectionProblems follow the core rules', () => {
	assert.deepEqual(fieldProblems({ name: ' x ', version: '1.2.3-rc1', category: 'video', engine: 'native', driver: '', tags: '' }), {});
	const problems = fieldProblems({ name: '', version: '1.0', category: 'photo', engine: 'Native', driver: 'x', tags: '' });
	assert.deepEqual(Object.keys(problems).sort(), ['category', 'driver', 'engine', 'name', 'version']);
	assert.equal(fieldProblems({ name: 'a', version: '1.0.0', category: 'image', engine: 'cloud', driver: '', tags: '' }).driver.includes('required'), true);
	assert.equal(fieldProblems({ name: 'a', version: '1.0.0', category: 'image', engine: 'cloud', driver: 'native.x', tags: '' }).driver.startsWith('<engine>'), true);
	assert.deepEqual(sectionProblems({ vars: 'a: 1', requirements: '- kind: x', llm: '' }), {});
	assert.deepEqual(Object.keys(sectionProblems({ vars: '- 1', requirements: 'a: 1', llm: 'a: [' })).sort(), ['llm', 'requirements', 'vars']);
});

test('applyManifestForm rewrites only the keys that changed and reports the comments it drops', () => {
	const form = manifestForm(SOURCE);
	const edited = { fields: { ...form.fields, name: 'Renamed', driver: ' ', tags: 'a, b, a' }, sections: { ...form.sections, vars: 'default_steps: 20\n', formulas: '' } };

	const result = applyManifestForm(SOURCE, edited, form);

	assert.equal(result.ok, true);
	assert.deepEqual(result.changed, ['name', 'tags', 'vars', 'formulas']);
	assert.deepEqual(result.lostComments, [11]);
	const data = parseYaml(result.text).data;
	assert.deepEqual({ name: data.name, tags: data.tags, vars: data.vars, modes: data.modes }, { name: 'Renamed', tags: ['a', 'b'], vars: { default_steps: 20 }, modes: ['txt2img'] });
	assert.equal('formulas' in data, false);
	assert.equal(result.text.includes('# shared values'), true);
	assert.equal(result.text.includes('name: "Renamed"'), true);
	assert.equal(result.text.includes('tags:\n  - "a"\n  - "b"'), true);
});

test('applyManifestForm leaves an untouched manifest alone and refuses bad fields', () => {
	const form = manifestForm(SOURCE);
	const same = applyManifestForm(SOURCE, { fields: form.fields, sections: form.sections }, form);
	assert.deepEqual([same.ok, same.text === SOURCE, same.changed, same.lostComments], [true, true, [], []]);
	const refused = applyManifestForm(SOURCE, { fields: { ...form.fields, version: 'v1' }, sections: { ...form.sections, vars: 'a: [' } }, form);
	assert.equal(refused.ok, false);
	assert.deepEqual(Object.keys(refused.problems).sort(), ['vars', 'version']);
	assert.equal(formSnapshot(form), JSON.stringify({ fields: form.fields, sections: form.sections }));
});

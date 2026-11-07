import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseFormDocument } from './formModel.js';
import { defaultProblem, duplicateAnchors, fieldProblems, treeProblems } from './formSchema.js';

const keys = (problems) => problems.map((item) => item.key).sort();

test('fieldProblems applies the FieldSpec rules the core enforces at load time', () => {
	assert.deepEqual(fieldProblems({ name: 'steps', type: 'slider', default: 30, width: '3/5', configuration: { min: 1 } }), []);
	assert.deepEqual(keys(fieldProblems({ type: 'slider', default: '30' })), ['default']);
	assert.deepEqual(keys(fieldProblems({ type: 'checkbox', default: 'false' })), ['default']);
	assert.deepEqual(keys(fieldProblems({ type: 'integer', default: 1.5 })), ['default']);
	assert.deepEqual(keys(fieldProblems({ type: 'select', default: ['a'] })), ['default']);
	assert.deepEqual(keys(fieldProblems({ type: 'string', default: 3 })), ['default']);
	assert.deepEqual(keys(fieldProblems({ type: 'string', default: '{{ vars.x }}' })), ['default']);
	assert.deepEqual(keys(fieldProblems({ type: 'string', value: 'old key', widht: 1 })), ['value', 'widht']);
	assert.deepEqual(keys(fieldProblems({ type: 'string', width: '0/2', full_width: 'yes', audience: 'expert', save_into: 'disk' })), ['audience', 'full_width', 'save_into', 'width']);
	assert.deepEqual(keys(fieldProblems({ type: '' })), ['type']);
	assert.deepEqual(keys(fieldProblems({ type: 'ghost' }, { types: ['string'] })), ['type']);
	assert.deepEqual(keys(fieldProblems({ name: 'a', type: 'string', merge_from: ['a', 'b', 'b'] })), ['merge_from', 'merge_from']);
	assert.equal(defaultProblem('image', { any: 'shape' }), null);
	assert.equal(defaultProblem('seed', -1), null);
});

test('treeProblems adds the per-tree rules and counts errors apart from warnings', () => {
	const doc = parseFormDocument('fields:\n  - type: header\n    label: Loose\n  - type: tabs\n    children:\n      - type: tab\n        label: Main\n        children:\n          - name: steps\n            type: slider\n            configuration: { min: 1, nope: 2 }\n          - name: steps\n            type: string\n          - type: row\n            children: []\n');
	const report = treeProblems(doc.fields, { kind: 'form', configKeys: { slider: ['min', 'max', 'step', 'tooltip'] } });
	const [header, tabs] = doc.fields;
	const [main] = tabs.children;
	const [steps, again, row] = main.children;
	assert.deepEqual(report.byNode.get(header.id).map((item) => item.key), ['name']);
	assert.equal(report.byNode.has(tabs.id), false);
	assert.deepEqual(report.byNode.get(steps.id).map((item) => [item.key, item.level]), [['configuration', 'warning']]);
	assert.equal(report.byNode.has(again.id), false);
	assert.deepEqual(report.byNode.get(row.id).map((item) => item.level), ['warning']);
	assert.deepEqual(report.general.map((item) => item.message), ['the name steps is used more than once']);
	assert.equal(report.count, 2);
	assert.equal(treeProblems(doc.fields, { kind: 'tab' }).count, 1);
});

test('a children include is a path or a file with scalar vars, as ChildrenIncludeSpec says', () => {
	assert.deepEqual(fieldProblems({ type: 'tab', children: '{{ paths.preset }}/modes/video/tabs/lora.yml' }), []);
	assert.deepEqual(fieldProblems({ type: 'section', children: { file: '{{ paths._shared }}/native/sampling_turbo_base.yml', vars: { steps: 8, turbo: true, sampler: 'euler' } } }), []);
	assert.deepEqual(fieldProblems({ type: 'section', children: { file: 'x.yml' } }), []);
	assert.deepEqual(keys(fieldProblems({ type: 'section', children: { file: 'x.yml', vars: { nested: { a: 1 } } } })), ['children']);
	assert.deepEqual(keys(fieldProblems({ type: 'section', children: { file: 'x.yml', extra: 1 } })), ['children']);
	assert.deepEqual(keys(fieldProblems({ type: 'section', children: { vars: {} } })), ['children']);
});

test('a fields fragment may carry vars placeholders in its defaults, a mode form may not', () => {
	assert.deepEqual(fieldProblems({ name: 'steps', type: 'slider', default: '{{ vars.steps }}' }, { allowVars: true }), []);
	assert.deepEqual(keys(fieldProblems({ name: 'steps', type: 'slider', default: '{{ vars.steps }}' })), ['default']);
	assert.deepEqual(keys(fieldProblems({ name: 'steps', type: 'slider', default: '{{ form.steps }}' }, { allowVars: true })), ['default']);
	const doc = parseFormDocument('fields:\n  - name: cfg\n    type: slider\n    default: "{{ vars.cfg }}"\n');
	assert.equal(treeProblems(doc.fields, { kind: 'tab' }).count, 0);
	assert.equal(treeProblems(doc.fields, { kind: 'form' }).count, 1);
});

test('a formula group that preset.yml does not declare is a warning, since the lint refuses it', () => {
	const doc = parseFormDocument('fields:\n  - name: steps\n    type: slider\n    formula: speed\n  - name: cfg\n    type: slider\n    formula: guidance\n  - name: seed\n    type: seed\n    formula: false\n');
	const report = treeProblems(doc.fields, { kind: 'tab', formulaGroups: ['speed'] });
	const [steps, cfg, seed] = doc.fields;

	assert.equal(report.byNode.has(steps.id), false);
	assert.deepEqual(report.byNode.get(cfg.id).map((item) => [item.key, item.level]), [['formula', 'warning']]);
	assert.equal(report.byNode.has(seed.id), false);
	assert.equal(report.count, 0);
	assert.equal(treeProblems(doc.fields, { kind: 'tab' }).byNode.size, 0);
});

test('an anchor names a tab or a section for plugin extensions, as FieldSpec and the loader check it', () => {
	assert.deepEqual(fieldProblems({ type: 'tab', anchor: 'generation', label: 'Generation', children: '{{ paths.preset }}/modes/video/tabs/generation.yml' }), []);
	assert.deepEqual(fieldProblems({ type: 'section', anchor: 'face_hand-2' }), []);
	assert.deepEqual(fieldProblems({ type: 'tab', anchor: null }), []);
	assert.deepEqual(keys(fieldProblems({ type: 'row', anchor: 'main' })), ['anchor']);
	assert.deepEqual(keys(fieldProblems({ name: 'steps', type: 'slider', anchor: 'steps' })), ['anchor']);
	assert.deepEqual(keys(fieldProblems({ type: 'tab', anchor: 'Generation' })), ['anchor']);
	assert.deepEqual(keys(fieldProblems({ type: 'tab', anchor: '_lora' })), ['anchor']);
	assert.deepEqual(keys(fieldProblems({ type: 'tab', anchor: '' })), ['anchor']);
	assert.deepEqual(keys(fieldProblems({ type: 'tab', anchor: 3 })), ['anchor']);
	assert.deepEqual(fieldProblems({ type: 'section', anchor: '{{ vars.anchor }}' }, { allowVars: true }), []);
	assert.deepEqual(keys(fieldProblems({ type: 'section', anchor: '{{ vars.anchor }}' })), ['anchor']);

	const doc = parseFormDocument('fields:\n  - type: tabs\n    children:\n      - type: tab\n        anchor: generation\n        children:\n          - type: section\n            anchor: generation\n            children: []\n      - type: tab\n        anchor: advanced\n        children: []\n      - type: tab\n        anchor: generation\n        children: "{{ paths._shared }}/tabs/lora.yml"\n');
	assert.deepEqual(duplicateAnchors(doc.fields), [{ type: 'tab', anchor: 'generation' }]);
	const report = treeProblems(doc.fields, { kind: 'form' });
	assert.deepEqual(report.general.map((item) => [item.key, item.message]), [['anchor', 'the tab anchor generation is used more than once (the core refuses the form)']]);
	assert.equal(report.count, 1);
});

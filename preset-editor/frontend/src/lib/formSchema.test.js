import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseFormDocument } from './formModel.js';
import { defaultProblem, fieldProblems, treeProblems } from './formSchema.js';

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

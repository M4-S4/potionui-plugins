import { test } from 'node:test';
import assert from 'node:assert/strict';
import { commentLines, dumpYaml, hasComments, parseYaml } from './yaml.js';

test('parseYaml gives the data or the position of the error', () => {
	assert.deepEqual(parseYaml('schema: 1\nmodes:\n  - txt2img\n'), { ok: true, data: { schema: 1, modes: ['txt2img'] } });
	assert.deepEqual(parseYaml(''), { ok: true, data: null });
	const broken = parseYaml('fields:\n  - name: "x\n    type: seed\n');
	assert.equal(broken.ok, false);
	assert.equal(typeof broken.error.message, 'string');
	assert.ok(broken.error.line >= 2);
	assert.equal(parseYaml(null).ok, true);
});

test('dumpYaml writes readable YAML with double quotes where needed', () => {
	const text = dumpYaml({ name: 'My preset', tags: ['a', 'b'], when: '{{ form.x }}', nested: { steps: 30 } });
	assert.equal(text, 'name: My preset\ntags:\n  - a\n  - b\nwhen: "{{ form.x }}"\nnested:\n  steps: 30\n');
	assert.deepEqual(parseYaml(text).data, { name: 'My preset', tags: ['a', 'b'], when: '{{ form.x }}', nested: { steps: 30 } });
});

test('commentLines finds comments outside quoted strings', () => {
	const text = [
		'# header',
		'schema: 1 # trailing',
		'name: "not # a comment"',
		"label: 'nor # this'",
		'url: "https://x/#anchor"',
		'tags: [a, b]',
		'  #indented'
	].join('\n');
	assert.deepEqual(commentLines(text), [1, 2, 7]);
	assert.equal(hasComments(text), true);
	assert.equal(hasComments('schema: 1\nname: "a#b"\n'), false);
	assert.equal(hasComments(''), false);
	assert.equal(hasComments(undefined), false);
});

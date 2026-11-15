import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'components', 'PipelineBuilder.svelte'), 'utf8');

test('the pipeline builder asks saveAllowed before every way of saving', () => {
	assert.match(SOURCE, /const canSave = \$derived\(saveAllowed\(\{ phase, doc, dirty, problems: blocked, saving \}\)\);/);
	assert.match(SOURCE, /async function save\(overrideEtag = null\) \{\n\t\tif \(!canSave\) return;/);
	assert.match(SOURCE, /\.key\.toLowerCase\(\) === 's'\) \{\n\t\t\tevent\.preventDefault\(\);\n\t\t\tif \(canSave\) save\(\);/);
	assert.match(SOURCE, /<ActionButton variant="primary" icon="check" loading=\{saving\} disabled=\{!canSave\}/);
	assert.equal([...SOURCE.matchAll(/writeFile\(/g)].length, 1);
	assert.equal([...SOURCE.matchAll(/\bsave\(/g)].length, 4);
});

test('the pipeline builder checks a pointer with the text of the pipeline it names', () => {
	assert.match(SOURCE, /pointerProblems\(doc, \{ mode, files, targetText \}\)/);
	assert.match(SOURCE, /readTarget\(pointer && pointerPath && files\.includes\(pointerPath\) \? pointerPath : null\);/);
});

test('a pointer replaces the whole pipe editor with the read-only view', () => {
	const pointer = SOURCE.indexOf('{:else if pointer}');
	const editor = SOURCE.indexOf('<div class="builder-grid');
	assert.ok(pointer > 0 && editor > pointer, `${pointer} ${editor}`);
	assert.doesNotMatch(SOURCE.slice(pointer, editor), /onclick=\{\(\) => (add|remove|duplicate)\(|insertPipe|removePipe/);
});

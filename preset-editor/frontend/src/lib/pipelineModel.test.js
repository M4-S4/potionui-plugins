import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { insertPipe, isPointer, movePipe, newPipe, parsePipelineDocument, pipeRef, pipeTitle, pipelineProblems, pointerFile, pointerProblems, removePipe, serializePipelineDocument, sourcesBefore, startChain } from './pipelineModel.js';
import { parseYaml } from './yaml.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures');
const REFERENCE = JSON.parse(readFileSync(join(FIXTURES, 'pipes-reference.json'), 'utf8'));

function* yamlFiles(root) {
	for (const entry of readdirSync(root)) {
		const path = join(root, entry);
		if (statSync(path).isDirectory()) yield* yamlFiles(path);
		else if (entry.endsWith('.yml')) yield path;
	}
}

const messages = (report, pipe) => (report.byPipe.get(pipe.id) ?? []).map((item) => item.message);

test('every marketplace pipeline fixture survives a round trip and wires its inputs to earlier pipes', () => {
	const files = [...yamlFiles(join(FIXTURES, 'pipelines'))];
	assert.ok(files.length >= 10, `found ${files.length} fixtures`);
	for (const file of files) {
		const text = readFileSync(file, 'utf8');
		const doc = parsePipelineDocument(text);
		assert.equal(doc.ok, true, `${file}: ${doc.ok ? '' : doc.error.message}`);
		assert.deepEqual(parseYaml(serializePipelineDocument(doc)).data, parseYaml(text).data, file);
		const report = pipelineProblems(doc, REFERENCE);
		const errors = [...report.byPipe.values()].flat().filter((item) => item.level !== 'warning');
		assert.deepEqual(errors, [], `${file}: ${JSON.stringify(errors)}`);
	}
});

test('pipelineProblems reports the pairs and keys the core would refuse', () => {
	const doc = parsePipelineDocument([
		'pipeline:',
		'  - name: seed_generator',
		'    enabled: true',
		'    configuration: { seed: "{{ form.seed }}", quantity: 1, nope: 3 }',
		'  - name: generator/sdxl',
		'    id: generator',
		'    input:',
		'      - ["seed", "seed_generator", "seed"]',
		'      - ["model", "checkpoint_loader/sdxl", "model"]',
		'      - ["conditioning", "seed_generator", "nothing"]',
		'      - ["image", "seed_generator", "seed"]',
		'      - ["bad"]',
		'      - ["image", "{% if form.x %}a{% else %}b{% endif %}", "image"]',
		'    configuration: { steps: 20, resolution: "1024x1024", quantity: 1 }',
		'  - name: generator/sdxl',
		'    enabled: "{{ form.twice }}"',
		'  - name: gallery',
		'    input:',
		'      - ["image", "generator", "image"]',
		'    extra: true',
		'  - name: ghost_pipe',
		'    enabled: 3',
		''
	].join('\n'));
	assert.equal(doc.ok, true);
	const [seed, generator, again, gallery, ghost] = doc.pipes;
	const report = pipelineProblems(doc, REFERENCE);

	assert.deepEqual(messages(report, seed), ['configuration.nope is not declared for seed_generator']);
	assert.deepEqual(messages(report, generator), [
		'input[1]: checkpoint_loader/sdxl is not declared before this pipe',
		'input[2]: seed_generator has no output nothing',
		'input[3]: seed is SEED, image expects IMAGE',
		'input[4] is [input, pipe, output]'
	]);
	assert.deepEqual(messages(report, again), ['generator/sdxl appears more than once: give each instance an id']);
	assert.deepEqual(messages(report, gallery), ['unknown key (the core refuses it)']);
	assert.deepEqual(messages(report, ghost), ['no pipe of this name on this instance', 'true, false or an expression']);
	assert.equal(report.count, 5);
	assert.equal(pipelineProblems(doc).count, 5);
	assert.equal([...pipelineProblems(doc).byPipe.values()].flat().filter((item) => item.level === 'warning').length, 0);
	assert.equal(pipeRef(generator), 'generator');
	assert.equal(pipeTitle(generator), 'generator/sdxl (generator)');
	assert.equal(pipeTitle(seed), 'seed_generator');
	assert.deepEqual(sourcesBefore(doc, again.id).map((item) => item.ref), ['seed_generator', 'generator']);
});

test('pipes are created from the reference, moved, removed and chains start from the snippets', () => {
	const doc = parsePipelineDocument('pipeline: []\n');
	const loader = newPipe('model_loader/flux', REFERENCE);
	assert.deepEqual(loader.attrs, { name: 'model_loader/flux', enabled: true, configuration: { diffusion_model: '', text_encoder: '', vae: '' } });
	assert.deepEqual(newPipe('unknown').attrs, { name: 'unknown', enabled: true });
	insertPipe(doc, newPipe('gallery', REFERENCE));
	insertPipe(doc, loader, 0);
	assert.deepEqual(doc.pipes.map((pipe) => pipe.attrs.name), ['model_loader/flux', 'gallery']);
	assert.equal(movePipe(doc, loader.id, 1), true);
	assert.equal(movePipe(doc, loader.id, 1), false);
	assert.deepEqual(doc.pipes.map((pipe) => pipe.attrs.name), ['gallery', 'model_loader/flux']);
	assert.equal(removePipe(doc, loader.id), loader);
	assert.equal(removePipe(doc, loader.id), null);
	assert.equal(parseYaml(serializePipelineDocument(doc)).data.pipeline.length, 1);

	const native = startChain('native', { family: 'z_image' });
	assert.deepEqual(native.map((pipe) => pipe.attrs.name), ['model_loader/z_image', 'prompt_encoder', 'seed_generator', 'generator/z_image', 'gallery']);
	const cloud = startChain('cloud');
	assert.deepEqual(cloud.map((pipe) => pipe.attrs.name), ['dynamic_prompts_renderer', 'seed_generator', 'cloud_generate', 'gallery']);
	assert.deepEqual(startChain('nope'), []);
	assert.equal(parsePipelineDocument('- a\n').ok, false);
	assert.equal(parsePipelineDocument('pipeline: 1\n').ok, false);
	assert.equal(parsePipelineDocument('pipeline:\n  - 1\n').ok, false);
	assert.deepEqual(parsePipelineDocument('').pipes, []);
	assert.deepEqual(parsePipelineDocument('future: 1\npipeline: []\n').unknown, { future: 1 });
});

test('a pipe cache key is refused, since the core dropped it from PipeSpec', () => {
	const doc = parsePipelineDocument('pipeline:\n  - name: seed_generator\n    enabled: true\n    cache: [seed]\n');
	const report = pipelineProblems(doc, null);

	assert.deepEqual(report.byPipe.get(doc.pipes[0].id), [{ key: 'cache', message: 'unknown key (the core refuses it)' }]);
	assert.equal(report.count, 1);
});

test('a mode that takes the pipeline of another mode saves back with pipeline_from alone', () => {
	for (const text of ['pipeline_from: video\n', 'pipeline_from: "video"\n']) {
		const doc = parsePipelineDocument(text);
		assert.equal(doc.ok, true);
		assert.equal(isPointer(doc), true);
		assert.equal(pointerFile(doc), 'modes/video/pipeline.yml');
		assert.deepEqual(doc.pipes, []);
		assert.equal(serializePipelineDocument(doc), 'pipeline_from: video\n');
		assert.deepEqual(pointerProblems(doc, { mode: 'first_last', files: ['modes/video/pipeline.yml'] }), []);
	}
});

test('a pipeline of its own is still written with its pipeline list, empty or not', () => {
	assert.equal(isPointer(parsePipelineDocument('pipeline: []\n')), false);
	assert.equal(serializePipelineDocument(parsePipelineDocument('')), 'pipeline: []\n');
	assert.equal(serializePipelineDocument(parsePipelineDocument('pipeline: []\n')), 'pipeline: []\n');
	assert.equal(pointerFile(parsePipelineDocument('pipeline: []\n')), null);
	assert.deepEqual(pointerProblems(parsePipelineDocument('pipeline: []\n')), []);
});

test('pointerProblems refuses what the core loader refuses', () => {
	const files = ['modes/video/pipeline.yml', 'modes/first_last/pipeline.yml'];
	const problems = (text, mode = 'first_last') => pointerProblems(parsePipelineDocument(text), { mode, files });
	assert.match(problems('pipeline_from: video\npipeline: []\n')[0], /cannot be combined with other keys \(pipeline\)/);
	assert.match(problems('pipeline_from: video\nnote: x\n')[0], /cannot be combined with other keys \(note\)/);
	assert.match(problems('pipeline_from: ../video\n')[0], /must name a sibling mode directory/);
	assert.match(problems('pipeline_from: .video\n')[0], /must name a sibling mode directory/);
	assert.match(problems('pipeline_from: ""\n')[0], /must name a sibling mode directory/);
	assert.match(problems('pipeline_from: 3\n')[0], /must name a sibling mode directory/);
	assert.match(problems('pipeline_from: refs\n')[0], /modes\/refs\/pipeline\.yml not found/);
	assert.match(problems('pipeline_from: first_last\n')[0], /cannot point at itself/);
	assert.deepEqual(problems('pipeline_from: video\n'), []);
});

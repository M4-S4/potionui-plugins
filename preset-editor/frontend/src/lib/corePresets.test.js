import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fileKind } from './files.js';
import { parseFormDocument, serializeFormDocument } from './formModel.js';
import { treeProblems } from './formSchema.js';
import { parsePipelineDocument, pipelineProblems, serializePipelineDocument } from './pipelineModel.js';
import { parseYaml } from './yaml.js';

const PRESETS = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', '..', '..', 'presets');
const MARKETPLACE = join(PRESETS, 'marketplace');
const SHARED = join(PRESETS, '_shared');
const skip = existsSync(MARKETPLACE) ? false : 'the plugin is not inside a core checkout (content/plugins/<kind>/preset-editor)';

function* files(root, pattern) {
	for (const entry of readdirSync(root)) {
		const path = join(root, entry);
		if (statSync(path).isDirectory()) yield* files(path, pattern);
		else if (pattern.test(entry)) yield path;
	}
}

function presetRoots() {
	return [...files(MARKETPLACE, /^preset\.yml$/)].map(dirname);
}

function posix(path) {
	return path.split(sep).join('/');
}

function errorsOf(report) {
	return [...report.byNode.values()].flat().filter((item) => item.level !== 'warning').map((item) => `${item.key}: ${item.message}`).concat(report.general.map((item) => item.message));
}

test('every form, tab and fields fragment of the core presets opens in the form builder, saves back unchanged and shows no blocking problem', { skip }, () => {
	let checked = 0;
	for (const root of presetRoots()) {
		for (const file of files(root, /\.ya?ml$/)) {
			const path = posix(relative(root, file));
			const kind = fileKind(path);
			if (!['form', 'tab', 'fragment'].includes(kind)) continue;
			const text = readFileSync(file, 'utf8');
			const data = parseYaml(text).data;
			if (kind === 'fragment' && Array.isArray(data)) continue;
			const doc = parseFormDocument(text, { kind: kind === 'form' ? 'form' : 'tab' });
			assert.equal(doc.ok, true, `${posix(relative(MARKETPLACE, file))}: ${doc.ok ? '' : doc.error.message}`);
			assert.deepEqual(parseYaml(serializeFormDocument(doc)).data, data, posix(relative(MARKETPLACE, file)));
			assert.deepEqual(Object.keys(doc.unknown), [], `${posix(relative(MARKETPLACE, file))}: keys the builder does not know`);
			assert.deepEqual(errorsOf(treeProblems(doc.fields, { kind: kind === 'form' ? 'form' : 'tab' })), [], posix(relative(MARKETPLACE, file)));
			checked += 1;
		}
	}
	assert.ok(checked >= 200, `checked ${checked} files`);
});

test('the fields fragments under files/form are offered to the form builder', { skip }, () => {
	const fragments = presetRoots().flatMap((root) => [...files(root, /\.ya?ml$/)].map((file) => posix(relative(root, file))).filter((path) => path.startsWith('files/form/')));
	assert.ok(fragments.length > 0);
	assert.deepEqual([...new Set(fragments.map(fileKind))], ['fragment']);
});

test('the shared fields fragments of content/presets/_shared parse and save back unchanged', { skip }, () => {
	for (const file of files(SHARED, /\.ya?ml$/)) {
		const text = readFileSync(file, 'utf8');
		const data = parseYaml(text).data;
		if (!data || Array.isArray(data) || !Array.isArray(data.fields)) continue;
		const doc = parseFormDocument(text, { kind: 'tab' });
		assert.equal(doc.ok, true, file);
		assert.deepEqual(parseYaml(serializeFormDocument(doc)).data, data, file);
		assert.deepEqual(errorsOf(treeProblems(doc.fields, { kind: 'tab' })), [], file);
	}
});

test('every pipeline of the core presets opens in the pipeline builder, saves back unchanged and shows no blocking problem', { skip }, () => {
	let checked = 0;
	for (const root of presetRoots()) {
		for (const file of files(root, /^pipeline\.yml$/)) {
			const text = readFileSync(file, 'utf8');
			const doc = parsePipelineDocument(text);
			assert.equal(doc.ok, true, file);
			assert.deepEqual(parseYaml(serializePipelineDocument(doc)).data, parseYaml(text).data, file);
			const report = pipelineProblems(doc, null);
			assert.equal(report.count, 0, `${file}: ${JSON.stringify([...report.byPipe.values()].flat())}`);
			checked += 1;
		}
	}
	assert.ok(checked >= 50, `checked ${checked} pipelines`);
});

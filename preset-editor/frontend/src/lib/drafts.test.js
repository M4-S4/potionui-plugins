import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	canPublish,
	copyFormProblems,
	copyRequestBody,
	describeSource,
	formatStamp,
	initialCopyForm,
	lintSummary,
	parseLintLine,
	slugify,
	targetDirOf
} from './drafts.js';

test('parseLintLine takes the level and the sub-file from the message prefix', () => {
	assert.deepEqual(parseLintLine('[ERROR] /tmp/x/preset.yml: modes/txt2img/pipeline.yml: pipeline[3]: pipe name \'nope\' not found'), {
		level: 'error', file: 'modes/txt2img/pipeline.yml', message: "pipeline[3]: pipe name 'nope' not found",
		raw: "[ERROR] /tmp/x/preset.yml: modes/txt2img/pipeline.yml: pipeline[3]: pipe name 'nope' not found"
	});
	assert.deepEqual(parseLintLine('[WARNING] C:\\x\\preset.yml: no tests.yml: this preset has no E2E test suite').file, 'preset.yml');
	assert.equal(parseLintLine('[WARNING] /x/preset.yml: tests.yml: failed to parse: boom').file, 'tests.yml');
	assert.equal(parseLintLine('[ERROR] /x/preset.yml: modes/txt2img: directory not found').file, 'modes/txt2img');
	assert.equal(parseLintLine('[ERROR] /x/preset.yml: preset.yml: failed to parse: bad').message, 'failed to parse: bad');
	assert.deepEqual(parseLintLine('plain text'), { level: 'error', file: 'preset.yml', message: 'plain text', raw: 'plain text' });
	assert.equal(parseLintLine(null).raw, '');
});

test('lintSummary groups issues by file and says whether the draft is clean', () => {
	const summary = lintSummary({
		errors: ['[ERROR] /p/preset.yml: modes/a/form.yml: bad field', '[ERROR] /p/preset.yml: id missing'],
		warnings: ['[WARNING] /p/preset.yml: modes/a/form.yml: unused'],
		at: '2026-10-15T10:00:00Z'
	});
	assert.equal(summary.clean, false);
	assert.equal(summary.at, '2026-10-15T10:00:00Z');
	assert.deepEqual(summary.files.map((group) => [group.file, group.issues.map((issue) => issue.level)]), [
		['modes/a/form.yml', ['error', 'warning']],
		['preset.yml', ['error']]
	]);
	assert.equal(lintSummary({ errors: [], warnings: [] }).clean, true);
	assert.equal(lintSummary(null).clean, true);
	assert.deepEqual(lintSummary(undefined).files, []);
});

test('canPublish needs a lint report without errors', () => {
	assert.equal(canPublish({ errors: [], warnings: ['w'] }), true);
	assert.equal(canPublish({ errors: ['e'], warnings: [] }), false);
	assert.equal(canPublish(null), false);
});

test('slugify makes a folder name the backend accepts', () => {
	assert.equal(slugify('Flux 2 (Dev) é!'), 'Flux-2-Dev-e');
	assert.equal(slugify('  --weird__name.. '), 'weird__name');
	assert.equal(slugify('!!!'), 'Preset');
	assert.equal(slugify('x'.repeat(80)).length, 64);
	assert.equal(slugify(undefined, 'Fallback'), 'Fallback');
});

test('initialCopyForm proposes a name and folders from the source', () => {
	const form = initialCopyForm({ id: 'krea', name: 'Krea 2', path: 'Krea2/official' });
	assert.deepEqual(form, { from_id: 'krea', name: 'Krea 2 (copy)', preset_id: '', model_dir: 'Krea2', variant_dir: 'custom' });
	assert.deepEqual(initialCopyForm(null), { from_id: '', name: '', preset_id: '', model_dir: '', variant_dir: 'custom' });
	assert.equal(initialCopyForm({ id: 'x', name: 'Loose name', path: '' }).model_dir, 'Loose-name');
});

test('copyFormProblems mirrors the backend rules', () => {
	const good = { from_id: 'krea', name: 'Copy', preset_id: '', model_dir: 'Krea2', variant_dir: 'custom' };
	assert.deepEqual(copyFormProblems(good, { sourceIds: ['krea'] }), {});
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, from_id: '' })), ['from_id']);
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, from_id: 'gone' }, { sourceIds: ['krea'] })), ['from_id']);
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, name: '  ' })), ['name']);
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, name: 'x'.repeat(121) })), ['name']);
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, preset_id: 'no' })), ['preset_id']);
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, model_dir: '.hidden' })), ['model_dir']);
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, model_dir: '' })), ['model_dir']);
	assert.deepEqual(Object.keys(copyFormProblems({ ...good, variant_dir: 'a/b' })), ['variant_dir']);
	assert.deepEqual(copyFormProblems({ ...good, variant_dir: '' }), {});
});

test('copyRequestBody and targetDirOf trim and drop the blanks', () => {
	const form = { from_id: 'krea', name: ' Copy ', preset_id: ' ', model_dir: ' Krea2 ', variant_dir: ' ' };
	assert.deepEqual(copyRequestBody(form), { from_id: 'krea', name: 'Copy', model_dir: 'Krea2' });
	assert.equal(targetDirOf(form), 'Krea2');
	const full = { ...form, preset_id: 'my-id', variant_dir: 'v1' };
	assert.deepEqual(copyRequestBody(full), { from_id: 'krea', name: 'Copy', model_dir: 'Krea2', preset_id: 'my-id', variant_dir: 'v1' });
	assert.equal(targetDirOf(full), 'Krea2/v1');
});

test('describeSource and formatStamp read the draft provenance', () => {
	assert.equal(describeSource('copy_of:krea'), 'Copy of krea');
	assert.equal(describeSource('edit_of:mine'), 'Edit of mine');
	assert.equal(describeSource('restore_of:mine@20261015T113000.123456'), 'Restored version of mine (2026-10-15 11:30:00 UTC)');
	assert.equal(describeSource('restore_of:mine'), 'Restored version of mine');
	assert.equal(describeSource(''), 'Draft');
	assert.equal(describeSource(null), 'Draft');
	assert.equal(formatStamp('nope'), 'nope');
	assert.equal(formatStamp(3), '');
});

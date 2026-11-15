import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deletionPlan, refusalOf, refusalView, removalMessage, removalPlan } from './modes.js';

const REMOVED = 'Its folder leaves the draft and the mode is removed from preset.yml.';
const DELETED = 'The file leaves the draft; publishing writes the draft as it is.';

test('a removal that adds no lint error says only what goes away', () => {
	assert.equal(removalMessage({ allowed: true, errors: [] }), REMOVED);
	assert.equal(removalMessage(null), REMOVED);
});

test('a removal that adds lint errors names them before it is confirmed', () => {
	assert.equal(
		removalMessage({ errors: ['[ERROR] preset.yml: prompt_syntax.loop: \'loop\' is not a mode of this preset'] }),
		`${REMOVED} The lint then reports one new error, and publishing waits until it is fixed: preset.yml: prompt_syntax.loop: 'loop' is not a mode of this preset.`
	);
	assert.equal(
		removalMessage({ errors: ['[ERROR] a: 1', '[ERROR] b: 2', 'c: 3', '[ERROR] d: 4', '[ERROR] e: 5'] }),
		`${REMOVED} The lint then reports 5 new errors, and publishing waits until they are fixed: a: 1; b: 2; c: 3; and 2 more.`
	);
});

test('a removal whose check failed still reaches the confirmation, which says the check did not run', () => {
	for (const result of [{ ok: false, error: { status: 404, message: 'Not found' } }, { ok: false, error: { status: 500, message: 'the lint of the draft without the mode loop could not run (ValueError)' } }, { ok: false }, null]) {
		const plan = removalPlan(result);
		assert.equal(plan.action, 'confirm');
		assert.ok(plan.message.startsWith(`${REMOVED} The check of what the removal leaves did not run (`), plan.message);
	}
	assert.equal(
		removalPlan({ ok: false, error: { message: 'Not found' } }).message,
		`${REMOVED} The check of what the removal leaves did not run (Not found): the server still refuses a mode that another file uses, and the lint shows the rest once the mode is gone.`
	);
});

test('a refused removal becomes a notice with one line per file, and an allowed one the confirmation', () => {
	const data = {
		allowed: false,
		message: 'The mode video cannot be removed: a and b take their pipeline from it, and c loads one of its files. Point them elsewhere, or remove those lines, first.',
		pointers: ['modes/a/pipeline.yml', 'modes/b/pipeline.yml'],
		loaders: ['modes/c/form.yml']
	};
	assert.deepEqual(removalPlan({ ok: true, data }), {
		action: 'refuse',
		refusal: {
			title: 'The mode video cannot be removed',
			lines: ['modes/a/pipeline.yml takes its pipeline from it', 'modes/b/pipeline.yml takes its pipeline from it', 'modes/c/form.yml loads one of its files'],
			ending: 'Point them elsewhere, or remove those lines, first.'
		}
	});
	assert.deepEqual(removalPlan({ ok: true, data: { allowed: true, errors: [] } }), { action: 'confirm', message: REMOVED });
	const link = { allowed: false, message: 'The mode x cannot be removed: the draft holds a link, l, and Preset Editor never works through a link.', pointers: [], loaders: [] };
	assert.deepEqual(removalPlan({ ok: true, data: link }).refusal, { title: link.message, lines: [], ending: '' });
});

test('a file deletion is checked before its confirmation', () => {
	assert.deepEqual(
		deletionPlan({ ok: true, data: { allowed: false, message: 'x.yml cannot be deleted: f.yml loads it. Point it elsewhere, or remove that line, first.', pointers: [], loaders: ['f.yml'] } }),
		{ action: 'refuse', refusal: { title: 'x.yml cannot be deleted', lines: ['f.yml loads it'], ending: 'Point it elsewhere, or remove that line, first.' } }
	);
	assert.deepEqual(deletionPlan({ ok: true, data: { allowed: true } }), { action: 'confirm', message: DELETED });
	assert.equal(
		deletionPlan({ ok: false, error: { message: 'Not found' } }).message,
		`${DELETED} The check of what the deletion breaks did not run (Not found): the server still refuses a file that another file uses.`
	);
});

test('a refusal that arrives with the deletion itself is shown the same way', () => {
	assert.deepEqual(refusalOf({ message: 'x.yml cannot be deleted: f.yml loads it. Point it elsewhere, or remove that line, first.', citing: ['f.yml'], pointers: [], loaders: ['f.yml'] }, 'file'), {
		title: 'x.yml cannot be deleted',
		lines: ['f.yml loads it'],
		ending: 'Point it elsewhere, or remove that line, first.'
	});
	assert.equal(refusalOf({ message: 'Not found' }, 'file'), null);
	assert.deepEqual(refusalView({ message: 'm', pointers: ['p'], loaders: [] }, 'file').lines, ['p takes its pipeline from it']);
});

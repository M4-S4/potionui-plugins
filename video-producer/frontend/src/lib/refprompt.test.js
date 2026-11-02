import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LAYOUTS, acknowledged, migrateReferencePrompt, referencePromptOf, replacement, sameReferencePrompt, setReferencePrompt, withPart } from './refprompt.js';
import { applyShotDraft, inputsChanged, migrateShots, shotDraft } from './shots.js';
import { normalizePrompts } from './api.js';

const reference = {
	layout: 'refs',
	composed: { subject_definitions: '<Subject 1> is the character shown in <Picture 1>.', retention_analysis: '<Subject 1> (appears in [Shot 1]): fully_preserved.', citations: '<Subject 1> appears in the shot.' },
	sent: {},
	overridden: false,
	changed: false,
	ignored: false
};

test('reference prompt: a replacement keeps only the parts of its layout, as text, with its base', () => {
	assert.deepEqual(Object.keys(LAYOUTS), ['refs', 'subjects', 'cast', 'sheet']);
	assert.deepEqual(LAYOUTS.sheet, ['sheet', 'cast']);
	assert.deepEqual(migrateReferencePrompt({ layout: 'cast', parts: { cast: 'Mine.', citations: 'x', extra: 3 }, base: { cast: 'Old.', summary: 'y' } }), { layout: 'cast', parts: { cast: 'Mine.' }, base: { cast: 'Old.' } });
	assert.deepEqual(migrateReferencePrompt({ layout: 'cast', parts: { cast: 4 } }), { layout: 'cast', parts: {}, base: {} });
	for (const bad of [null, 'x', { layout: 'prose', parts: {} }, { layout: 'toString', parts: {} }, { layout: 'cast' }]) assert.equal(migrateReferencePrompt(bad), null);
	assert.equal(referencePromptOf({}), null);
	assert.deepEqual(migrateShots({ clips: [{ id: 's1', referencePrompt: { layout: 'nope' } }, { id: 's2', referencePrompt: { layout: 'subjects', parts: { subject_definitions: 'x' } } }] }).clips, [
		{ id: 's1' },
		{ id: 's2', referencePrompt: { layout: 'subjects', parts: { subject_definitions: 'x' }, base: {} } }
	]);
});

test('reference prompt: replacing starts from the composed text the server sent, and keeping updates only the base', () => {
	const value = replacement(reference);
	assert.deepEqual(value, { layout: 'refs', parts: { ...reference.composed }, base: { ...reference.composed } });
	assert.equal(replacement(null), null);
	const edited = withPart(value, 'citations', 'She walks.');
	assert.deepEqual(edited.parts, { ...reference.composed, citations: 'She walks.' });
	assert.deepEqual(edited.base, reference.composed);
	const moved = { ...reference, composed: { ...reference.composed, citations: '<Subject 1> appears.' } };
	assert.deepEqual(acknowledged(edited, moved), { ...edited, base: moved.composed });
	assert.deepEqual(acknowledged(edited, { ...moved, layout: 'cast' }), edited);
	assert.equal(withPart(null, 'cast', 'x'), null);
});

test('reference prompt: only the layout and the text count as a change, not the base', () => {
	const value = replacement(reference);
	assert.ok(sameReferencePrompt(null, undefined));
	assert.ok(!sameReferencePrompt(null, value));
	assert.ok(sameReferencePrompt(value, { ...value, base: {} }));
	assert.ok(!sameReferencePrompt(value, withPart(value, 'citations', 'Other.')));
	assert.ok(!sameReferencePrompt(value, { ...value, layout: 'subjects' }));
});

test('reference prompt: the shot editor carries the replacement, counts a new text as a change and writes it back', () => {
	const doc = { clips: [{ id: 's1', start: 0, dur: 4 }], prompts: [], frames: [], references: [] };
	const clip = doc.clips[0];
	const before = shotDraft(doc, clip, {});
	assert.equal(before.referencePrompt, null);
	const after = { ...structuredClone(before), referencePrompt: withPart(replacement(reference), 'citations', 'She walks.') };
	assert.ok(inputsChanged(before, after));
	applyShotDraft(doc, clip, before, after, { makeId: () => 'id' });
	assert.deepEqual(clip.referencePrompt, after.referencePrompt);
	assert.equal(clip.revision, 1);
	const kept = { ...structuredClone(after), referencePrompt: { ...after.referencePrompt, base: { citations: 'new' } } };
	assert.ok(!inputsChanged(after, kept));
	applyShotDraft(doc, clip, after, kept, { makeId: () => 'id' });
	assert.deepEqual(clip.referencePrompt.base, { citations: 'new' });
	assert.equal(clip.revision, 1);
	applyShotDraft(doc, clip, kept, { ...kept, referencePrompt: null }, { makeId: () => 'id' });
	assert.ok(!('referencePrompt' in clip));
	const target = { id: 's2' };
	setReferencePrompt(target, { layout: 'nope' });
	assert.ok(!('referencePrompt' in target));
});

test('reference prompt: the prompts route answer carries the composed and the sent part', () => {
	const data = normalizePrompts({
		prompts: [
			{ shot_id: 's1', engine: 'h3', prompt: 'p', reference: { layout: 'subjects', composed: { subject_definitions: 'a', x: 1 }, sent: { subject_definitions: 'b' }, overridden: true, changed: true, ignored: false } },
			{ shot_id: 's2', engine: 'wan', prompt: 'p', reference: { layout: 'prose' } }
		]
	});
	assert.deepEqual(data.prompts.map((p) => p.reference), [{ layout: 'subjects', composed: { subject_definitions: 'a' }, sent: { subject_definitions: 'b' }, overridden: true, changed: true, ignored: false }, null]);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	LABEL_LIMIT,
	PROMPT_LIMIT,
	applyPrompts,
	clipped,
	editedPrompts,
	issuesContext,
	promptChanges,
	promptPlan,
	proposalFrom,
	reviewCount,
	reviewFrom,
	seamsContext,
	shotsContext
} from './assistant.js';

function sampleDoc() {
	return {
		clips: [
			{ id: 'c1', label: 'Ridge', start: 0, dur: 4.004, stage: 'draft', take: 't1' },
			{ id: 'c2', label: '', start: 4, dur: 3, stage: 'todo', take: null },
			{ id: 'c3', label: 'Hut', start: 7, dur: 5, stage: 'todo' }
		],
		prompts: [
			{ id: 'p1', shotId: 'c1', start: 0, dur: 4, strength: 75, text: 'Wide shot of the ridge at dawn.' },
			{ id: 'p2', shotId: 'c2', start: 4, dur: 3, strength: 75, text: 'x'.repeat(400) }
		],
		frames: [
			{ id: 'f1', shotId: 'c1', time: 0, assetId: 'a1', role: 'Début' },
			{ id: 'f2', shotId: 'c1', time: 4, assetId: 'a2', role: 'Fin' },
			{ id: 'f3', shotId: 'c2', time: 4, assetId: null, role: 'first' },
			{ id: 'f4', shotId: 'c3', time: 7, assetId: 'a3', role: 'Transition' }
		]
	};
}

const clone = (value) => JSON.parse(JSON.stringify(value));
let counter = 0;
const makeId = () => `id${++counter}`;

test('clipped: text over the limit ends with an ellipsis and keeps the limit', () => {
	assert.equal(clipped('short'), 'short');
	assert.equal(clipped(null), '');
	assert.equal(clipped('x'.repeat(400)).length, PROMPT_LIMIT);
	assert.ok(clipped('x'.repeat(400)).endsWith('…'));
	assert.equal(clipped('abcdef', 4), 'abc…');
});

test('shotsContext: one entry per shot with its prompt bounded, its frames and its take', () => {
	const shots = shotsContext(sampleDoc(), (c) => c.label || 'Shot');
	assert.deepEqual(shots[0], { id: 'c1', label: 'Ridge', start: 0, dur: 4, stage: 'draft', promptId: 'p1', prompt: 'Wide shot of the ridge at dawn.', hasFirstFrame: true, hasLastFrame: true, take: 't1' });
	assert.equal(shots[1].label, 'Shot');
	assert.equal(shots[1].prompt.length, PROMPT_LIMIT);
	assert.equal(shots[1].hasFirstFrame, false, 'a frame without an asset does not count');
	assert.deepEqual([shots[2].promptId, shots[2].prompt, shots[2].hasFirstFrame, shots[2].hasLastFrame, shots[2].take], [null, '', false, false, null]);
});

test('issuesContext and seamsContext keep only what the backend reads', () => {
	const issues = issuesContext([
		{ level: 'conflict', text: 'Neon is excluded', prompt: { id: 'p1', shotId: 'c1' } },
		{ level: 'missing', text: 'Empty prompt.', prompt: { id: 'p9', shotId: null } }
	]);
	assert.deepEqual(issues, [
		{ shotId: 'c1', level: 'conflict', text: 'Neon is excluded' },
		{ shotId: null, level: 'missing', text: 'Empty prompt.' }
	]);
	const seams = seamsContext([{ from: { id: 'c1' }, to: { id: 'c2' }, issues: [{ kind: 'lum', text: 'Brighter', fix: true }], pending: false, measured: true }]);
	assert.deepEqual(seams, [{ fromShotId: 'c1', toShotId: 'c2', issues: [{ kind: 'lum', text: 'Brighter' }], measured: true }]);
});

test('promptChanges reads both writing tools and drops malformed entries', () => {
	assert.deepEqual(promptChanges('vp_write_shot_prompt', { project_id: 'P', shot_id: 'c1', prompt_id: 'p1', text: 'New', version: 4 }), [{ shotId: 'c1', promptId: 'p1', text: 'New' }]);
	assert.deepEqual(promptChanges('vp_write_shot_prompt', { shot_id: 'c1', text: 'No id' }), []);
	const fixed = promptChanges('vp_fix_conflicts', {
		project_id: 'P',
		changes: [
			{ shot_id: 'c1', prompt_id: 'p1', before: 'Old', after: 'Fixed' },
			{ shot_id: 'c2', prompt_id: 'p2', before: 'Old' }
		],
		version: 4
	});
	assert.deepEqual(fixed, [{ shotId: 'c1', promptId: 'p1', text: 'Fixed' }]);
	assert.deepEqual(promptChanges('vp_fix_conflicts', null), []);
});

test('promptPlan: another project is stale, an old version is a no-op, a skipped version or an edited prompt reloads', () => {
	const doc = sampleDoc();
	const saved = clone(doc);
	const changes = [{ shotId: 'c1', promptId: 'p1', text: 'New' }];
	const base = { changes, projectId: 'P', version: 3, saved, current: doc };
	assert.equal(promptPlan({ ...base, result: { project_id: 'Q', version: 4 } }), 'stale');
	assert.equal(promptPlan({ ...base, projectId: null, result: { project_id: 'P', version: 4 } }), 'stale');
	assert.equal(promptPlan({ ...base, result: { project_id: 'P', version: 4 } }), 'apply');
	assert.equal(promptPlan({ ...base, result: { project_id: 'P', version: 3 } }), 'apply', 'an unchanged save keeps the version');
	assert.equal(promptPlan({ ...base, result: { project_id: 'P', version: 2 } }), 'noop');
	assert.equal(promptPlan({ ...base, result: { project_id: 'P', version: '4' } }), 'noop');
	assert.equal(promptPlan({ ...base, changes: [], result: { project_id: 'P', version: 4 } }), 'noop');
	assert.equal(promptPlan({ ...base, result: { project_id: 'P', version: 5 } }), 'reload');
	assert.equal(promptPlan({ ...base, saved: null, result: { project_id: 'P', version: 4 } }), 'reload');
	assert.equal(promptPlan({ ...base, changes: [{ shotId: 'gone', promptId: 'p9', text: 'New' }], result: { project_id: 'P', version: 4 } }), 'reload');
	const edited = clone(doc);
	edited.prompts[0].text = 'Typed but not saved yet';
	assert.equal(promptPlan({ ...base, current: edited, result: { project_id: 'P', version: 4 } }), 'reload');
	const elsewhere = clone(doc);
	elsewhere.prompts[1].text = 'Another prompt changed';
	assert.equal(promptPlan({ ...base, current: elsewhere, result: { project_id: 'P', version: 4 } }), 'apply', 'unsaved changes on other prompts do not block');
});

test('editedPrompts compares the saved and the current text of the touched shots only', () => {
	const saved = sampleDoc();
	const current = clone(saved);
	current.prompts[1].text = 'changed';
	current.prompts.push({ id: 'p3', shotId: 'c3', start: 7, dur: 5, strength: 75, text: 'new' });
	const changes = [
		{ shotId: 'c1', promptId: 'p1', text: 'a' },
		{ shotId: 'c2', promptId: 'p2', text: 'b' },
		{ shotId: 'c3', promptId: 'p3', text: 'c' }
	];
	assert.deepEqual(editedPrompts(saved, current, changes), ['c2', 'c3']);
});

test('applyPrompts replaces an existing prompt and creates a missing one, the same way on the document and its saved copy', () => {
	const doc = sampleDoc();
	const saved = clone(doc);
	const changes = [
		{ shotId: 'c1', promptId: 'p1', text: 'Rewritten ridge' },
		{ shotId: 'c3', promptId: 'p3', text: 'Inside the hut' },
		{ shotId: 'gone', promptId: 'p9', text: 'Ignored' }
	];
	applyPrompts(doc, changes);
	assert.equal(applyPrompts(saved, changes), saved);
	assert.equal(doc.prompts[0].text, 'Rewritten ridge');
	assert.deepEqual(doc.prompts[2], { id: 'p3', shotId: 'c3', start: 7, dur: 5, strength: 75, text: 'Inside the hut' });
	assert.equal(doc.prompts.length, 3);
	assert.equal(JSON.stringify(doc), JSON.stringify(saved));
});

test('proposalFrom: valid shots become a kept, numbered proposal with bounded label and duration', () => {
	counter = 0;
	const proposal = proposalFrom(
		{
			project_id: 'P',
			proposal: [
				{ label: 'Dawn on the ridge', prompt: ' Wide shot of the ridge. ', duration_s: 4 },
				{ label: 'A label much longer than thirty-four characters', prompt: 'Close-up.', duration_s: 20 },
				{ label: 'Empty', prompt: '  ', duration_s: 4 },
				{ label: 'No duration', prompt: 'Text', duration_s: 'soon' },
				{ prompt: 'Short', duration_s: 1.04 }
			]
		},
		makeId
	);
	assert.deepEqual(proposal[0], { id: 'id1', keep: true, n: 1, label: 'Dawn on the ridge', prompt: 'Wide shot of the ridge.', dur: 4 });
	assert.equal(proposal[1].label.length, LABEL_LIMIT);
	assert.equal(proposal[1].dur, 15);
	assert.deepEqual([proposal[2].n, proposal[2].label, proposal[2].dur], [3, '', 2]);
	assert.equal(proposal.length, 3);
	assert.equal(proposalFrom({ proposal: Array.from({ length: 30 }, () => ({ label: 'x', prompt: 'y', duration_s: 3 })) }, makeId).length, 24);
	assert.deepEqual(proposalFrom({}, makeId), []);
});

test('reviewFrom keeps the seams with issues and marks the measured ones', () => {
	const review = reviewFrom(
		{
			project_id: 'P',
			checked_at: '2026-10-17T12:00:00Z',
			seams: [
				{
					from_shot_id: 'c1',
					to_shot_id: 'c2',
					from_label: 'Ridge',
					to_label: 'Path',
					issues: [
						{ kind: 'lum', text: 'Path is brighter', fix: 'Match the exposure' },
						{ kind: 'camera_change', text: 'Orbit then dolly', fix: null },
						{ kind: 'conflict', text: '“Path”: no neon.', fix: 'Rewrite.', shot_id: 'c2', rule: 'noNeon' }
					]
				},
				{ from_shot_id: 'c2', to_shot_id: 'c3', issues: [{ kind: 'duration', text: ' ' }] },
				{ from_shot_id: 'c2', to_shot_id: 'c3', issues: [{ kind: 'framing', text: 'Measured jump', measured: true }] }
			]
		},
		0
	);
	assert.equal(review.projectId, 'P');
	assert.equal(review.checkedAt, '2026-10-17T12:00:00.000Z');
	assert.equal(review.seams.length, 2);
	assert.deepEqual(review.seams[0].issues, [
		{ kind: 'lum', text: 'Path is brighter', fix: 'Match the exposure', shotId: null, rule: null, measured: true, simulated: false },
		{ kind: 'camera_change', text: 'Orbit then dolly', fix: '', shotId: null, rule: null, measured: false, simulated: false },
		{ kind: 'conflict', text: '“Path”: no neon.', fix: 'Rewrite.', shotId: 'c2', rule: 'noNeon', measured: false, simulated: false }
	]);
	assert.deepEqual([review.seams[1].fromLabel, review.seams[1].toLabel, review.seams[1].issues[0].measured], ['', '', true]);
	const identity = reviewFrom({ project_id: 'P', seams: [{ from_shot_id: 'c1', to_shot_id: 'c2', issues: [{ kind: 'identity', text: 'Check', measured: true }] }] }, 0);
	assert.deepEqual([identity.seams[0].issues[0].measured, identity.seams[0].issues[0].simulated], [false, true]);
	assert.equal(reviewFrom({ project_id: 'P' }), null);
	assert.equal(reviewCount(reviewFrom({ project_id: 'P' })), 0);
	assert.equal(reviewCount(review), 4);
	assert.equal(reviewCount(null), 0);
	const empty = reviewFrom({ project_id: 'P', checked_at: 'not a date', seams: [] }, Date.parse('2026-10-17T08:00:00Z'));
	assert.deepEqual(empty, { projectId: 'P', checkedAt: '2026-10-17T08:00:00.000Z', seams: [] });
});

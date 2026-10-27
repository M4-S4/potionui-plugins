import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyShotDraft, rebaseDraft, shotDraft } from './shots.js';

const clone = (value) => JSON.parse(JSON.stringify(value));
const makeId = () => 'new-ref';

function project() {
	return {
		engine: { variants: 1 },
		clips: [{ id: 's1', label: 'Arrival', start: 0, dur: 4, referenceOverrides: { exclude: ['r-look'] } }],
		prompts: [{ id: 'p1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'Wide shot' }],
		frames: [],
		references: [
			{ id: 'r-look', name: 'Look', space: 'identite', type: 'Style', assetId: 'img-look', role: 'Identité', scope: { type: 'global' } },
			{ id: 'r-rain', name: 'Rain', space: 'identite', type: 'Style', assetId: 'img-rain', role: 'Identité', scope: { type: 'global' } }
		],
		assets: []
	};
}

function assistantCasts(doc) {
	doc.clips[0].cast = { characters: ['c-mara'], place: 'p-dock' };
	doc.references.push({ id: 'r-gate', name: 'Gate', space: 'identite', type: 'Décor', assetId: 'img-gate', role: 'Identité', scope: { type: 'shot', shotId: 's1' } });
	doc.clips[0].referenceOverrides = { exclude: ['r-look', 'r-rain'] };
}

test('saving a shot editor opened before the assistant cast the shot keeps the cast and the reference it added', () => {
	const doc = project();
	const baseline = clone(shotDraft(doc, doc.clips[0], doc.engine));
	const draft = { ...clone(baseline), text: 'Wide shot at dawn' };
	assistantCasts(doc);

	const current = clone(shotDraft(doc, doc.clips[0], doc.engine));
	const { draft: rebased, conflicts } = rebaseDraft(baseline, draft, current);
	const result = applyShotDraft(doc, doc.clips[0], current, rebased, { makeId });

	assert.equal(doc.prompts[0].text, 'Wide shot at dawn');
	assert.deepEqual(doc.clips[0].cast, { characters: ['c-mara'], place: 'p-dock' });
	assert.deepEqual(
		doc.references.map((r) => r.id),
		['r-look', 'r-rain', 'r-gate']
	);
	assert.deepEqual(doc.clips[0].referenceOverrides, { exclude: ['r-look', 'r-rain'] });
	assert.equal(result.changed, true);
	assert.equal(conflicts, 0);
});

test('the editor and the assistant both changing the cast and the left-out references keep what each added and removed', () => {
	const doc = project();
	const baseline = clone(shotDraft(doc, doc.clips[0], doc.engine));
	const draft = { ...clone(baseline), exclude: [], cast: { characters: ['c-ivo'], place: null } };
	assistantCasts(doc);

	const current = clone(shotDraft(doc, doc.clips[0], doc.engine));
	const { draft: rebased, conflicts } = rebaseDraft(baseline, draft, current);
	applyShotDraft(doc, doc.clips[0], current, rebased, { makeId });

	assert.deepEqual(doc.clips[0].cast, { characters: ['c-ivo', 'c-mara'], place: 'p-dock' });
	assert.deepEqual(doc.clips[0].referenceOverrides, { exclude: ['r-rain'] });
	assert.equal(conflicts, 0);
});

test('a prompt rewritten by the assistant while the editor left the text alone is kept, and one the editor also rewrote keeps the editor text as a conflict', () => {
	const doc = project();
	const baseline = clone(shotDraft(doc, doc.clips[0], doc.engine));
	doc.prompts[0].text = 'Wide shot of the dock at night';
	const current = clone(shotDraft(doc, doc.clips[0], doc.engine));

	const untouched = rebaseDraft(baseline, { ...clone(baseline), dur: 6 }, current);
	const rewritten = rebaseDraft(baseline, { ...clone(baseline), text: 'Close on the rider' }, current);

	assert.deepEqual([untouched.draft.text, untouched.draft.dur, untouched.conflicts], ['Wide shot of the dock at night', 6, 0]);
	assert.deepEqual([rewritten.draft.text, rewritten.conflicts], ['Close on the rider', 1]);
});

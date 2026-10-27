import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
	CHARACTERS,
	PLACES,
	addCard,
	bibleContext,
	castCards,
	castLabels,
	castOf,
	convertDirection,
	instructionOf,
	linkable,
	migrateBible,
	migrateCast,
	missingLabels,
	names,
	newCard,
	removeCard,
	sameCast,
	setCast,
	shotsCasting,
	suggestedLabel
} from './bible.js';
import { applyShotDraft, inputsChanged, migrateShots, shotDraft } from './shots.js';
import { migrate } from './starter.js';
import { normalizePrompts } from './api.js';
import { reviewFrom, shotsContext } from './assistant.js';

const here = dirname(fileURLToPath(import.meta.url));
const LABEL_CASES = JSON.parse(readFileSync(join(here, '..', '..', '..', 'tests', 'fixtures', 'bible_labels.json'), 'utf-8'));

const woman = { id: 'c-woman', label: 'the red-haired woman', text: 'Copper hair.', props: 'a lantern', references: ['r1'] };
const fisher = { id: 'c-fisher', label: 'the old fisherman', text: 'White beard.', props: '', references: [] };
const blank = { id: 'c-blank', label: '  ', text: 'No tag.', props: '', references: [] };
const harbour = { id: 'p-harbour', label: 'the harbour', text: 'Mist.', references: [] };

function project(extra = {}) {
	return {
		bible: { characters: [{ ...woman }, { ...fisher }, { ...blank }], places: [{ ...harbour }] },
		clips: [
			{ id: 's1', start: 0, dur: 4, cast: { characters: ['c-fisher', 'c-woman'], place: 'p-harbour' } },
			{ id: 's2', start: 4, dur: 4, cast: { characters: ['c-woman'] } },
			{ id: 's3', start: 8, dur: 4 }
		],
		prompts: [{ id: 'p1', shotId: 's1', start: 0, dur: 4, text: 'The red-haired woman waits.' }],
		references: [
			{ id: 'r1', space: 'identite', name: 'Hero' },
			{ id: 'r2', space: 'decors3d', name: 'Quay' }
		],
		direction: { personnages: '' },
		...extra
	};
}

test('bible: a label is found as whole words ignoring case, accents and spacing, the same cases as the server', () => {
	for (const { label, text, found } of LABEL_CASES) assert.equal(names(text, label), found, `${label} in ${text}`);
});

test('bible: the cards of a cast follow the bible, without the cards that have no tag or no longer exist', () => {
	const doc = project();
	const { characters, place } = castCards(doc, { characters: ['c-fisher', 'c-gone', 'c-blank', 'c-woman'], place: 'p-gone' });
	assert.deepEqual(characters.map((c) => c.id), ['c-woman', 'c-fisher']);
	assert.equal(place, null);
	assert.deepEqual(castLabels(doc, doc.clips[0]), ['the red-haired woman', 'the old fisherman', 'the harbour']);
	assert.deepEqual(castLabels(doc, doc.clips[2]), []);
	assert.deepEqual(missingLabels('The Red-Haired Woman waits.', characters), ['the old fisherman']);
});

test('bible: a cast keeps distinct ids and a place, and goes when it is empty', () => {
	assert.deepEqual(migrateCast({ characters: ['a', 'a', '', 3, 'b'], place: '' }), { characters: ['a', 'b'] });
	assert.deepEqual(migrateCast({ characters: [], place: 'p' }), { place: 'p' });
	assert.equal(migrateCast({ characters: [], place: null }), null);
	assert.equal(migrateCast('cast'), null);
	assert.deepEqual(castOf({}), { characters: [], place: null });
	const clip = { id: 's1', cast: { characters: ['a'] } };
	setCast(clip, { characters: [], place: null });
	assert.ok(!('cast' in clip));
	setCast(clip, { characters: ['b'], place: 'p' });
	assert.deepEqual(clip.cast, { characters: ['b'], place: 'p' });
	assert.ok(sameCast({ characters: ['a', 'b'] }, { characters: ['b', 'a'], place: null }));
	assert.ok(!sameCast({ characters: ['a'] }, { characters: ['a'], place: 'p' }));
	assert.ok(sameCast(undefined, { characters: [] }));
});

test('bible: the migration keeps well-formed cards once, in order, and never creates a bible', () => {
	const bible = migrateBible({
		characters: [{ id: 'c1', label: 'A', text: 'x', props: 'y', references: ['r', 'r', 4], extra: 1 }, { id: 'c1', label: 'dup' }, { label: 'no id' }, 'junk'],
		places: [{ id: 'p1', label: 'P', props: 'dropped' }]
	});
	assert.deepEqual(bible, {
		characters: [{ id: 'c1', label: 'A', text: 'x', references: ['r'], props: 'y' }],
		places: [{ id: 'p1', label: 'P', text: '', references: [] }]
	});
	assert.deepEqual(migrateBible(null), { characters: [], places: [] });
	assert.ok(!('bible' in migrate({ name: 'Old' })));
	const doc = migrate({ name: 'New', bible: { characters: [{ id: 'c1', label: 'A', text: '', props: '', references: [] }], places: [] } });
	assert.deepEqual(doc.bible.characters.map((c) => c.id), ['c1']);
	assert.deepEqual(migrate(doc), doc);
	assert.deepEqual(migrateShots({ clips: [{ id: 's1', cast: { characters: [] } }, { id: 's2', cast: { place: 'p' } }] }).clips, [{ id: 's1' }, { id: 's2', cast: { place: 'p' } }]);
});

test('bible: adding, deleting and counting cards keeps the casts of the shots in step', () => {
	const doc = { clips: [{ id: 's1', cast: { characters: ['c1', 'c2'], place: 'p1' } }, { id: 's2', cast: { characters: ['c1'] } }, { id: 's3' }] };
	addCard(doc, CHARACTERS, newCard(CHARACTERS, 'c3'));
	assert.deepEqual(doc.bible, { characters: [{ props: '', id: 'c3', label: '', text: '', references: [] }], places: [] });
	assert.deepEqual(newCard(PLACES, 'p9'), { id: 'p9', label: '', text: '', references: [] });
	assert.deepEqual(shotsCasting(doc, CHARACTERS, 'c1').map((c) => c.id), ['s1', 's2']);
	assert.deepEqual(shotsCasting(doc, PLACES, 'p1').map((c) => c.id), ['s1']);
	doc.bible.characters.push({ id: 'c1' });
	doc.bible.places.push({ id: 'p1' });
	assert.ok(removeCard(doc, CHARACTERS, 'c1'));
	assert.ok(removeCard(doc, PLACES, 'p1'));
	assert.ok(!removeCard(doc, PLACES, 'p1'));
	assert.deepEqual(doc.clips, [{ id: 's1', cast: { characters: ['c2'] } }, { id: 's2' }, { id: 's3' }]);
	assert.deepEqual(linkable(project(), CHARACTERS).map((r) => r.id), ['r1']);
	assert.deepEqual(linkable(project(), PLACES).map((r) => r.id), ['r2']);
});

test('bible: the free Characters field turns into a card cast in every shot, with a suggested tag', () => {
	const doc = project({ direction: { personnages: '  Lena, a young sailor in a yellow coat. Her brother.  ' } });
	const card = convertDirection(doc, 'c-new');
	assert.deepEqual(card, { props: '', id: 'c-new', label: 'Lena', text: 'Lena, a young sailor in a yellow coat. Her brother.', references: [] });
	assert.equal(doc.direction.personnages, '');
	assert.deepEqual(doc.clips.map((c) => castOf(c).characters), [['c-fisher', 'c-woman', 'c-new'], ['c-woman', 'c-new'], ['c-new']]);
	assert.equal(convertDirection(doc, 'c-other'), null);
	assert.equal(suggestedLabel(`${'x'.repeat(80)} y`), `${'x'.repeat(59)}…`);
});

test('bible: the instruction of a shot is its own prompt, else the global prompt covering most of it', () => {
	const doc = project({
		prompts: [
			{ id: 'p1', shotId: 's1', start: 0, dur: 4, text: ' Own. ' },
			{ id: 'g1', shotId: null, start: 3, dur: 2, text: 'Short.' },
			{ id: 'g2', shotId: null, start: 5, dur: 10, text: 'Long.' }
		]
	});
	assert.equal(instructionOf(doc, doc.clips[0]), 'Own.');
	assert.equal(instructionOf(doc, doc.clips[1]), 'Long.');
	assert.equal(instructionOf({ prompts: [] }, doc.clips[1]), '');
});

test('bible: the shot editor carries the cast, a changed cast counts as a change and is written back', () => {
	const doc = project();
	const clip = doc.clips[1];
	const before = shotDraft(doc, clip, {});
	assert.deepEqual(before.cast, { characters: ['c-woman'], place: null });
	const after = { ...structuredClone(before), cast: { characters: ['c-woman'], place: 'p-harbour' } };
	assert.ok(inputsChanged(before, after));
	assert.ok(!inputsChanged(before, structuredClone(before)));
	const result = applyShotDraft(doc, clip, before, after, { makeId: () => 'id' });
	assert.equal(result.changed, true);
	assert.deepEqual(clip.cast, { characters: ['c-woman'], place: 'p-harbour' });
	assert.equal(clip.revision, 1);
	applyShotDraft(doc, clip, after, { ...after, cast: { characters: [], place: null } }, { makeId: () => 'id' });
	assert.ok(!('cast' in clip));
});

test('bible: the prompts route answer is normalized', () => {
	const data = normalizePrompts({
		prompts: [
			{
				shot_id: 's1',
				preset_id: 'p',
				profile: 'FL2VA',
				engine: 'ltx',
				prompt: 'Hello.',
				video_tracks: [{ slot: 2, track_id: 't2', label: '<Video 1>' }, { slot: '1', label: '<Video 2>' }, { slot: 3 }],
				warnings: [{ code: 'prompt_too_long', message: 'm', data: { tokens: 600 } }, 'junk']
			},
			{ shot_id: 's2', engine: 'mystery' },
			{ prompt: 'no shot' }
		],
		blocks: [{ code: 'no_preset', message: 'm' }]
	});
	assert.deepEqual(data, {
		prompts: [
			{
				shotId: 's1',
				presetId: 'p',
				profile: 'FL2VA',
				engine: 'ltx',
				prompt: 'Hello.',
				reference: null,
				videoTracks: [{ slot: 2, trackId: 't2', label: '<Video 1>' }],
				warnings: [{ code: 'prompt_too_long', message: 'm', data: { tokens: 600 } }]
			},
			{ shotId: 's2', presetId: null, profile: null, engine: 'other', prompt: '', reference: null, videoTracks: [], warnings: [] }
		],
		blocks: [{ code: 'no_preset', message: 'm', data: null }]
	});
	assert.equal(normalizePrompts(null), null);
});

test('bible: the assistant reads the bible and the cast of each shot, and the labels of a continuity issue', () => {
	const doc = project();
	assert.deepEqual(bibleContext(doc), {
		characters: [
			{ label: 'the red-haired woman', text: 'Copper hair.' },
			{ label: 'the old fisherman', text: 'White beard.' }
		],
		places: [{ label: 'the harbour', text: 'Mist.' }]
	});
	assert.deepEqual(shotsContext({ ...doc, frames: [] }, (c) => c.id).map((s) => s.cast), [['the red-haired woman', 'the old fisherman', 'the harbour'], ['the red-haired woman'], []]);
	const review = reviewFrom({ seams: [{ from_shot_id: 's1', to_shot_id: 's1', issues: [{ kind: 'cast_unnamed', text: 'x', labels: ['the old fisherman', 3, ' '] }, { kind: 'lum', text: 'y' }] }] });
	assert.deepEqual(review.seams[0].issues.map((i) => i.labels), [['the old fisherman'], []]);
});

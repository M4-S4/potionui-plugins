import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CHARACTERS, migrateBible, removeCard, setVoice, voiceChoices, voiceReferences } from './bible.js';
import { DEFAULT_LANGUAGE, LANGUAGES, linesOf, migrateDialogue, newLine, nextSpeaker, sameDialogue, setDialogue, spokenLanguage, spokenWords, wordLimit } from './dialogue.js';
import { applyShotDraft, inputsChanged, migrateShots, shotDraft } from './shots.js';
import { migrate } from './starter.js';

const woman = { id: 'c-woman', label: 'the woman', text: '', references: [], props: '', voice: 'a low voice', language: 'French', voiceRef: 'r-voice' };
const fisher = { id: 'c-fisher', label: 'the fisherman', text: '', references: [], props: '' };

function project() {
	return {
		bible: { characters: [{ ...woman }, { ...fisher }], places: [] },
		clips: [
			{ id: 's1', start: 0, dur: 4, cast: { characters: ['c-woman', 'c-fisher'] }, dialogue: [{ id: 'l1', speaker: 'c-woman', text: 'Bonjour.' }] },
			{ id: 's2', start: 4, dur: 2, dialogue: [{ id: 'l2', speaker: 'c-fisher', text: 'Salut.', offscreen: true }] }
		],
		prompts: [],
		frames: [],
		references: [
			{ id: 'r-voice', space: 'son', name: 'Voice', assetId: 'voice' },
			{ id: 'r-hero', space: 'identite', name: 'Hero' }
		]
	};
}

test('dialogue: a line keeps its id, its speaker or none, its words and an off-screen flag only when set; an empty list goes', () => {
	assert.deepEqual(
		migrateDialogue([{ id: 'l1', speaker: 'c-woman', text: 'Hi', offscreen: false, tone: 'soft' }, { id: 'l2', speaker: '', text: 3, offscreen: true }, { id: 'l1', text: 'again' }, 'junk', { speaker: 'x' }]),
		[
			{ id: 'l1', speaker: 'c-woman', text: 'Hi' },
			{ id: 'l2', speaker: null, text: '', offscreen: true }
		]
	);
	assert.equal(migrateDialogue([]), null);
	assert.equal(migrateDialogue('x'), null);
	const clip = { id: 's1', dialogue: [{ id: 'l1', speaker: null, text: 'Hi' }] };
	setDialogue(clip, []);
	assert.ok(!('dialogue' in clip));
	assert.deepEqual(linesOf(clip), []);
	assert.deepEqual(newLine('l9', 'c-woman'), { id: 'l9', speaker: 'c-woman', text: '' });
});

test('dialogue: only the speaker, the words and the off-screen flag count as a change, spaces at the ends aside', () => {
	const a = [{ id: 'l1', speaker: 'c-woman', text: 'Hi' }];
	assert.ok(sameDialogue(a, [{ id: 'other', speaker: 'c-woman', text: ' Hi ' }]));
	assert.ok(!sameDialogue(a, [{ id: 'l1', speaker: null, text: 'Hi' }]));
	assert.ok(!sameDialogue(a, [{ id: 'l1', speaker: 'c-woman', text: 'Hi', offscreen: true }]));
	assert.ok(sameDialogue(undefined, []));
});

test('dialogue: words, the limit of a shot at three words a second, the next speaker and the spoken language', () => {
	assert.equal(spokenWords([{ text: ' Il  part. ' }, { text: '' }, { text: 'Oui' }, {}]), 3);
	assert.equal(wordLimit(4), 12);
	assert.equal(wordLimit(2.5), 7);
	assert.equal(nextSpeaker([], ['c-woman', 'c-fisher']), 'c-woman');
	assert.equal(nextSpeaker([{ speaker: 'c-woman' }], ['c-woman', 'c-fisher']), 'c-fisher');
	assert.equal(nextSpeaker([{ speaker: 'c-woman' }], ['c-woman']), 'c-woman');
	assert.equal(nextSpeaker([], []), null);
	assert.equal(spokenLanguage({}, woman), 'French');
	assert.equal(spokenLanguage({ dialogueLanguage: 'Spanish' }, fisher), 'Spanish');
	assert.equal(spokenLanguage({}, null), DEFAULT_LANGUAGE);
	assert.ok(LANGUAGES.includes(DEFAULT_LANGUAGE));
});

test('dialogue: the shot editor carries the lines, a new line counts as a change and is written back', () => {
	const doc = project();
	const clip = doc.clips[0];
	const before = shotDraft(doc, clip, {});
	assert.deepEqual(before.dialogue, [{ id: 'l1', speaker: 'c-woman', text: 'Bonjour.' }]);
	assert.ok(!inputsChanged(before, structuredClone(before)));
	const after = { ...structuredClone(before), dialogue: [...before.dialogue, { id: 'l3', speaker: 'c-fisher', text: 'Au revoir.' }] };
	assert.ok(inputsChanged(before, after));
	const result = applyShotDraft(doc, clip, before, after, { makeId: () => 'id' });
	assert.equal(result.changed, true);
	assert.equal(clip.revision, 1);
	assert.deepEqual(clip.dialogue.map((l) => l.id), ['l1', 'l3']);
	applyShotDraft(doc, clip, after, { ...after, dialogue: [] }, { makeId: () => 'id' });
	assert.ok(!('dialogue' in clip));
});

test('dialogue: removing a character keeps its lines without a speaker', () => {
	const doc = project();
	removeCard(doc, CHARACTERS, 'c-fisher');
	assert.deepEqual(doc.clips[1].dialogue, [{ id: 'l2', speaker: null, text: 'Salut.', offscreen: true }]);
	assert.equal(doc.clips[0].dialogue[0].speaker, 'c-woman');
});

test('dialogue: a character keeps its voice, its language and its voice reference only when set', () => {
	const bible = migrateBible({ characters: [{ ...woman }, { ...fisher, voice: '', language: '', voiceRef: null }], places: [] });
	assert.deepEqual(bible.characters[0], woman);
	assert.deepEqual(bible.characters[1], fisher);
	const card = { ...fisher };
	setVoice(card, 'voice', 'a hoarse voice');
	assert.equal(card.voice, 'a hoarse voice');
	setVoice(card, 'voice', '');
	assert.ok(!('voice' in card));
	const doc = project();
	assert.deepEqual([...voiceReferences(doc)], ['r-voice']);
	assert.deepEqual(voiceChoices(doc).map((r) => r.id), ['r-voice']);
});

test('dialogue: a stored project keeps its lines and its spoken language through the page migration', () => {
	const doc = { ...project(), dialogueLanguage: 'French' };
	doc.clips[0].dialogue.push({ id: 'l1', text: 'duplicate' }, { text: 'no id' });
	const next = migrate(doc);
	assert.equal(next.dialogueLanguage, 'French');
	assert.deepEqual(next.clips[0].dialogue, [{ id: 'l1', speaker: 'c-woman', text: 'Bonjour.' }]);
	assert.deepEqual(migrateShots({ clips: [{ id: 's1', dialogue: [] }] }).clips[0], { id: 's1' });
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { MAX_REQUEST, WRITER_CODES, canUndo, canWrite, normalizeWriterStatus, normalizeWritten, writeBody, writerCode, writerIdle, writerStep } from './promptwriter.js';
import { normalizePrompts } from './api.js';
import { setShotCardWords, shotCardWordsOf, shotCardWordsView } from './cardwords.js';
import { applyShotDraft, inputsChanged, migrateShots, shotDraft } from './shots.js';

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const READY = { available: true, vision: true, name: 'Qwen3-VL', code: null, message: null };
const run = (state, ...events) => events.reduce(writerStep, state);

test('the writer status reads the core answer and never says available without a model', () => {
	assert.deepEqual(normalizeWriterStatus({ available: true, vision: true, name: 'Qwen3-VL', code: null, message: null, models: [{}] }), READY);
	assert.deepEqual(normalizeWriterStatus({ available: false, vision: true, name: 'x', code: 'no_llm', message: 'No language model.' }), { available: false, vision: false, name: 'x', code: 'no_llm', message: 'No language model.' });
	assert.deepEqual(normalizeWriterStatus({ available: 'yes' }), { available: false, vision: false, name: null, code: 'no_llm', message: null });
	assert.equal(normalizeWriterStatus(null), null);
});

test('a written prompt needs a text and counts the images sent and left out', () => {
	assert.deepEqual(normalizeWritten({ text: '  The fisherman lights his lantern.  ', name: 'Qwen3-VL', images: 2, images_skipped: 0 }), { text: 'The fisherman lights his lantern.', name: 'Qwen3-VL', images: 2, imagesSkipped: 0, imagesDropped: 0, lostTags: [], keptTags: [] });
	assert.deepEqual(normalizeWritten({ text: 'A wave.', images: -1, images_skipped: 'two' }), { text: 'A wave.', name: null, images: 0, imagesSkipped: 0, imagesDropped: 0, lostTags: [], keptTags: [] });
	assert.equal(normalizeWritten({ text: '   ' }), null);
	assert.deepEqual(normalizeWritten({ text: 'A wave.', kept_tags: ['<Subject 3>', '<Audio 1>', '<Scene 1>', '@vref1', 4] }).keptTags, ['<Subject 3>', '<Audio 1>']);
	assert.equal(normalizeWritten({ text: 'A wave.', images: 1, images_dropped: 1 }).imagesDropped, 1);
	assert.deepEqual(normalizeWritten({ text: 'A wave.', lost_tags: ['@vref1', '@VREF2', '@vref0', 'vref3', 7] }).lostTags, ['@vref1', '@VREF2']);
	assert.equal(normalizeWritten(null), null);
});

test('the request sent names the engine of the page and carries the unsaved document', () => {
	const doc = { clips: [] };
	assert.deepEqual(writeBody('  the lantern  ', { preset: 'MiniMax-H3-12GB', model: null }, doc), { request: 'the lantern', preset_id: 'MiniMax-H3-12GB', model_id: null, doc });
	assert.deepEqual(writeBody('x', { preset: 'wan', model: 'm1' }, doc).model_id, 'm1');
});

test('the button writes only with a language model, a request of at most a thousand characters, and not twice at once', () => {
	const open = run(writerIdle(), { type: 'open' });
	assert.equal(canWrite(open, READY), false);
	const asked = run(open, { type: 'edit', request: 'the lantern' });
	assert.equal(canWrite(asked, READY), true);
	assert.equal(canWrite(asked, { ...READY, available: false }), false);
	assert.equal(canWrite(asked, null), false);
	assert.equal(canWrite(run(asked, { type: 'start' }), READY), false);
	assert.equal(canWrite(run(open, { type: 'edit', request: 'x'.repeat(MAX_REQUEST + 1) }), READY), false);
	assert.equal(canWrite(run(open, { type: 'edit', request: '   ' }), READY), false);
});

test('the text is shown before it is placed, and a rejected text leaves the prompt as it was', () => {
	let state = run(writerIdle(), { type: 'open' }, { type: 'edit', request: 'the lantern' }, { type: 'start' });
	assert.equal(state.phase, 'writing');
	state = writerStep(state, { type: 'done', run: state.run, written: { text: 'The fisherman lights his lantern.' } });
	assert.equal(state.phase, 'proposed');
	assert.equal(state.proposal.text, 'The fisherman lights his lantern.');
	assert.equal(state.applied, null);
	state = writerStep(state, { type: 'reject' });
	assert.deepEqual([state.phase, state.proposal, state.applied, state.request], ['open', null, null, 'the lantern']);
});

test('accepting places the text and one undo gives back the prompt of before, only while the text is untouched', () => {
	let state = run(writerIdle(), { type: 'open' }, { type: 'edit', request: 'the lantern' }, { type: 'start' });
	state = writerStep(state, { type: 'done', run: state.run, written: { text: 'Written.' } });
	state = writerStep(state, { type: 'accept', current: 'Mine.' });
	assert.deepEqual([state.phase, state.before, state.applied, state.request], ['closed', 'Mine.', 'Written.', '']);
	assert.equal(canUndo(state, 'Written.'), true);
	assert.equal(canUndo(state, 'Written. And more.'), false);
	state = writerStep(state, { type: 'undo' });
	assert.equal(canUndo(state, 'Written.'), false);
	assert.deepEqual([state.before, state.applied], [null, null]);
});

test('a cancelled or closed writing drops the late answer, and a failure keeps the request for another try', () => {
	let state = run(writerIdle(), { type: 'open' }, { type: 'edit', request: 'the lantern' }, { type: 'start' });
	const first = state.run;
	state = writerStep(state, { type: 'cancel' });
	assert.equal(state.phase, 'open');
	assert.equal(writerStep(state, { type: 'done', run: first, written: { text: 'Late.' } }), state);
	state = writerStep(state, { type: 'start' });
	const second = state.run;
	assert.notEqual(second, first);
	assert.equal(writerStep(state, { type: 'done', run: first, written: { text: 'Late.' } }).phase, 'writing');
	state = writerStep(state, { type: 'fail', run: second, error: { code: 'write_timeout' } });
	assert.deepEqual([state.phase, state.error.code, state.request], ['failed', 'write_timeout', 'the lantern']);
	assert.equal(canWrite(state, READY), true);
	state = run(state, { type: 'start' }, { type: 'close' });
	assert.deepEqual([state.phase, state.error], ['closed', null]);
	assert.equal(writerStep(writerIdle(), { type: 'accept', current: 'x' }).applied, null);
});

test('every failure code the writer names has a message in English and French', () => {
	assert.equal(writerCode({ code: 'no_llm' }), 'no_llm');
	assert.equal(writerCode({ code: 'network_error' }), null);
	assert.equal(writerCode(null), null);
	for (const locale of ['en', 'fr']) {
		const modals = json(`../i18n/${locale}/modals.json`);
		for (const code of WRITER_CODES) assert.ok(modals[`shot.writer.error.${code}`], `${locale} ${code}`);
	}
});

test('the prompts route says which card words a shot uses when a card picture goes with it', () => {
	const data = normalizePrompts({ prompts: [{ shot_id: 's1', card_words: 'label' }, { shot_id: 's2', card_words: 'words' }, { shot_id: 's3' }] });
	assert.deepEqual(
		data.prompts.map((item) => item.cardWords),
		['label', null, null]
	);
});

test('a shot follows the project card words until it sets its own, saved with the rest of the shot editor', () => {
	const doc = { clips: [{ id: 's1', start: 0, dur: 4 }], prompts: [], frames: [], references: [], cardWords: 'label' };
	const clip = doc.clips[0];
	const before = shotDraft(doc, clip, {});
	assert.equal(before.cardWords, null);
	assert.equal(shotCardWordsOf(clip), null);
	const after = { ...structuredClone(before), cardWords: 'picture' };
	assert.equal(inputsChanged(before, after), true);
	applyShotDraft(doc, clip, before, after, { makeId: () => 'id' });
	assert.equal(clip.cardWords, 'picture');
	assert.equal(doc.cardWords, 'label');
	assert.equal(shotDraft(doc, clip, {}).cardWords, 'picture');
	const back = shotDraft(doc, clip, {});
	applyShotDraft(doc, clip, back, { ...back, cardWords: null }, { makeId: () => 'id' });
	assert.equal('cardWords' in clip, false);
	assert.equal(inputsChanged(back, { ...back }), false);
	setShotCardWords(clip, 'card');
	assert.equal(clip.cardWords, 'card');
	setShotCardWords(clip, 'junk');
	assert.equal('cardWords' in clip, false);
});

test('the migration keeps a shot card words only when it is one of the three', () => {
	const doc = migrateShots({ clips: [{ id: 's1', cardWords: 'label' }, { id: 's2', cardWords: 'all' }, { id: 's3' }] });
	assert.deepEqual(doc.clips, [{ id: 's1', cardWords: 'label' }, { id: 's2' }, { id: 's3' }]);
});

test('the card words of a shot are greyed and say why when the shot replaced its reference part by hand', () => {
	const refs = (overridden) => ({ layout: 'refs', composed: {}, sent: {}, overridden, changed: false, ignored: false });
	assert.deepEqual(shotCardWordsView({ cardWords: 'label', reference: refs(false) }, null), { show: true, used: 'label', replaced: false, disabled: false });
	assert.deepEqual(shotCardWordsView({ cardWords: 'label', reference: refs(true) }, 'label'), { show: true, used: 'label', replaced: true, disabled: true });
	assert.deepEqual(shotCardWordsView({ cardWords: null, reference: refs(true) }, 'picture'), { show: true, used: null, replaced: false, disabled: false });
	assert.deepEqual(shotCardWordsView(null, null), { show: false, used: null, replaced: false, disabled: false });
	assert.deepEqual(shotCardWordsView({ cardWords: 'card', reference: { ...refs(true), layout: 'subjects' } }, null).replaced, false);
	const source = readFileSync(new URL('../components/modals/ShotEditor.svelte', import.meta.url), 'utf8');
	assert.match(source, /disabled=\{cardWordsView\.disabled\}/);
	assert.match(source, /cardWordsView\.replaced\) return t\('modals\.shot\.cardWords\.replaced'\)/);
});

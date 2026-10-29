import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';
import { moves, undoneAction } from './keepframing.js';
import { applyShotDraft, inputsChanged, keepsFraming, migrateShots, setKeepFraming, shotDraft } from './shots.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const json = (path) => JSON.parse(source(path));
const { doc, ui, clipLabel, dispose } = await import('./state.svelte.js');
const { noteText } = await import('./production.svelte.js');
const { t } = await import('../i18n/index.svelte.js');
const SHOT_EDITOR = new URL('../components/modals/ShotEditor.svelte', import.meta.url).href;

after(() => dispose());
const WALK = 'The fisherman walks slowly along the stone quay toward the lighthouse, then stops and looks at the boats.';
const IN_PLACE = 'The fisherman stands still on the stone quay, turns his head to look at the boats moored on the right, then turns back toward the camera. He stays where he is.';

const project = () => ({
	bible: { characters: [], places: [] },
	clips: [{ id: 's1', start: 0, dur: 4 }],
	prompts: [{ id: 'p1', shotId: 's1', start: 0, dur: 4, text: WALK }],
	frames: [],
	references: [],
	assets: [],
	direction: {}
});

test('an instruction asks for a move with a verb of moving or a verb and a direction, the same words as the server', () => {
	assert.equal(moves(WALK), true);
	assert.equal(moves(IN_PLACE), false);
	assert.equal(moves('She steps forward and smiles.'), true);
	assert.equal(moves('The dog comes closer to the camera.'), true);
	assert.equal(moves('He turns his head toward the boats.'), false);
	assert.equal(moves('She looks toward the lighthouse, then faces the camera.'), false);
	assert.equal(moves(''), false);
	assert.equal(moves(null), false);
});

test('the editor warns when the shot ends on its first frame and its action moves', () => {
	assert.equal(undoneAction({ first: 'a', last: null, keepFraming: true, text: WALK }), true);
	assert.equal(undoneAction({ first: 'a', last: null, keepFraming: true, text: IN_PLACE }), false);
	assert.equal(undoneAction({ first: 'a', last: 'a', keepFraming: false, text: WALK }), true);
	assert.equal(undoneAction({ first: 'a', last: 'b', keepFraming: false, text: WALK }), false);
	assert.equal(undoneAction({ first: 'a', last: 'b', keepFraming: true, text: WALK }), false);
	assert.equal(undoneAction({ first: null, last: null, keepFraming: true, text: WALK }), false);
	assert.equal(undoneAction(null), false);
});

test('the shot editor carries the option, a change makes the takes out of date and is written back as true or nothing', () => {
	const doc = project();
	const clip = doc.clips[0];
	const before = shotDraft(doc, clip, {});
	assert.equal(before.keepFraming, false);
	const after = { ...structuredClone(before), keepFraming: true };
	assert.ok(inputsChanged(before, after));
	const result = applyShotDraft(doc, clip, before, after, { makeId: () => 'id' });
	assert.equal(result.changed, true);
	assert.equal(clip.keepFraming, true);
	assert.equal(clip.revision, 1);
	assert.equal(shotDraft(doc, clip, {}).keepFraming, true);
	applyShotDraft(doc, clip, after, { ...after, keepFraming: false }, { makeId: () => 'id' });
	assert.equal('keepFraming' in clip, false);
	assert.equal(keepsFraming(clip), false);
	setKeepFraming(clip, true);
	assert.equal(keepsFraming(clip), true);
	setKeepFraming(clip, false);
	assert.equal('keepFraming' in clip, false);
});

test('the migration keeps the option only as true', () => {
	const doc = migrateShots({ clips: [{ id: 's1', keepFraming: true }, { id: 's2', keepFraming: false }, { id: 's3', keepFraming: 'yes' }] });
	assert.deepEqual(doc.clips, [{ id: 's1', keepFraming: true }, { id: 's2' }, { id: 's3' }]);
});

test('wiring: the editor switch and warning, the estimate warnings naming their shot, in English and French', async () => {
	ui.me = null;
	doc.assets = [{ id: 'a', kind: 'image', name: 'Start', src: '/m/start.png' }];
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo', keepFraming: true }];
	doc.prompts = [{ id: 'p1', shotId: 's1', start: 0, dur: 4, strength: 75, text: WALK }];
	doc.frames = [{ id: 'f1', shotId: 's1', time: 0, assetId: 'a', role: 'first', strength: 100 }];
	const kept = await renderComponent(SHOT_EDITOR, { id: 's1' });
	const toggle = hostUis(kept, 'Switch').find((props) => props.id === 'vp-shot-keep-framing');
	assert.deepEqual([toggle.checked, toggle.label], [true, t('modals.shot.keepFraming')]);
	assert.match(kept, /data-action-undone/);
	assert.ok(textOf(kept).includes(t('modals.shot.actionUndone')));
	delete doc.clips[0].keepFraming;
	const free = await renderComponent(SHOT_EDITOR, { id: 's1' });
	assert.equal(hostUis(free, 'Switch').find((props) => props.id === 'vp-shot-keep-framing').checked, false);
	assert.doesNotMatch(free, /data-action-undone/);
	const shot = clipLabel(doc.clips[0]);
	for (const [code, key] of [['keep_framing_unavailable', 'keepFramingUnavailable'], ['keep_framing_last_frame', 'keepFramingLast'], ['action_undone', 'actionUndone']]) {
		assert.equal(noteText({ code, data: { shot_id: 's1' } }), t(`generation.warn.${key}`, { shot }));
		for (const locale of ['en', 'fr']) assert.ok(json(`../i18n/${locale}/generation.json`)[`warn.${key}`], `${locale} warn.${key}`);
	}
	for (const locale of ['en', 'fr']) {
		const modals = json(`../i18n/${locale}/modals.json`);
		for (const key of ['shot.keepFraming', 'shot.keepFramingHint', 'shot.keepFramingLast', 'shot.actionUndone']) assert.ok(modals[key], `${locale} ${key}`);
		assert.ok(json(`../i18n/${locale}/panels.json`)['director.pick.keepFraming'], `${locale} director.pick.keepFraming`);
	}
});

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, hostUis, renderComponent, textOf } from './svelte-harness.js';
import { normalizePreset } from './api.js';
import { FAMILY_ICONS, TYPE_KEYS } from './reftags.js';
import { applyShotDraft, inputsChanged, migrateShots, setExcluded, shotDraft } from './shots.js';
import {
	CONDITION,
	IGNORED,
	MAX_MARGIN,
	MUX,
	SOUND_ROLE,
	SOUND_SPACE,
	SOUND_TYPES,
	audioBehavior,
	conditionWindow,
	excludedLanesOf,
	followLane,
	hasOwnReference,
	isReferenceItem,
	isReferenceLane,
	muxWindow,
	referenceLanes,
	referenceMargin,
	setExcludedLanes,
	setReferenceItem,
	setReferenceLane,
	setReferenceMargin,
	shotSound,
	soundReferences,
	trackPortion
} from './sound.js';
import { typesOf } from './refmedia.js';
import { laneTitle } from './tracks.js';

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { families, refTypeLabel } = await import('./references.js');
const { noteText } = await import('./production.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const WAN = '01KX47WANVIDEO0000000000TV';
const SOUND_NOTE = new URL('../components/shots/SoundNote.svelte', import.meta.url).href;
const INSPECTOR = new URL('../components/inspector/Inspector.svelte', import.meta.url).href;
const CONSOLE = new URL('../components/mixer/Console.svelte', import.meta.url).href;
const STORYBOARD = new URL('../components/storyboard/StoryboardView.svelte', import.meta.url).href;
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

after(() => dispose());
const lane = (id, extra = {}) => ({ id, name: id, role: 'Dialogue', vol: 0, pan: 0, mute: false, solo: false, ...extra });
const item = (id, laneId, start, dur) => ({ id, assetId: 'voice', lane: laneId, start, dur, srcIn: 0, fadeIn: 0, fadeOut: 0, gain: 0 });

function soundDoc(extra = {}) {
	return {
		engine: { variants: 2 },
		clips: [{ id: 's1', start: 2, dur: 3 }],
		lanes: [lane('A1', { reference: true }), lane('A2', { reference: true }), lane('A3')],
		audio: [item('a', 'A1', 0, 2.5), item('b', 'A1', 4, 4), item('c', 'A1', 9, 1), item('d', 'A2', 5.5, 1), item('e', 'A3', 2, 3)],
		assets: [
			{ id: 'voice', kind: 'audio', name: 'voice.wav', src: '/v.wav', srcDur: 6 },
			{ id: 'rain', kind: 'audio', name: 'rain.wav', src: '/r.wav', srcDur: 20 },
			{ id: 'hero', kind: 'image', name: 'hero.png', src: '/h.png' }
		],
		references: [
			{ id: 'g-rain', name: 'Rain', space: SOUND_SPACE, type: 'Ambiance', assetId: 'rain', role: SOUND_ROLE, scope: { type: 'global' } },
			{ id: 'g-hero', name: 'Hero', space: 'identite', type: 'Personnage', assetId: 'hero', role: 'Identité', scope: { type: 'global' } },
			{ id: 's-voice', name: 'Voice', space: SOUND_SPACE, type: 'Voix', assetId: 'voice', role: SOUND_ROLE, scope: { type: 'shot', shotId: 's1' } },
			{ id: 'o-voice', name: 'Other', space: SOUND_SPACE, type: 'Voix', assetId: 'voice', role: SOUND_ROLE, scope: { type: 'shot', shotId: 's9' } }
		],
		...extra
	};
}


test('margin: read from the engine of the project, 0 by default, held between 0 and 10 seconds, removed at 0', () => {
	const engine = {};
	assert.equal(referenceMargin(engine), 0);
	setReferenceMargin(engine, '2.46');
	assert.equal(engine.referenceMargin, 2.5);
	setReferenceMargin(engine, 40);
	assert.equal(engine.referenceMargin, MAX_MARGIN);
	assert.equal(referenceMargin({ referenceMargin: -3 }), 0);
	assert.equal(referenceMargin({ referenceMargin: '3' }), 0);
	setReferenceMargin(engine, 0);
	assert.equal('referenceMargin' in engine, false);
});

test('reference track: the flag is a boolean set on the lane and removed when unchecked', () => {
	const l = lane('A1');
	assert.equal(isReferenceLane(l), false);
	setReferenceLane(l, true);
	assert.equal(l.reference, true);
	setReferenceLane(l, false);
	assert.equal('reference' in l, false);
});

test('reference clip: its own flag wins over its track, and without one it follows the track', () => {
	const on = lane('A1', { reference: true });
	const off = lane('A2');
	const clip = item('x', 'A1', 0, 1);
	assert.equal(isReferenceItem(clip, on), true);
	assert.equal(isReferenceItem(clip, off), false);
	setReferenceItem(clip, on, false);
	assert.equal(clip.reference, false);
	assert.equal(isReferenceItem(clip, on), false);
	setReferenceItem(clip, on, true);
	assert.equal(hasOwnReference(clip), false);
	setReferenceItem(clip, off, true);
	assert.deepEqual([clip.reference, isReferenceItem(clip, off), isReferenceItem(clip, null)], [true, true, true]);
	followLane(clip);
	assert.equal('reference' in clip, false);
	assert.equal(isReferenceItem({ reference: 'yes' }, on), true);
});

test('portion of a track: the items of that track crossing the interval, clipped to it, in time order', () => {
	const doc = soundDoc();
	assert.deepEqual(
		trackPortion(doc, 'A1', [2, 5]).map(({ item: i, from, to }) => [i.id, from, to]),
		[
			['a', 2, 2.5],
			['b', 4, 5]
		]
	);
	assert.deepEqual(trackPortion(doc, 'A2', [2, 5]), []);
	assert.deepEqual(trackPortion(doc, 'A1', [2.5, 4]), []);
});

test('windows: a guided shot takes the margin on both sides, never before 0; a mixed shot is cut to itself', () => {
	const doc = soundDoc({ engine: { referenceMargin: 2.5 } });
	assert.deepEqual(conditionWindow(doc, doc.clips[0]), [0, 7.5]);
	assert.deepEqual(muxWindow(doc.clips[0]), [2, 5]);
});

test('behaviour: MiniMax H3 in Ref2VA guides with the sound, an engine whose director takes audio mixes it, the others ignore it', () => {
	assert.equal(audioBehavior(null, 'FL2VA'), null);
	assert.equal(audioBehavior({ id: 'h3', audioMux: true }, 'Ref2VA'), CONDITION);
	assert.equal(audioBehavior({ id: 'ltx', audioMux: true }, 'FL2VA'), MUX);
	assert.equal(audioBehavior({ id: 'wan', audioMux: false }, 'FL2VA'), IGNORED);
	assert.equal(audioBehavior({ id: 'cloud', cloud: true, audioMux: true }, 'FL2VA'), IGNORED);
	assert.equal(normalizePreset({ id: 'ltx', audio_mux: true }).audioMux, true);
	assert.equal(normalizePreset({ id: 'wan' }).audioMux, false);
});

test('sound of a shot: its own sounds then the global ones, its reference tracks, and what a muted or silent track does not send', () => {
	const doc = soundDoc();
	assert.deepEqual(
		soundReferences(doc, doc.clips[0]).map((r) => r.id),
		['s-voice', 'g-rain']
	);
	const mixed = shotSound(doc, doc.clips[0], { audioMux: true }, 'FL2VA');
	assert.equal(mixed.behavior, MUX);
	assert.deepEqual(mixed.window, [2, 5]);
	assert.deepEqual(mixed.lanes, ['A1']);
	assert.deepEqual(mixed.warnings, [{ code: 'audio_track_empty', laneId: 'A2' }]);
	assert.equal(mixed.sends, true);

	doc.engine.referenceMargin = 1;
	doc.lanes[0].mute = true;
	const guided = shotSound(doc, doc.clips[0], { audioMux: true }, 'Ref2VA');
	assert.deepEqual(guided.window, [1, 6]);
	assert.deepEqual(guided.lanes, ['A2']);
	assert.deepEqual(guided.warnings, [{ code: 'audio_track_muted', laneId: 'A1' }]);

	assert.equal(shotSound(doc, doc.clips[0], { audioMux: false }, 'FL2VA').sends, false);
	assert.equal(shotSound({ ...doc, references: [], lanes: [lane('A1')] }, doc.clips[0], { audioMux: true }, 'FL2VA'), null);
});

test('sound of a shot: the voice of a character of the bible is a sample for Ref2VA, never a sound mixed onto a take', () => {
	const doc = soundDoc({ bible: { characters: [{ id: 'c-woman', label: 'the woman', text: '', props: '', references: [], voiceRef: 's-voice' }], places: [] } });
	assert.deepEqual(shotSound(doc, doc.clips[0], { audioMux: true }, 'FL2VA').references.map((r) => r.id), ['g-rain']);
	assert.deepEqual(shotSound(doc, doc.clips[0], { audioMux: true }, 'Ref2VA').references.map((r) => r.id), ['s-voice', 'g-rain']);
});

function clipsDoc() {
	const doc = soundDoc({ references: [] });
	doc.lanes.push(lane('A4'));
	doc.audio = [
		item('a', 'A1', 1, 2),
		{ ...item('b', 'A1', 3, 3), reference: false },
		{ ...item('c', 'A3', 2, 3), reference: true },
		item('d', 'A3', 6, 2),
		{ ...item('e', 'A2', 2, 3), reference: false },
		{ ...item('f', 'A4', 9, 1), reference: true }
	];
	return doc;
}

test('reference clips: a track sends the clips set or left as a reference under the shot, and a clip switched off says nothing', () => {
	const doc = clipsDoc();
	const clip = doc.clips[0];
	assert.deepEqual(
		trackPortion(doc, 'A1', [2, 5]).map(({ item: i, from, to }) => [i.id, from, to]),
		[['a', 2, 3]]
	);
	assert.deepEqual(
		trackPortion(doc, 'A3', [2, 5]).map(({ item: i }) => i.id),
		['c']
	);
	assert.deepEqual(trackPortion(doc, 'A2', [2, 5]), []);
	assert.deepEqual(
		referenceLanes(doc, clip, [], [2, 5]).map((x) => x.lane.id),
		['A1', 'A3']
	);
	assert.deepEqual(
		referenceLanes(doc, clip, [], [3.5, 5]).map((x) => x.lane.id),
		['A3']
	);
	assert.deepEqual(
		referenceLanes(doc, clip, [], [6.5, 7]).map((x) => x.lane.id),
		['A1', 'A2']
	);

	const mixed = shotSound(doc, clip, { audioMux: true }, 'FL2VA');
	assert.deepEqual([mixed.lanes, mixed.warnings, mixed.sends], [['A1', 'A3'], [], true]);
	doc.engine.referenceMargin = 4;
	const guided = shotSound(doc, clip, { audioMux: true }, 'Ref2VA');
	assert.deepEqual(guided.window, [0, 9]);
	assert.deepEqual([guided.lanes, guided.warnings], [['A1', 'A3'], []]);
	doc.engine.referenceMargin = 0;

	doc.lanes[2].mute = true;
	doc.audio[0].reference = false;
	const muted = shotSound(doc, clip, { audioMux: true }, 'FL2VA');
	assert.deepEqual([muted.lanes, muted.warnings, muted.sends], [[], [{ code: 'audio_track_muted', laneId: 'A3' }], false]);
	doc.audio[2].reference = false;
	assert.equal(shotSound(doc, clip, { audioMux: true }, 'Ref2VA'), null);
	assert.equal(shotSound(doc, clip, { audioMux: false }, 'FL2VA'), null);
	doc.audio[5].start = 3;
	assert.deepEqual(shotSound(doc, clip, { audioMux: false }, 'FL2VA').behavior, IGNORED);
});

test('a shot leaves out a global sound by its reference id and a reference track by its lane id', () => {
	const doc = soundDoc();
	const clip = doc.clips[0];
	setExcluded(clip, ['g-rain']);
	setExcludedLanes(clip, ['A2', 'A2', '']);
	assert.deepEqual(clip.referenceOverrides, { exclude: ['g-rain'], excludeLanes: ['A2'] });
	assert.deepEqual(soundReferences(doc, clip).map((r) => r.id), ['s-voice']);
	assert.deepEqual(referenceLanes(doc, clip).map((x) => [x.lane.id, x.excluded]), [
		['A1', false],
		['A2', true]
	]);
	assert.deepEqual(shotSound(doc, clip, { audioMux: true }, 'FL2VA').lanes, ['A1']);
});

test('referenceOverrides stays extensible: each key is set and cleared on its own and unknown keys survive', () => {
	const clip = { id: 's1', referenceOverrides: { future: true } };
	setExcludedLanes(clip, ['A1']);
	setExcluded(clip, ['r1']);
	assert.deepEqual(clip.referenceOverrides, { future: true, excludeLanes: ['A1'], exclude: ['r1'] });
	setExcludedLanes(clip, []);
	assert.deepEqual(clip.referenceOverrides, { future: true, exclude: ['r1'] });
	setExcluded(clip, []);
	assert.deepEqual(clip.referenceOverrides, { future: true });
	const bare = { id: 's2' };
	setExcludedLanes(bare, []);
	assert.equal('referenceOverrides' in bare, false);
	assert.deepEqual(excludedLanesOf({ referenceOverrides: { excludeLanes: 'A1' } }), []);
});

test('migration keeps the tracks a shot leaves out next to its excluded references and drops the malformed ones', () => {
	const migrated = migrateShots({
		clips: [
			{ id: 's1', referenceOverrides: { exclude: ['r1'], excludeLanes: ['A1', 'A1', 4] } },
			{ id: 's2', referenceOverrides: { excludeLanes: [] } },
			{ id: 's3', referenceOverrides: { excludeLanes: ['A2'] } }
		]
	});
	assert.deepEqual(
		migrated.clips.map((c) => c.referenceOverrides ?? null),
		[{ exclude: ['r1'], excludeLanes: ['A1'] }, null, { excludeLanes: ['A2'] }]
	);
});

test('shot editor: the draft carries the excluded tracks and saving one marks the takes as made from an older prompt', () => {
	const doc = { ...soundDoc(), prompts: [], frames: [] };
	const clip = doc.clips[0];
	const before = shotDraft(doc, clip, doc.engine);
	assert.deepEqual(before.excludeLanes, []);
	const after = { ...before, excludeLanes: ['A1'] };
	assert.equal(inputsChanged(before, after), true);
	assert.deepEqual(applyShotDraft(doc, clip, before, after, { makeId: () => 'x', engine: doc.engine }), { changed: true, resized: false, released: null });
	assert.deepEqual(clip.referenceOverrides, { excludeLanes: ['A1'] });
	assert.equal(clip.revision, 1);
});


test('sound space: a new reference family with its voice, music and ambience types, listed after the others with its icon and its words', () => {
	assert.equal(SOUND_SPACE, 'son');
	assert.deepEqual(SOUND_TYPES, ['Voix', 'Musique', 'Ambiance']);
	const family = families.find((f) => f.id === SOUND_SPACE);
	assert.equal(families.indexOf(family), families.length - 1);
	assert.equal(family.icon, FAMILY_ICONS[SOUND_SPACE]);
	assert.equal(FAMILY_ICONS[SOUND_SPACE], 'wave');
	assert.deepEqual([family.label, family.short, family.hint], [t('lib.family.son.label'), t('lib.family.son.short'), t('lib.family.son.hint')]);
	assert.deepEqual(typesOf(SOUND_SPACE), SOUND_TYPES);
	assert.deepEqual(SOUND_TYPES.map((type) => TYPE_KEYS[type]), ['voice', 'music', 'ambience']);
	assert.deepEqual(SOUND_TYPES.map(refTypeLabel), SOUND_TYPES.map((type) => t(`lib.refType.${TYPE_KEYS[type]}`)));
});

test('the pages say how the sound of a shot is taken: the note of a shot in full and on a card, the reference switches of the Inspector and the console, and the words of the production notes', async () => {
	for (const [behavior, key, tone] of [[CONDITION, 'generation.sound.condition', 'text-success'], [MUX, 'generation.sound.mux', 'text-fg-muted'], [IGNORED, 'generation.sound.ignored', 'text-warning']]) {
		const full = clean(await renderComponent(SOUND_NOTE, { behavior }));
		assert.match(full, new RegExp(`<p class="[^"]*${tone}"`), behavior);
		assert.equal(textOf(full), t(key));
		const compact = clean(await renderComponent(SOUND_NOTE, { behavior, compact: true }));
		assert.match(compact, new RegExp(`<span class="[^"]*${tone}" role="img" aria-label="${escaped(t(key))}"`), behavior);
		assert.deepEqual(hostUis(compact, 'Tooltip').map((tip) => tip.text), [t(key)]);
	}
	project.id = 'p1';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'], audioMux: true }] };
	ui.workspace = 'storyboard';
	ui.storyView = 'grid';
	doc.engine = { backend: 'native', preset: WAN, model: null };
	doc.clips = [{ id: 's1', start: 0, dur: 4, srcIn: 0, stage: 'todo', label: 'One', take: null }, { id: 's2', start: 4, dur: 4, srcIn: 0, stage: 'todo', label: 'Two', take: null }];
	doc.assets = [{ id: 'stem', kind: 'audio', name: 'stem.wav', src: '/s.wav', srcDur: 20 }];
	doc.audio = [{ id: 'a1', assetId: 'stem', lane: doc.lanes[0].id, start: 0, dur: 8, srcIn: 0, fadeIn: 0, fadeOut: 0, gain: 0 }];
	doc.lanes[0].reference = true;
	setTakes('p1', []);
	assert.deepEqual([...clean(await renderComponent(STORYBOARD)).matchAll(/data-shot-sound="([^"]*)"/g)].map((m) => m[1]), [MUX, MUX]);
	ui.me.presets[0].audioMux = false;
	assert.deepEqual([...clean(await renderComponent(STORYBOARD)).matchAll(/data-shot-sound="([^"]*)"/g)].map((m) => m[1]), [IGNORED, IGNORED]);
	ui.selection = { kind: 'lane', id: doc.lanes[0].id };
	const laneSwitch = async () => hostUis(await renderComponent(INSPECTOR), 'Switch').filter((item) => item.id === 'vp-lane-reference').map((item) => item.checked);
	assert.deepEqual(await laneSwitch(), [true]);
	setReferenceLane(doc.lanes[0], false);
	assert.deepEqual(await laneSwitch(), [false]);
	setReferenceLane(doc.lanes[0], true);
	const pressed = (html) => doc.lanes.map((l) => clean(html).match(new RegExp(`aria-pressed="(true|false)" aria-label="${escaped(t('mixer.reference', { name: l.name }))}"`))?.[1]);
	assert.deepEqual(pressed(await renderComponent(CONSOLE)), ['true', ...doc.lanes.slice(1).map(() => 'false')]);
	const shot = { shot_id: 's1' };
	const lane = { shot_id: 's1', lane_id: doc.lanes[0].id };
	const name = laneTitle(doc.lanes, doc.lanes[0]);
	assert.deepEqual(
		[['audio_condition', shot], ['audio_mux', shot], ['audio_ignored', shot], ['audio_track_muted', lane], ['audio_track_empty', lane], ['audio_track_silent', lane], ['audio_only_references', shot], ['audio_ffmpeg_missing', {}], ['audio_source_missing', shot]].map(([code, data]) => noteText({ code, data })),
		[
			t('generation.warn.audioCondition', { shot: 'One' }),
			t('generation.warn.audioMux', { shot: 'One' }),
			t('generation.warn.audioIgnored', { shot: 'One' }),
			t('generation.warn.audioTrackMuted', { shot: 'One', lane: name }),
			t('generation.warn.audioTrackEmpty', { shot: 'One', lane: name }),
			t('generation.warn.audioTrackSilent', { shot: 'One', lane: name }),
			t('generation.block.audioOnly', { shot: 'One' }),
			t('generation.block.audioFfmpeg'),
			t('generation.block.audioSource', { shot: 'One' })
		]
	);
});

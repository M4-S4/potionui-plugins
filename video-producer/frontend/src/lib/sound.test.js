import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { normalizePreset } from './api.js';
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
	isReferenceLane,
	muxWindow,
	referenceLanes,
	referenceMargin,
	setExcludedLanes,
	setReferenceLane,
	setReferenceMargin,
	shotSound,
	soundReferences,
	trackPortion
} from './sound.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
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

test('sound space: a new reference family with its voice, music and ambience types, listed with the others', () => {
	assert.equal(SOUND_SPACE, 'son');
	assert.deepEqual(SOUND_TYPES, ['Voix', 'Musique', 'Ambiance']);
	const references = source('./references.js');
	assert.match(references, /id: SOUND_SPACE,\n\t\ticon: 'wave'/);
	assert.match(references, /\[SOUND_SPACE\]: SOUND_TYPES/);
	assert.match(references, /if \(type === 'Voix'\) return t\('lib\.refType\.voice'\)/);
});

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
	assert.deepEqual(applyShotDraft(doc, clip, before, after, { makeId: () => 'x', engine: doc.engine }), { changed: true, resized: false });
	assert.deepEqual(clip.referenceOverrides, { excludeLanes: ['A1'] });
	assert.equal(clip.revision, 1);
});

test('the pages say how the sound of a shot is taken: the shot editor, the Storyboard card, the Inspector, the console and the Engine section', () => {
	assert.match(source('../components/modals/ShotEditor.svelte'), /<SoundNote \{behavior\} \/>/);
	assert.match(source('../components/storyboard/StoryboardView.svelte'), /<SoundNote behavior=\{sound\.behavior\} compact \/>/);
	assert.match(source('../components/inspector/Inspector.svelte'), /setReferenceLane\(item, v\)/);
	assert.match(source('../components/mixer/Console.svelte'), /setReferenceLane\(l, !isReferenceLane\(l\)\)/);
	assert.match(source('../components/panels/DirectorDock.svelte'), /setReferenceMargin\(doc\.engine, e\.currentTarget\.value\)/);
	const production = source('./production.svelte.js');
	for (const code of ['audio_condition', 'audio_mux', 'audio_ignored', 'audio_track_muted', 'audio_track_empty', 'audio_only_references', 'audio_ffmpeg_missing', 'audio_source_missing']) {
		assert.match(production, new RegExp(`code === '${code}'`));
	}
});

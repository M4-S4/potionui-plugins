import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isUlid } from './ulid.js';
import { migrate } from './starter.js';
import {
	SOUND_FALLBACK,
	anySolo,
	clipSoundAudible,
	fitSounds,
	laneAudible,
	laneCode,
	laneFor,
	laneItemCount,
	laneTitle,
	migrateTracks,
	newLaneId,
	newSound,
	removeLane,
	soundSpan,
	videoTrack
} from './tracks.js';

const here = dirname(fileURLToPath(import.meta.url));

function lane(id, extra = {}) {
	return { id, name: id, role: 'Ambiance', vol: 0, pan: 0, mute: false, solo: false, sends: { R1: -60, D1: -60 }, inserts: [], ...extra };
}

function makeDoc({ lanes = ['A1', 'A2', 'A3'], video, audio = [], clips = [] } = {}) {
	return {
		lanes: lanes.map((l) => (typeof l === 'string' ? lane(l) : l)),
		audio,
		clips,
		engine: { audioDriver: 'A1' },
		...(video ? { video } : {})
	};
}

test('videoTrack: both flags off when the document has no video track or a malformed one', () => {
	assert.deepEqual(videoTrack({}), { mute: false, solo: false });
	assert.deepEqual(videoTrack({ video: null }), { mute: false, solo: false });
	assert.deepEqual(videoTrack({ video: { mute: 'yes', solo: 1 } }), { mute: false, solo: false });
	assert.deepEqual(videoTrack({ video: { mute: true, solo: false } }), { mute: true, solo: false });
});

test('anySolo: the video track counts with the audio lanes', () => {
	assert.equal(anySolo(makeDoc()), false);
	assert.equal(anySolo(makeDoc({ video: { mute: false, solo: true } })), true);
	assert.equal(anySolo(makeDoc({ lanes: ['A1', lane('A2', { solo: true })] })), true);
});

test('laneAudible: a missing lane is silent, a muted lane too, a soloed track silences the others', () => {
	const doc = makeDoc({ lanes: ['A1', lane('A2', { mute: true })] });
	assert.equal(laneAudible(doc, doc.lanes[0]), true);
	assert.equal(laneAudible(doc, doc.lanes[1]), false);
	assert.equal(laneAudible(doc, undefined), false);
	assert.equal(laneAudible(doc, null), false);
	const solo = makeDoc({ lanes: [lane('A1', { solo: true }), 'A2'] });
	assert.deepEqual(solo.lanes.map((l) => laneAudible(solo, l)), [true, false]);
	const soloMuted = makeDoc({ lanes: [lane('A1', { solo: true, mute: true }), 'A2'] });
	assert.deepEqual(soloMuted.lanes.map((l) => laneAudible(soloMuted, l)), [false, false]);
	const videoSolo = makeDoc({ video: { mute: false, solo: true } });
	assert.ok(videoSolo.lanes.every((l) => !laneAudible(videoSolo, l)), 'a soloed video track silences every audio lane that is not soloed');
});

test('clipSoundAudible: track mute, shot mute and the solo of any track', () => {
	const clip = { id: 'c1' };
	assert.equal(clipSoundAudible(makeDoc(), clip), true);
	assert.equal(clipSoundAudible(makeDoc(), { ...clip, mute: true }), false);
	assert.equal(clipSoundAudible(makeDoc({ video: { mute: true, solo: false } }), clip), false);
	assert.equal(clipSoundAudible(makeDoc({ video: { mute: true, solo: true } }), clip), false, 'mute wins over solo');
	const audioSolo = makeDoc({ lanes: [lane('A1', { solo: true }), 'A2'] });
	assert.equal(clipSoundAudible(audioSolo, clip), false, 'a soloed audio lane silences the shots');
	const both = makeDoc({ lanes: [lane('A1', { solo: true }), 'A2'], video: { mute: false, solo: true } });
	assert.equal(clipSoundAudible(both, clip), true);
	assert.deepEqual(both.lanes.map((l) => laneAudible(both, l)), [true, false]);
	assert.equal(clipSoundAudible(makeDoc({ video: { mute: false, solo: true } }), { ...clip, mute: true }), false);
	assert.equal(clipSoundAudible({}, clip), true, 'a document from before the video track plays the shots');
});

test('laneCode and laneTitle: A1, A2… by position, renumbered when a lane goes, whatever the ids', () => {
	const lanes = [lane('X'), lane('01J00000000000000000000000'), lane('A1')];
	assert.deepEqual(lanes.map((l) => laneCode(lanes, l.id)), ['A1', 'A2', 'A3']);
	assert.equal(laneCode(lanes, 'missing'), '');
	assert.equal(laneTitle(lanes, { ...lanes[1], name: 'Music' }), 'A2 · Music');
	lanes.splice(0, 1);
	assert.deepEqual(lanes.map((l) => laneCode(lanes, l.id)), ['A1', 'A2']);
});

test('laneFor: the first lane of the role, else the first lane, else none', () => {
	const doc = makeDoc({ lanes: [lane('A1', { role: 'Dialogue' }), lane('A2', { role: 'Musique' })] });
	assert.equal(laneFor(doc, 'Musique').id, 'A2');
	assert.equal(laneFor(doc, 'SFX').id, 'A1');
	assert.equal(laneFor(makeDoc({ lanes: [] }), 'SFX'), null);
});

test('removeLane: the lane goes with its audio clips only, the audio driver moves to the first lane left', () => {
	const audio = [
		{ id: 'u1', lane: 'A1' },
		{ id: 'u2', lane: 'A2' },
		{ id: 'u3', lane: 'A1' },
		{ id: 'u4', lane: 'A3' }
	];
	const doc = makeDoc({ audio: structuredClone(audio) });
	const before = structuredClone(doc);
	assert.equal(laneItemCount(doc, 'A1'), 2);
	const removed = removeLane(doc, 'A1');
	assert.equal(removed.lane.id, 'A1');
	assert.deepEqual(removed.items.map((i) => i.id), ['u1', 'u3']);
	assert.deepEqual(doc.lanes.map((l) => l.id), ['A2', 'A3']);
	assert.deepEqual(doc.audio.map((i) => i.id), ['u2', 'u4']);
	assert.equal(doc.engine.audioDriver, 'A2');
	assert.equal(laneItemCount(doc, 'A1'), 0);
	assert.equal(removeLane(doc, 'A1'), null, 'a lane that is gone is not removed twice');
	assert.deepEqual(JSON.parse(JSON.stringify(before)).audio, audio, 'a snapshot taken before restores every clip');
});

test('removeLane: the last lane can go, the audio driver is then empty, the other driver is kept', () => {
	const doc = makeDoc({ lanes: ['A1'], audio: [{ id: 'u1', lane: 'A1' }] });
	removeLane(doc, 'A1');
	assert.deepEqual([doc.lanes, doc.audio, doc.engine.audioDriver], [[], [], '']);
	const other = makeDoc();
	removeLane(other, 'A3');
	assert.equal(other.engine.audioDriver, 'A1');
});

test('newLaneId: a ULID, so that adding a lane after a deletion never reuses an id', () => {
	const doc = makeDoc({ lanes: ['A1', 'A2', 'A3', 'A4'], audio: [{ id: 'u4', lane: 'A4' }] });
	removeLane(doc, 'A2');
	const id = newLaneId();
	assert.ok(isUlid(id));
	assert.ok(!doc.lanes.some((l) => l.id === id));
	doc.lanes.push(lane(id));
	assert.deepEqual(doc.lanes.map((l) => laneCode(doc.lanes, l.id)), ['A1', 'A2', 'A3', 'A4']);
	assert.equal(laneItemCount(doc, 'A4'), 1, 'the clip of A4 stays on its lane');
});

test('migrateTracks: old documents keep A1 to A4 and their clips, gain the video track and the shot mute, duplicate ids are split', () => {
	const old = {
		lanes: [lane('A1'), lane('A2'), lane('A3'), lane('A4')],
		audio: [{ id: 'u1', lane: 'A3' }],
		clips: [{ id: 'c1' }, { id: 'c2', mute: true }]
	};
	const next = migrateTracks(old);
	assert.deepEqual(next.lanes.map((l) => l.id), ['A1', 'A2', 'A3', 'A4']);
	assert.equal(next.lanes[0], old.lanes[0], 'a lane that needs nothing is kept as is');
	assert.deepEqual(next.audio, old.audio);
	assert.deepEqual(next.video, { mute: false, solo: false });
	assert.deepEqual(next.clips.map((c) => c.mute), [false, true]);
	assert.ok(!('video' in old) && !('mute' in old.clips[0]), 'the input is not changed');
	assert.deepEqual(migrateTracks(next), next);
	const kept = migrateTracks({ video: { mute: true, solo: true } });
	assert.deepEqual(kept.video, { mute: true, solo: true });
	const twice = migrateTracks({ lanes: [lane('A1'), lane('A1'), lane('')] });
	assert.equal(twice.lanes[0].id, 'A1');
	assert.ok(isUlid(twice.lanes[1].id) && isUlid(twice.lanes[2].id));
	assert.equal(new Set(twice.lanes.map((l) => l.id)).size, 3);
});

test('migrate: the document migration runs the track migration', () => {
	const next = migrate({ name: 'Old', lanes: [lane('A1')], clips: [{ id: 'c1' }] });
	assert.deepEqual(next.video, { mute: false, solo: false });
	assert.equal(next.clips[0].mute, false);
	assert.equal(next.lanes[0].id, 'A1');
});

test('preview: the playback engine applies the shared rule to lanes and shot sound', () => {
	const source = readFileSync(join(here, 'playback.svelte.js'), 'utf-8');
	assert.match(source, /import \{ clipSoundAudible, laneAudible \} from '\.\/tracks\.js';/);
	assert.match(source, /stripOf\(mixRule, lane, doc\.aux, laneAudible\(doc, lane\)\)/);
	assert.match(source, /clipSoundAudible\(doc, c\) \? envelope\(c, t\) : 0/);
	assert.doesNotMatch(source, /lanes\.some\(\(l\) => l\.solo\)/, 'no second copy of the solo rule');
});

test('newSound: a placed sound spans its whole source, a stem of several minutes included, and 8 s while its length is unknown', () => {
	const stem = newSound('stem', 'A2', 12.4, 435.072);
	assert.ok(isUlid(stem.id));
	assert.deepEqual({ ...stem, id: null }, { id: null, assetId: 'stem', lane: 'A2', start: 12.4, dur: 435.072, srcIn: 0, fadeIn: 0.5, fadeOut: 0.5, gain: -6 });
	assert.equal(newSound('a', 'A1', 0, 3.2).dur, 3.2);
	assert.equal(SOUND_FALLBACK, 8);
	for (const unknown of [null, undefined, 0, -2, Number.NaN, Infinity, '12']) assert.equal(soundSpan(unknown), SOUND_FALLBACK);
});

test('fitSounds: the length read late replaces the 8 s fallback of untouched items only, longer or shorter', () => {
	const doc = makeDoc({
		audio: [
			{ id: 'fresh', assetId: 'stem', lane: 'A1', start: 0, dur: 8, srcIn: 0 },
			{ id: 'trimmed', assetId: 'stem', lane: 'A1', start: 9, dur: 6.4, srcIn: 0 },
			{ id: 'slipped', assetId: 'stem', lane: 'A2', start: 2, dur: 8, srcIn: 1.2 },
			{ id: 'other', assetId: 'voice', lane: 'A2', start: 0, dur: 8, srcIn: 0 }
		]
	});
	assert.deepEqual(fitSounds(doc, 'stem', 435.072).map((item) => item.id), ['fresh']);
	assert.deepEqual(doc.audio.map((item) => item.dur), [435.072, 6.4, 8, 8]);
	assert.deepEqual(fitSounds(doc, 'voice', 3.2).map((item) => item.id), ['other']);
	assert.equal(doc.audio[3].dur, 3.2);
	assert.deepEqual(fitSounds(doc, 'stem', null), []);
	assert.deepEqual(fitSounds({}, 'stem', 12), []);
});

test('placing a sound: every path reads its length first and places the whole source, the 5 s shot default stays', () => {
	const importer = readFileSync(join(here, 'importer.js'), 'utf-8');
	const state = readFileSync(join(here, 'state.svelte.js'), 'utf-8');
	assert.match(importer, /export async function placeAsset\(id, row, at\) \{\n\tawait probeAsset\(id\)\.catch\(\(\) => \{\}\);/);
	assert.match(importer, /export async function addToTimeline\(id, at = null\) \{\n\tconst start = at \?\? ui\.playhead;\n\tif \(asset\(id\)\?\.kind === 'audio'\) await probeAsset\(id\)/);
	assert.match(importer, /const end = await placeAsset\(id, target\.row, at\);/);
	assert.match(importer, /newSound\(id, row\.id, start, a\.srcDur\)/);
	assert.match(importer, /if \(target\.kind === 'audio'\) fitSounds\(doc, id, info\.srcDur\);/);
	assert.match(state, /doc\.audio\.push\(newSound\(assetId, laneId, round\(at \?\? ui\.playhead, 0\.04\), a\.srcDur\)\)/);
	assert.match(state, /newClip\(\{ assetId, dur: Math\.min\(5, a\.srcDur \?\? 5\)/);
	for (const source of [importer, state]) assert.doesNotMatch(source, /Math\.min\(8|, 8\)/);
	for (const path of ['../components/panels/MediaBrowser.svelte', '../components/panels/MixerPanel.svelte', '../components/viewer/Viewer.svelte']) {
		const component = readFileSync(join(here, path), 'utf-8');
		assert.match(component, /addToTimeline\(/, path);
		assert.doesNotMatch(component, /addAssetToTimeline/, path);
	}
});

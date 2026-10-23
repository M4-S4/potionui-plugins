import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isUlid } from './ulid.js';
import { migrate } from './starter.js';
import { anySolo, clipSoundAudible, laneAudible, laneCode, laneFor, laneItemCount, laneTitle, migrateTracks, newLaneId, removeLane, videoTrack } from './tracks.js';

const here = dirname(fileURLToPath(import.meta.url));

function lane(id, extra = {}) {
	return { id, name: id, role: 'Ambiance', vol: 0, pan: 0, mute: false, solo: false, automation: 'off', sends: { R1: -60, D1: -60 }, inserts: [], ...extra };
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
	assert.match(source, /laneAudible\(doc, lane\) \? db\(lane\.vol\) : 0/);
	assert.match(source, /clipSoundAudible\(doc, c\) \? envelope\(c, t\) : 0/);
	assert.doesNotMatch(source, /lanes\.some\(\(l\) => l\.solo\)/, 'no second copy of the solo rule');
});

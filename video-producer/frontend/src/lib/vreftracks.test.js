import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { readFileSync } from 'node:fs';

const hooks = `
import { readFile } from 'node:fs/promises';
export async function load(url, context, next) {
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

const { VIDEO_TRACKS, shotReception } = await import('./reception.js');
const { MAX_VREF_TRACKS, videoTracksOf } = await import('./vrefs.js');
const { excludedVrefsOf } = await import('./shots.js');
const { effectiveEngine } = await import('./engine.js');
const { assetUses, removeAsset, USE_KINDS } = await import('./usage.js');
const { rowKinds } = await import('./upload.js');
const v = await import('./vreftracks.js');
const { freeReferenceLane, takeSound } = await import('./sound.js');

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const { engines, cases } = read('../../../tests/fixtures/reception_cases.json');
const caseDoc = (name) => structuredClone(cases.find((c) => c.name.startsWith(name)).doc);
const infoOf = (engine) => {
	const found = Object.values(engines).find((e) => e.preset === engine.preset && (e.model ?? null) === (engine.model ?? null));
	return found ? { id: found.preset, cloud: found.cloud, audioMux: found.audio_mux, profiles: found.profiles } : null;
};
const receptions = (doc) => doc.clips.map((clip) => shotReception(doc, clip, { ...effectiveEngine(clip, doc), info: infoOf(effectiveEngine(clip, doc)) }));

test('a new track takes the smallest free slot, and a fourth one is refused', () => {
	const doc = { clips: [] };
	assert.equal(v.freeSlot(doc), 1);
	assert.deepEqual(['a', 'b', 'c'].map((id) => v.addVrefTrack(doc, id, '').slot), [1, 2, 3]);
	assert.equal(v.freeSlot(doc), null);
	assert.equal(v.addVrefTrack(doc, 'd', ''), null);
	assert.equal(doc.vrefTracks.length, MAX_VREF_TRACKS);
	v.removeVrefTrack(doc, 'a');
	assert.deepEqual(
		videoTracksOf(doc).map((track) => [track.id, v.vrefLabel(track.slot)]),
		[
			['b', 'vref2'],
			['c', 'vref3']
		]
	);
	assert.equal(v.addVrefTrack(doc, 'e', 'Walk').slot, 1);
	assert.deepEqual(v.trackOf(doc, 'e'), { id: 'e', slot: 1, name: 'Walk', role: 'motion' });
});

test('deleting a track takes its parts and the shots that left it out forget it; empty lists leave the document', () => {
	const doc = { clips: [{ id: 's1', referenceOverrides: { excludeVrefs: ['t1', 't2'], exclude: ['r1'] } }, { id: 's2', referenceOverrides: { excludeVrefs: ['t1'] } }] };
	v.addVrefTrack(doc, 't1', '');
	v.addVrefTrack(doc, 't2', '');
	v.addVrefItem(doc, { id: 'i1', track: 't1', assetId: 'a', start: 0, srcDur: 4 });
	v.addVrefItem(doc, { id: 'i2', track: 't2', assetId: 'a', start: 2, srcDur: null });
	const gone = v.removeVrefTrack(doc, 't1');
	assert.deepEqual(gone.items.map((item) => item.id), ['i1']);
	assert.deepEqual(excludedVrefsOf(doc.clips[0]), ['t2']);
	assert.deepEqual(doc.clips[0].referenceOverrides.exclude, ['r1']);
	assert.equal('referenceOverrides' in doc.clips[1], false);
	v.removeVrefTrack(doc, 't2');
	assert.equal('vrefTracks' in doc, false);
	assert.equal('vrefItems' in doc, false);
	assert.equal(v.removeVrefTrack(doc, 't2'), null);
});

test('a dropped video lasts its source, or 5 s until the source is probed', () => {
	const doc = {};
	v.addVrefTrack(doc, 't', '');
	const known = v.addVrefItem(doc, { id: 'i1', track: 't', assetId: 'a', start: 3, srcDur: 7.5 });
	const unknown = v.addVrefItem(doc, { id: 'i2', track: 't', assetId: 'b', start: 12, srcDur: null });
	assert.deepEqual([known.dur, unknown.dur, unknown.srcIn], [7.5, v.VREF_FALLBACK, 0]);
	assert.deepEqual(v.fitVrefItems(doc, 'b', 6.2).map((item) => item.id), ['i2']);
	assert.equal(unknown.dur, 6.2);
	assert.deepEqual(v.fitVrefItems(doc, 'b', 9), []);
});

test('a track row takes only videos', () => {
	assert.deepEqual(rowKinds({ id: 'vtrack:t', vtrack: 't' }), ['video']);
	assert.deepEqual(rowKinds({ id: 'l1', lane: {} }), ['audio']);
});

test('the shots that cite @vrefN, as the server reads the mention', () => {
	const doc = {
		clips: [{ id: 's1' }, { id: 's2' }, { id: 's3' }, { id: 's4' }, { id: 's5' }],
		prompts: [
			{ id: 'p1', shotId: 's1', text: 'The walk of @vref1, slower.' },
			{ id: 'p2', shotId: 's2', text: 'mail x@vref1 and @vref12' },
			{ id: 'p3', shotId: 's3', text: '@VREF1 at the start' },
			{ id: 'p4', shotId: null, text: '@vref1 without a shot' },
			{ id: 'p5', shotId: 's5', text: 'as in @vref2' }
		]
	};
	assert.deepEqual(v.citingShots(doc, 1).map((clip) => clip.id), ['s1', 's3']);
	assert.deepEqual(v.citingShots(doc, 2).map((clip) => clip.id), ['s5']);
	assert.deepEqual(v.citingShots(doc, 3), []);
});

test('the lengths a track can send run from 56 frames up to 15 s, by 17 frames', () => {
	const choices = v.lengthChoices();
	assert.deepEqual(choices[0], { frames: VIDEO_TRACKS.minFrames, seconds: VIDEO_TRACKS.minFrames / VIDEO_TRACKS.fps });
	assert.equal(choices.at(-1).frames, 345);
	assert.ok(choices.every((c, i) => i === 0 || c.frames - choices[i - 1].frames === VIDEO_TRACKS.chunk));
	const track = { id: 't', slot: 1, name: '', role: 'motion' };
	assert.equal(v.trackFrames(track), 56);
	v.setTrackFrames(track, 73);
	assert.equal(v.trackFrames(track), 73);
	v.setTrackFrames(track, 56);
	assert.equal('seconds' in track, false);
	v.setTrackOff(track, true);
	assert.equal(track.off, true);
	v.setTrackOff(track, false);
	assert.equal('off' in track, false);
});

test('the marks of a track: the sent window under a Ref2VA shot, a hatch under the shots whose engine ignores it, nothing where the shot leaves it out', () => {
	const motion = caseDoc('a motion track sends a Ref2VA shot');
	const motionShots = receptions(motion);
	const motionTrack = videoTracksOf(motion)[0].id;
	const [sent] = v.trackMarks(motionShots, motionTrack);
	assert.deepEqual([sent.status, sent.tone, sent.frames], ['sent', 'sent', 56]);
	assert.deepEqual(sent.span, motionShots[0].videoTracks[0].window);
	assert.equal(v.receivingCount(motionShots, motionTrack), 1);

	const doc = caseDoc('a reference video track is ignored by every engine');
	const shots = receptions(doc);
	const track = videoTracksOf(doc)[0].id;
	const marks = v.trackMarks(shots, track);
	assert.deepEqual(
		marks.map((mark) => mark.clip.id),
		doc.clips.map((clip) => clip.id)
	);
	for (const mark of marks) {
		assert.equal(mark.tone, 'ignored', mark.clip.id);
		assert.ok(mark.span[1] > mark.span[0], mark.clip.id);
	}
	assert.equal(v.receivingCount(shots, track), 0);

	const off = caseDoc('a disabled track is sent nowhere');
	assert.deepEqual(v.trackMarks(receptions(off), videoTracksOf(off)[0].id), []);

	const quiet = caseDoc('a shot that leaves a track out');
	const quietShots = receptions(quiet);
	const quietTrack = videoTracksOf(quiet)[0].id;
	assert.deepEqual(
		v.trackMarks(quietShots, quietTrack).map((mark) => [mark.clip.id, mark.status]),
		quietShots.filter((shot) => shot.videoTracks.some((x) => x.track.id === quietTrack && x.status !== 'excluded')).map((shot) => [shot.clip.id, shot.videoTracks.find((x) => x.track.id === quietTrack).status])
	);
	assert.ok(quietShots.some((shot) => shot.videoTracks.some((x) => x.status === 'excluded')));
	assert.ok(v.trackMarks(quietShots, quietTrack).every((mark) => mark.status !== 'excluded'));
});

test('a continuation track marks the window just before the shot, and a short window warns', () => {
	const doc = caseDoc('a continuation track sends what lies just before the shot');
	const shots = receptions(doc);
	const marks = v.trackMarks(shots, videoTracksOf(doc)[0].id);
	const sent = marks.find((mark) => mark.status === 'sent');
	assert.ok(sent.span[1] <= sent.clip.start + 1e-6);
	assert.ok(marks.some((mark) => mark.status === 'short' && mark.tone === 'warn'));
});

test('shotReception counts what a Ref2VA shot sends, and counts nothing for another profile', () => {
	const doc = caseDoc('the videos of the shot go first');
	const [shot] = receptions(doc);
	assert.deepEqual(Object.keys(shot.counts).sort(), ['audio', 'image', 'video']);
	assert.equal(shot.counts.video, 3);
	assert.ok(receptions(caseDoc('a reference video track is ignored by every engine')).every((reception) => reception.counts === null));
	assert.deepEqual(receptions(caseDoc('a motion track sends a Ref2VA shot'))[0].counts.video, 1);
});

test('the shot editor leaves a track out in its draft, which counts as a change of the shot', async () => {
	const { applyShotDraft, inputsChanged, rebaseDraft, shotDraft } = await import('./shots.js');
	const doc = { clips: [{ id: 's1', start: 0, dur: 3, srcIn: 0 }], prompts: [], frames: [], references: [], engine: {} };
	const before = shotDraft(doc, doc.clips[0], doc.engine);
	assert.deepEqual(before.excludeVrefs, []);
	const draft = { ...structuredClone(before), excludeVrefs: ['t1'] };
	assert.equal(inputsChanged(before, draft), true);
	assert.deepEqual(rebaseDraft(before, draft, before).draft.excludeVrefs, ['t1']);
	applyShotDraft(doc, doc.clips[0], before, draft, { makeId: () => 'x' });
	assert.deepEqual(excludedVrefsOf(doc.clips[0]), ['t1']);
	assert.equal(doc.clips[0].revision, 1);
	const back = shotDraft(doc, doc.clips[0], doc.engine);
	applyShotDraft(doc, doc.clips[0], back, { ...structuredClone(back), excludeVrefs: [] }, { makeId: () => 'x' });
	assert.equal('referenceOverrides' in doc.clips[0], false);
});

test('removing a video from the Media takes its parts off the tracks and says so first', () => {
	assert.ok(USE_KINDS.includes('vrefs'));
	const doc = { assets: [{ id: 'a', kind: 'video' }], clips: [], audio: [], references: [], frames: [] };
	v.addVrefTrack(doc, 't', '');
	v.addVrefItem(doc, { id: 'i1', track: 't', assetId: 'a', start: 0, srcDur: 3 });
	v.addVrefItem(doc, { id: 'i2', track: 't', assetId: 'b', start: 4, srcDur: 3 });
	assert.deepEqual(assetUses(doc, 'a').vrefs.map((item) => item.id), ['i1']);
	removeAsset(doc, 'a');
	assert.deepEqual(doc.vrefItems.map((item) => item.id), ['i2']);
	doc.assets.push({ id: 'b', kind: 'video' });
	removeAsset(doc, 'b');
	assert.equal('vrefItems' in doc, false);
	assert.equal(doc.vrefTracks.length, 1);
});

test('a piece copied from a take remembers it, and a track is busy where one of its pieces lies', () => {
	const doc = { clips: [] };
	v.addVrefTrack(doc, 'a', '');
	v.addVrefTrack(doc, 'b', 'Walk');
	const item = v.addVrefItem(doc, { id: 'i1', track: 'a', assetId: 'gen-t1', start: 4, srcDur: 3, fromTake: 't1' });
	assert.deepEqual(item, { id: 'i1', track: 'a', assetId: 'gen-t1', start: 4, dur: 3, srcIn: 0, fromTake: 't1' });
	assert.equal('fromTake' in v.addVrefItem(doc, { id: 'i2', track: 'b', assetId: 'walk', start: 0, srcDur: 2 }), false);
	assert.equal(v.trackBusy(doc, 'a', 0, 4), false);
	assert.equal(v.trackBusy(doc, 'a', 6.9, 9), true);
	assert.equal(v.trackBusy(doc, 'a', 7, 9), false);
	assert.equal(v.trackBusy(doc, 'b', 1, 3), true);
	assert.deepEqual(v.takeTracks(doc, 't1').map((track) => track.id), ['a']);
	v.addVrefItem(doc, { id: 'i3', track: 'b', assetId: 'gen-t1', start: 10, srcDur: 3, fromTake: 't1' });
	assert.deepEqual(v.takeTracks(doc, 't1').map((track) => v.vrefLabel(track.slot)), ['vref1', 'vref2']);
	assert.deepEqual(v.takeTracks(doc, 't9'), []);
	assert.deepEqual(v.takeTracks(doc, null), []);
});

test('@vrefN is read as the server reads it, and citing a track writes the mention once, at the cursor', () => {
	assert.deepEqual(v.citedSlots('The walk of @vref2, then @VREF1 and @vref2 again; x@vref3, @vref12, @vref0'), [2, 1]);
	assert.deepEqual(v.citedSlots(null), []);
	assert.deepEqual(v.citeTrack('', 1), { text: '@vref1', caret: 6, added: true });
	assert.deepEqual(v.citeTrack('She walks.', 2), { text: 'She walks. @vref2', caret: 17, added: true });
	assert.deepEqual(v.citeTrack('She walks as in .', 1, 16), { text: 'She walks as in @vref1.', caret: 22, added: true });
	assert.deepEqual(v.citeTrack('Walkslowly', 3, 4), { text: 'Walk @vref3 slowly', caret: 11, added: true });
	assert.deepEqual(v.citeTrack('As in (', 1), { text: 'As in (@vref1', caret: 13, added: true });
	assert.deepEqual(v.citeTrack('Walk @vref1 slowly', 1, 0), { text: 'Walk @vref1 slowly', caret: 0, added: false });
	assert.equal(v.citeTrack('abc', 1, 99).text, 'abc @vref1');
});

test('the labels the server gives the tracks of a shot split its composed prompt', () => {
	const tracks = [
		{ slot: 1, trackId: 't1', label: '<Video 2>' },
		{ slot: 3, trackId: 't3', label: '<Video 1>' }
	];
	assert.deepEqual(v.labelParts('<Video 1> is the footage; <Video 2> moves. <Video 3> is a plain video.', tracks), [
		{ text: '<Video 1>', slot: 3 },
		{ text: ' is the footage; ', slot: null },
		{ text: '<Video 2>', slot: 1 },
		{ text: ' moves. <Video 3> is a plain video.', slot: null }
	]);
	assert.deepEqual(v.labelParts('No track.', []), [{ text: 'No track.', slot: null }]);
	assert.deepEqual(v.labelParts('', tracks), []);
});

test('the sound of a take goes on the first reference sound track free under it, at its own level and without fades', () => {
	const doc = { lanes: [{ id: 'A1' }, { id: 'A2', reference: true }, { id: 'A3', reference: true }], audio: [{ id: 'x', lane: 'A2', start: 2, dur: 3 }] };
	assert.equal(freeReferenceLane(doc, [0, 4])?.id, 'A3');
	assert.equal(freeReferenceLane(doc, [5, 8])?.id, 'A2');
	doc.audio.push({ id: 'y', lane: 'A3', start: 0, dur: 10 });
	assert.equal(freeReferenceLane(doc, [0, 4]), null);
	assert.equal(freeReferenceLane({ lanes: [{ id: 'A1' }], audio: [] }, [0, 4]), null);
	assert.deepEqual(takeSound({ id: 's', assetId: 'gen-t1', lane: 'A2', start: 5, dur: 3, fromTake: 't1' }), {
		id: 's',
		assetId: 'gen-t1',
		lane: 'A2',
		start: 5,
		dur: 3,
		srcIn: 0,
		fadeIn: 0,
		fadeOut: 0,
		gain: 0,
		fromTake: 't1'
	});
});

test('the reception of a track groups its shots by engine and verdict, the shots that leave it out last, and only those it should reach but does not are to check', () => {
	const doc = caseDoc('a reference video track is ignored by every engine');
	const shots = receptions(doc);
	const track = videoTracksOf(doc)[0];
	const groups = v.trackGroups(shots, track.id);
	assert.deepEqual(
		groups.map((g) => [g.status, g.clips.map((c) => c.id)]),
		[['ignored', ['s1']], ['ignored', ['s2']], ['ignored', ['s3']], ['ignored', ['s4']]]
	);
	assert.deepEqual(v.trackIssues(shots, [track]).map((issue) => [issue.status, issue.track.id, issue.clips.map((c) => c.id)]), groups.map((g) => ['ignored', track.id, g.clips.map((c) => c.id)]));

	const motion = caseDoc('a motion track sends a Ref2VA shot');
	const [sent] = v.trackGroups(receptions(motion), videoTracksOf(motion)[0].id);
	assert.deepEqual([sent.status, sent.entry.frames, sent.clips.map((c) => c.id)], ['sent', 56, ['s1']]);
	assert.deepEqual(v.trackIssues(receptions(motion), videoTracksOf(motion)), []);

	const full = caseDoc('three videos of the shot fill the budget');
	assert.deepEqual(v.trackIssues(receptions(full), videoTracksOf(full)).map((issue) => issue.status), ['trimmed']);

	const quiet = caseDoc('a shot that leaves a track out');
	const quietGroups = v.trackGroups(receptions(quiet), videoTracksOf(quiet)[0].id);
	assert.equal(quietGroups.at(-1).status, 'excluded');
	assert.equal(quietGroups.at(-1).engine, null);
	assert.ok(v.trackIssues(receptions(quiet), videoTracksOf(quiet)).every((issue) => issue.status !== 'excluded'));

	const off = caseDoc('a disabled track is sent nowhere');
	assert.deepEqual(v.trackIssues(receptions(off), videoTracksOf(off)), []);
	assert.ok(v.trackGroups(receptions(off), videoTracksOf(off)[0].id).every((g) => g.status === 'off'));

	const short = caseDoc('a continuation track sends what lies just before the shot');
	assert.ok(v.trackIssues(receptions(short), videoTracksOf(short)).some((issue) => issue.status === 'short'));
	assert.ok(!v.trackIssues(receptions(short), videoTracksOf(short)).some((issue) => issue.clips.some((c) => c.id === 's1') && issue.status === 'sent'));
});

test('the shots a track goes into before and after a change: which start, which stop and why', () => {
	const doc = caseDoc('a motion track sends a Ref2VA shot');
	const before = v.sendings(receptions(doc));
	assert.deepEqual([...before.entries()], [['t1', ['s1']]]);
	assert.deepEqual(v.sendingChanges(before, receptions(doc)), []);

	doc.direction.mode = 'FL2VA';
	const [stopped] = v.sendingChanges(before, receptions(doc));
	assert.deepEqual([stopped.track.id, stopped.started, stopped.stopped.map((x) => [x.clip.id, x.status])], ['t1', [], [['s1', 'ignored']]]);

	const after = v.sendings(receptions(doc));
	doc.direction.mode = 'Ref2VA';
	const [started] = v.sendingChanges(after, receptions(doc));
	assert.deepEqual([started.started.map((c) => c.id), started.stopped], [['s1'], []]);

	delete doc.vrefTracks;
	delete doc.vrefItems;
	assert.deepEqual(v.sendingChanges(before, receptions(doc)), []);
});

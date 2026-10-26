import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CHOICES, frameNotes, nextShot, nextSource, previousSource, retrieveChoices, sidesOf, startOfCut, takesLastFrame, targetsEnd, targetsStart } from './shotimages.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

function film(extra = {}) {
	return {
		fps: 25,
		clips: [
			{ id: 's1', start: 0, dur: 4, srcIn: 0, assetId: 'take-1', stage: 'draft' },
			{ id: 's2', start: 4, dur: 4, srcIn: 0, assetId: null, stage: 'todo' },
			{ id: 's3', start: 8, dur: 4, srcIn: 0.5, assetId: 'take-3', stage: 'draft' }
		],
		assets: [
			{ id: 'take-1', kind: 'video', src: '/m/1.mp4', generated: true, resultId: 't1', srcDur: 5, fps: 25 },
			{ id: 'take-3', kind: 'video', src: '/m/3.mp4', generated: true, resultId: 't3', srcDur: 5, fps: 25 },
			{ id: 'still', kind: 'image', src: '/m/still.png' }
		],
		frames: [],
		...extra
	};
}

const shot = (doc, id) => doc.clips.find((c) => c.id === id);

test('the six choices: three images made by the model and three frames taken from the shots around', () => {
	assert.deepEqual(CHOICES, ['first', 'last', 'both', 'previous', 'next', 'neighbors']);
	assert.deepEqual(CHOICES.filter(targetsStart), ['first', 'both', 'previous', 'neighbors']);
	assert.deepEqual(CHOICES.filter(targetsEnd), ['last', 'both', 'next', 'neighbors']);
	assert.deepEqual(sidesOf('neighbors'), ['previous', 'next']);
	assert.deepEqual(sidesOf('both'), []);
});

test('the previous shot gives its last frame like the link of the shot: ready, current, out of date, waited for or missing', () => {
	const doc = film();
	const s2 = shot(doc, 's2');

	assert.equal(previousSource(doc, shot(doc, 's1'), {}).state, 'none');
	const ready = previousSource(doc, s2, { first: null });
	assert.deepEqual([ready.state, ready.shot.id, ready.source], ['ready', 's1', { shotId: 's1', takeId: 't1', assetId: 'take-1', at: 4 }]);
	doc.assets.push({ id: 'chain-a', kind: 'image', src: '/m/a.png', frameOf: { shotId: 's1', takeId: 't1', assetId: 'take-1', at: 4 } });
	assert.equal(previousSource(doc, s2, { first: 'chain-a' }).state, 'current');
	doc.clips[0].dur = 3;
	assert.equal(previousSource(doc, s2, { first: 'chain-a' }).state, 'stale');
	assert.equal(previousSource(doc, s2, { first: 'still' }).state, 'ready');

	const bare = film();
	bare.clips[0].assetId = null;
	const running = [{ id: 'tx', shotId: 's1', kind: 'render', status: 'running' }];
	assert.equal(previousSource(bare, shot(bare, 's2'), { first: null }, running).state, 'linked');
	assert.equal(previousSource(bare, shot(bare, 's2'), { first: null, firstFromPrevious: false }, running).state, 'pending');
	assert.equal(previousSource(bare, shot(bare, 's2'), { first: 'still' }, running).state, 'pending');
	assert.equal(previousSource(bare, shot(bare, 's2'), { first: null }, [{ ...running[0], kind: 'keyframe' }]).state, 'empty');
	assert.equal(previousSource(bare, shot(bare, 's2'), { first: null }).state, 'empty');
});

test('the next shot gives the first frame of its cut, else its own start image, and nothing while it is generated', () => {
	const doc = film();
	const s2 = shot(doc, 's2');

	assert.equal(nextShot(doc, 's3'), null);
	assert.equal(nextSource(doc, shot(doc, 's3'), {}).state, 'none');
	assert.deepEqual(nextSource(doc, s2, {}).source, { shotId: 's3', takeId: 't3', assetId: 'take-3', at: 0.5 });
	doc.assets.push({ id: 'first-3', kind: 'image', src: '/m/f.png', frameOf: { shotId: 's3', takeId: 't3', assetId: 'take-3', at: 0.5 } });
	assert.equal(nextSource(doc, s2, { last: 'first-3' }).state, 'current');
	assert.deepEqual(startOfCut(doc, { id: 's9', assetId: 'still' }), { shotId: 's9', takeId: null, assetId: 'still', at: null });

	doc.clips[2].assetId = null;
	doc.frames.push({ id: 'f3', shotId: 's3', time: 8, assetId: 'still', role: 'first', strength: 100 });
	const start = nextSource(doc, s2, {});
	assert.deepEqual([start.state, start.image.id], ['ready', 'still']);
	assert.equal(nextSource(doc, s2, { last: 'still' }).state, 'current');
	doc.frames = [];
	assert.equal(nextSource(doc, s2, {}, [{ id: 'ty', shotId: 's3', kind: 'render', status: 'queued' }]).state, 'pending');
	assert.equal(nextSource(doc, s2, {}).state, 'empty');
});

test('a retrieve option is greyed when its shot has nothing to give, both only when each side can, and done when already in place', () => {
	const of = (previous, next) => retrieveChoices({ previous: { side: 'previous', state: previous }, next: { side: 'next', state: next } }).map((o) => [o.id, o.enabled, o.done]);

	assert.deepEqual(of('ready', 'ready'), [['previous', true, false], ['next', true, false], ['neighbors', true, false]]);
	assert.deepEqual(of('none', 'ready'), [['previous', false, false], ['next', true, false], ['neighbors', false, false]]);
	assert.deepEqual(of('pending', 'pending'), [['previous', true, false], ['next', false, false], ['neighbors', false, false]]);
	assert.deepEqual(of('stale', 'empty'), [['previous', true, false], ['next', false, false], ['neighbors', false, false]]);
	assert.deepEqual(of('current', 'current'), [['previous', false, true], ['next', false, true], ['neighbors', false, true]]);
	assert.deepEqual(of('linked', 'ready'), [['previous', false, true], ['next', true, false], ['neighbors', true, false]]);
	assert.deepEqual(of('current', 'empty'), [['previous', false, true], ['next', false, false], ['neighbors', false, false]]);
});

test('the engine of the shot says whether it takes a start and an end image', () => {
	const native = (modes) => ({ kind: 'local', info: { id: 'p', directorModes: modes, profiles: null } });
	const cloud = (lastFrame) => ({ kind: 'cloud', info: { id: 'c' }, modelInfo: { lastFrame } });

	assert.deepEqual([takesLastFrame(native(['t2v', 'i2v', 'flf'])), takesLastFrame(native(['t2v', 'i2v'])), takesLastFrame(native([])), takesLastFrame(null)], [true, false, true, true]);
	assert.deepEqual([takesLastFrame(cloud(true)), takesLastFrame(cloud(false)), takesLastFrame(cloud(null))], [true, false, true]);
	assert.deepEqual(frameNotes({ option: native(['t2v']), choice: 'first' }), ['textOnly']);
	assert.deepEqual(frameNotes({ option: native(['t2v', 'i2v']), choice: 'next', hasStart: true }), ['noLastFrame']);
	assert.deepEqual(frameNotes({ option: native(['t2v', 'i2v']), choice: 'previous' }), []);
	assert.deepEqual(frameNotes({ option: native(['t2v', 'i2v', 'flf']), choice: 'last', hasStart: false, chained: false }), ['endWithoutStart']);
	assert.deepEqual(frameNotes({ option: native(['t2v', 'i2v', 'flf']), choice: 'last', hasStart: false, chained: true }), []);
	assert.deepEqual(frameNotes({ option: native(['t2v', 'i2v', 'flf']), choice: 'neighbors' }), []);
	const h3 = { kind: 'local', info: { id: '01KWYF2M63A2YSKKNR6B9JDWYB', directorModes: ['i2v', 'flf', 'refs'], profiles: ['FL2VA', 'Ref2VA'] } };
	assert.deepEqual(frameNotes({ option: h3, profile: 'Ref2VA', choice: 'both' }), ['refs']);
	assert.deepEqual(frameNotes({ option: h3, profile: 'FL2VA', choice: 'both' }), []);
});

test('the panel offers the six choices in two rows, greys the retrieve ones with their reason and says what the engine leaves out', () => {
	const panel = source('../components/shots/KeyframeCandidates.svelte');

	assert.match(panel, /\['make', MAKE, t\('keyframes\.makeGroup'\)\], \['retrieve', RETRIEVE, t\('keyframes\.retrieveGroup'\)\]/);
	assert.match(panel, /disabled=\{off\}\n\t+title=\{off \? choiceReason\(/);
	assert.match(panel, /data-retrieve-reason=\{o\.id\}/);
	assert.match(panel, /frameNotes\(\{ option: engineOption, profile: engine\.profile, choice, hasStart: Boolean\(draft\.first\), chained: linked \}\)/);
	assert.match(panel, /onclick: \(\) => retrieveImages\(clip, draft, choice\)/);
	assert.match(panel, /<option value=\{o\.key\} disabled=\{o\.disabled\}>\{optionLabel\(o\)\}<\/option>/);
	assert.match(panel, /data-frame-role=\{take\.frameRole\}/);
	const editor = source('../components/modals/ShotEditor.svelte');
	assert.match(editor, /<KeyframeCandidates \{clip\} \{draft\} onaccept=\{\(role, assetId\) => \(draft\[role\] = assetId\)\} \/>/);
});

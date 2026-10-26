import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chainAssetId, chainFrames, chainPlan, chainState, chainWaiting, normalizeChain, ownChain, placesTakeFrame, resetShotChain, seamChain, setChain, setShotChain, shotChained, takeFrameAsset } from './chain.js';
import { colorPlanOf, colorsApart } from './continuity.js';
import { canPrioritize, isWaiting, queueOrder } from './queue.js';
import { normalizeTake } from './api.js';
import { migrateShots } from './shots.js';
import { seamImage } from './seam.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const media = { itemId: 'item-1', url: '/api/media/uploads/gen-t1-frame-4s.png', filename: 'gen-t1-frame-4s.png', width: 832, height: 480 };

function sampleDoc() {
	return {
		fps: 25,
		clips: [
			{ id: 's1', assetId: null, take: null, start: 0, dur: 4, srcIn: 0, stage: 'todo' },
			{ id: 's2', assetId: null, take: null, start: 4, dur: 4, srcIn: 0, stage: 'todo' },
			{ id: 's3', assetId: null, take: null, start: 8, dur: 4, srcIn: 0, stage: 'todo' }
		],
		frames: [],
		assets: [
			{ id: 'gen-t1', kind: 'video', name: 'Take 1', src: '/api/media/generations/g1/wan.mp4', origin: { kind: 'history', generationId: 'g1', fileId: 'f1' }, srcDur: 4, fps: 16, generated: true, resultId: 't1' },
			{ id: 'own', kind: 'image', name: 'Poster', src: '/api/media/uploads/poster.png', origin: { kind: 'library', itemId: 'u2' }, generated: false },
			{ id: 'pic', kind: 'image', name: 'Still', src: '/api/media/uploads/still.png', origin: { kind: 'library', itemId: 'u3' }, generated: false }
		]
	};
}

function taken(id, extra = {}) {
	return { id, shotId: 's2', status: 'running', variant: 'A', createdAt: '2026-10-26T10:00:00Z', chain: { previous: 's1', after: 't1', state: 'taken', batch: 'b1', source: { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4 }, frame: media }, ...extra };
}

function first(doc, shotId, assetId) {
	doc.frames.push({ id: `f-${shotId}`, shotId, time: 4, assetId, role: 'first', strength: 100 });
}

test('shotChained: the shot’s own choice wins over the project’s, which stays the default', () => {
	const doc = sampleDoc();
	assert.equal(ownChain(doc.clips[1]), null);
	assert.equal(shotChained(doc, doc.clips[1]), true);
	setChain(doc, false);
	assert.equal(shotChained(doc, doc.clips[1]), false);
	doc.clips[1].firstFromPrevious = true;
	assert.equal(shotChained(doc, doc.clips[1]), true);
	assert.equal(shotChained(doc, doc.clips[2]), false);
	setChain(doc, true);
	doc.clips[2].firstFromPrevious = false;
	assert.equal(shotChained(doc, doc.clips[2]), false);
	assert.equal(chainPlan({ ...doc, clips: [{ ...doc.clips[0], assetId: 'gen-t1' }, doc.clips[1], doc.clips[2]] }, doc.clips[2]), null);
});

test('setShotChain: turning a shot off drops the frame taken from a previous shot and keeps one chosen by hand', () => {
	const doc = sampleDoc();
	doc.assets.push({ id: 'chain-x', kind: 'image', src: '/x.png', origin: { kind: 'library', itemId: 'u9' }, frameOf: { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4 } });
	first(doc, 's2', 'chain-x');
	first(doc, 's3', 'own');
	assert.deepEqual(chainFrames(doc, doc.clips[1]).map((f) => f.id), ['f-s2']);
	assert.deepEqual(setShotChain(doc, doc.clips[1], false).map((f) => f.id), ['f-s2']);
	assert.equal(doc.clips[1].firstFromPrevious, false);
	assert.equal(seamImage(doc, 's2', 'first'), null);
	assert.deepEqual(setShotChain(doc, doc.clips[2], false), []);
	assert.equal(seamImage(doc, 's3', 'first').id, 'own');
	setShotChain(doc, doc.clips[1], true);
	assert.equal(doc.clips[1].firstFromPrevious, true);
	resetShotChain(doc, doc.clips[1]);
	assert.equal('firstFromPrevious' in doc.clips[1], false);
	assert.equal(chainFrames(doc, doc.clips[0]).length, 0);
});

test('chainState offers the last frame only to a shot that starts from the previous one', () => {
	const doc = sampleDoc();
	Object.assign(doc.clips[0], { assetId: 'gen-t1', take: 't1', stage: 'draft' });
	assert.equal(chainState(doc, 1).state, 'offer');
	doc.clips[1].firstFromPrevious = false;
	assert.equal(chainState(doc, 1), null);
	setChain(doc, false);
	doc.clips[1].firstFromPrevious = true;
	assert.equal(chainState(doc, 1).state, 'offer');
});

test('seamChain: off, text only, waiting, own, fresh, stale, ready and later', () => {
	const doc = sampleDoc();
	const waiting = { id: 'w', shotId: 's2', status: 'queued', variant: 'B', chain: { previous: 's1', after: 'p', state: 'waiting' } };
	const previous = { id: 'p', shotId: 's1', status: 'running', variant: 'A' };
	assert.equal(seamChain(doc, 0), null);
	assert.equal(seamChain(doc, 1).state, 'later');
	assert.equal(seamChain(doc, 1, [], true).state, 'textOnly');
	const state = seamChain(doc, 1, [waiting, previous]);
	assert.equal(state.state, 'waiting');
	assert.equal(state.after.id, 'p');
	assert.equal(state.take.id, 'w');
	doc.clips[1].firstFromPrevious = false;
	assert.deepEqual([seamChain(doc, 1).state, seamChain(doc, 1).own], ['off', true]);
	delete doc.clips[1].firstFromPrevious;
	Object.assign(doc.clips[0], { assetId: 'gen-t1', take: 't1', stage: 'draft' });
	assert.equal(seamChain(doc, 1).state, 'ready');
	first(doc, 's2', 'own');
	assert.equal(seamChain(doc, 1).state, 'own');
	doc.assets.push({ id: 'chain-t9', kind: 'image', src: '/c.png', origin: { kind: 'library', itemId: 'u8' }, frameOf: { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4 } });
	doc.frames[0].assetId = 'chain-t9';
	assert.equal(seamChain(doc, 1).state, 'fresh');
	doc.clips[0].dur = 2;
	assert.equal(seamChain(doc, 1).state, 'stale');
});

test('chainWaiting: a queued take that waits for the last frame of the previous shot, which the queue never moves up', () => {
	const waiting = { id: 'w', status: 'queued', generationId: null, priority: 0, createdAt: 'b', chain: { previous: 's1', after: 'p', state: 'waiting' } };
	const plain = { id: 'q', status: 'queued', generationId: null, priority: 0, createdAt: 'c', chain: null };
	const head = { id: 'h', status: 'queued', generationId: null, priority: 0, createdAt: 'a', chain: null };
	assert.equal(chainWaiting(waiting), true);
	assert.equal(chainWaiting({ ...waiting, status: 'failed' }), false);
	assert.equal(chainWaiting({ ...waiting, chain: { ...waiting.chain, state: 'taken' } }), false);
	assert.equal(isWaiting(waiting), false);
	assert.equal(isWaiting(plain), true);
	const ordered = queueOrder([waiting, plain, head]);
	assert.equal(canPrioritize(waiting, ordered), false);
	assert.equal(canPrioritize(plain, ordered), true);
});

test('normalizeTake keeps what a chained take waits for or got, and nothing malformed', () => {
	const chain = { previous: 's1', after: 't1', state: 'taken', batch: 'b1', source: { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4 }, frame: { kind: 'library', item_id: 'item-1', media_type: 'image', url: media.url, filename: media.filename, width: 832, height: 480 } };
	assert.deepEqual(normalizeTake({ id: 't2', chain }).chain, { previous: 's1', after: 't1', state: 'taken', batch: 'b1', source: chain.source, frame: media });
	assert.deepEqual(normalizeTake({ id: 't2', chain: { previous: 's1', after: null, state: 'waiting' } }).chain, { previous: 's1', after: null, state: 'waiting', batch: null, source: null, frame: null });
	assert.equal(normalizeTake({ id: 't2' }).chain, null);
	assert.equal(normalizeChain({ previous: 's1', state: 'done' }), null);
	assert.equal(normalizeChain({ state: 'waiting' }), null);
	assert.equal(normalizeChain('s1'), null);
});

test('takeFrameAsset: the extracted image with where it was taken, or a copy of the still, under the id of the take', () => {
	const doc = sampleDoc();
	const asset = takeFrameAsset(doc, taken('t2'), 'Last frame · Shot 1');
	assert.equal(asset.id, chainAssetId({ id: 't2' }));
	assert.equal(asset.src, media.url);
	assert.deepEqual(asset.frameOf, { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4 });
	const still = takeFrameAsset(doc, taken('t3', { chain: { previous: 's1', after: null, state: 'taken', batch: 'b1', source: { shotId: 's1', takeId: null, assetId: 'pic', at: null }, frame: null } }), 'x');
	assert.deepEqual([still.id, still.src, still.frameOf.at], ['chain-t3', '/api/media/uploads/still.png', null]);
	assert.equal(takeFrameAsset(doc, { id: 't4', chain: { previous: 's1', state: 'waiting', source: null } }, 'x'), null);
});

test('placesTakeFrame: once per take, never over an image chosen by hand, the first of a batch and the newer batch winning', () => {
	const doc = sampleDoc();
	const a = taken('t2');
	const b = taken('t3', { variant: 'B' });
	assert.equal(placesTakeFrame(doc, a, [a, b]), true);
	assert.equal(placesTakeFrame(doc, { ...a, chain: { ...a.chain, state: 'waiting' } }, [a]), false);
	assert.equal(placesTakeFrame(doc, { ...a, status: 'failed' }, [a]), false);
	assert.equal(placesTakeFrame(doc, a, [a], (id) => id === 't2'), false);
	assert.equal(placesTakeFrame(doc, { ...a, shotId: 's3' }, [a]), false);
	doc.assets.push({ ...takeFrameAsset(doc, a, 'x') });
	first(doc, 's2', 'chain-t2');
	assert.equal(placesTakeFrame(doc, a, [a, b]), false);
	assert.equal(placesTakeFrame(doc, b, [a, b]), false);
	const later = taken('t4', { createdAt: '2026-10-26T11:00:00Z', chain: { ...a.chain, batch: 'b2' } });
	assert.equal(placesTakeFrame(doc, later, [a, b, later]), true);
	const done = taken('t5', { status: 'done', chain: { ...a.chain, batch: 'b3' }, createdAt: '2026-10-26T12:00:00Z' });
	doc.assets.push({ id: 'gen-t5', kind: 'video' });
	assert.equal(placesTakeFrame(doc, done, [a, done]), false);
	doc.frames[0].assetId = 'own';
	assert.equal(placesTakeFrame(doc, later, [a, b, later]), false);
});

test('colorPlanOf: each seam over the gap is matched, the next seam measured against the corrected shot', () => {
	const grey = { lum: 0.5, warm: 0 };
	assert.equal(colorsApart(grey, { lum: 0.6, warm: 0 }), false);
	assert.equal(colorsApart(grey, { lum: 0.7, warm: 0 }), true);
	assert.equal(colorsApart(grey, { lum: 0.5, warm: 0.15 }), true);
	const plan = colorPlanOf([
		{ from: grey, to: { lum: 0.3, warm: 0 } },
		{ from: { lum: 0.3, warm: 0 }, to: { lum: 0.32, warm: 0 } },
		null,
		{ from: grey, to: { lum: 0.55, warm: 0 } }
	]);
	assert.deepEqual(plan.map((step) => step.index), [0, 1]);
	assert.deepEqual(plan[1].from, { lum: 0.5, warm: 0 });
	assert.deepEqual(colorPlanOf([{ from: grey, to: null }, { from: grey, to: grey }]), []);
});

test('both migrations drop a shot’s own option that is not a boolean, from the same cases', () => {
	const cases = JSON.parse(readFileSync(new URL('../../../tests/fixtures/chain_flag_migration.json', import.meta.url), 'utf8'));
	for (const { value, expected } of cases) {
		const [, shot] = migrateShots({ clips: [{ id: 's1' }, { id: 's2', firstFromPrevious: value }] }).clips;
		assert.equal('firstFromPrevious' in shot, expected !== null, JSON.stringify(value));
		if (expected !== null) assert.equal(shot.firstFromPrevious, expected);
	}
});

test('wiring: the seams of the storyboard carry their actions and the option of each shot', () => {
	const grid = source('../components/storyboard/StoryboardView.svelte');
	assert.match(grid, /data-seam-alert=\{c\.id\}\n\t+onclick=\{\(e\) => openSeamMenu\(e, c\)\}/);
	assert.match(grid, /<SeamPanel clip=\{seamClip\} \/>/);
	assert.match(grid, /\{#if i > 0\}<ChainChip clip=\{c\} \/>\{\/if\}/);
	assert.match(grid, /onclick: matchAll \}\}>\{t\('storyboard\.matchAll', \{ count: colorFixes \}\)\}/);
	assert.match(source('../components/storyboard/BandView.svelte'), /onclick: matchAll \}\}>\{t\('storyboard\.matchAll', \{ count: colorFixes \}\)\}/);
	assert.match(source('../components/storyboard/BandLanes.svelte'), /\{#if i > 0 && w > 46\}<ChainChip clip=\{c\} small \/>\{\/if\}/);
	assert.match(source('../components/storyboard/BandMonitor.svelte'), /<SeamPanel \{clip\} title=\{false\} compare=\{false\} \/>/);
	assert.match(source('../components/storyboard/StoryWindow.svelte'), /\{#if check\.kind === 'seam'\}<SeamFix clip=\{check\.clip\} issue=\{check\.issue\} \/>\{\/if\}/);
	const panel = source('../components/storyboard/SeamPanel.svelte');
	assert.match(panel, /<SeamFix \{clip\} \{issue\} \/>/);
	assert.match(panel, /<ChainSwitch \{clip\} \/>/);
	const fix = source('../components/storyboard/SeamFix.svelte');
	assert.match(fix, /onclick=\{\(e\) => run\(e, matchToPrevious\)\}/);
	assert.match(fix, /onclick=\{\(e\) => run\(e, compareSeamTakes\)\}/);
	assert.match(fix, /<SeamAction \{clip\} \/>/);
	assert.match(source('../components/inspector/Inspector.svelte'), /<SeamAction clip=\{item\} variant="button" \/>\n\t+<ChainSwitch clip=\{item\} \/>/);
	assert.match(source('../components/storyboard/ShotQuickEdit.svelte'), /<ChainSwitch \{clip\} \/>/);
	assert.match(source('../components/panels/QueuePanel.svelte'), /const wait = waitText\(take\);\n\t\tif \(wait\) return wait;/);
	assert.match(source('../components/takes/TakeCard.svelte'), /if \(status === 'queued'\) return waitText\(take\) \|\| t\('lib\.status\.queued'\);/);
	const chain = source('./chain.svelte.js');
	assert.match(chain, /^onTake\(placeTakeFrame\);$/m);
	assert.match(source('./takes.svelte.js'), /for \(const take of takeStore\.list\) told\(take, false\);/);
	assert.match(source('./takes.svelte.js'), /const stored = takeById\(take\.id\);\n\ttold\(stored, true\);/);
	assert.doesNotMatch(source('../components/director/ReviewView.svelte'), /SeamPanel|SeamFix|ChainSwitch/);
});

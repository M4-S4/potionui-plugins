import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { clean, hostUis, renderComponent, textOf } from './svelte-harness.js';
import { chainAssetId, chainFrames, chainPlan, chainState, chainWaiting, normalizeChain, ownChain, placesTakeFrame, resetShotChain, seamChain, setChain, setShotChain, shotChained, takeFrameAsset } from './chain.js';
import { colorPlanOf, colorsApart } from './continuity.js';
import { canPrioritize, isWaiting, queueOrder } from './queue.js';
import { normalizeTake } from './api.js';
import { migrateShots } from './shots.js';
import { frameErrorText, seamImage } from './seam.js';
import { normalizeLooks } from './looks.js';

globalThis.Image = class {
	set src(value) {}
};

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes, upsertTake } = await import('./takes.svelte.js');
const { waitText } = await import('./chain.svelte.js');
const { lookState } = await import('./looks.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const WAN = '01KX47WANVIDEO0000000000TV';
const SEAM_PANEL = new URL('../components/storyboard/SeamPanel.svelte', import.meta.url).href;
const CHAIN_CHIP = new URL('../components/storyboard/ChainChip.svelte', import.meta.url).href;
const TAKE_CARD = new URL('../components/takes/TakeCard.svelte', import.meta.url).href;
const STORYBOARD = new URL('../components/storyboard/StoryboardView.svelte', import.meta.url).href;
const BAND_LANES = new URL('../components/storyboard/BandLanes.svelte', import.meta.url).href;
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const issuesOf = (html) => [...clean(html).matchAll(/data-seam-issue="([^"]*)"/g)].map((m) => m[1]);

after(() => dispose());
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


test('frame errors: one text per code of the frame routes, the missing media named by the caller, anything else generic', () => {
	const t = (key) => key;
	assert.equal(frameErrorText({ code: 'shot_not_found' }, t), 'lib.seam.error.shot');
	assert.equal(frameErrorText({ code: 'no_previous_take' }, t), 'lib.seam.error.noTake');
	assert.equal(frameErrorText({ code: 'no_media' }, t), 'lib.chain.error.noMedia');
	assert.equal(frameErrorText({ code: 'no_media' }, t, { noMedia: 'keyframes.retrieve.error.noMedia' }), 'keyframes.retrieve.error.noMedia');
	assert.equal(frameErrorText({ code: 'ffmpeg_missing' }, t), 'lib.chain.error.ffmpeg');
	assert.equal(frameErrorText({ code: 'workdir_unwritable' }, t), 'lib.chain.error.workdir');
	assert.equal(frameErrorText({ code: 'extract_failed' }, t), 'lib.seam.error.extract');
	assert.equal(frameErrorText({ code: 'extract_failed', data: { code: 'store_failed' } }, t), 'lib.seam.error.store');
	assert.equal(frameErrorText({ code: 'invalid_request' }, t), 'lib.seam.error.invalid');
	assert.equal(frameErrorText({ code: 'something_else' }, t), 'lib.seam.error.generic');
	assert.equal(frameErrorText(null, t), 'lib.seam.error.generic');
});

test('wiring: the seam panel carries the fix of each issue and the chain option of the shot, the chips say the chain of each shot, the cards say what a queued take waits for, and a taken frame lands on its shot as soon as the take is known', async () => {
	project.id = 'p1';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	ui.workspace = 'storyboard';
	ui.storyView = 'grid';
	doc.engine = { backend: 'native', preset: WAN, model: null };
	const base = sampleDoc();
	doc.clips = base.clips.map((c, i) => ({ ...c, label: ['One', 'Two', 'Three'][i] }));
	doc.clips[0].assetId = 'own';
	doc.assets = base.assets;
	doc.frames = [];
	setTakes('p1', []);
	lookState.projectId = 'p1';
	lookState.data = normalizeLooks(null);
	const panel = clean(await renderComponent(SEAM_PANEL, { clip: doc.clips[1] }));
	assert.match(panel, /data-seam-panel="s2"/);
	assert.match(textOf(panel), new RegExp(escaped(t('storyboard.band.seamTitle', { n: '01', m: '02' }))));
	assert.deepEqual(issuesOf(panel), ['chain_offer']);
	assert.match(panel, new RegExp(`data-seam-fix="chain">[\\s\\S]*?<button[^>]*>${escaped(t('lib.seam.use'))}</button>`));
	assert.match(panel, /data-chain-switch="ready"/);
	assert.deepEqual(hostUis(panel, 'Switch').map((item) => item.checked), [true]);
	assert.match(textOf(panel), new RegExp(escaped(t('storyboard.band.seamCompare'))));
	const bare = clean(await renderComponent(SEAM_PANEL, { clip: doc.clips[1], title: false, compare: false }));
	assert.doesNotMatch(textOf(bare), new RegExp(escaped(t('storyboard.band.seamCompare'))));
	assert.doesNotMatch(textOf(bare), new RegExp(escaped(t('storyboard.band.seamTitle', { n: '01', m: '02' }))));
	assert.equal(clean(await renderComponent(SEAM_PANEL, { clip: doc.clips[0] })), '');
	doc.clips[0].take = 't1';
	doc.clips[1].take = 't2';
	lookState.data = normalizeLooks({ embedder: { available: true }, seams: [{ shot_id: 's2', previous_id: 's1', from_take: 't1', to_take: 't2', score: 0.4, status: 'done' }] });
	const low = clean(await renderComponent(SEAM_PANEL, { clip: doc.clips[1] }));
	assert.deepEqual(issuesOf(low), ['identity', 'chain_offer']);
	assert.match(low, new RegExp(`data-seam-fix="identity"[^>]*>${escaped(t('storyboard.seam.compareTakes'))}</button>`));
	lookState.data = normalizeLooks(null);
	const chip = clean(await renderComponent(CHAIN_CHIP, { clip: doc.clips[1] }));
	assert.match(chip, /aria-pressed="true"/);
	assert.match(chip, /data-chain-chip="ready"/);
	assert.match(chip, new RegExp(`aria-label="${escaped(t('storyboard.chain.chipOn', { previous: 'One' }))}"`));
	assert.equal(clean(await renderComponent(CHAIN_CHIP, { clip: doc.clips[0] })), '');
	doc.clips[1].firstFromPrevious = false;
	const off = clean(await renderComponent(CHAIN_CHIP, { clip: doc.clips[1], small: true }));
	assert.match(off, /aria-pressed="false"/);
	assert.match(off, /data-chain-chip="off"/);
	assert.match(off, new RegExp(`aria-label="${escaped(t('storyboard.chain.chipOff', { previous: 'One' }))}"`));
	delete doc.clips[1].firstFromPrevious;
	const grid = clean(await renderComponent(STORYBOARD));
	assert.deepEqual([...grid.matchAll(/data-chain-chip="([^"]*)"/g)].map((m) => m[1]), ['ready', 'later']);
	assert.match(grid, /data-seam-alert="s2"/);
	assert.ok([...clean(await renderComponent(BAND_LANES)).matchAll(/data-chain-chip="/g)].length >= 1);
	const waiting = { id: 't3', shotId: 's2', status: 'queued', label: 'draft', quality: 'draft', variant: 'B', url: null, createdAt: '2026-10-26T10:01:00Z', chain: { previous: 's1', after: 't1', state: 'waiting', batch: 'b1', source: null, frame: null } };
	setTakes('p1', [{ id: 't1', shotId: 's1', status: 'running', label: 'draft', quality: 'draft', variant: 'A', url: null, createdAt: '2026-10-26T10:00:00Z' }, waiting]);
	assert.equal(waitText(waiting), t('lib.chain.waitTake', { variant: 'A', shot: 'One' }));
	assert.equal(waitText({ ...waiting, chain: { ...waiting.chain, after: null } }), t('lib.chain.waitFrame', { shot: 'One' }));
	assert.equal(waitText({ ...waiting, status: 'running' }), '');
	assert.match(textOf(await renderComponent(TAKE_CARD, { take: waiting, clip: doc.clips[1] })), new RegExp(escaped(t('lib.chain.waitTake', { variant: 'A', shot: 'One' }))));
	doc.frames = [];
	const take = taken('t2');
	setTakes('p1', [take]);
	assert.equal(seamImage(doc, 's2', 'first')?.id, chainAssetId(take));
	const live = taken('t4', { shotId: 's3', chain: { ...taken('t4').chain, previous: 's2', after: 't2', batch: 'b2', source: { shotId: 's2', takeId: 't2', assetId: 'gen-t1', at: 4 } } });
	upsertTake(live);
	assert.equal(seamImage(doc, 's3', 'first')?.id, chainAssetId(live));
});

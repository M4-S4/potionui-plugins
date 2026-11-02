import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, hostUis, renderComponent } from './svelte-harness.js';
import { chainOn, chainPlan, chainSource, chainState, cutEnd, frameAsset, ignoresFirstFrame, normalizeFrameSource, sameFrame, setChain, stillAsset } from './chain.js';
import { framesOf, placeSeamFrame, seamImage } from './seam.js';
import { seamPick } from './continuity.js';

globalThis.Image = class {
	set src(value) {}
};

const { doc, ui, addShot, acceptProposal, adopt, bladeAt, undo, dispose } = await import('./state.svelte.js');
const { project, bindClient } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { chainOf } = await import('./chain.svelte.js');
const { useSeamFrame } = await import('./seam.svelte.js');
const { seam } = await import('./continuity.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const SEAM_ACTION = new URL('../components/takes/SeamAction.svelte', import.meta.url).href;
const SEAM_FIX = new URL('../components/storyboard/SeamFix.svelte', import.meta.url).href;
const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;
const escaped = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

after(() => dispose());

function liveScene(previousAsset = 'pic') {
	project.id = 'p1';
	ui.selection = null;
	ui.storyProposal = null;
	ui.playhead = 0;
	ui.modal = null;
	delete doc.firstFromPrevious;
	doc.clips = [{ id: 's1', assetId: previousAsset, take: previousAsset === 'gen-t1' ? 't1' : null, start: 0, dur: 4, srcIn: 0.5, stage: 'draft', label: 'One' }];
	doc.assets = sampleDoc().assets;
	doc.frames = [];
	doc.prompts = [];
	setTakes('p1', []);
}
let counter = 0;
const makeId = () => `id-${++counter}`;
const takeUrl = (gen, file) => `/api/media/generations/${gen}/${file}`;

function sampleDoc() {
	return {
		fps: 25,
		clips: [
			{ id: 's1', assetId: 'gen-t1', take: 't1', start: 0, dur: 4, srcIn: 0.5, stage: 'draft' },
			{ id: 's2', assetId: null, take: null, start: 4, dur: 4, srcIn: 0, stage: 'todo' }
		],
		frames: [],
		assets: [
			{ id: 'gen-t1', kind: 'video', name: 'Take 1', src: takeUrl('g1', 'wan_00001.mp4'), origin: { kind: 'history', generationId: 'g1', fileId: 'f1' }, srcDur: 5.0625, fps: 16, generated: true, resultId: 't1' },
			{ id: 'gen-t2', kind: 'video', name: 'Take 2', src: takeUrl('g2', 'wan_00002.mp4'), origin: { kind: 'history', generationId: 'g2', fileId: 'f2' }, srcDur: 5.0625, fps: 16, generated: true, resultId: 't2' },
			{ id: 'imp', kind: 'video', name: 'Harbour', src: '/api/media/uploads/harbour.mp4', origin: { kind: 'library', itemId: 'u1' }, srcDur: 12, fps: 25, generated: false },
			{ id: 'pic', kind: 'image', name: 'Poster', src: '/api/media/uploads/poster.png', origin: { kind: 'library', itemId: 'u2' }, width: 1280, height: 720, res: '1280×720', generated: false }
		]
	};
}

function extracted(doc, clip, from, at) {
	const media = { itemId: `item-${at}`, url: `/api/media/uploads/e-${at}.png`, filename: `wan_00001-frame-${at}s.png`, width: 832, height: 480 };
	const asset = frameAsset(media, { shotId: from.id, takeId: from.take, assetId: from.assetId, at }, 'fallback');
	placeSeamFrame(doc, clip, 'first', asset, makeId);
	return asset;
}

test('chainOn: on by default and in every document saved before the option, off only when set to false', () => {
	const doc = sampleDoc();
	assert.equal(chainOn(doc), true);
	setChain(doc, false);
	assert.equal(doc.firstFromPrevious, false);
	assert.equal(chainOn(doc), false);
	setChain(doc, true);
	assert.equal('firstFromPrevious' in doc, false);
	assert.equal(chainOn(doc), true);
});

test('chainSource: the placed take, an imported video or a still, at the end of the cut of the shot', () => {
	const doc = sampleDoc();
	assert.deepEqual(chainSource(doc, doc.clips[0]), { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4.5 });
	Object.assign(doc.clips[0], { assetId: 'imp', take: null, srcIn: 2.25, dur: 3.1 });
	assert.deepEqual(chainSource(doc, doc.clips[0]), { shotId: 's1', takeId: null, assetId: 'imp', at: 5.35 });
	doc.clips[0].assetId = 'pic';
	assert.deepEqual(chainSource(doc, doc.clips[0]), { shotId: 's1', takeId: null, assetId: 'pic', at: null });
	assert.equal(chainSource(doc, doc.clips[1]), null);
	doc.assets.push({ id: 'lost', kind: 'video', src: 'https://elsewhere/v.mp4', origin: null, generated: false });
	doc.clips[0].assetId = 'lost';
	assert.equal(chainSource(doc, doc.clips[0]), null);
	assert.equal(cutEnd({ srcIn: 0.1, dur: 0.2 }), 0.3);
});

test('creation with the option: a new shot after a shot with a take asks for the last frame of its cut', () => {
	const doc = sampleDoc();
	assert.deepEqual(chainPlan(doc, doc.clips[1]), { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4.5 });
	assert.equal(chainPlan(doc, doc.clips[0]), null);
	extracted(doc, doc.clips[1], doc.clips[0], 4.5);
	assert.equal(chainPlan(doc, doc.clips[1]), null);
});

test('creation without the option, or after a shot that has no media yet: nothing is asked', () => {
	const doc = sampleDoc();
	setChain(doc, false);
	assert.equal(chainPlan(doc, doc.clips[1]), null);
	setChain(doc, true);
	doc.clips.push({ id: 's3', assetId: null, start: 8, dur: 4, srcIn: 0, stage: 'todo' });
	assert.equal(chainPlan(doc, doc.clips[2]), null);
	assert.equal(chainState(doc, 2), null);
});

test('creation after a still: the image itself, as a copy that keeps where it came from', () => {
	const doc = sampleDoc();
	doc.clips[0].assetId = 'pic';
	const plan = chainPlan(doc, doc.clips[1]);
	const copy = stillAsset(doc, plan, 'Last frame · Opening');
	placeSeamFrame(doc, doc.clips[1], 'first', copy, makeId);
	assert.deepEqual([copy.kind, copy.src, copy.origin, copy.res, copy.name], ['image', '/api/media/uploads/poster.png', { kind: 'library', itemId: 'u2' }, '1280×720', 'Last frame · Opening']);
	assert.deepEqual(copy.frameOf, { shotId: 's1', takeId: null, assetId: 'pic', at: null });
	assert.equal(seamImage(doc, 's2', 'first'), copy);
	assert.equal(chainState(doc, 1).state, 'fresh');
	doc.assets.push({ ...doc.assets.find((a) => a.id === 'pic'), id: 'pic2' });
	doc.clips[0].assetId = 'pic2';
	assert.equal(chainState(doc, 1).state, 'stale');
});

test('chainState: fresh while the previous shot keeps its take and its cut, stale after a new take, a trim or a reorder', () => {
	const doc = sampleDoc();
	const first = extracted(doc, doc.clips[1], doc.clips[0], 4.5);
	assert.deepEqual(first.frameOf, { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4.5 });
	assert.equal(chainState(doc, 1).state, 'fresh');
	doc.clips[0].dur = 3.96;
	assert.equal(chainState(doc, 1).state, 'fresh', 'at 16 fps a cut that ends at 4.46 s still ends on the frame 71, as at 4.5 s');
	doc.clips[0].dur = 3.8;
	assert.equal(chainState(doc, 1).state, 'stale');
	doc.clips[0].dur = 4;
	assert.equal(chainState(doc, 1).state, 'fresh');
	Object.assign(doc.clips[0], { assetId: 'gen-t2', take: 't2' });
	const stale = chainState(doc, 1);
	assert.deepEqual([stale.state, stale.source], ['stale', { shotId: 's1', takeId: 't2', assetId: 'gen-t2', at: 4.5 }]);
	Object.assign(doc.clips[0], { assetId: 'gen-t1', take: 't1' });
	doc.clips.splice(1, 0, { id: 's0', assetId: 'imp', start: 4, dur: 2, srcIn: 0, stage: 'source' });
	assert.equal(chainState(doc, 2).state, 'stale');
});

test('chainState: a frame past the end of a take stays fresh while the cut still ends past it', () => {
	const doc = sampleDoc();
	doc.clips[0].dur = 4.8;
	extracted(doc, doc.clips[1], doc.clips[0], 5.3);
	doc.clips[0].dur = 4.9;
	assert.equal(chainState(doc, 1).state, 'fresh');
	assert.equal(sameFrame(doc, { shotId: 's1', assetId: 'gen-t1', at: 5.3 }, { shotId: 's1', assetId: 'gen-t1', at: 5.0 }), false);
});

test('chainState: a previous shot that loses its media leaves the first frame stale with nothing to take', () => {
	const doc = sampleDoc();
	extracted(doc, doc.clips[1], doc.clips[0], 4.5);
	Object.assign(doc.clips[0], { assetId: null, take: null, srcIn: 0, stage: 'todo' });
	const state = chainState(doc, 1);
	assert.deepEqual([state.state, state.source], ['stale', null]);
});

test('reprise: the new last frame replaces the stale one, which stays fresh afterwards', () => {
	const doc = sampleDoc();
	extracted(doc, doc.clips[1], doc.clips[0], 4.5);
	Object.assign(doc.clips[0], { assetId: 'gen-t2', take: 't2', srcIn: 0 });
	const { source: next } = chainState(doc, 1);
	extracted(doc, doc.clips[1], doc.clips[0], next.at);
	assert.equal(framesOf(doc, 's2', 'first').length, 1);
	assert.equal(seamImage(doc, 's2', 'first').frameOf.assetId, 'gen-t2');
	assert.equal(chainState(doc, 1).state, 'fresh');
});

test('chainState: a frame chosen by hand is never stale, and the seam offers the last frame once a take arrives', () => {
	const doc = sampleDoc();
	doc.clips[0].assetId = null;
	assert.equal(chainState(doc, 1), null);
	doc.clips[0].assetId = 'gen-t1';
	const offer = chainState(doc, 1);
	assert.deepEqual([offer.state, offer.source.assetId, offer.image], ['offer', 'gen-t1', null]);
	setChain(doc, false);
	assert.equal(chainState(doc, 1), null);
	setChain(doc, true);
	for (const stage of ['draft', 'final', 'source']) {
		doc.clips[1].stage = stage;
		assert.equal(chainState(doc, 1), null, stage);
	}
	doc.clips[1].stage = 'todo';
	placeSeamFrame(doc, doc.clips[1], 'first', { id: 'manual', kind: 'image', src: '/api/media/uploads/m.png' }, makeId);
	Object.assign(doc.clips[0], { assetId: 'gen-t2', take: 't2' });
	assert.equal(chainState(doc, 1), null);
});

test('seamPick: a first frame taken from the previous take is never measured as the shot’s own image', () => {
	const doc = sampleDoc();
	extracted(doc, doc.clips[1], doc.clips[0], 4.5);
	Object.assign(doc.clips[1], { assetId: 'gen-t2', take: 't2' });
	const takes = [
		{ id: 't1', shotId: 's1', url: takeUrl('g1', 'wan_00001.mp4') },
		{ id: 't2', shotId: 's2', url: takeUrl('g2', 'wan_00002.mp4') }
	];
	assert.deepEqual(seamPick(doc, 1, takes), { last: null, first: null });
});

test('normalizeFrameSource: the shot, take, asset and time the server answers', () => {
	assert.deepEqual(normalizeFrameSource({ shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4.5 }), { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4.5 });
	assert.deepEqual(normalizeFrameSource({ shotId: 's1', takeId: null, assetId: 'imp', at: Infinity }), { shotId: 's1', takeId: null, assetId: 'imp', at: null });
	assert.equal(normalizeFrameSource({ shotId: 's1' }), null);
	assert.equal(normalizeFrameSource(null), null);
});

test('ignoresFirstFrame: a local preset that composes from text only, never a cloud model', () => {
	assert.equal(ignoresFirstFrame({ kind: 'native.local', info: { directorModes: ['t2v'] } }), true);
	assert.equal(ignoresFirstFrame({ kind: 'native.local', info: { directorModes: ['t2v', 'i2v', 'flf'] } }), false);
	assert.equal(ignoresFirstFrame({ kind: 'native.local', info: { directorModes: [] } }), false);
	assert.equal(ignoresFirstFrame({ kind: 'cloud', info: { directorModes: ['t2v'] } }), false);
	assert.equal(ignoresFirstFrame(null), false);
});



test('the cut of a slowed shot ends where its take stops showing: its in point plus its duration times its speed', () => {
	assert.equal(cutEnd({ srcIn: 1, dur: 4, speed: 0.5 }), 3);
	assert.equal(cutEnd({ srcIn: 0.5, dur: 8, speed: 0.25 }), 2.5);
	assert.equal(cutEnd({ srcIn: 1, dur: 4, speed: 2 }), 5);
	const doc = sampleDoc();
	Object.assign(doc.clips[0], { srcIn: 0.5, dur: 4, speed: 0.5 });
	assert.deepEqual(chainSource(doc, doc.clips[0]), { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 2.5 });
});

test('wiring: every path that adds a shot gives it the end of the previous one inside the same undo step, and a blade cut does not', () => {
	liveScene();
	const before = JSON.stringify(doc);
	const added = addShot('Two');
	assert.deepEqual(seamImage(doc, added.id, 'first')?.frameOf, { shotId: 's1', takeId: null, assetId: 'pic', at: null });
	undo();
	assert.equal(JSON.stringify(doc), before);
	ui.storyProposal = [{ keep: true, label: 'Three', dur: 4, prompt: 'A boat leaves the harbour.' }];
	acceptProposal();
	assert.equal(doc.clips.length, 2);
	assert.equal(seamImage(doc, doc.clips[1].id, 'first')?.frameOf?.assetId, 'pic');
	undo();
	assert.equal(JSON.stringify(doc), before);
	const next = JSON.parse(before);
	next.clips.push({ id: 's9', assetId: null, take: null, start: 4, dur: 4, srcIn: 0, stage: 'todo', label: 'Nine' });
	adopt(next);
	assert.equal(seamImage(doc, 's9', 'first')?.frameOf?.assetId, 'pic');
	undo();
	assert.equal(JSON.stringify(doc), before);
	bladeAt(2);
	assert.equal(doc.clips.length, 2);
	assert.equal(seamImage(doc, doc.clips[1].id, 'first') ?? null, null);
});

test('wiring: the seam says when the first frame is stale or when the previous shot can give one, and its action takes the new end frame without asking', async () => {
	liveScene('gen-t1');
	const calls = [];
	const asked = [];
	bindClient({
		async saveProject(id, next, version) {
			return { ok: true, data: { version: version + 1, updatedAt: null } };
		},
		async endFrame(projectId, shotId) {
			calls.push([projectId, shotId]);
			const media = { itemId: 'item-9', url: '/api/media/uploads/e-9.png', filename: 'wan_00001-frame-4.5s.png', width: 832, height: 480 };
			return { ok: true, data: { media, source: { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: cutEnd(doc.clips[0]) } } };
		}
	});
	window.__potionui.confirm = async (options) => (asked.push(options), false);
	doc.clips.push({ id: 's2', assetId: null, take: null, start: 4, dur: 4, srcIn: 0, stage: 'todo', label: 'Two' });
	assert.deepEqual(seam(1).issues.map((issue) => [issue.kind, issue.text]), [['chain_offer', t('lib.chain.offer', { shot: 'Two', previous: 'One' })]]);
	const offer = clean(await renderComponent(SEAM_ACTION, { clip: doc.clips[1] }));
	assert.match(offer, new RegExp(`<button[^>]*>${escaped(t('lib.seam.use'))}</button>`));
	assert.doesNotMatch(offer.match(/<button[^>]*>/)[0], /\sdisabled(?!:)/);
	extracted(doc, doc.clips[1], doc.clips[0], 3);
	assert.deepEqual(seam(1).issues.map((issue) => [issue.kind, issue.text]), [['chain_stale', t('lib.chain.stale', { shot: 'Two', previous: 'One' })]]);
	assert.equal(chainOf(doc.clips[1]).state, 'stale');
	const stale = clean(await renderComponent(SEAM_ACTION, { clip: doc.clips[1] }));
	assert.match(stale, new RegExp(`<button[^>]*>${escaped(t('lib.chain.refresh'))}</button>`));
	const fix = clean(await renderComponent(SEAM_FIX, { clip: doc.clips[1], issue: seam(1).issues[0] }));
	assert.match(fix, new RegExp(`data-seam-fix="chain">[\\s\\S]*<button[^>]*>${escaped(t('lib.chain.refresh'))}</button>`));
	await useSeamFrame(doc.clips[1]);
	assert.deepEqual([calls, asked], [[['p1', 's1']], []]);
	assert.equal(chainOf(doc.clips[1]).state, 'fresh');
	assert.deepEqual(seam(1).issues, []);
	await useSeamFrame(doc.clips[1]);
	assert.deepEqual([calls.length, asked.length], [1, 1]);
	ui.modal = { type: 'project' };
	const chainSwitch = async () => hostUis(await renderComponent(MODALS), 'Switch').filter((item) => item.id === 'vp-project-chain').map((item) => item.checked);
	assert.deepEqual(await chainSwitch(), [true]);
	setChain(doc, false);
	assert.deepEqual(await chainSwitch(), [false]);
	ui.modal = null;
	window.__potionui.confirm = async () => true;
});

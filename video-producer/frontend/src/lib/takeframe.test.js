import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent } from './svelte-harness.js';

globalThis.Image = class {
	set src(value) {}
};

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project, bindClient } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { FRAMES_LIMIT, estimateRequest, estimateState, refreshEstimate, thumbRatio } = await import('./production.svelte.js');
const { frameBox, frameTile, takeFrame } = await import('./framing.js');
const { normalizeEstimate } = await import('./api.js');

const url = (path) => new URL(path, import.meta.url).href;
const INSPECTOR = url('../components/inspector/Inspector.svelte');
const SHOT_EDITOR = url('../components/modals/ShotEditor.svelte');
const QUICK_EDIT = url('../components/storyboard/ShotQuickEdit.svelte');
const BAND_MONITOR = url('../components/storyboard/BandMonitor.svelte');
const REVIEW_SEAM = url('../components/director/ReviewSeam.svelte');
const REVIEW_TAKE = url('../components/director/ReviewTake.svelte');

after(() => dispose());

const DRAFT = 26 / 15;
const SCOPE = 2.39;

const WAN = '01KX47WANVIDEO0000000000TV';
const H3 = '01M54HN72B0KY7H63BKQ16T253';
let projects = 0;

function scene(aspect, target = 'sequence') {
	project.id = `p${++projects}`;
	project.status = 'saved';
	project.version = 1;
	Object.assign(ui, { workspace: 'storyboard', storyView: 'band', selection: { kind: 'clip', id: 's2' }, seamCompare: 's2', preview: null, compare: null, picked: [], modal: null, dirty: false });
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [WAN, H3].map((id) => ({ id, name: id, video: true, cloud: false, profiles: ['FL2VA'], limits: { defaultDuration: 5, maxDuration: null }, resolutions: [] })), settings: { draftResolution: '832x480', maxParallelJobs: null } };
	ui.production.target = target;
	ui.production.quality = 'draft';
	doc.aspect = aspect;
	doc.engine = { backend: 'native', preset: WAN, model: null };
	doc.direction.mode = 'FL2VA';
	doc.clips = [
		{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo', take: null, assetId: null, srcIn: 0 },
		{ id: 's2', start: 4, dur: 4, label: 'Two', stage: 'todo', take: null, assetId: null, srcIn: 0 }
	];
	doc.prompts = [];
	doc.assets = [
		{ id: 'square', kind: 'image', name: 'Square', src: '/square.png', width: 1024, height: 1024, origin: { kind: 'library', itemId: 'u1' } },
		{ id: 'wide', kind: 'image', name: 'Wide', src: '/wide.png', width: 1280, height: 720, origin: { kind: 'library', itemId: 'u2' } }
	];
	doc.frames = [
		{ id: 'f1', shotId: 's1', role: 'last', time: 4, assetId: 'square' },
		{ id: 'f2', shotId: 's2', role: 'first', time: 4, assetId: 'square' },
		{ id: 'f3', shotId: 's2', role: 'last', time: 8, assetId: 'wide' }
	];
	setTakes(project.id, []);
	Object.assign(estimateState, { key: null, data: null, error: null });
}

const estimated = async (frames) => {
	const data = normalizeEstimate({ shots: Object.entries(frames).map(([shot_id, frame]) => ({ shot_id, director_mode: 'flf', seconds: 4, resolution: '832x480', fps: 16, frame })), blocks: [], warnings: [] });
	bindClient({ estimate: async () => ({ ok: true, data }) });
	refreshEstimate();
	await new Promise((resolve) => setTimeout(resolve, 0));
	assert.equal(estimateState.key, estimateRequest()?.key);
};

test('the box of a start or end image takes the ratio of the take when the take is in another ratio than the film, and the picture\'s own ratio when it is sent as it is', () => {
	assert.equal(takeFrame({ aspect: '16:9' }, DRAFT), 16 / 9);
	assert.equal(takeFrame({ aspect: '2.39:1' }, DRAFT), DRAFT);
	assert.equal(takeFrame({ aspect: '2.39:1' }, DRAFT, { width: 1024, height: 1024 }), DRAFT);
	assert.equal(takeFrame({ aspect: '2.39:1' }, DRAFT, { width: 1280, height: 720 }), 1280 / 720);
	assert.equal(takeFrame({ aspect: '2.39:1' }, DRAFT, { resolution: '1280x720' }), 1280 / 720);
	assert.equal(takeFrame({ aspect: '2.39:1' }, null, { width: 1280, height: 720 }), SCOPE);
	assert.equal(takeFrame({ aspect: '9:16' }, 16 / 9), 16 / 9);
	assert.equal(frameBox({ aspect: '2.39:1' }, '7rem', DRAFT), `aspect-ratio: ${DRAFT}; width: 100%`);
	assert.equal(frameBox({ aspect: '16:9' }, '7rem', 9 / 16), `aspect-ratio: ${9 / 16}; height: 7rem; width: auto; max-width: 100%; margin: 0 auto`);
	assert.equal(frameTile({ aspect: '2.39:1' }, 88, 50, 2), 'aspect-ratio: 2; width: 88px');
	assert.equal(frameTile({ aspect: '2.39:1' }, 88, 50, DRAFT), `aspect-ratio: ${DRAFT}; height: 50px`);
	assert.equal(frameTile({ aspect: '16:9' }, 88, 50, 1), 'aspect-ratio: 1; height: 50px');
});

test('the page reads the ratio of each shot\'s take from the estimate, gives it to the shots of the same engine, and keeps the frame of the film for a take it has not seen', async () => {
	scene('2.39:1');
	assert.equal(thumbRatio('s2'), SCOPE);
	await estimated({ s2: [26, 15] });
	assert.deepEqual(estimateState.data.shots[0].frame, [26, 15]);
	assert.equal(thumbRatio('s2'), DRAFT);
	assert.equal(thumbRatio('s2', doc.assets[1]), 1280 / 720);
	assert.equal(thumbRatio('s1'), DRAFT);
	scene('2.39:1');
	assert.equal(thumbRatio('s1'), SCOPE);
	await estimated({ s2: null });
	assert.equal(thumbRatio('s2'), SCOPE);
});

test('with the Shot target, selecting another shot keeps the frame of its take while its estimate is on its way', async () => {
	scene('2.39:1', 'clip');
	ui.selection = { kind: 'clip', id: 's1' };
	await estimated({ s1: [26, 15] });
	const tiles = async (clip) => [...clean(await renderComponent(QUICK_EDIT, { clip })).matchAll(/style="(aspect-ratio: [^"]*)" data-quick-frame/g)].map((match) => match[1]);
	assert.deepEqual(await tiles(doc.clips[0]), [`aspect-ratio: ${DRAFT}; height: 50px`, `aspect-ratio: ${DRAFT}; height: 50px`]);
	ui.selection = { kind: 'clip', id: 's2' };
	assert.notEqual(estimateRequest().key, estimateState.key);
	const before = await tiles(doc.clips[1]);
	await estimated({ s2: [26, 15] });
	assert.deepEqual(await tiles(doc.clips[1]), before);
	assert.deepEqual(before, [`aspect-ratio: ${DRAFT}; height: 50px`, `aspect-ratio: ${1280 / 720}; width: 88px`]);
	ui.selection = { kind: 'clip', id: 's1' };
	assert.deepEqual(await tiles(doc.clips[0]), [`aspect-ratio: ${DRAFT}; height: 50px`, `aspect-ratio: ${DRAFT}; height: 50px`]);
});

test('a frame that no longer holds for the project, or an estimate in error, gives the frame of the film', async () => {
	scene('2.39:1');
	await estimated({ s1: [26, 15], s2: [26, 15] });
	assert.equal(thumbRatio('s2'), DRAFT);
	doc.engine = { backend: 'native', preset: H3, model: null };
	assert.notEqual(estimateRequest().key, estimateState.key);
	assert.equal(thumbRatio('s2'), SCOPE);
	await estimated({ s1: [30, 13], s2: [30, 13] });
	assert.equal(thumbRatio('s2'), 30 / 13);
	ui.production.quality = 'final';
	assert.equal(thumbRatio('s2'), SCOPE);
	ui.production.quality = 'draft';
	doc.engine.sizes = { [H3]: { draft: '832x480' } };
	project.version += 1;
	assert.equal(thumbRatio('s2'), SCOPE);
	delete doc.engine.sizes;
	project.version += 1;
	assert.equal(thumbRatio('s2'), 30 / 13);
	doc.clips[1].engine = { preset: WAN, model: null };
	project.version += 1;
	assert.equal(thumbRatio('s2'), DRAFT);
	assert.equal(thumbRatio('s1'), 30 / 13);
	doc.clips[1].engine = { preset: WAN, model: null, quality: 'final' };
	project.version += 1;
	assert.equal(thumbRatio('s2'), SCOPE);
	delete doc.clips[1].engine;
	project.version += 1;
	doc.aspect = '2:1';
	project.version += 1;
	assert.equal(thumbRatio('s2'), 2);
	doc.aspect = '2.39:1';
	project.version += 1;
	assert.equal(thumbRatio('s2'), 30 / 13);
	Object.assign(estimateState, { key: estimateRequest().key, data: null, error: { code: 'network', message: 'x' } });
	assert.equal(thumbRatio('s2'), SCOPE);
});

test('the inspector shows the start and end images of a shot in the frame of its take', async () => {
	scene('2.39:1');
	const thumbs = async () => [...clean(await renderComponent(INSPECTOR)).matchAll(/<img src="([^"]*)" alt="" class="object-cover" style="aspect-ratio: ([0-9.]+); width: 100%" data-frame-thumb/g)].map((match) => [match[1], Number(match[2])]);
	assert.deepEqual(await thumbs(), [['/square.png', SCOPE], ['/wide.png', SCOPE]]);
	await estimated({ s2: [26, 15] });
	assert.deepEqual(await thumbs(), [['/square.png', DRAFT], ['/wide.png', 1280 / 720]]);
});

test('the shot editor picks the start and end images in the frame of the shot\'s take', async () => {
	scene('2.39:1');
	await estimated({ s2: [26, 15] });
	const html = clean(await renderComponent(SHOT_EDITOR, { id: 's2' }));
	const thumbs = [...html.matchAll(/<img src="([^"]*)" alt="" class="object-cover" style="aspect-ratio: ([0-9.]+); width: 100%" data-frame-thumb/g)].map((match) => [match[1], Number(match[2])]);
	assert.deepEqual(thumbs, [['/square.png', DRAFT], ['/wide.png', 1280 / 720]]);
});

test('the key frame tiles of the quick edit have the ratio of the shot\'s take', async () => {
	scene('2.39:1');
	await estimated({ s2: [26, 15] });
	const html = clean(await renderComponent(QUICK_EDIT, { clip: doc.clips[1] }));
	assert.deepEqual([...html.matchAll(/style="aspect-ratio: ([0-9.]+); (?:width: 88px|height: 50px)" data-quick-frame/g)].map((match) => Number(match[1])), [DRAFT, 1280 / 720]);
});

test('the seam monitor and the seam review show a start or end image in the frame of its shot\'s take', async () => {
	scene('2.39:1');
	await estimated({ s1: [16, 9], s2: [26, 15] });
	const monitor = clean(await renderComponent(BAND_MONITOR));
	assert.deepEqual([...monitor.matchAll(/style="aspect-ratio: ([0-9.]+); width: 100%; grid-area: still(\d);" data-seam-still/g)].map((match) => [Number(match[1]), match[2]]), [[16 / 9, '0'], [DRAFT, '1']]);
	const review = clean(await renderComponent(REVIEW_SEAM, { clip: doc.clips[1], previous: doc.clips[0] }));
	assert.deepEqual([...review.matchAll(/style="aspect-ratio: ([0-9.]+); width: 100%" data-seam-still/g)].map((match) => Number(match[1])), [16 / 9, DRAFT]);
});

test('a still of the seam monitor and of the seam review that is the media placed on the shot, not its start or end image, keeps the frame of the film', async () => {
	scene('2.39:1');
	doc.clips[1].assetId = 'wide';
	await estimated({ s1: [16, 9], s2: [26, 15] });
	const stills = (html) => [...clean(html).matchAll(/style="aspect-ratio: ([0-9.]+); width: 100%(?:; grid-area: still\d;)?" data-seam-still="">(?:<img [^>]*?src="([^"]*)")?/g)].map((match) => [Number(match[1]), match[2] ?? null]);
	assert.deepEqual(stills(await renderComponent(REVIEW_SEAM, { clip: doc.clips[1], previous: doc.clips[0] })), [[16 / 9, '/square.png'], [SCOPE, '/wide.png']]);
	assert.deepEqual(stills(await renderComponent(BAND_MONITOR)), [[16 / 9, '/square.png'], [SCOPE, '/wide.png']]);
});

test('the seams of the review of a take show the start image of the next shot in the frame of its take, and the take in the frame of the film', async () => {
	scene('2.39:1');
	const take = { id: 't1', shotId: 's1', status: 'done', label: 'draft', quality: 'draft', variant: 'A', url: '/t1.mp4', thumbUrl: '/t1.jpg', createdAt: '2026-10-29T10:00:00Z' };
	setTakes(project.id, [take]);
	const stills = async () => [...clean(await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take })).matchAll(/style="(aspect-ratio: [^"]*)" data-take-seam-still="">(?:<img src="([^"]*)")?/g)].map((match) => [match[1], match[2] ?? null]);
	const before = await stills();
	assert.deepEqual(before.map(([box]) => box), [`aspect-ratio: ${SCOPE}; width: 64px`, `aspect-ratio: ${SCOPE}; width: 64px`]);
	assert.equal(before[1][1], '/square.png');
	await estimated({ s1: [26, 15], s2: [26, 15] });
	assert.deepEqual((await stills()).map(([box]) => box), [`aspect-ratio: ${SCOPE}; width: 64px`, `aspect-ratio: ${DRAFT}; height: 36px`]);
});

test('two renders in a row of the seam monitor give the same thumbnails when the neighbouring shot was not estimated', async () => {
	scene('2.39:1', 'clip');
	ui.selection = { kind: 'clip', id: 's2' };
	await estimated({ s2: [26, 15] });
	const stills = async () => [...clean(await renderComponent(BAND_MONITOR)).matchAll(/style="aspect-ratio: ([0-9.]+); width: 100%; grid-area: still(\d);" data-seam-still/g)].map((match) => [Number(match[1]), match[2]]);
	const first = await stills();
	assert.deepEqual(first, [[DRAFT, '0'], [DRAFT, '1']]);
	assert.deepEqual(await stills(), first);
});

test('an estimate keeps its frames under the take the request asked for, and leaves nothing behind once its request no longer holds', async () => {
	scene('2.39:1');
	let answer;
	const data = normalizeEstimate({ shots: [{ shot_id: 's1', director_mode: 'flf', seconds: 4, resolution: '832x480', fps: 16, frame: [26, 15] }, { shot_id: 's2', director_mode: 'flf', seconds: 4, resolution: '832x480', fps: 16, frame: [26, 15] }], blocks: [], warnings: [] });
	bindClient({ estimate: () => new Promise((resolve) => (answer = resolve)) });
	refreshEstimate();
	project.version += 1;
	answer({ ok: true, data });
	await new Promise((resolve) => setTimeout(resolve, 0));
	assert.equal(thumbRatio('s2'), SCOPE);
	project.version += 1;
	assert.equal(thumbRatio('s2'), SCOPE);
	bindClient({ estimate: () => new Promise((resolve) => (answer = resolve)) });
	refreshEstimate();
	ui.me.settings.draftResolution = '1280x720';
	answer({ ok: true, data });
	await new Promise((resolve) => setTimeout(resolve, 0));
	project.version += 1;
	assert.equal(thumbRatio('s2'), SCOPE);
	ui.me.settings.draftResolution = '832x480';
	assert.equal(thumbRatio('s2'), DRAFT);
});

test('the frames the page keeps belong to their project and are bounded', async () => {
	scene('2.39:1');
	const first = project.id;
	await estimated({ s2: [26, 15] });
	project.id = 'another';
	assert.equal(thumbRatio('s2'), SCOPE);
	project.id = first;
	project.version += 1;
	assert.equal(thumbRatio('s2'), DRAFT);
	project.id = 'bound';
	doc.clips = Array.from({ length: FRAMES_LIMIT }, (_, index) => ({ id: `s${index + 1}`, start: 4 * index, dur: 4, label: `${index + 1}`, stage: 'todo', take: null, assetId: null, srcIn: 0 }));
	await estimated(Object.fromEntries(doc.clips.map((clip) => [clip.id, [26, 15]])));
	project.id = first;
	assert.equal(thumbRatio('s2'), SCOPE);
});

test('the review of a take shows its seams in the frame of the film, whatever the film', async () => {
	const take = { id: 't1', shotId: 's1', status: 'done', label: 'draft', quality: 'draft', variant: 'A', url: '/t1.mp4', thumbUrl: '/t1.jpg', createdAt: '2026-10-29T10:00:00Z' };
	const boxes = async () => [...clean(await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take })).matchAll(/style="(aspect-ratio: [^"]*)" data-take-seam-still/g)].map((match) => match[1]);
	scene('9:16');
	setTakes(project.id, [take]);
	assert.deepEqual(await boxes(), [`aspect-ratio: ${9 / 16}; height: 36px`, `aspect-ratio: ${9 / 16}; height: 36px`]);
	assert.equal(36 * (9 / 16), 20.25);
	scene('2.39:1');
	setTakes(project.id, [take]);
	assert.deepEqual(await boxes(), [`aspect-ratio: ${SCOPE}; width: 64px`, `aspect-ratio: ${SCOPE}; width: 64px`]);
	assert.equal(Math.round((64 / SCOPE) * 10) / 10, 26.8);
});

test('when the take has the ratio of the film, every thumbnail is the one it was, to the byte', async () => {
	const renders = async () => [
		await renderComponent(INSPECTOR),
		await renderComponent(SHOT_EDITOR, { id: 's2' }),
		await renderComponent(QUICK_EDIT, { clip: doc.clips[1] }),
		await renderComponent(BAND_MONITOR),
		await renderComponent(REVIEW_SEAM, { clip: doc.clips[1], previous: doc.clips[0] }),
		await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: { id: 't1', shotId: 's1', status: 'done', label: 'draft', quality: 'draft', variant: 'A', url: '/t1.mp4', createdAt: '2026-10-29T10:00:00Z' } })
	].map(clean);
	for (const [aspect, frame] of [['16:9', [26, 15]], ['9:16', [15, 26]], ['16:9', [16, 9]], ['1:1', [1, 1]]]) {
		scene(aspect);
		const before = await renders();
		await estimated({ s1: frame, s2: frame });
		assert.deepEqual(await renders(), before, aspect);
	}
});

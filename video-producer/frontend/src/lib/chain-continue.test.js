import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { hostUis, renderComponent } from './svelte-harness.js';
import { CHAIN_BY, chainByOf, setChainBy, setShotChainBy } from './chain.js';

globalThis.Image = class {
	set src(value) {}
};

const { doc, ui, dispose, secs } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { chainStatusText, chooseShotChainBy, seamChainOf } = await import('./chain.svelte.js');
const { noteText } = await import('./production.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;
const CHAIN_SWITCH = new URL('../components/shots/ChainSwitch.svelte', import.meta.url).href;

after(() => dispose());

test('a project chains by the last frame unless it or a shot chose the continuation', () => {
	const film = { clips: [{ id: 's1' }, { id: 's2' }] };
	assert.deepEqual(CHAIN_BY, ['frame', 'video']);
	assert.equal(chainByOf(film, film.clips[1]), 'frame');
	setChainBy(film, 'video');
	assert.equal(film.chainBy, 'video');
	assert.equal(chainByOf(film, film.clips[1]), 'video');
	setShotChainBy(film, film.clips[1], 'frame');
	assert.equal(film.clips[1].chainBy, 'frame');
	setShotChainBy(film, film.clips[1], 'video');
	assert.equal('chainBy' in film.clips[1], false);
	setChainBy(film, 'audio');
	assert.equal(film.chainBy, 'video');
	setChainBy(film, 'frame');
	assert.equal('chainBy' in film, false);
});

test('the project properties offer the chain by continuation while the chain is on', async () => {
	delete doc.chainBy;
	delete doc.firstFromPrevious;
	ui.modal = { type: 'project' };
	const control = async () => hostUis(await renderComponent(MODALS), 'SegmentedControl').find((item) => item.ariaLabel === t('shell.properties.chainBy'));
	const shown = await control();
	assert.deepEqual(
		shown.items.map((item) => [item.id, item.label]),
		[
			['frame', t('shell.properties.chainByFrame')],
			['video', t('shell.properties.chainByVideo')]
		]
	);
	assert.equal(shown.selected, 'frame');
	doc.chainBy = 'video';
	assert.equal((await control()).selected, 'video');
	doc.firstFromPrevious = false;
	assert.equal(await control(), undefined);
	delete doc.firstFromPrevious;
	delete doc.chainBy;
	ui.modal = null;
});

test('a chained shot chooses how it chains in FL2VA and in Ref2VA, where only the continuation sends the end of the previous take', async () => {
	project.id = 'p1';
	doc.direction = { ...(doc.direction ?? {}), mode: 'FL2VA' };
	doc.clips = [
		{ id: 's1', assetId: null, take: null, start: 0, dur: 4, srcIn: 0, stage: 'todo', label: 'One' },
		{ id: 's2', assetId: null, take: null, start: 4, dur: 4, srcIn: 0, stage: 'todo', label: 'Two' }
	];
	setTakes('p1', []);
	const control = async () => hostUis(await renderComponent(CHAIN_SWITCH, { clip: doc.clips[1] }), 'SegmentedControl').find((item) => item.ariaLabel === t('shell.properties.chainBy'));
	assert.equal((await control()).selected, 'frame');
	chooseShotChainBy(doc.clips[1], 'video');
	assert.equal(doc.clips[1].chainBy, 'video');
	assert.equal((await control()).selected, 'video');
	doc.direction.mode = 'Ref2VA';
	assert.equal(seamChainOf(doc.clips[1]).state, 'continueLater');
	assert.equal((await control()).selected, 'video');
	chooseShotChainBy(doc.clips[1], 'frame');
	assert.equal(seamChainOf(doc.clips[1]).state, 'references');
	assert.equal(chainStatusText(seamChainOf(doc.clips[1])), t('storyboard.chain.references', { previous: 'One' }));
	assert.equal((await control()).selected, 'frame');
	doc.direction.mode = 'FL2VA';
	doc.clips[1].firstFromPrevious = false;
	assert.equal(await control(), undefined);
});

test('the estimate says why a shot asked to continue starts from the last image', () => {
	for (const code of ['chain_continue_unsupported', 'chain_continue_still', 'chain_continue_short', 'chain_continue_last_frame', 'chain_continue_too_long', 'chain_continue_sound']) {
		const text = noteText({ code, message: 'server text', data: { shot_id: 's2' } });
		assert.notEqual(text, 'server text', code);
		assert.equal(text.split('{').length, 1, code);
	}
});

const H3_12GB = '01M54HN72B0KY7H63BKQ16T253';
const FAST_12GB = '01M54HN72PABVRE54YNQA2Q7ZT';
const FACE = { id: 'face', kind: 'image', name: 'face', src: '/api/media/uploads/face.png', width: 1024, height: 1024 };
const QUAY = { id: 'quay', kind: 'image', name: 'quay', src: '/api/media/uploads/quay.png', width: 1344, height: 768 };
const BOOTS = { id: 'boots', kind: 'image', name: 'boots', src: '/api/media/uploads/boots.png', width: 1024, height: 1024 };

function chained({ mode, by = 'video', preset = H3_12GB, modes = ['video', 'refs', 'extend'], profiles = ['FL2VA', 'Ref2VA'], size = '832x480', pictures = [], first = {}, second = {}, takes = [] }) {
	ui.me = {
		engines: [{ id: 'native', kind: 'local', name: 'Local' }],
		presets: [
			{
				id: preset,
				name: 'MiniMax-H3 (12 GB)',
				video: true,
				cloud: false,
				listed: true,
				profiles,
				modes,
				directorModes: ['t2v', 'i2v'],
				resolutions: [{ value: '960x544' }, { value: '832x480' }],
				limits: { defaultDuration: 5, maxDuration: null },
				options: { refs: [{ name: 'reference_pixel_budget', type: 'select', default: '1' }] }
			}
		]
	};
	project.id = 'p1';
	doc.engine = { backend: 'native', preset, model: null, sizes: { [preset]: { draft: size } } };
	doc.direction = { ...(doc.direction ?? {}), mode };
	if (by === 'video') doc.chainBy = 'video';
	else delete doc.chainBy;
	delete doc.firstFromPrevious;
	doc.assets = pictures.map((asset) => ({ ...asset }));
	doc.references = pictures.map((asset) => ({ id: `r-${asset.id}`, assetId: asset.id, space: 'identite', type: 'image', scope: { type: 'global' } }));
	doc.frames = [];
	doc.clips = [
		{ id: 's1', assetId: null, take: null, start: 0, dur: 4, srcIn: 0, stage: 'todo', label: 'One', ...first },
		{ id: 's2', assetId: null, take: null, start: 4, dur: 3, srcIn: 0, stage: 'todo', label: 'Two', ...second }
	];
	setTakes('p1', takes);
	const state = seamChainOf(doc.clips[1]);
	return { state: state.state, extends: state.extends, tokens: state.tokens ?? null, text: chainStatusText(state) };
}

test('a chained shot says what the server does in FL2VA and Ref2VA, by the last frame or by continuation, with and without the continue mode', () => {
	const previous = 'One';
	assert.deepEqual(chained({ mode: 'FL2VA' }), { state: 'continueLater', extends: true, tokens: null, text: t('storyboard.chain.extendLater', { previous }) });
	assert.deepEqual(chained({ mode: 'FL2VA', modes: ['video', 'refs'] }), { state: 'later', extends: false, tokens: null, text: t('storyboard.chain.later', { previous }) });
	assert.deepEqual(chained({ mode: 'FL2VA', by: 'frame' }), { state: 'later', extends: false, tokens: null, text: t('storyboard.chain.later', { previous }) });
	assert.deepEqual(chained({ mode: 'Ref2VA' }), { state: 'continueLater', extends: false, tokens: null, text: t('storyboard.chain.continueLater', { previous }) });
	assert.deepEqual(chained({ mode: 'Ref2VA', modes: ['video', 'refs'] }), { state: 'continueLater', extends: false, tokens: null, text: t('storyboard.chain.continueLater', { previous }) });
	assert.deepEqual(chained({ mode: 'Ref2VA', by: 'frame' }), { state: 'references', extends: false, tokens: null, text: t('storyboard.chain.references', { previous }) });
	assert.notEqual(t('storyboard.chain.extendLater', { previous }), t('storyboard.chain.later', { previous }));
});

test('a core MiniMax-H3 preset keeps the last frame in FL2VA although its own extend mode is listed', () => {
	const previous = 'One';
	const last = { state: 'later', extends: false, tokens: null, text: t('storyboard.chain.later', { previous }) };
	assert.deepEqual(chained({ mode: 'FL2VA', preset: '01KX47H3MINIMAX000000000VA', modes: ['video', 'refs', 'upscale', 'refine_faces', 'extend', 'remix', 'talk', 'long'] }), last);
	assert.deepEqual(chained({ mode: 'FL2VA', preset: '01KX47H3FASTH30000000000VA', modes: ['video', 'refine_faces', 'extend'] }), last);
	assert.equal(chained({ mode: 'FL2VA' }).state, 'continueLater');
});

test('a Hybrid AV shot keeps the last frame on the 12 GB presets, whose continuation runs in FL2VA only', () => {
	const previous = 'One';
	const last = { state: 'later', extends: false, tokens: null, text: t('storyboard.chain.later', { previous }) };
	assert.deepEqual(chained({ mode: 'Hybrid AV', profiles: ['FL2VA', 'Ref2VA', 'Hybrid AV'] }), last);
	assert.deepEqual(chained({ mode: 'Hybrid AV', preset: FAST_12GB, modes: ['video', 'extend'], profiles: ['FL2VA', 'Hybrid AV'] }), last);
	assert.equal(chained({ mode: 'FL2VA', preset: FAST_12GB, modes: ['video', 'extend'], profiles: ['FL2VA', 'Hybrid AV'] }).state, 'continueLater');
});

test('a chained shot in a profile its engine cannot run says the shot will be blocked, as the server does', () => {
	const blocked = chained({ mode: 'Ref2VA', preset: FAST_12GB, modes: ['video', 'extend'], profiles: ['FL2VA', 'Hybrid AV'] });
	assert.deepEqual(blocked, { state: 'profileUnsupported', extends: false, tokens: null, text: t('modals.shot.profileUnsupported', { profile: 'Ref2VA' }) });
	assert.equal(chained({ mode: 'Ref2VA', preset: FAST_12GB, by: 'frame', modes: ['video', 'extend'], profiles: ['FL2VA', 'Hybrid AV'] }).state, 'profileUnsupported');
	assert.equal(chained({ mode: 'Ref2VA' }).state, 'continueLater');
	const waiting = { id: 'w2', shotId: 's2', status: 'queued', variant: 'A', chain: { previous: 's1', state: 'waiting', after: null, video: { frames: 56 } } };
	assert.equal(chained({ mode: 'Ref2VA', preset: FAST_12GB, modes: ['video', 'extend'], profiles: ['FL2VA', 'Hybrid AV'], takes: [waiting] }).state, 'waiting');
});

test('a shot chained by continuation in FL2VA keeps the last frame for the reasons the server falls back on, and says which', () => {
	const previous = 'One';
	const seconds = secs(56 / 24);
	assert.deepEqual(chained({ mode: 'FL2VA', first: { dur: 2 } }), { state: 'continueShort', extends: true, tokens: null, text: t('storyboard.chain.extendShort', { previous, seconds }) });
	assert.deepEqual(chained({ mode: 'FL2VA', second: { keepFraming: true } }), { state: 'continueOwnLast', extends: true, tokens: null, text: t('storyboard.chain.extendOwnLast', { previous }) });
	assert.deepEqual(chained({ mode: 'FL2VA', second: { dur: 14 } }), { state: 'continueLong', extends: true, tokens: null, text: t('storyboard.chain.extendLong', { previous, seconds: secs(328 / 24) }) });
	assert.equal(chained({ mode: 'FL2VA', second: { dur: 13.6 } }).state, 'continueLater');
	assert.deepEqual(chained({ mode: 'Ref2VA', first: { dur: 2 } }), { state: 'continueShort', extends: false, tokens: null, text: t('storyboard.chain.continueShort', { previous, seconds }) });
});

test('on the 12 GB preset a Ref2VA shot says the end of the previous take is left out where the encoder guard of the server leaves it out', () => {
	assert.equal(chained({ mode: 'Ref2VA', size: '832x480', pictures: [FACE, QUAY] }).state, 'continueLater');
	const refused = chained({ mode: 'Ref2VA', size: '960x544', pictures: [FACE, QUAY] });
	assert.equal(refused.state, 'continueEncoder');
	assert.equal(refused.tokens, 2507);
	assert.ok(refused.text.includes('2,507') && refused.text.includes('2,200'), refused.text);
	assert.equal(refused.text.split('{').length, 1);
	const third = chained({ mode: 'Ref2VA', size: '832x480', pictures: [FACE, QUAY, BOOTS] });
	assert.deepEqual([third.state, third.tokens], ['continueEncoder', 2256]);
	assert.equal(chained({ mode: 'FL2VA', size: '960x544', pictures: [FACE, QUAY] }).state, 'continueLater');
});

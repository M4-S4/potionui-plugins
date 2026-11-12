import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import './svelte-harness.js';
import { normalizeChain, placesTakeFrame, seamChain } from './chain.js';
import { failureFixes } from './director.js';

globalThis.Image = class {
	set src(value) {}
};

const { dispose } = await import('./state.svelte.js');
const { waitText, chainStatusText } = await import('./chain.svelte.js');
const { noteText } = await import('./production.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

after(() => dispose());

function sampleDoc() {
	return {
		fps: 25,
		clips: [
			{ id: 's1', assetId: null, take: null, start: 0, dur: 4, srcIn: 0, stage: 'todo', label: 'One' },
			{ id: 's2', assetId: null, take: null, start: 4, dur: 4, srcIn: 0, stage: 'todo', label: 'Two' }
		],
		frames: [],
		assets: [
			{ id: 'gen-t1', kind: 'video', name: 'Take 1', src: '/api/media/generations/g1/h3.mp4', origin: { kind: 'history', generationId: 'g1', fileId: 'f1' }, srcDur: 4, fps: 24, generated: true, resultId: 't1' },
			{ id: 'pic', kind: 'image', name: 'Still', src: '/api/media/uploads/still.png', origin: { kind: 'library', itemId: 'u3' }, generated: false }
		]
	};
}

const VIDEO = { previous: 's1', frames: 56, seconds: 2.333333, size: [832, 480], sound: false, value: 'uploads/end.mp4', filename: 'end.mp4' };

test('seamChain: in Ref2VA a chained shot continues the end of the previous take, later, or not after a still', () => {
	const doc = sampleDoc();
	assert.equal(seamChain(doc, 1, [], false, true).state, 'continueLater');
	assert.equal(seamChain(doc, 1, [], true, true).state, 'continueLater');
	Object.assign(doc.clips[0], { assetId: 'gen-t1', take: 't1', stage: 'draft' });
	assert.equal(seamChain(doc, 1, [], false, true).state, 'continues');
	assert.equal(seamChain(doc, 1).state, 'ready');
	Object.assign(doc.clips[0], { assetId: 'pic', take: null, stage: 'source' });
	assert.equal(seamChain(doc, 1, [], false, true).state, 'continueStill');
	doc.clips[1].firstFromPrevious = false;
	assert.equal(seamChain(doc, 1, [], false, true).state, 'off');
});

test('chainStatusText says what a Ref2VA shot sends of the previous shot', () => {
	const doc = sampleDoc();
	const from = doc.clips[0];
	assert.equal(chainStatusText({ state: 'continues', from }), t('storyboard.chain.continues', { previous: 'One' }));
	assert.equal(chainStatusText({ state: 'continueStill', from }), t('storyboard.chain.continueStill', { previous: 'One' }));
	assert.equal(chainStatusText({ state: 'continueLater', from }), t('storyboard.chain.continueLater', { previous: 'One' }));
});

test('a take that continues the previous take keeps its video, waits for its end and never places a first frame', () => {
	const doc = sampleDoc();
	const chain = normalizeChain({ previous: 's1', after: null, state: 'taken', batch: 'b1', source: { shotId: 's1', takeId: 't1', assetId: 'gen-t1', at: 4 }, frame: null, video: VIDEO });
	assert.deepEqual(chain.video, { frames: 56, seconds: 2.333333, value: 'uploads/end.mp4' });
	assert.equal('video' in normalizeChain({ previous: 's1', state: 'waiting' }), false);
	const take = { id: 'w', shotId: 's2', status: 'running', variant: 'A', chain };
	assert.equal(placesTakeFrame(doc, take, [take]), false);
	assert.equal(placesTakeFrame(doc, { ...take, chain: { ...chain, video: null } }, [take]), true);
	const waiting = { id: 'w2', shotId: 's2', status: 'queued', variant: 'A', chain: { ...chain, state: 'waiting', video: { frames: 56 } } };
	assert.match(waitText(waiting), /“/);
	assert.equal(waitText(waiting), t('lib.chain.waitEnd', { shot: '—' }));
	assert.deepEqual(failureFixes({ errorCode: 'chain_video_failed' }), ['previous', 'retry']);
});

test('the estimate says why a Ref2VA shot does not continue the previous take', () => {
	for (const [code, key] of [
		['chain_video_own', 'generation.warn.chainVideoOwn'],
		['chain_video_none', 'generation.warn.chainVideoNone'],
		['chain_video_still', 'generation.warn.chainVideoStill'],
		['chain_video_short', 'generation.warn.chainVideoShort'],
		['chain_video_trimmed', 'generation.warn.chainVideoTrimmed'],
		['chain_video_rows', 'generation.warn.chainVideoRows'],
		['chain_video_encoder', 'generation.warn.chainVideoEncoder']
	]) {
		const text = noteText({ code, message: 'server text', data: { shot_id: 's2', previous: 's1', slot: 1, rows: 30000, tokens: 2507, limit: 28000 } });
		assert.notEqual(text, 'server text', code);
		assert.equal(text.split('{').length, 1, code);
		assert.ok(t(key).length > 0 && text.length > 20, code);
	}
	assert.ok(noteText({ code: 'chain_video_encoder', message: 'server text', data: { shot_id: 's2', tokens: 2507, limit: 2200 } }).includes('2,507'));
});

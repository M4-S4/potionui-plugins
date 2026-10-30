import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { hostUis, renderComponent } from './svelte-harness.js';
import { migrate, newAsset } from './starter.js';
import { releaseOverrun } from './shots.js';
import { USE_KINDS, assetUses, removeAsset } from './usage.js';

const { doc, ui, dispose } = await import('./state.svelte.js');
const { deleteAsset } = await import('./assets.svelte.js');
const { t } = await import('../i18n/index.svelte.js');
const MEDIA_BROWSER = new URL('../components/panels/MediaBrowser.svelte', import.meta.url).href;
const USE_KEYS = { shots: 'lib.media.use.shots', sounds: 'lib.media.use.sounds', vrefs: 'lib.media.use.vrefs', references: 'lib.media.use.references', edges: 'lib.media.use.edges', frames: 'lib.media.use.frames' };

after(() => dispose());
const ids = (list) => list.map((item) => item.id);
const unused = Object.fromEntries(USE_KINDS.map((kind) => [kind, []]));

function makeDoc() {
	const shared = newAsset({ id: 'pic', kind: 'image', name: 'Port' });
	const other = newAsset({ id: 'other', kind: 'image', name: 'Gull' });
	return {
		assets: [shared, other],
		clips: [
			{ id: 's1', assetId: 'pic', take: 't1', srcIn: 1.2, start: 0, dur: 4, stage: 'final', label: 'Harbour' },
			{ id: 's2', assetId: 'other', take: null, srcIn: 0, start: 4, dur: 4, stage: 'source', label: 'Gulls' }
		],
		audio: [
			{ id: 'a1', assetId: 'pic', lane: 'A1', start: 0, dur: 3, srcIn: 0 },
			{ id: 'a2', assetId: 'other', lane: 'A1', start: 3, dur: 3, srcIn: 0 }
		],
		references: [
			{ id: 'r1', name: 'Fisherman', space: 'identite', type: 'Personnage', assetId: 'pic', role: 'Identité', scope: { type: 'global' } },
			{ id: 'r2', name: 'Set', space: 'decors3d', type: 'Capture 3D', assetId: 'pic', role: '', scope: { type: 'shot', shotId: 's1' } },
			{ id: 'r3', name: 'Gull', space: 'identite', type: 'Objet', assetId: 'other', role: 'Identité', scope: { type: 'global' } }
		],
		frames: [
			{ id: 'f1', shotId: 's1', time: 0, assetId: 'pic', role: 'first', strength: 100 },
			{ id: 'f2', shotId: 's1', time: 4, assetId: 'pic', role: 'fin', strength: 100 },
			{ id: 'f3', shotId: 's2', time: 5, assetId: 'pic', role: 'Transition', strength: 75 },
			{ id: 'f4', shotId: 's2', time: 6, assetId: 'pic', role: 'Capture 3D', strength: 75 },
			{ id: 'f5', shotId: 's2', time: 4, assetId: 'other', role: 'début', strength: 100 }
		],
		prompts: [{ id: 'p-s1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'Dawn over the harbour' }]
	};
}

test('assetUses: every place that holds a media, first and last images apart from the other frames', () => {
	const uses = assetUses(makeDoc(), 'pic');
	assert.deepEqual(Object.keys(uses), USE_KINDS);
	assert.deepEqual(ids(uses.shots), ['s1']);
	assert.deepEqual(ids(uses.sounds), ['a1']);
	assert.deepEqual(ids(uses.references), ['r1', 'r2']);
	assert.deepEqual(ids(uses.edges), ['f1', 'f2']);
	assert.deepEqual(ids(uses.frames), ['f3', 'f4']);
	assert.deepEqual(assetUses(makeDoc(), 'missing'), unused);
	assert.deepEqual(assetUses({ assets: [] }, 'pic'), unused);
});

test('removeAsset: the shots and references that held the media stay, emptied; the sounds and frames that placed it go', () => {
	const doc = makeDoc();
	const result = removeAsset(doc, 'pic');
	assert.equal(result.asset.id, 'pic');
	assert.deepEqual(result.released, [{ take: 't1' }]);
	assert.deepEqual(ids(doc.assets), ['other']);
	assert.deepEqual(doc.clips[0], { id: 's1', assetId: null, take: null, srcIn: 0, start: 0, dur: 4, stage: 'todo', label: 'Harbour' });
	assert.equal(doc.clips[1].assetId, 'other');
	assert.deepEqual(doc.prompts[0].text, 'Dawn over the harbour');
	assert.deepEqual(ids(doc.audio), ['a2']);
	assert.deepEqual(
		doc.references.map((r) => [r.id, r.assetId]),
		[
			['r1', null],
			['r2', null],
			['r3', 'other']
		]
	);
	assert.deepEqual(ids(doc.frames), ['f5']);
	assert.deepEqual(assetUses(doc, 'pic'), unused);
});

test('removeAsset: an unused media leaves alone, an unknown one changes nothing', () => {
	const doc = makeDoc();
	doc.clips[1].assetId = null;
	doc.audio.pop();
	doc.references.pop();
	doc.frames.pop();
	const before = JSON.stringify(doc);
	assert.equal(removeAsset(doc, 'missing'), null);
	assert.equal(JSON.stringify(doc), before);
	const result = removeAsset(doc, 'other');
	assert.deepEqual(result.uses, unused);
	assert.deepEqual(result.released, []);
	assert.deepEqual(ids(doc.assets), ['pic']);
});

test('removeAsset: what stays emptied survives the document migration, nothing is dropped behind the user', () => {
	const doc = makeDoc();
	removeAsset(doc, 'pic');
	const next = migrate(doc);
	assert.deepEqual(ids(next.references), ['r1', 'r2', 'r3']);
	assert.deepEqual(ids(next.frames), ['f5']);
	assert.equal(next.clips[0].stage, 'todo');
});

test('a released shot looks the same whether its take was overrun or its media removed', () => {
	const doc = makeDoc();
	const overrun = { ...doc.clips[0], assetId: 'gen-t1', dur: 8 };
	doc.assets.push(newAsset({ id: 'gen-t1', kind: 'video', generated: true, resultId: 't1', srcDur: 4 }));
	doc.clips[0] = overrun;
	assert.deepEqual(releaseOverrun(doc, overrun, 4), { take: 't1' });
	const removed = makeDoc();
	removeAsset(removed, 'pic');
	const shape = (clip) => ({ assetId: clip.assetId, take: clip.take, srcIn: clip.srcIn, stage: clip.stage });
	assert.deepEqual(shape(overrun), shape(removed.clips[0]));
});

test('the media browser removes a media after a confirmation that lists its uses, in one undoable step', async () => {
	Object.assign(doc, makeDoc());
	Object.assign(ui, { mediaCollection: 'all', mediaQuery: '', preview: null, selection: null });
	const browser = await renderComponent(MEDIA_BROWSER);
	const trash = hostUis(browser, 'IconButton').filter((props) => props.icon === 'trash');
	assert.deepEqual(trash.map((props) => props.label), doc.assets.map((a) => t('panels.media.deleteNamed', { name: a.name })));
	assert.ok(trash.every((props) => props.tooltip === t('panels.media.deleteTip')));
	const asked = [];
	window.__potionui.confirm = async (options) => {
		asked.push(options);
		return asked.length > 1;
	};
	assert.equal(await deleteAsset('pic'), false);
	assert.ok(doc.assets.some((a) => a.id === 'pic'));
	ui.toasts.length = 0;
	assert.equal(await deleteAsset('pic'), true);
	assert.equal(asked.length, 2);
	assert.equal(asked[1].title, t('lib.media.deleteTitle', { name: 'Port' }));
	assert.deepEqual([asked[1].variant, asked[1].confirmLabel, asked[1].cancelLabel], ['danger', t('lib.media.deleteConfirm'), t('lib.cancel')]);
	const uses = assetUses(makeDoc(), 'pic');
	for (const kind of USE_KINDS) if (uses[kind].length) assert.ok(asked[1].message.includes(t(USE_KEYS[kind], { count: uses[kind].length })), kind);
	assert.equal(doc.assets.some((a) => a.id === 'pic'), false);
	const toast = ui.toasts.at(-1);
	assert.deepEqual([toast.message, toast.level, toast.action.label], [t('lib.toast.mediaRemoved', { name: 'Port' }), 'info', t('shell.toast.undo')]);
	toast.action.run();
	assert.ok(doc.assets.some((a) => a.id === 'pic'));
	window.__potionui.confirm = async () => true;
});

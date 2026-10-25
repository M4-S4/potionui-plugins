import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { migrate, newAsset } from './starter.js';
import { releaseOverrun } from './shots.js';
import { USE_KINDS, assetUses, removeAsset, useCount } from './usage.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const ids = (list) => list.map((item) => item.id);

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
			{ id: 'f4', shotId: 's2', time: 6, assetId: 'pic', role: 'Capture 3D', strength: 75, sceneId: 'sc1' },
			{ id: 'f5', shotId: 's2', time: 4, assetId: 'other', role: 'début', strength: 100 }
		],
		controls: [
			{ id: 'c1', shotId: 's1', name: 'Guide 3D', start: 0, dur: 4, guidance: 65, source: 'scene3d', stale: false, planId: 'p1', assetId: 'pic' },
			{ id: 'c2', shotId: 's2', name: 'Control', start: 4, dur: 4, guidance: 65, source: 'import', stale: false, assetId: 'pic' },
			{ id: 'c3', shotId: 's2', name: 'Other', start: 4, dur: 4, guidance: 65, source: 'import', stale: false, assetId: 'other' }
		],
		scenes: [{ id: 'sc1', kind: 'splat', name: 'Harbour', sourceAssetId: 'pic', sourceTime: null, status: 'done', progress: 1, jobId: null, fileId: 'file', count: 10, view: null, error: null }],
		prompts: [{ id: 'p-s1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'Dawn over the harbour' }]
	};
}

test('assetUses: every place that holds a media, first and last images apart from the other frames; the Control videos of an older document are not counted', () => {
	const uses = assetUses(makeDoc(), 'pic');
	assert.deepEqual(Object.keys(uses), USE_KINDS);
	assert.deepEqual(ids(uses.shots), ['s1']);
	assert.deepEqual(ids(uses.sounds), ['a1']);
	assert.deepEqual(ids(uses.references), ['r1', 'r2']);
	assert.deepEqual(ids(uses.edges), ['f1', 'f2']);
	assert.deepEqual(ids(uses.frames), ['f3', 'f4']);
	assert.deepEqual(ids(uses.scenes), ['sc1']);
	assert.equal(useCount(uses), 9);
	assert.equal(useCount(assetUses(makeDoc(), 'missing')), 0);
	assert.equal(useCount(assetUses({ assets: [] }, 'pic')), 0);
});

test('removeAsset: the shots, references and scenes that held the media stay, emptied; the sounds and frames that placed it go; the Control videos of an older document stay as they are', () => {
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
	assert.deepEqual(doc.controls, makeDoc().controls);
	assert.equal(doc.scenes[0].sourceAssetId, null);
	assert.equal(useCount(assetUses(doc, 'pic')), 0);
});

test('removeAsset: an unused media leaves alone, an unknown one changes nothing', () => {
	const doc = makeDoc();
	doc.clips[1].assetId = null;
	doc.audio.pop();
	doc.references.pop();
	doc.frames.pop();
	doc.controls.pop();
	const before = JSON.stringify(doc);
	assert.equal(removeAsset(doc, 'missing'), null);
	assert.equal(JSON.stringify(doc), before);
	const result = removeAsset(doc, 'other');
	assert.equal(useCount(result.uses), 0);
	assert.deepEqual(result.released, []);
	assert.deepEqual(ids(doc.assets), ['pic']);
});

test('removeAsset: what stays emptied survives the document migration, nothing is dropped behind the user', () => {
	const doc = makeDoc();
	removeAsset(doc, 'pic');
	const next = migrate(doc);
	assert.deepEqual(ids(next.references), ['r1', 'r2', 'r3']);
	assert.deepEqual(ids(next.controls), ['c1', 'c2', 'c3']);
	assert.deepEqual(ids(next.scenes), ['sc1']);
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

test('the media browser removes a media after a confirmation that lists its uses, in one undoable step, without a server call', () => {
	const browser = source('../components/panels/MediaBrowser.svelte');
	assert.match(browser, /import \{ deleteAsset \} from '\.\.\/\.\.\/lib\/assets\.svelte\.js';/);
	assert.match(browser, /icon: 'trash', label: t\('panels\.media\.deleteNamed', \{ name: a\.name \}\), size: 'xs', tooltip: t\('panels\.media\.deleteTip'\), onclick: \(e\) => \(e\.stopPropagation\(\), deleteAsset\(a\.id\)\)/);
	assert.match(browser, /icon: 'trash', label: t\('panels\.media\.delete'\), size: 'xs', tooltip: t\('panels\.media\.deleteTip'\), onclick: \(\) => deleteAsset\(cur\.id\)/);
	const assets = source('./assets.svelte.js');
	assert.match(assets, /await confirm\(\{ title: t\('lib\.media\.deleteTitle', \{ name \}\), message: deleteText\(a, assetUses\(doc, id\)\), variant: 'danger', confirmLabel: t\('lib\.media\.deleteConfirm'\) \}\)/);
	assert.match(assets, /act\(\(\) => \(removed = removeAsset\(doc, id\)\)\);/);
	assert.match(assets, /for \(const released of removed\.released\) releaseTake\(released\);/);
	assert.match(assets, /toast\(t\('lib\.toast\.mediaRemoved', \{ name \}\), 'info', \{ label: t\('shell\.toast\.undo'\), run: undo \}\);/);
	assert.doesNotMatch(assets, /getClient|fetch\(/);
	for (const kind of USE_KINDS) assert.match(assets, new RegExp(`t\\('lib\\.media\\.use\\.${kind}', \\{ count \\}\\)`), kind);
	const production = source('./production.svelte.js');
	assert.match(production, /export function releaseTake\(released\) \{/);
	assert.match(production, /\treleaseTake\(released\);\n\ttoast\(t\('lib\.toast\.takeReleased'/);
});

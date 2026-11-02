import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

const hooks = `
import { readFile } from 'node:fs/promises';
import { compileModule } from ${JSON.stringify(import.meta.resolve('svelte/compiler'))};
export async function load(url, context, next) {
	if (url.endsWith('.svelte.js')) return { format: 'module', shortCircuit: true, source: compileModule(await readFile(new URL(url), 'utf8'), { generate: 'client', filename: url }).js.code };
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

const { doc, ui, replaceDoc, dispose } = await import('./state.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { showShot, previewTake } = await import('./monitor.svelte.js');
const { emptyDoc, newAsset, newClip } = await import('./starter.js');

globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast() {} } } };

after(() => {
	dispose();
	delete globalThis.window;
});

const take = (id, shotId) => ({ id, projectId: null, shotId, kind: 'render', quality: 'draft', status: 'done', variant: 'A', label: 'draft', url: `/media/${id}.mp4`, thumbUrl: null, durationS: 4 });

function project(extra = {}) {
	replaceDoc({
		...emptyDoc((key) => key),
		assets: [newAsset({ id: 'gen-t1', src: '/media/t1.mp4', generated: true, resultId: 't1' }), newAsset({ id: 'gen-t2', src: '/media/t2.mp4', generated: true, resultId: 't2' }), newAsset({ id: 'a3', src: '/media/a3.mp4' })],
		clips: [newClip({ id: 's1', start: 0, dur: 4, take: 't1', assetId: 'gen-t1' }), newClip({ id: 's2', start: 4, dur: 4, take: 't2', assetId: 'gen-t2' }), newClip({ id: 's3', start: 8, dur: 4, assetId: 'a3' })]
	});
	setTakes(null, [take('t1', 's1'), take('t1b', 's1'), take('t2', 's2')]);
	Object.assign(ui, { workspace: 'director', directorView: null, storyView: 'band', playhead: 1, selection: null, preview: null, compare: null, seamCompare: null, reviewMonitor: false, ...extra });
}

const shotOf = (id) => doc.clips.find((c) => c.id === id);
const inside = (id) => {
	const c = shotOf(id);
	return ui.playhead >= c.start && ui.playhead < c.start + c.dur;
};

test('monitor flow: a shot the playhead is not on comes under the playhead and becomes the selected shot', () => {
	project();
	showShot(shotOf('s2'));
	assert.ok(inside('s2'), `playhead at ${ui.playhead}`);
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's2' });
});

test('monitor flow: a shot already under the playhead keeps the playhead where it is', () => {
	project({ playhead: 6.5, selection: { kind: 'clip', id: 's2' } });
	showShot(shotOf('s2'));
	assert.equal(ui.playhead, 6.5);
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's2' });
});

test('monitor flow: the preview of the take placed on the shot stays, a take that is not placed and the take of another shot close', () => {
	project({ preview: { kind: 'result', id: 't2' } });
	showShot(shotOf('s2'));
	assert.deepEqual({ ...ui.preview }, { kind: 'result', id: 't2' });
	assert.ok(inside('s2'));

	project({ preview: { kind: 'result', id: 't1b' } });
	showShot(shotOf('s1'));
	assert.equal(ui.preview, null);
	assert.equal(ui.playhead, 1);

	project({ preview: { kind: 'result', id: 't1' } });
	showShot(shotOf('s2'));
	assert.equal(ui.preview, null);
	assert.ok(inside('s2'));
});

test('monitor flow: a comparison stays while one of its takes is placed on the shot, and closes otherwise', () => {
	project({ compare: ['t1', 't1b'] });
	showShot(shotOf('s1'));
	assert.deepEqual([...ui.compare], ['t1', 't1b']);

	showShot(shotOf('s2'));
	assert.equal(ui.compare, null);
	assert.ok(inside('s2'));
});

test('monitor flow: a source media in the viewer gives way to the sequence, even the media of the shot', () => {
	project({ preview: { kind: 'asset', id: 'a3' } });
	showShot(shotOf('s3'));
	assert.equal(ui.preview, null);
	assert.ok(inside('s3'));
});

test('monitor flow: the seam of the band stays open for both its shots, with its shot chosen and the playhead where it is, and closes for another', () => {
	project({ workspace: 'storyboard', selection: { kind: 'clip', id: 's2' }, seamCompare: 's2', playhead: 4.01 });
	showShot(shotOf('s2'));
	assert.equal(ui.seamCompare, 's2');

	showShot(shotOf('s1'));
	assert.equal(ui.seamCompare, 's2');
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's2' });
	assert.equal(ui.playhead, 4.01);

	showShot(shotOf('s3'));
	assert.equal(ui.seamCompare, null);
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's3' });
	assert.ok(inside('s3'));
});

test('monitor flow: a seam left open outside the band closes when the shot before it is graded', () => {
	project({ workspace: 'director', selection: { kind: 'clip', id: 's2' }, seamCompare: 's2', playhead: 4.01 });
	showShot(shotOf('s1'));
	assert.equal(ui.seamCompare, null);
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's1' });
	assert.ok(inside('s1'));
});

test('monitor flow: opening a take chooses its shot, brings the playhead onto it only from elsewhere, and leaves the preview open', () => {
	project({ selection: { kind: 'clip', id: 's1' }, compare: ['t1', 't2'], seamCompare: 's2' });
	previewTake(take('t2', 's2'));
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's2' });
	assert.ok(inside('s2'));
	assert.deepEqual({ ...ui.preview }, { kind: 'result', id: 't2' });
	assert.equal(ui.compare, null);
	assert.equal(ui.seamCompare, null);

	project({ playhead: 2.5 });
	previewTake(take('t1b', 's1'));
	assert.equal(ui.playhead, 2.5);
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's1' });
	assert.deepEqual({ ...ui.preview }, { kind: 'result', id: 't1b' });

	project();
	previewTake({ ...take('t9', 's1'), status: 'running', url: null });
	previewTake(null);
	assert.equal(ui.preview, null);
	assert.equal(ui.selection, null);
});

test('monitor flow: in the Review, grading the shot of the placed take keeps its preview, grading after another take closes it and keeps the monitor open on the cut', () => {
	project({ directorView: 'review', playhead: 9 });
	previewTake(take('t1', 's1'));
	showShot(shotOf('s1'));
	assert.deepEqual({ ...ui.preview }, { kind: 'result', id: 't1' });
	assert.equal(ui.reviewMonitor, true);

	project({ directorView: 'review', playhead: 9 });
	previewTake(take('t1b', 's1'));
	assert.ok(inside('s1'));
	showShot(shotOf('s1'));
	assert.equal(ui.preview, null);
	assert.equal(ui.reviewMonitor, true);
	assert.ok(inside('s1'));
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's1' });
});

test('monitor flow: outside the Review, a grade leaves the monitor of the Review closed', () => {
	project({ directorView: 'direction' });
	showShot(shotOf('s2'));
	assert.equal(ui.reviewMonitor, false);

	project({ workspace: 'storyboard', directorView: 'review' });
	showShot(shotOf('s2'));
	assert.equal(ui.reviewMonitor, false);
});

test('monitor flow: a shot that left the project changes nothing', () => {
	project({ preview: { kind: 'result', id: 't1b' } });
	showShot({ id: 'gone' });
	showShot(null);
	assert.deepEqual({ ...ui.preview }, { kind: 'result', id: 't1b' });
	assert.equal(ui.playhead, 1);
	assert.equal(ui.selection, null);
});

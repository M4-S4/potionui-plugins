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

globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast() {} } } };
globalThis.document = { body: {}, querySelector: () => null };

const { doc, ui, replaceDoc, select, openDirector, directorShot, productionRange, allIssues, followIssue, followedIssue, issueRule, witness, dispose } = await import('./state.svelte.js');
const { jobClips, readiness } = await import('./production.svelte.js');
const { showInReview } = await import('./band.svelte.js');
const { emptyDoc, newAsset, newClip } = await import('./starter.js');
const { t } = await import('../i18n/index.svelte.js');

after(() => {
	dispose();
	delete globalThis.window;
	delete globalThis.document;
});

function project(extra = {}) {
	const base = emptyDoc((key) => key);
	replaceDoc({
		...base,
		promptLanguage: 'en',
		direction: { ...base.direction, photographie: 'Steady camera. Soft light from the harbour.' },
		assets: [newAsset({ id: 'snd', kind: 'audio', name: 'theme.wav', src: '/media/theme.wav', srcDur: 12 })],
		clips: [newClip({ id: 's1', start: 0, dur: 4 }), newClip({ id: 's2', start: 4, dur: 4 }), newClip({ id: 's3', start: 8, dur: 4 })],
		prompts: [{ id: 'p2', shotId: 's2', start: 4, dur: 4, strength: 75, text: 'Lina runs on the pier. Handheld camera, rain.' }],
		audio: [{ id: 'a1', assetId: 'snd', lane: base.lanes[0].id, start: 0, dur: 12, srcIn: 0, gain: 0, fadeIn: 0, fadeOut: 0 }]
	});
	Object.assign(ui, { workspace: 'media', directorView: null, reviewFilter: null, witness: null, playhead: 9, production: { ...ui.production, target: 'clip' }, ...extra });
}

const shotOf = (id) => doc.clips.find((c) => c.id === id);

test('director flow: a sound chosen in Media stays chosen, Director AI shows no shot for it, and the Plan target aims at nothing instead of the hidden playhead', () => {
	project();
	select('audio', 'a1');
	assert.equal(ui.selectedIn, 'media');
	openDirector('review');
	assert.deepEqual({ ...ui.selection }, { kind: 'audio', id: 'a1' });
	assert.equal(directorShot(), null);
	assert.deepEqual(productionRange(), [0, 0]);
	assert.deepEqual(jobClips(), []);
	assert.ok(readiness().missing.includes(t('lib.block.noShot')));
	ui.workspace = 'media';
	assert.equal(directorShot(), undefined);
	assert.deepEqual(productionRange(), [8, 12]);
});

test('director flow: in Review and References the chosen shot is the target, wherever the playhead is', () => {
	project({ playhead: 1 });
	openDirector('review');
	select('clip', 's3');
	assert.equal(ui.selectedIn, 'director:review');
	assert.equal(directorShot(), shotOf('s3'));
	assert.deepEqual(jobClips(), [shotOf('s3')]);
	assert.deepEqual(productionRange(), [8, 12]);
	ui.directorView = 'references';
	assert.equal(directorShot(), shotOf('s3'));
	ui.directorView = 'bible';
	assert.equal(directorShot(), null);
	ui.production.target = 'sequence';
	assert.equal(jobClips().length, 3);
});

test('director flow: in Direction the target is the sample shot, which follows the chosen shot until it is pinned', () => {
	project();
	openDirector('direction');
	assert.deepEqual({ clip: witness().clip.id, source: witness().source }, { clip: 's2', source: 'first' });
	select('clip', 's3');
	assert.equal(witness().source, 'selection');
	assert.equal(directorShot(), shotOf('s3'));
	ui.witness = 's1';
	select('clip', 's2');
	assert.equal(witness().source, 'pinned');
	assert.deepEqual(jobClips(), [shotOf('s1')]);
});

test('director flow: following a contradiction makes its shot the sample, keeps the prompt unselected and finds both sentences', () => {
	project({ witness: 's1' });
	select('audio', 'a1');
	const issue = allIssues().find((i) => i.level === 'conflict');
	assert.equal(issue.id, 'stableCamera');
	followIssue(issue);
	assert.equal(ui.workspace, 'director');
	assert.equal(ui.directorView, 'direction');
	assert.equal(ui.witness, null);
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's2' });
	assert.deepEqual({ ...ui.issue }, { prompt: 'p2', rule: 'stableCamera' });
	assert.equal(witness().clip, shotOf('s2'));
	assert.equal(followedIssue(shotOf('s2'))?.prompt.id, 'p2');
	assert.equal(followedIssue(shotOf('s1')), null);
	const rule = issueRule(issue.id);
	assert.ok(rule.global.test('Steady camera.') && rule.local.test('Handheld camera, rain.'));
	doc.prompts[0].text = 'Lina runs on the pier.';
	assert.equal(followedIssue(shotOf('s2')), null);
});

test('director flow: a shot chip opens the Review on that shot, shows every shot when the filter hid it, and asks the row to come on screen', () => {
	project({ reviewFilter: 'final', workspace: 'director', directorView: 'bible' });
	showInReview(shotOf('s3'));
	assert.equal(ui.directorView, 'review');
	assert.equal(ui.reviewFilter, 'all');
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's3' });
	assert.equal(ui.reveal, 's3');
	assert.ok(ui.playhead >= 8 && ui.playhead < 12);
});

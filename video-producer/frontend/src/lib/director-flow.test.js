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

const { doc, ui, replaceDoc, select, bladeAt, duplicateSelection, openDirector, directorShot, productionRange, allIssues, followIssue, followedIssue, issueRule, witness, reviewPick, dispose } = await import('./state.svelte.js');
const { jobClips, readiness } = await import('./production.svelte.js');
const { showInReview, chooseTake, chooseSeam } = await import('./band.svelte.js');
const { setTakes, takeStore } = await import('./takes.svelte.js');
const { reception, setReferenceShot, setSent, addShotReference, linkReferenceCard, startImage } = await import('./references.js');
const { emptyDoc, newAsset, newClip } = await import('./starter.js');
const { t } = await import('../i18n/index.svelte.js');
const { castIssues, identityIssues, issueKey, normalizeLooks, pushInIssues } = await import('./looks.js');

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

const done = (id, shotId, fields = {}) => ({ id, projectId: null, shotId, kind: 'render', quality: 'draft', status: 'done', variant: id.slice(-1).toUpperCase(), label: 'draft', url: `/media/${id}.mp4`, thumbUrl: null, durationS: 4, createdAt: `2026-10-27T10:0${id.length}:00Z`, ...fields });

function review(extra = {}) {
	project({ workspace: 'director', directorView: 'review', reviewFilter: 'all', preview: null, compare: null, reviewMonitor: false, ...extra });
	setTakes(null, [done('t2a', 's2'), done('t2b', 's2', { label: 'final' }), done('t3a', 's3', { status: 'failed', url: null, errorCode: 'cuda_oom' }), done('t3b', 's3', { status: 'running', url: null })]);
}

test('director flow: in the Review a card chooses its take, opens it in the monitor and the panel follows it; a running take leaves the shot chosen', () => {
	review({ playhead: 1 });
	chooseTake(takeStore.list[0]);
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's2' });
	assert.deepEqual({ ...ui.reviewPick }, { kind: 'take', id: 't2a' });
	assert.deepEqual({ ...ui.preview }, { kind: 'result', id: 't2a' });
	assert.ok(ui.playhead >= 4 && ui.playhead < 8);
	assert.deepEqual({ kind: reviewPick().kind, take: reviewPick().take.id }, { kind: 'take', take: 't2a' });
	assert.equal(directorShot(), shotOf('s2'));
	chooseTake(takeStore.list[2]);
	assert.deepEqual({ kind: reviewPick().kind, take: reviewPick().take.id }, { kind: 'failed', take: 't3a' });
	assert.equal(ui.preview, null);
	chooseTake(takeStore.list[3]);
	assert.deepEqual({ ...ui.reviewPick }, { kind: 'shot', id: 's3' });
	assert.deepEqual({ kind: reviewPick().kind, clip: reviewPick().clip.id }, { kind: 'shot', clip: 's3' });
});

test('director flow: a seam line chooses the seam and its arriving shot, and a plain selection or Escape drops the choice of the Review', () => {
	review();
	chooseSeam(shotOf('s1'));
	assert.equal(ui.reviewPick, null);
	chooseSeam(shotOf('s3'));
	assert.deepEqual({ ...ui.reviewPick }, { kind: 'seam', id: 's3' });
	assert.deepEqual({ kind: reviewPick().kind, clip: reviewPick().clip.id, previous: reviewPick().previous.id }, { kind: 'seam', clip: 's3', previous: 's2' });
	assert.equal(directorShot(), shotOf('s3'));
	select('clip', 's1');
	assert.equal(ui.reviewPick, null);
	assert.equal(reviewPick().kind, 'shot');
	chooseTake(takeStore.list[0]);
	select(null);
	assert.equal(ui.reviewPick, null);
	assert.equal(reviewPick(), null);
	chooseTake(takeStore.list[0]);
	replaceDoc({ ...emptyDoc((key) => key) });
	assert.equal(ui.reviewPick, null);
});

test('director flow: a sound chosen in Media leaves the panel of the Review empty, and following a contradiction asks its row to come on screen', () => {
	review();
	ui.workspace = 'media';
	select('audio', 'a1');
	openDirector('review');
	assert.equal(reviewPick(), null);
	assert.deepEqual({ ...ui.selection }, { kind: 'audio', id: 'a1' });
	followIssue(allIssues().find((i) => i.level === 'conflict'));
	assert.equal(ui.reveal, 's2');
	assert.deepEqual({ ...ui.selection }, { kind: 'clip', id: 's2' });
});

const reference = (id, extra = {}) => ({ id, name: id, space: 'identite', type: 'Personnage', assetId: null, role: 'Identité', scope: { type: 'global' }, ...extra });

test('director flow: in References a reference goes to the shot chosen in the panel, never to the one under the hidden playhead', () => {
	project({ playhead: 9 });
	doc.references = [reference('g1')];
	openDirector('references');
	select('reference', 'g1');
	setReferenceShot(doc.references[0], 's1');
	assert.deepEqual({ ...doc.references[0].scope }, { type: 'shot', shotId: 's1' });
	setReferenceShot(doc.references[0], null);
	assert.deepEqual({ ...doc.references[0].scope }, { type: 'global' });
	assert.deepEqual({ ...ui.selection }, { kind: 'reference', id: 'g1' });
});

test('director flow: a shot chosen in References sends or leaves out a project reference, which marks its takes, and a reference added there is its own', () => {
	project();
	doc.references = [reference('g1'), reference('g2')];
	openDirector('references');
	select('clip', 's2');
	setSent(shotOf('s2'), 'g1', false);
	assert.deepEqual([...shotOf('s2').referenceOverrides.exclude], ['g1']);
	assert.equal(shotOf('s2').revision, 1);
	setSent(shotOf('s2'), 'g1', false);
	assert.equal(shotOf('s2').revision, 1);
	setSent(shotOf('s2'), 'g1', true);
	assert.equal(shotOf('s2').referenceOverrides, undefined);
	assert.equal(shotOf('s2').revision, 2);
	const added = addShotReference(shotOf('s2'));
	assert.deepEqual({ ...added.scope }, { type: 'shot', shotId: 's2' });
	assert.deepEqual({ ...ui.selection }, { kind: 'reference', id: added.id });
	startImage(shotOf('s2'));
	assert.deepEqual({ ...ui.modal }, { type: 'shot', id: 's2', focus: 'keyframes' });
	ui.modal = null;
});

test('director flow: what a reference becomes follows the engine and the profile of each shot from the presets the page reads, and its card is linked from the panel', () => {
	project();
	const me = ui.me;
	const wan = '01KX47WANVIDEO0000000000TV';
	const h3 = '01KX47H3MINIMAX000000000VA';
	ui.me = {
		engines: [{ id: 'native', kind: 'local', name: 'Local' }],
		presets: [
			{ id: wan, name: 'Wan 2.1 / 2.2', video: true, cloud: false, audioMux: false, profiles: ['FL2VA'] },
			{ id: h3, name: 'MiniMax-H3', video: true, cloud: false, audioMux: true, profiles: ['FL2VA', 'Ref2VA', 'Hybrid AV'] }
		]
	};
	doc.engine.preset = wan;
	doc.engine.model = null;
	shotOf('s3').engine = { preset: h3, model: null, profile: 'Ref2VA' };
	shotOf('s2').referenceOverrides = { exclude: ['g1'] };
	doc.assets.push(newAsset({ id: 'img', kind: 'image', name: 'lina.jpg', src: '/media/lina.jpg', origin: { kind: 'library', itemId: 'lib-lina' } }));
	doc.references = [reference('g1', { assetId: 'img' })];
	const found = reception(doc.references[0]);
	assert.deepEqual(
		found.groups.map((g) => [g.engine?.preset ?? null, g.engine?.profile ?? null, g.status, g.shots.map((s) => s.clip.id)]),
		[
			[wan, 'FL2VA', 'ignored', ['s1']],
			[h3, 'Ref2VA', 'sent', ['s3']],
			[null, null, 'excluded', ['s2']]
		]
	);
	doc.bible = { characters: [{ id: 'lina', label: 'Lina', text: '', props: '', references: [] }, { id: 'malo', label: 'Malo', text: '', props: '', references: ['g1'] }], places: [] };
	linkReferenceCard(doc.references[0], 'characters', 'lina');
	assert.deepEqual(doc.bible.characters.map((c) => [...c.references]), [['g1'], []]);
	assert.equal(reception(doc.references[0]).linked.card.id, 'lina');
	linkReferenceCard(doc.references[0], 'characters', null);
	assert.deepEqual(doc.bible.characters.map((c) => [...c.references]), [[], []]);
	ui.me = me;
});

test('director flow: a cut or a copy of a shot whose take is flagged keeps one alert per shot in To check, each with its own key', () => {
	project();
	shotOf('s1').take = 't1';
	select('clip', 's1');
	bladeAt(2);
	duplicateSelection();
	const shared = doc.clips.filter((c) => c.take === 't1');
	assert.equal(shared.length, 3);
	const looks = normalizeLooks({
		thresholds: { cast: 0.6, push_in: 1.5, identity: 0.6 },
		takes: [{ take_id: 't1', shot_id: 's1', status: 'done', cards: [{ card_id: 'c1', label: 'Marin', score: 0.4, status: 'done' }, { card_id: 'c2', label: 'Lina', score: 0.3, status: 'done' }], push_in: 2.4, identity: { score: 0.3, at: 1 } }]
	});
	const lists = { cast: castIssues(looks, doc.clips), pushIn: pushInIssues(looks, doc.clips), identity: identityIssues(looks, doc.clips) };
	assert.deepEqual([lists.cast.length, lists.pushIn.length, lists.identity.length], [6, 3, 3]);
	assert.deepEqual(new Set(lists.pushIn.map((item) => item.takeId)), new Set(['t1']));
	for (const [name, items] of Object.entries(lists)) assert.equal(new Set(items.map(issueKey)).size, items.length, name);
	assert.deepEqual(lists.pushIn.map(issueKey), shared.map((c) => `look:${c.id}:t1`));
});

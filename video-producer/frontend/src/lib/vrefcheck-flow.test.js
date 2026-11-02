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

const toasts = [];
globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast: (level, message) => toasts.push(message) } } };

const { doc, ui, act, undo, dispose } = await import('./state.svelte.js');
const { bindClient, openProject } = await import('./project.svelte.js');
const { selectEngine, engineChoices } = await import('./production.svelte.js');
const { engineTitle, engineOf, shotReceptionFor } = await import('./references.js');
const { trackSendings, announceSendings, withSendings, leaveAside, shotList } = await import('./vreftracks.svelte.js');
const { trackIssues } = await import('./vreftracks.js');
const { videoTracksOf } = await import('./vrefs.js');
const { excludedVrefsOf } = await import('./shots.js');
const { anchorsOf, defaultAnchor, suiteAnchors } = await import('./match.svelte.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { t } = await import('../i18n/index.svelte.js');

const H3 = '01KX47H3MINIMAX000000000VA';
const WAN = '01KX47WANVIDEO0000000000TV';
const copy = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

const projects = new Map();
bindClient({
	async getProject(id) {
		const p = projects.get(id);
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: copy(p.doc), createdAt: null, updatedAt: null, unchanged: false } };
	},
	async saveProject(id, next) {
		const p = projects.get(id);
		p.doc = copy(next);
		p.version += 1;
		return { ok: true, data: { id, name: p.doc.name, version: p.version, doc: null, createdAt: null, updatedAt: null, unchanged: false } };
	},
	async listTakes() {
		return { ok: true, data: [] };
	},
	saveLastProject() {}
});

after(() => {
	dispose();
	delete globalThis.window;
});

ui.me = {
	engines: [{ id: 'native', kind: 'local', name: 'This machine' }],
	presets: [
		{ id: H3, name: 'MiniMax-H3', video: true },
		{ id: WAN, name: 'Wan 2.2', video: true }
	]
};

const keyOf = (preset) => engineChoices().find((option) => option.preset === preset).key;

async function open(id, role = 'motion') {
	const start = emptyDoc((key) => key);
	start.clips = [newClip({ id: 's1', start: 0, dur: 4 }), newClip({ id: 's2', start: 4, dur: 4 })];
	start.engine = { ...start.engine, preset: H3, model: null };
	start.direction = { ...start.direction, mode: 'Ref2VA' };
	start.assets = [{ id: 'a1', kind: 'video', name: 'walk.mp4', src: '/media/walk.mp4', srcDur: 8, origin: { kind: 'library', itemId: 'lib-walk' } }];
	start.vrefTracks = [{ id: 't1', slot: 1, name: '', role }];
	start.vrefItems = [{ id: 'i1', track: 't1', assetId: 'a1', start: 0, dur: 8, srcIn: 0 }];
	projects.set(id, { doc: start, version: 1 });
	const result = await openProject(id);
	assert.equal(result.ok, true);
	await settle();
	toasts.length = 0;
	ui.toasts.length = 0;
}

const last = () => ui.toasts.at(-1)?.message;

test('vref checks: changing the engine of the project says which shots a track stops or starts going into, and See opens the track in the References', async () => {
	await open('p-engine');
	assert.deepEqual([...trackSendings().entries()], [['t1', ['s1', 's2']]]);

	selectEngine(keyOf(WAN));
	assert.equal(last(), t('lib.vref.change.blocked', { label: 'vref1', shots: shotList(doc.clips), engine: engineTitle(engineOf(doc.clips[0])) }));
	assert.deepEqual([...trackSendings().entries()], []);

	selectEngine(keyOf(H3));
	assert.equal(last(), t('lib.vref.change.started', { label: 'vref1', shots: shotList(doc.clips) }));

	withSendings(() => act(() => (doc.direction.mode = 'FL2VA')));
	assert.equal(last(), t('lib.vref.change.ignored', { label: 'vref1', shots: shotList(doc.clips), engine: engineTitle(engineOf(doc.clips[0])) }));
	assert.match(last(), /MiniMax H3 · FL2VA/);

	ui.toasts.at(-1).action.run();
	assert.deepEqual([ui.workspace, ui.directorView, { ...ui.selection }], ['director', 'references', { kind: 'vtrack', id: 't1' }]);

	const count = ui.toasts.length;
	selectEngine(keyOf(H3));
	withSendings(() => act(() => (doc.clips[0].label = 'Dock')));
	assert.equal(ui.toasts.length, count);
});

test('vref checks: a change of one shot names that shot only, and a project without tracks says nothing', async () => {
	await open('p-shot');
	withSendings(() => act(() => (doc.clips[1].engine = { profile: 'FL2VA' })));
	assert.equal(last(), t('lib.vref.change.ignored', { label: 'vref1', shots: '02', engine: engineTitle(engineOf(doc.clips[1])) }));
	withSendings(() => act(() => (doc.clips[0].engine = { preset: WAN, model: null, profile: 'FL2VA' })));
	assert.equal(last(), t('lib.vref.change.ignored', { label: 'vref1', shots: '01', engine: engineTitle(engineOf(doc.clips[0])) }));
	assert.match(last(), /Wan 2\.2/);

	act(() => {
		delete doc.vrefTracks;
		delete doc.vrefItems;
	});
	const before = trackSendings();
	assert.equal(before.size, 0);
	const count = ui.toasts.length;
	assert.deepEqual(announceSendings(before), []);
	assert.equal(ui.toasts.length, count);
});

test('vref checks: a track under shots whose engine ignores it is to check, and Leave out sets it aside in those shots in one undo step', async () => {
	await open('p-check');
	assert.deepEqual(trackIssues(doc.clips.map(shotReceptionFor), videoTracksOf(doc)), []);
	selectEngine(keyOf(WAN));
	assert.deepEqual(trackIssues(doc.clips.map(shotReceptionFor), videoTracksOf(doc)), []);
	selectEngine(keyOf(H3));
	act(() => (doc.direction.mode = 'FL2VA'));

	const [issue] = trackIssues(doc.clips.map(shotReceptionFor), videoTracksOf(doc));
	assert.deepEqual([issue.status, issue.track.id, issue.clips.map((c) => c.id)], ['ignored', 't1', ['s1', 's2']]);

	assert.equal(leaveAside('t1', issue.clips), 2);
	assert.deepEqual(doc.clips.map(excludedVrefsOf), [['t1'], ['t1']]);
	assert.equal(last(), t('lib.vref.leftAside', { label: 'vref1', shots: shotList(doc.clips) }));
	assert.deepEqual(trackIssues(doc.clips.map(shotReceptionFor), videoTracksOf(doc)), []);
	assert.equal(leaveAside('t1', doc.clips), 0);

	undo();
	assert.deepEqual(doc.clips.map(excludedVrefsOf), [[], []]);
	assert.equal(trackIssues(doc.clips.map(shotReceptionFor), videoTracksOf(doc)).length, 1);
});

test('vref checks: a shot after a continuation track can match its colour to the last frame of the cut, which comes before the last frame of the previous shot', async () => {
	await open('p-suite', 'continuation');
	assert.deepEqual(suiteAnchors(doc.clips[0]), []);

	const [anchor] = suiteAnchors(doc.clips[1]);
	assert.deepEqual([anchor.kind, anchor.id, anchor.slot, anchor.media.id, anchor.at], ['vref', 't1', 1, 'a1', 3.96]);
	assert.equal(anchor.label, t('inspector.match.anchorVref', { label: 'vref1' }));
	assert.ok(anchorsOf(doc.clips[1]).some((a) => a.kind === 'vref'));
	assert.equal(defaultAnchor(anchorsOf(doc.clips[1]))?.kind, 'vref');

	act(() => (doc.vrefTracks[0].role = 'motion'));
	assert.deepEqual(suiteAnchors(doc.clips[1]), []);
});

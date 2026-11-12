import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';

const { doc, ui, replaceDoc, dispose } = await import('./state.svelte.js');
const { finishState, resetFinishing, disposeFinishing } = await import('./finishing.svelte.js');
const { normalizeTool } = await import('./api.js');
const { project } = await import('./project.svelte.js');
const { emptyDoc, newClip } = await import('./starter.js');
const { setLocale, t } = await import('../i18n/index.svelte.js');

const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;

const TOOLS = [
	{ id: 'film_grain', params: [{ name: 'amount', default: 30, min: 0, max: 100, step: 1 }, { name: 'size', default: 1.5, min: 1, max: 3, step: 0.1 }] },
	{ id: 'vignette', params: [{ name: 'amount', default: 40, min: 0, max: 100, step: 1 }, { name: 'radius', default: 50, min: 0, max: 100, step: 1 }] },
	{ id: 'fix_colors', params: [{ name: 'strength', default: 100, min: 0, max: 100, step: 5 }] },
	{ id: 'lut', params: [{ name: 'lut', type: 'lut', options: [{ label: 'None', value: '' }] }, { name: 'strength', default: 1, min: 0, max: 1, step: 0.05 }] },
	{ id: 'look', params: [{ name: 'look', type: 'look', options: [{ label: 'None', value: '' }, { label: 'Noir', value: 'noir' }] }, { name: 'strength', default: 1, min: 0, max: 1, step: 0.05 }] }
].map(normalizeTool);

after(() => dispose());

beforeEach(() => {
	setLocale('en');
	const start = emptyDoc((key) => key);
	start.clips = [newClip({ id: 's1', label: 'One', start: 0, dur: 4 })];
	replaceDoc(start);
	resetFinishing();
	project.id = 'p1';
	ui.modal = { type: 'export' };
});

const switches = (html) => hostUis(html, 'Switch').filter((item) => String(item.id).startsWith('vp-finish-'));
const primary = (html) => hostUis(html, 'Button').find((item) => item.variant === 'primary');

test('finishing dialog: a Finishing section lists the five effects, all off, and the export stays plain', async () => {
	finishState.tools = TOOLS;
	const html = await renderComponent(MODALS);
	const text = textOf(html);
	assert.ok(text.includes(t('exports.finish.title')));
	assert.deepEqual(
		switches(html).map((item) => [item.id, item.checked, item.disabled]),
		[
			['vp-finish-fixColors', false, false],
			['vp-finish-lut', false, true],
			['vp-finish-look', false, false],
			['vp-finish-vignette', false, false],
			['vp-finish-grain', false, false]
		]
	);
	assert.ok(text.includes(t('exports.finish.noLut')));
	assert.ok(!text.includes(t('exports.finish.encodeNote')));
	assert.ok(text.endsWith(t('modals.export.export')));
});

test('finishing dialog: a switched-on effect shows its settings, the second encode and the Export and finish button', async () => {
	finishState.tools = TOOLS;
	doc.master.finishing = { grain: { on: true, amount: 45, size: 2 }, look: { on: true, ref: 'noir', strength: 0.5 } };
	const html = await renderComponent(MODALS);
	const text = textOf(html);
	assert.match(html, /type="range" min="0" max="100" step="1" value="45"/);
	assert.match(html, /type="range" min="1" max="3" step="0.1" value="2"/);
	assert.match(html, /<option value="noir"[^>]*>Noir<\/option>/);
	assert.ok(text.includes('45%') && text.includes('2.0') && text.includes('50%'));
	assert.ok(text.includes(t('exports.finish.encodeNote')));
	assert.ok(text.endsWith(t('exports.finish.exportAndFinish')));
	assert.equal(primary(html).disabled, false);
});

test('finishing dialog: a saved LUT that is no longer offered is shown as missing, not replaced', async () => {
	finishState.tools = [...TOOLS.slice(0, 3), normalizeTool({ id: 'lut', params: [{ name: 'lut', type: 'lut', options: [{ label: 'None', value: '' }, { label: 'warm', value: 'warm.cube' }] }, { name: 'strength', min: 0, max: 1 }] }), TOOLS[4]];
	doc.master.finishing = { lut: { on: true, ref: 'gone.cube', strength: 1 } };
	const html = await renderComponent(MODALS);
	const text = textOf(html);
	assert.match(html, /<option value="gone\.cube" disabled[^>]*>gone\.cube<\/option>/);
	assert.match(html, /data-finish-missing="lut"/);
	assert.ok(text.includes('The saved LUT “gone.cube” is no longer offered by PotionUI: pick another one, or the LUT is left out of the finishing.'));
	assert.ok(text.endsWith(t('modals.export.export')));
});

test('finishing dialog: a finishing left running when the page closed does not hold the export when the page opens again', async () => {
	finishState.tools = TOOLS;
	doc.master.finishing = { grain: { on: true } };
	finishState.runs = [{ key: 'job-p1', jobId: 'job-p1', projectId: 'p1', runId: 'run1', status: 'running', cancelling: true, progress: 0.4, item: null, failure: null, message: '', fileName: 'Film_720p.mp4' }];
	assert.equal(primary(await renderComponent(MODALS)).disabled, true);
	disposeFinishing();
	const html = await renderComponent(MODALS);
	const text = textOf(html);
	assert.equal(primary(html).disabled, false);
	assert.ok(text.includes(t('exports.finish.failure.lost')));
	assert.ok(!text.includes(t('exports.finish.cancelling')));
	assert.ok(!text.includes(t('exports.finish.step')));
});

test('finishing dialog: a saved look that is no longer offered is told without its id', async () => {
	finishState.tools = TOOLS;
	doc.master.finishing = { look: { on: true, ref: 'mine:01M77QZK4V', strength: 1 } };
	const html = await renderComponent(MODALS);
	const text = textOf(html);
	assert.match(html, /data-finish-missing="look"/);
	assert.match(html, /<option value="mine:01M77QZK4V" disabled[^>]*>Saved look, no longer offered<\/option>/);
	assert.ok(text.includes('The saved look is no longer offered by PotionUI: pick another one, or the look is left out of the finishing.'));
	assert.ok(!text.includes('01M77QZK4V'));
});

test('finishing dialog: a finishing the page lost track of reads as not followed, not as failed', async () => {
	finishState.tools = TOOLS;
	const run = (failure) => ({ key: 'job-p1', jobId: 'job-p1', projectId: 'p1', runId: 'run1', status: 'failed', cancelling: false, progress: 0.4, item: null, failure, message: '', fileName: 'Film_720p.mp4' });
	const card = (html) => html.match(/<section[^>]*data-finish-run[\s\S]*?<\/section>/)[0];
	finishState.runs = [run('lost')];
	let html = card(await renderComponent(MODALS));
	assert.ok(textOf(html).includes(t('exports.finish.notFollowed')));
	assert.ok(!textOf(html).includes(t('lib.status.failed')));
	assert.ok(!html.includes('danger'));
	assert.match(html, /text-warning/);
	assert.match(html, /role="status"[^>]*>[^<]*The page lost track/);
	finishState.runs = [run('failed')];
	html = card(await renderComponent(MODALS));
	assert.ok(textOf(html).includes(t('lib.status.failed')));
	assert.match(html, /text-danger/);
});

test('finishing dialog: while the catalog loads, and when the core has none of the effects, it says so', async () => {
	let text = textOf(await renderComponent(MODALS));
	assert.ok(text.includes(t('exports.finish.loading')));
	finishState.toolsFailed = true;
	const failedHtml = await renderComponent(MODALS);
	assert.ok(textOf(failedHtml).includes(t('exports.finish.toolsFailed')));
	assert.match(failedHtml, /data-finish-tools="failed"/);
	assert.ok(textOf(failedHtml).includes(t('exports.finish.retry')));
	finishState.toolsFailed = false;
	finishState.tools = [];
	text = textOf(await renderComponent(MODALS));
	assert.ok(text.includes(t('exports.finish.unavailable')));
	assert.deepEqual(switches(await renderComponent(MODALS)), []);
});

test('finishing dialog: a running finishing shows its progress and locks the export; a failed one says the plain export is kept', async () => {
	finishState.tools = TOOLS;
	finishState.runs = [{ jobId: 'j1', projectId: 'p1', runId: 'r1', status: 'running', progress: 0.42, item: null, failure: null, message: '', fileName: 'Film_1080p.mp4' }];
	let html = await renderComponent(MODALS);
	let text = textOf(html);
	assert.ok(text.includes('Film_1080p_finished.mp4'));
	assert.ok(text.includes('42%'));
	assert.ok(text.includes(t('exports.finish.cancel')));
	assert.equal(primary(html).disabled, true);
	finishState.runs = [{ ...finishState.runs[0], status: 'failed', failure: 'busy' }];
	text = textOf(await renderComponent(MODALS));
	assert.ok(text.includes(`${t('exports.finish.failure.busy')} ${t('exports.finish.rawKept')}`));
	finishState.runs = [{ ...finishState.runs[0], status: 'cancelled' }];
	setLocale('fr');
	text = textOf(await renderComponent(MODALS));
	assert.ok(text.includes('Finition annulée. L’export brut reste disponible.'));
	finishState.runs = [{ ...finishState.runs[0], status: 'done', item: { id: 'i', url: '/u.mp4' } }];
	text = textOf(await renderComponent(MODALS));
	assert.ok(text.includes('Le film fini est dans votre bibliothèque.'));
	assert.ok(text.includes('Télécharger le film fini'));
});

test('finishing dialog: a finishing of another project is not shown', async () => {
	finishState.tools = TOOLS;
	finishState.runs = [{ jobId: 'j1', projectId: 'other', runId: 'r1', status: 'running', progress: 0.5, item: null, failure: null, message: '', fileName: 'X.mp4' }];
	const text = textOf(await renderComponent(MODALS));
	assert.ok(!text.includes('X_finished.mp4'));
});

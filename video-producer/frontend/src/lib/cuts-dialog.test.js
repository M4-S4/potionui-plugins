import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';

const { ui, replaceDoc, dispose } = await import('./state.svelte.js');
const { cuts, cutFailureText } = await import('./cuts.svelte.js');
const { commandById } = await import('./commands.js');
const { emptyDoc, newClip, newAsset } = await import('./starter.js');
const { setLocale, t } = await import('../i18n/index.svelte.js');

const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;

after(() => dispose());

beforeEach(() => {
	setLocale('en');
	const start = emptyDoc((key) => key);
	start.assets = [
		newAsset({ id: 'src', kind: 'video', name: 'trailer.mp4', src: '/api/media/uploads/t.mp4', origin: { kind: 'library', itemId: 'u1' }, srcDur: 6 }),
		newAsset({ id: 'pic', kind: 'image', name: 'poster.png', src: '/api/media/uploads/p.png', origin: { kind: 'library', itemId: 'u2' } })
	];
	start.clips = [newClip({ id: 'a', label: 'Opening', start: 0, dur: 4 }), newClip({ id: 'b', label: 'Ending', start: 4, dur: 3 })];
	replaceDoc(start);
	Object.assign(cuts, { status: 'idle', progress: 0, runId: null, failure: null, message: '' });
	ui.selection = null;
	ui.modal = null;
});

const control = (html, label) => hostUis(html, 'SegmentedControl').find((item) => item.ariaLabel === label);
const button = (html, label) => textOf(html).endsWith(label);

test('cut dialog: the command opens it, and it offers the two uses of a piece and where the shots go', async () => {
	commandById('import-cuts').run();
	assert.deepEqual(ui.modal, { type: 'cuts' });
	ui.modal = { type: 'cuts', assetId: 'src' };
	const html = await renderComponent(MODALS);
	const text = textOf(html);
	assert.ok(text.includes(t('project.cuts.title')));
	assert.ok(text.includes('trailer.mp4 · 6.0 s'));
	assert.ok(!text.includes('poster.png'));
	assert.deepEqual(control(html, t('project.cuts.becomes')).items.map((x) => x.id), ['source', 'motion']);
	assert.equal(control(html, t('project.cuts.becomes')).selected, 'source');
	assert.ok(text.includes(t('project.cuts.mode.sourceHelp')));
	assert.deepEqual(control(html, t('project.cuts.place')).items.map((x) => x.id), ['end']);
	assert.ok(text.includes(t('project.cuts.libraryNote')));
	assert.match(html, /type="range" min="0" max="100" step="5"/);
	assert.ok(button(html, t('project.cuts.start')));
});

test('cut dialog: with a shot selected, the shots can go after it', async () => {
	ui.selection = { kind: 'clip', id: 'a' };
	ui.modal = { type: 'cuts', assetId: 'src', settings: { mode: 'motion', at: 'after', sensitivity: 70, shortest: 1 } };
	const html = await renderComponent(MODALS);
	const place = control(html, t('project.cuts.place'));
	assert.deepEqual(place.items, [
		{ id: 'end', label: 'At the end' },
		{ id: 'after', label: 'After shot 01' }
	]);
	assert.equal(place.selected, 'after');
	assert.equal(control(html, t('project.cuts.becomes')).selected, 'motion');
	assert.ok(textOf(html).includes(t('project.cuts.mode.motionHelp')));
});

test('cut dialog: without a video it cannot start, and it says what to do', async () => {
	ui.modal = { type: 'cuts' };
	const html = await renderComponent(MODALS);
	assert.ok(textOf(html).includes(t('project.cuts.needVideo')));
	const start = hostUis(html, 'Button').find((item) => item.variant === 'primary');
	assert.equal(start.disabled, true);
});

test('cut dialog: each failure is told in the words of the page, in both languages', () => {
	assert.equal(cutFailureText('none'), 'No cut was found. Raise the sensitivity or shorten the shortest shot.');
	assert.equal(cutFailureText('tooMany'), 'More than 200 shots were found. Lower the sensitivity or lengthen the shortest shot.');
	assert.equal(cutFailureText('busy'), 'Eight media tool runs are already waiting in PotionUI. Let one finish, then try again.');
	assert.equal(cutFailureText('failed', 'ffmpeg is not available'), 'The cut finder failed: ffmpeg is not available');
	assert.equal(cutFailureText('failed'), 'The cut finder failed.');
	setLocale('fr');
	assert.equal(cutFailureText('none'), 'Aucune coupe trouvée. Montez la sensibilité ou raccourcissez le plan le plus court.');
	assert.equal(cutFailureText('tooMany'), 'Plus de 200 plans trouvés. Baissez la sensibilité ou allongez le plan le plus court.');
	assert.equal(cutFailureText('busy'), 'Huit traitements de médias attendent déjà dans PotionUI. Laissez-en finir un, puis réessayez.');
});

test('cut dialog: opening it again forgets the last failure', async () => {
	Object.assign(cuts, { status: 'failed', failure: 'none', message: 'No cuts were found' });
	ui.modal = { type: 'cuts', assetId: 'src' };
	const text = textOf(await renderComponent(MODALS));
	assert.ok(!text.includes(cutFailureText('none')));
	assert.equal(cuts.status, 'idle');
});

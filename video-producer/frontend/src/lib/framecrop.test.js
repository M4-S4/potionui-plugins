import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import './svelte-harness.js';
import { DOMAINS, LOCALES, mergeDomains, translate } from '../i18n/core.js';

const here = dirname(fileURLToPath(import.meta.url));
const i18nDir = join(here, '..', 'i18n');
const dictionaries = Object.fromEntries(
	LOCALES.map((locale) => [locale, mergeDomains(Object.fromEntries(DOMAINS.map((domain) => [domain, JSON.parse(readFileSync(join(i18nDir, locale, `${domain}.json`), 'utf-8'))])))])
);
const translator = (locale, missing) => (key, params) => translate(dictionaries, locale, key, params, (k, l) => missing.push(`${l}:${k}`));
const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { MAX_MEGAPIXELS, estimateState, noteText, readiness } = await import('./production.svelte.js');
const { t } = await import('../i18n/index.svelte.js');
const WAN = '01KX47WANVIDEO0000000000TV';

after(() => dispose());

function scene() {
	project.id = 'p1';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Local' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	ui.workspace = 'storyboard';
	ui.selection = { kind: 'clip', id: 's1' };
	ui.dirty = true;
	ui.production.target = 'clip';
	doc.engine = { backend: 'native', preset: WAN, model: null };
	doc.direction.mode = 'FL2VA';
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'Opening', stage: 'todo', take: null }];
	doc.prompts = [{ id: 'pr1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'A walk.' }];
}

const cropped = (code, extra = {}) => ({ code, data: { shot_id: 's1', roles: ['first'], size: '1024x768', aspect: '16:9', loss: 23, chained: false, ...extra } });

test('a start image cropped to the frame of the take is a warning that says the share it loses, and a large crop also offers a start image of the shot', () => {
	scene();
	estimateState.data = { blocks: [], warnings: [cropped('frame_cropped'), cropped('frame_cropped_large', { size: '1024x1024', loss: 42 }), { code: 'time_unknown' }] };
	const ready = readiness();
	assert.deepEqual(ready.missing, []);
	assert.deepEqual(ready.warnings, [
		t('generation.warn.frameCropped', { shot: 'Opening', size: '1024×768', aspect: '16:9', loss: 23 }),
		t('generation.warn.frameCroppedLarge', { shot: 'Opening', size: '1024×1024', aspect: '16:9', loss: 42 })
	]);
	assert.deepEqual(ready.notes, [noteText({ code: 'time_unknown' })]);
	assert.deepEqual(ready.crops, ['s1']);
	estimateState.data = { blocks: [], warnings: [cropped('frame_cropped')] };
	assert.deepEqual(readiness().crops, []);
	estimateState.data = null;
});

test('the crop of an end image and of the last image of the previous shot name that image', () => {
	scene();
	assert.equal(noteText(cropped('frame_cropped', { roles: ['last'] })), t('generation.warn.frameCroppedLast', { shot: 'Opening', size: '1024×768', aspect: '16:9', loss: 23 }));
	assert.equal(noteText(cropped('frame_cropped_large', { roles: ['last'] })), t('generation.warn.frameCroppedLastLarge', { shot: 'Opening', size: '1024×768', aspect: '16:9', loss: 23 }));
	assert.equal(noteText(cropped('frame_cropped', { roles: ['first', 'last'] })), t('generation.warn.frameCropped', { shot: 'Opening', size: '1024×768', aspect: '16:9', loss: 23 }));
	assert.equal(noteText(cropped('frame_cropped', { chained: true })), t('generation.warn.frameCroppedChained', { shot: 'Opening', size: '1024×768', aspect: '16:9', loss: 23 }));
	assert.equal(noteText(cropped('frame_cropped_large', { chained: true })), t('generation.warn.frameCroppedChainedLarge', { shot: 'Opening', size: '1024×768', aspect: '16:9', loss: 23 }));
});

test('the texts of the crop exist in every language the plugin ships, with the same parameters', () => {
	const missing = [];
	const en = translator('en', missing);
	const fr = translator('fr', missing);
	const params = { shot: 'Opening', size: '1024×1024', aspect: '16:9', loss: 42 };
	assert.equal(en('generation.warn.frameCropped', params), 'The start image of “Opening” is 1024×1024, not 16:9: it is cropped at its centre, 42 % of the picture left out.');
	assert.equal(en('generation.warn.frameCroppedLarge', params), 'The start image of “Opening” is 1024×1024, not 16:9: cropped at its centre, it loses 42 % of the picture. Make a start image in the frame of the take.');
	assert.equal(fr('generation.warn.frameCropped', params), 'L’image de début de « Opening » est en 1024×1024, pas en 16:9 : elle est recadrée au centre, 42 % de l’image en moins.');
	assert.equal(fr('generation.warn.frameCroppedLarge', params), 'L’image de début de « Opening » est en 1024×1024, pas en 16:9 : recadrée au centre, elle perd 42 % de l’image. Faites une image de début au cadre de la prise.');
	assert.equal(en('generation.warn.frameCroppedLastLarge', params), 'The end image of “Opening” is 1024×1024, not 16:9: cropped at its centre, it loses 42 % of the picture. Make an end image in the frame of the take.');
	assert.equal(fr('generation.warn.frameCroppedLastLarge', params), 'L’image de fin de « Opening » est en 1024×1024, pas en 16:9 : recadrée au centre, elle perd 42 % de l’image. Faites une image de fin au cadre de la prise.');
	assert.equal(en('generation.warn.frameCroppedChainedLarge', params), 'The last image of the shot before “Opening” is 1024×1024, not 16:9: cropped at its centre, it loses 42 % of the picture. Make a start image in the frame of the take.');
	assert.equal(fr('generation.warn.frameCroppedChainedLarge', params), 'La dernière image du plan avant « Opening » est en 1024×1024, pas en 16:9 : recadrée au centre, elle perd 42 % de l’image. Faites une image de début au cadre de la prise.');
	for (const key of ['frameCropped', 'frameCroppedLast', 'frameCroppedChained', 'frameCroppedLarge', 'frameCroppedLastLarge', 'frameCroppedChainedLarge']) {
		for (const locale of LOCALES) assert.match(dictionaries[locale][`generation.warn.${key}`], /\{shot\}.*\{size\}.*\{aspect\}.*\{loss\}/, `${locale} ${key}`);
	}
	for (const locale of LOCALES) {
		assert.ok(dictionaries[locale]['production.deck.startImage'], locale);
		assert.match(dictionaries[locale]['production.deck.startImageTip'], /\{shot\}/, locale);
	}
	assert.equal(en('keyframes.note.aspect_mismatch', { size: '1024×1024', aspect: '16:9' }), 'The images will be 1024×1024, not 16:9: a take crops them at their centre. Put a picture in the frame of the project first, or choose a model with an output size.');
	assert.equal(fr('keyframes.note.aspect_mismatch', { size: '1024×1024', aspect: '16:9' }), 'Les images seront en 1024×1024, pas en 16:9 : une prise les recadre au centre. Mettez d’abord une image au cadre du projet, ou choisissez un modèle qui a une taille de sortie.');
	assert.deepEqual(missing, []);
});

const { renderComponent, hostUis, clean, textOf } = await import('./svelte-harness.js');
const DECK = new URL('../components/production/ProductionDeck.svelte', import.meta.url).href;
const cropButtons = (html) => [...clean(html).matchAll(/<button type="button" class="vp-deck-inline-action" data-crop-start-image="">(.*?)<\/button>/g)].map((match) => textOf(match[1]));
const strong = (shot, roles = ['first']) => cropped('frame_cropped_large', { shot_id: shot, roles, size: '1024x1024', loss: 42 });
const tips = (html) => hostUis(html, 'Tooltip').map((props) => props.text);
const EMPTY = { shots: [], vram: null, time: { seconds: null, samples: 0 }, quota: null, cost: null, blocks: [], warnings: [] };

test('the deck offers to make a start image for the first shot whose image a large crop cuts, while nothing blocks and nothing runs', async () => {
	scene();
	doc.clips.push({ id: 's2', start: 4, dur: 4, label: 'Second', stage: 'todo', take: null });
	estimateState.data = { ...EMPTY, blocks: [], warnings: [strong('s2'), strong('s1')] };
	const offered = await renderComponent(DECK);
	assert.deepEqual(cropButtons(offered), [t('production.deck.startImage')]);
	assert.ok(tips(offered).includes(t('production.deck.startImageTip', { shot: 'Second' })));
	estimateState.data = { ...EMPTY, blocks: [{ code: 'missing_models', message: 'x', data: { models: ['a'] } }], warnings: [strong('s1')] };
	assert.deepEqual(cropButtons(await renderComponent(DECK)), []);
	estimateState.data = { ...EMPTY, blocks: [], warnings: [strong('s1')] };
	ui.production.state = 'running';
	assert.deepEqual(cropButtons(await renderComponent(DECK)), []);
	ui.production.state = 'ready';
	assert.deepEqual(cropButtons(await renderComponent(DECK)), [t('production.deck.startImage')]);
	estimateState.data = { ...EMPTY, blocks: [], warnings: [cropped('frame_cropped')] };
	assert.deepEqual(cropButtons(await renderComponent(DECK)), []);
	estimateState.data = null;
	assert.match(source('../components/production/ProductionDeck.svelte'), /onclick=\{\(\) => startImage\(cropClip\)\}/);
	const { startImage } = await import('./references.js');
	startImage(doc.clips[1]);
	assert.deepEqual(ui.modal, { type: 'shot', id: 's2', focus: 'keyframes' });
	ui.modal = null;
});

const framing = await import('./framing.js');
const { frameBox } = await import('./framing.js');
const PICKER = new URL('../components/shots/MediaPicker.svelte', import.meta.url).href;

test('a start image thumbnail has the ratio of the film, wide films across the width and tall ones on a fixed height', () => {
	assert.equal(frameBox({ aspect: '16:9' }), `aspect-ratio: ${16 / 9}; width: 100%`);
	assert.equal(frameBox({ aspect: '1:1' }), 'aspect-ratio: 1; width: 100%');
	assert.equal(frameBox({ aspect: '9:16' }), `aspect-ratio: ${9 / 16}; height: 7rem; width: auto; max-width: 100%; margin: 0 auto`);
	assert.equal(frameBox({ aspect: '2.39:1' }), `aspect-ratio: ${2.39}; width: 100%`);
	assert.equal(frameBox({}), `aspect-ratio: ${16 / 9}; width: 100%`);
});

test('the picker of a start image shows the centre the take keeps, in the frame of the film, and other pickers stay 16:9', async () => {
	doc.assets = [{ id: 'a1', kind: 'image', name: 'square.png', src: '/api/media/uploads/square.png', width: 1024, height: 1024 }];
	const framed = await renderComponent(PICKER, { title: 'Start image', value: 'a1', onpick: () => {}, frame: frameBox({ aspect: '9:16' }) });
	assert.match(framed, /<img src="\/api\/media\/uploads\/square\.png" alt="" class="object-cover" style="aspect-ratio: 0\.5625; height: 7rem; width: auto; max-width: 100%; margin: 0 auto" data-frame-thumb=""/);
	const plain = await renderComponent(PICKER, { title: 'Reference', value: 'a1', onpick: () => {} });
	assert.match(plain, /class="aspect-video w-full object-cover"/);
	assert.doesNotMatch(plain, /data-frame-thumb/);
	const empty = await renderComponent(PICKER, { title: 'Start image', value: null, onpick: () => {}, frame: frameBox({ aspect: '1:1' }) });
	assert.match(empty, /style="aspect-ratio: 1; width: 100%"/);
	doc.assets = [];
});

test('a key frame tile has the ratio of the film when no take ratio is given, wide ones 88 px across and tall ones 50 px high', async () => {
	const { frameTile } = await import('./framing.js');
	assert.equal(frameTile({ aspect: '16:9' }), `aspect-ratio: ${16 / 9}; width: 88px`);
	assert.equal(frameTile({ aspect: '2.39:1' }), `aspect-ratio: ${2.39}; width: 88px`);
	assert.equal(frameTile({ aspect: '1:1' }), 'aspect-ratio: 1; height: 50px');
	assert.equal(frameTile({ aspect: '9:16' }), `aspect-ratio: ${9 / 16}; height: 50px`);
});

test('an image that could not be cropped is said to be sent as it is, with its cause and the image it is', () => {
	scene();
	const said = (data) => noteText({ code: 'frame_not_cropped', data: { shot_id: 's1', roles: ['first'], chained: false, ...data } });
	const first = t('generation.warn.notCroppedImageFirst', { shot: 'Opening' });
	assert.equal(said({ cause: 'storage_full' }), t('generation.warn.frameNotCroppedStorage', { image: first }));
	assert.equal(said({ cause: 'upload_too_large' }), t('generation.warn.frameNotCroppedUpload', { image: first }));
	assert.equal(said({ cause: 'too_many_pixels' }), t('generation.warn.frameNotCroppedPixels', { image: first, max: MAX_MEGAPIXELS }));
	assert.equal(said({ cause: 'failed' }), t('generation.warn.frameNotCropped', { image: first }));
	assert.equal(said({ cause: 'storage_full', roles: ['last'] }), t('generation.warn.frameNotCroppedStorage', { image: t('generation.warn.notCroppedImageLast', { shot: 'Opening' }) }));
	assert.equal(said({ cause: 'failed', chained: true }), t('generation.warn.frameNotCropped', { image: t('generation.warn.notCroppedImageChained', { shot: 'Opening' }) }));
	assert.equal(said({ cause: 'storage_full' }), 'The start image of “Opening” is sent as it is, not cropped to the frame of the take: the storage of the project\'s owner is full.');
	assert.equal(said({ cause: 'upload_too_large' }), 'The start image of “Opening” is sent as it is, not cropped to the frame of the take: its crop is larger than the largest file the project\'s owner may upload.');
	for (const locale of LOCALES) {
		for (const key of ['frameNotCropped', 'frameNotCroppedStorage', 'frameNotCroppedUpload', 'frameNotCroppedPixels']) assert.match(dictionaries[locale][`generation.warn.${key}`], /^\{image\} /, `${locale} ${key}`);
		assert.ok(dictionaries[locale]['generation.card.notCropped'], locale);
		assert.equal(dictionaries[locale]['generation.block.frameCropFailed'], undefined, locale);
	}
});

test('the French texts of a full storage and of a crop too large to upload name the limits of the project owner', () => {
	const missing = [];
	const fr = translator('fr', missing);
	const image = fr('generation.warn.notCroppedImageFirst', { shot: 'Ouverture' });
	assert.equal(fr('generation.warn.frameNotCroppedStorage', { image }), 'L’image de début de « Ouverture » est envoyée telle quelle, sans recadrage au cadre de la prise : le stockage du propriétaire du projet est plein.');
	assert.equal(fr('generation.warn.frameNotCroppedUpload', { image }), 'L’image de début de « Ouverture » est envoyée telle quelle, sans recadrage au cadre de la prise : le recadrage dépasse le plus gros fichier que le propriétaire du projet peut envoyer.');
	assert.deepEqual(missing, []);
});

test('a take keeps the notes of the images it was sent without their crop, and its card shows them', async () => {
	const { normalizeTake } = await import('./api.js');
	const note = { code: 'frame_not_cropped', message: 'x', data: { shot_id: 's2', cause: 'storage_full', roles: ['first'], chained: true } };
	const take = normalizeTake({ id: 't1', shot_id: 's2', status: 'queued', frame_notes: [note, { code: 'other' }] });
	assert.deepEqual(take.frameNotes, [{ shot_id: 's2', cause: 'storage_full', roles: ['first'], chained: true }]);
	assert.deepEqual(normalizeTake({ id: 't2', shot_id: 's2', status: 'done' }).frameNotes, []);
	scene();
	const card = new URL('../components/takes/TakeCard.svelte', import.meta.url).href;
	const own = { code: 'frame_not_cropped', message: 'x', data: { shot_id: 's1', cause: 'upload_too_large', roles: ['last'], chained: false } };
	const badges = (html) => [...clean(html).matchAll(/<span [^>]*title="([^"]*)" data-take-not-cropped="">([^<]*)<\/span>/g)].map((match) => [match[1].replaceAll('&#39;', "'").replaceAll('&quot;', '"').replaceAll('&amp;', '&'), match[2]]);
	const noted = normalizeTake({ id: 't3', shot_id: 's1', status: 'queued', variant: 'A', quality: 'draft', frame_notes: [own, { ...note, data: { ...note.data, shot_id: 's1', roles: ['first'], chained: false } }] });
	assert.deepEqual(badges(await renderComponent(card, { take: noted, clip: doc.clips[0] })), [
		[`${noteText(own)} ${noteText({ code: 'frame_not_cropped', data: { shot_id: 's1', cause: 'storage_full', roles: ['first'], chained: false } })}`, t('generation.card.notCropped')]
	]);
	assert.deepEqual(badges(await renderComponent(card, { take: normalizeTake({ id: 't4', shot_id: 's1', status: 'queued', variant: 'A', quality: 'draft' }), clip: doc.clips[0] })), []);
});

test('a seam still box has the ratio of the film when no take ratio is given, on a height of its own for a tall film', () => {
	const { frameBox } = framing;
	assert.equal(frameBox({ aspect: '9:16' }, '18rem'), `aspect-ratio: ${9 / 16}; height: 18rem; width: auto; max-width: 100%; margin: 0 auto`);
	assert.equal(frameBox({ aspect: '16:9' }, '18rem'), `aspect-ratio: ${16 / 9}; width: 100%`);
});

test('the pixel ceiling the page names is the one of the formats table, in every language', async () => {
	const table = (await import('./formatstable.js')).default;
	assert.equal(MAX_MEGAPIXELS, Math.floor(table.startImages.maxPixels / 1_000_000));
	scene();
	assert.match(noteText({ code: 'frame_not_cropped', data: { shot_id: 's1', roles: ['first'], cause: 'too_many_pixels' } }), new RegExp(`more than ${MAX_MEGAPIXELS} million pixels`));
	for (const locale of LOCALES) {
		assert.match(dictionaries[locale]['generation.warn.frameNotCroppedPixels'], /\{max\}/, locale);
		assert.doesNotMatch(dictionaries[locale]['generation.warn.frameNotCroppedPixels'], /\d/, locale);
	}
});

test('a strong warning that cuts only the end image of a shot offers to make an end image', async () => {
	scene();
	const strong = (roles) => ({ code: 'frame_cropped_large', data: { shot_id: 's1', roles, size: '1024x1024', aspect: '16:9', loss: 42, chained: false } });
	estimateState.data = { blocks: [], warnings: [strong(['last'])] };
	assert.deepEqual([readiness().crops, readiness().cropEnds], [['s1'], ['s1']]);
	estimateState.data = { blocks: [], warnings: [strong(['first']), strong(['last'])] };
	assert.deepEqual([readiness().crops, readiness().cropEnds], [['s1', 's1'], ['s1']]);
	estimateState.data = { ...EMPTY, warnings: [strong(['last'])] };
	const end = await renderComponent(DECK);
	assert.deepEqual(cropButtons(end), [t('production.deck.endImage')]);
	assert.ok(tips(end).includes(t('production.deck.endImageTip', { shot: 'Opening' })));
	estimateState.data = { ...EMPTY, warnings: [strong(['last']), strong(['first'])] };
	assert.deepEqual(cropButtons(await renderComponent(DECK)), [t('production.deck.startImage')]);
	estimateState.data = null;
	for (const locale of LOCALES) assert.match(dictionaries[locale]['production.deck.endImageTip'], /\{shot\}/, locale);
});

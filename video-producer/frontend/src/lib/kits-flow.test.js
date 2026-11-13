import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const hooks = `
import { readFile } from 'node:fs/promises';
import { compileModule } from ${JSON.stringify(import.meta.resolve('svelte/compiler'))};
export async function load(url, context, next) {
	if (url.endsWith('.svelte.js')) return { format: 'module', shortCircuit: true, source: compileModule(await readFile(new URL(url), 'utf8'), { generate: 'client', filename: url }).js.code };
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

class Media {
	removeAttribute() {}
	load() {}
	remove() {}
	set src(value) {
		queueMicrotask(() => this.onerror?.());
	}
}

const toasts = [];
const mounted = [];
const components = {};
function modal(name) {
	return {
		mount(target, props) {
			const handle = { name, props, open: true };
			mounted.push(handle);
			return handle;
		},
		update(handle, next) {
			Object.assign(handle.props, next);
			if (next.isOpen === false) handle.open = false;
		},
		unmount() {}
	};
}

globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast: (level, message) => toasts.push([level, message]) }, components } };
globalThis.document = { body: { appendChild: (node) => node }, createElement: () => new Media(), querySelector: () => null };
globalThis.Image = Media;

const { doc, ui, replaceDoc, dispose, undo } = await import('./state.svelte.js');
const { bindClient } = await import('./project.svelte.js');
const importer = await import('./importer.js');
const { emptyDoc, newAsset } = await import('./starter.js');
const { setLocale } = await import('../i18n/index.svelte.js');
const { addCardImage, addCardImages } = await import('./references.js');
const { PALETTE_SIZE, commandById, menus, paletteCommands, shown } = await import('./commands.js');
const { mediaOf, rateOf } = await import('../../../tests/fixtures/make_kit_picks.mjs');

const fixture = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures', 'kit_picks.json'), 'utf-8'));

after(() => {
	dispose();
	delete globalThis.window;
	delete globalThis.document;
	delete globalThis.Image;
});

const resolved = [];
const server = { gate: null, lie: null, rateHang: false };
bindClient({
	async resolveMedia(origin) {
		resolved.push(origin);
		if (server.gate) await server.gate;
		if (origin.kind !== 'library' || !origin.itemId.startsWith('up-')) return { ok: false, error: { status: 404 } };
		const media = mediaOf(origin);
		return { ok: true, data: server.lie ? { ...media, mediaType: server.lie } : media };
	},
	async libraryItem(itemId) {
		if (server.rateHang) return new Promise(() => {});
		return { ok: true, data: { fps: rateOf(itemId) } };
	}
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function item(extra = {}) {
	return { id: 'it_face', kit_id: 'kt_mara', kind: 'image', name: 'face', position: 0, media_ref: 'up-image-1', text: null, url: '/api/media/uploads/hands.png', thumbnail_url: null, width: 512, height: 512, duration_seconds: null, missing: false, created_at: '', ...extra };
}

const MARA = {
	id: 'kt_mara',
	name: 'Mara',
	handle: 'mara',
	items: [
		item(),
		item({ id: 'it_bio', kind: 'text', name: 'bio', position: 1, media_ref: null, url: null, text: 'Mara is tall.' }),
		item({ id: 'it_coat', name: 'coat', position: 2, media_ref: 'up-image-3' }),
		item({ id: 'it_walk', kind: 'video', name: 'walk', position: 3, media_ref: 'up-video-2' }),
		item({ id: 'it_gone', name: 'gone', position: 4, media_ref: null, url: null, missing: true }),
		item({ id: 'it_voice', kind: 'audio', name: 'voice', position: 5, media_ref: 'up-audio-5' })
	]
};

const picked = (kitItem, kit = MARA) => ({ key: `kit:${kitItem.id}`, mediaType: kitItem.kind, filename: kitItem.name, origin: { kind: 'kit', kitId: kit.id, itemId: kitItem.id }, kit: { id: kit.id, name: kit.name, handle: kit.handle }, kitItem });
const byId = (id) => MARA.items.find((it) => it.id === id);
const last = () => mounted.at(-1);
const assetsOf = () => doc.assets.map((a) => [a.kind, a.origin, a.name]);
const lib = (ref) => ({ kind: 'library', itemId: ref });

function close(handle) {
	handle.props.onClose();
}

beforeEach(() => {
	setLocale('en');
	replaceDoc(emptyDoc((key) => key));
	ui.hostModal = false;
	toasts.length = 0;
	mounted.length = 0;
	resolved.length = 0;
	server.gate = null;
	server.lie = null;
	server.rateHang = false;
	for (const key of Object.keys(components)) delete components[key];
	components.MediaPickerModal = modal('MediaPickerModal');
	components.UploadLibraryModal = modal('UploadLibraryModal');
});

test('the kit import opens the host picker on the Kits source only, multiple, for the kinds of the place, with the whole-kit choice and no kits.accepted', () => {
	importer.openKitImport();
	const { name, props } = last();
	assert.equal(name, 'MediaPickerModal');
	assert.deepEqual(props.sources, ['kits']);
	assert.equal(props.initialSource, 'kits');
	assert.deepEqual(props.mediaTypes, ['image', 'video']);
	assert.deepEqual(props.selectableMediaTypes, ['image', 'video']);
	assert.equal(props.multiple, true);
	assert.equal(typeof props.kits.onLoad, 'function');
	assert.equal('accepted' in props.kits, false);
	assert.equal(props.title, 'Import images and videos from a kit');
	assert.equal(ui.hostModal, true);
	close(last());
	assert.equal(ui.hostModal, false);
	importer.openKitImport('audio');
	assert.deepEqual(last().props.mediaTypes, ['audio']);
	assert.equal(last().props.title, 'Import audio from a kit');
});

test('several kit items picked: each becomes an ordinary library asset of its media_ref, in the order picked, and the document gains no other key', async () => {
	const before = Object.keys(JSON.parse(JSON.stringify(doc))).sort();
	importer.openKitImport();
	const handle = last();
	handle.props.onConfirm(['kit:it_walk', 'kit:it_face'], [picked(byId('it_walk')), picked(byId('it_face'))]);
	close(handle);
	await settle();
	assert.deepEqual(assetsOf(), [
		['video', lib('up-video-2'), 'hands.mp4'],
		['image', lib('up-image-1'), 'face.png']
	]);
	assert.deepEqual(Object.keys(JSON.parse(JSON.stringify(doc))).sort(), before);
	assert.ok(doc.assets.every((a) => Object.keys(a.origin).join() === 'kind,itemId'));
	assert.deepEqual(toasts, [['success', '2 files imported']]);
});

test('the whole kit: its accepted media in kit order, then a warning that says how many were left and why', async () => {
	importer.openKitImport();
	const handle = last();
	handle.props.kits.onLoad([MARA]);
	close(handle);
	await settle();
	assert.deepEqual(assetsOf().map(([kind, origin]) => [kind, origin.itemId]), [
		['image', 'up-image-1'],
		['image', 'up-image-3'],
		['video', 'up-video-2']
	]);
	assert.deepEqual(toasts, [
		['success', '3 files imported'],
		['warning', '3 kit items left out: 1 text, 1 file deleted from the library, 1 not an image or a video']
	]);
});

test('picked items and a whole kit confirmed together: picked first, then the kit, and a file reached twice is one asset', async () => {
	importer.openKitImport();
	const handle = last();
	handle.props.onConfirm(['kit:it_coat'], [picked(byId('it_coat'))]);
	handle.props.kits.onLoad([MARA]);
	close(handle);
	await settle();
	assert.deepEqual(doc.assets.map((a) => a.origin.itemId), ['up-image-3', 'up-image-1', 'up-video-2']);
	assert.equal(resolved.length, 3);
});

test('a kit the host could not load leaves the picker open, and the next confirm imports what it brings, not only the first one', async () => {
	importer.openKitImport();
	const handle = last();
	handle.props.onConfirm(['kit:it_coat'], [picked(byId('it_coat'))]);
	await settle();
	assert.deepEqual(doc.assets.map((a) => a.origin.itemId), ['up-image-3']);
	handle.props.kits.onLoad([MARA]);
	close(handle);
	await settle();
	assert.deepEqual(doc.assets.map((a) => a.origin.itemId), ['up-image-3', 'up-image-1', 'up-video-2']);
	assert.equal(ui.hostModal, false);
});

test('a file already in the project, from the Library or from a kit, stays one asset and is counted already present', async () => {
	replaceDoc({ ...emptyDoc((key) => key), assets: [newAsset({ id: 'have', kind: 'image', name: 'hands.png', src: '/api/media/uploads/hands.png', origin: lib('up-image-1') })] });
	importer.openKitImport();
	const handle = last();
	handle.props.onConfirm(['kit:it_face', 'kit:it_coat'], [picked(byId('it_face')), picked(byId('it_coat'))]);
	close(handle);
	await settle();
	assert.deepEqual(doc.assets.map((a) => [a.id === 'have' ? 'have' : 'new', a.origin.itemId]), [['have', 'up-image-1'], ['new', 'up-image-3']]);
	assert.deepEqual(toasts, [['success', '1 file imported · 1 file already in the project']]);
});

test('a kit item whose library file the server no longer resolves is counted like a library file that fails', async () => {
	importer.openKitImport();
	const handle = last();
	handle.props.onConfirm(['kit:it_x'], [picked(item({ id: 'it_x', media_ref: 'gone-1' }))]);
	close(handle);
	await settle();
	assert.equal(doc.assets.length, 0);
	assert.deepEqual(toasts, [['warning', '1 file could not be imported']]);
});

test('closing the kit picker without choosing imports nothing and says nothing', async () => {
	importer.openKitImport();
	close(last());
	await settle();
	assert.equal(doc.assets.length, 0);
	assert.deepEqual(toasts, []);
	assert.equal(ui.hostModal, false);
});

test('a single slot (reference media, first image, a video to cut): one item, single select, and the slot gets its asset id', async () => {
	const got = [];
	importer.pickKitMedia('video', 'Shot reference', (id) => got.push(id), () => got.push('dismissed'));
	const handle = last();
	assert.equal(handle.props.multiple, undefined);
	assert.equal(handle.props.closeOnPick, false);
	assert.deepEqual(handle.props.mediaTypes, ['video']);
	assert.equal(handle.props.kits, undefined);
	handle.props.onPick(picked(byId('it_walk')));
	assert.equal(handle.open, false);
	await settle();
	assert.equal(got.length, 1);
	assert.equal(doc.assets.find((a) => a.id === got[0]).origin.itemId, 'up-video-2');
});

test('a single slot refuses a text, a deleted file and a wrong kind with a warning, and the picker stays open for another choice', async () => {
	const got = [];
	importer.pickKitMedia('image', 'Card', (id) => got.push(id), () => got.push('dismissed'));
	const handle = last();
	handle.props.onPick(picked(byId('it_bio')));
	handle.props.onPick(picked(byId('it_gone')));
	handle.props.onPick(picked(byId('it_walk')));
	await settle();
	assert.equal(handle.open, true);
	assert.deepEqual(got, []);
	assert.deepEqual(toasts, [
		['warning', '“bio” is a text, not a media file.'],
		['warning', '“gone” has no file: it was deleted from the library.'],
		['warning', '“walk” is not an image.']
	]);
	handle.props.onPick(picked(byId('it_coat')));
	await settle();
	assert.equal(got.length, 1);
	close(handle);
	assert.equal(got.length, 1);
});

test('a single slot dismissed: the caller hears it, as with the Library picker', () => {
	const got = [];
	importer.pickKitMedia('video', 'Cut', () => got.push('picked'), () => got.push('dismissed'));
	close(last());
	assert.deepEqual(got, ['dismissed']);
});

test('a place that adds (a bible card, a new reference or sound of a shot): many items or the whole kit, and every asset id reaches it in order', async () => {
	const got = [];
	importer.pickKitMany('image', 'Add an image', (ids) => got.push(...ids), () => got.push('dismissed'));
	const handle = last();
	assert.equal(handle.props.multiple, true);
	assert.deepEqual(handle.props.mediaTypes, ['image']);
	handle.props.kits.onLoad([MARA]);
	close(handle);
	await settle();
	assert.deepEqual(got.map((id) => doc.assets.find((a) => a.id === id).origin.itemId), ['up-image-1', 'up-image-3']);
	assert.deepEqual(toasts, [['warning', '4 kit items left out: 1 text, 1 file deleted from the library, 2 not images']]);
});

test('a place that adds, with a file the project already has: the existing asset id is given, no new asset', async () => {
	replaceDoc({ ...emptyDoc((key) => key), assets: [newAsset({ id: 'have', kind: 'audio', name: 'voice.wav', src: '/x.wav', origin: lib('up-audio-5') })] });
	const got = [];
	importer.pickKitMany('audio', 'New sound', (ids) => got.push(...ids));
	const handle = last();
	handle.props.onConfirm(['kit:it_voice'], [picked(byId('it_voice'))]);
	close(handle);
	await settle();
	assert.deepEqual(got, ['have']);
	assert.equal(doc.assets.length, 1);
	assert.equal(resolved.length, 0);
});

test('a place that adds, where the kit has nothing it takes: nothing is added and the caller hears it was dismissed', async () => {
	const got = [];
	importer.pickKitMany('audio', 'New sound', (ids) => got.push(...ids), () => got.push('dismissed'));
	const handle = last();
	handle.props.kits.onLoad([{ ...MARA, items: MARA.items.filter((it) => it.kind !== 'audio') }]);
	close(handle);
	await settle();
	assert.deepEqual(got, ['dismissed']);
	assert.equal(doc.assets.length, 0);
});

test('a host without MediaPickerModal: no kit entry, and the Library picker opens as before, with the same props', () => {
	delete components.MediaPickerModal;
	assert.equal(importer.kitsAvailable(), false);
	assert.equal(importer.libraryAvailable(), true);
	importer.openKitImport();
	assert.equal(mounted.length, 0);
	assert.deepEqual(toasts, [['warning', 'The media picker is not available on this server.']]);
	importer.openImport();
	const { name, props } = last();
	assert.equal(name, 'UploadLibraryModal');
	assert.deepEqual(Object.keys(props).sort(), ['isOpen', 'mediaType', 'multiple', 'onClose', 'onConfirm', 'selectableMediaTypes', 'selectedKeys', 'title']);
	assert.deepEqual(props.selectableMediaTypes, ['image', 'video']);
});

test('the Library picker of a single slot still opens UploadLibraryModal with onSelect, where the kit picker is offered', () => {
	importer.pickMedia('image', 'Card', () => {});
	assert.equal(last().name, 'UploadLibraryModal');
	assert.equal(typeof last().props.onSelect, 'function');
	assert.equal(last().props.sources, undefined);
});

test('on the kits of tests/fixtures/kit_picks.json, the whole-kit import builds the assets the fixture holds, which the server schema accepts', async () => {
	for (const [n, { kits, allowed }] of fixture.cases.entries()) {
		replaceDoc(emptyDoc((key) => key));
		toasts.length = 0;
		const kind = allowed.length > 1 ? 'media' : allowed[0];
		if (kind === 'media' || kind === 'audio') importer.openKitImport(kind);
		else importer.pickKitMany(kind, 'Place', () => {});
		const handle = last();
		handle.props.kits.onLoad(kits);
		close(handle);
		await settle();
		const strip = (assets) => JSON.parse(JSON.stringify(assets)).map(({ id, ...rest }) => rest);
		assert.deepEqual(strip(doc.assets), strip(fixture.cases[n].assets), `kit ${n}`);
	}
});

const twice = () => settle().then(settle);
function undoSteps() {
	let steps = 0;
	while ((doc.assets.length || doc.references.length) && steps < 60) {
		undo();
		steps += 1;
	}
	return steps;
}
const imageKit = (n, first = 0) => ({ id: 'kt_many', name: 'Many', handle: 'many', items: Array.from({ length: n }, (_, i) => item({ id: `it_${i}`, name: `n${i}`, position: i, media_ref: `up-image-${first + i}` })) });

test('closing the picker while the host still loads a kit: what arrives afterwards enters nothing and says nothing', async () => {
	importer.openKitImport();
	const handle = last();
	close(handle);
	handle.props.onConfirm(['kit:it_coat'], [picked(byId('it_coat'))]);
	handle.props.kits.onLoad([MARA]);
	await twice();
	assert.equal(doc.assets.length, 0);
	assert.deepEqual(toasts, []);
	assert.equal(resolved.length, 0);
});

test('closing the picker while a kit loads, at a place that adds: the caller hears it was dismissed, once, and gets no ids', async () => {
	const calls = [];
	importer.pickKitMany('image', 'Add an image', (ids) => calls.push(['picked', ids.length]), () => calls.push(['dismissed']));
	const handle = last();
	close(handle);
	handle.props.kits.onLoad([imageKit(2)]);
	await twice();
	assert.deepEqual(calls, [['dismissed']]);
	assert.equal(doc.assets.length, 0);
});

test('a single slot closed by the user: a pick that arrives afterwards does nothing', async () => {
	const got = [];
	importer.pickKitMedia('image', 'Card', (id) => got.push(id), () => got.push('dismissed'));
	const handle = last();
	close(handle);
	handle.props.onPick(picked(byId('it_coat')));
	await twice();
	assert.deepEqual(got, ['dismissed']);
	assert.equal(doc.assets.length, 0);
});

test('two confirms that overlap, the second while the first still resolves: one asset per file, and the second batch says the file is already there', async () => {
	let release;
	server.gate = new Promise((resolve) => (release = resolve));
	importer.openKitImport();
	const handle = last();
	handle.props.onConfirm(['kit:it_face'], [picked(byId('it_face'))]);
	await settle();
	handle.props.kits.onLoad([MARA]);
	await settle();
	release();
	await twice();
	await twice();
	assert.deepEqual(doc.assets.map((a) => a.origin.itemId), ['up-image-1', 'up-image-3', 'up-video-2']);
	assert.deepEqual(toasts.filter(([level]) => level === 'success'), [['success', '1 file imported'], ['success', '2 files imported · 1 file already in the project']]);
});

test('after a first batch, the second confirm counts only what it brings: the first batch is not counted again', async () => {
	importer.openKitImport();
	const handle = last();
	handle.props.onConfirm(['kit:it_face'], [picked(byId('it_face'))]);
	await twice();
	handle.props.onConfirm(['kit:it_coat'], [picked(byId('it_coat'))]);
	await twice();
	assert.deepEqual(toasts, [['success', '1 file imported'], ['success', '1 file imported']]);
});

test('the whole kit on a bible card is one undo step, assets and references together, and so is a card that only links files the project has', async () => {
	const card = { id: 'card', label: 'Lumi', references: [] };
	doc.bible = { characters: [card], places: [] };
	importer.pickKitMany('image', 'Add an image', (ids) => addCardImages(doc.bible.characters[0], 'identite', ids));
	last().props.kits.onLoad([imageKit(9)]);
	await twice();
	assert.equal(doc.assets.length, 9);
	assert.equal(doc.references.length, 9);
	assert.equal(doc.bible.characters[0].references.length, 9);
	assert.equal(undoSteps(), 1);
	replaceDoc({ ...emptyDoc((key) => key), assets: [newAsset({ id: 'have', kind: 'image', name: 'face.png', src: '/f.png', origin: lib('up-image-0') })] });
	ui.hostModal = false;
	doc.bible = { characters: [{ id: 'card', label: 'Lumi', references: [] }], places: [] };
	importer.pickKitMany('image', 'Add an image', (ids) => addCardImages(doc.bible.characters[0], 'identite', ids));
	last().props.kits.onLoad([imageKit(1)]);
	await twice();
	assert.equal(doc.references.length, 1);
	undo();
	assert.equal(doc.references.length, 0);
	assert.equal(doc.assets.length, 1);
});

test('a place that keeps its picks in a draft (the shot editor): the new assets are one undo step and stay in the project if the draft is dropped, as with the Library', async () => {
	const draft = [];
	importer.pickKitMany('image', 'New reference', (ids) => ids.forEach((id) => draft.push(id)));
	last().props.kits.onLoad([imageKit(5)]);
	await twice();
	assert.equal(draft.length, 5);
	assert.equal(doc.assets.length, 5);
	undo();
	assert.equal(doc.assets.length, 0);
});

test('the same video taken by the Library import and from a kit becomes the same asset, frame rate included', async () => {
	importer.openImport();
	last().props.onConfirm(['up-video-2'], [{ key: 'up-video-2', mediaType: 'video', filename: 'hands.mp4', origin: lib('up-video-2'), item: { id: 'up-video-2', fps: rateOf('up-video-2') } }]);
	await twice();
	const strip = (a) => {
		const { id, ...rest } = JSON.parse(JSON.stringify(a));
		return rest;
	};
	const fromLibrary = strip(doc.assets[0]);
	replaceDoc(emptyDoc((key) => key));
	ui.hostModal = false;
	importer.openKitImport();
	last().props.onConfirm(['kit:it_walk'], [picked(byId('it_walk'))]);
	await twice();
	assert.equal(fromLibrary.fps, 26);
	assert.deepEqual(strip(doc.assets[0]), fromLibrary);
});

test('a host whose kit item lacks media_ref (its form changed) is not told the file was deleted, but that the item could not be read', async () => {
	importer.pickKitMedia('image', 'Card', () => {});
	const odd = item({ id: 'it_odd', name: 'odd' });
	delete odd.media_ref;
	last().props.onPick(picked(odd));
	ui.hostModal = false;
	importer.openKitImport();
	last().props.kits.onLoad([{ ...MARA, items: [odd] }]);
	await twice();
	assert.deepEqual(toasts, [
		['warning', '“odd” could not be read: this PotionUI sends kit items in a form Video Producer does not know.'],
		['warning', '1 kit item left out: 1 in a form Video Producer cannot read']
	]);
});

test('what is left says the type the place takes, in English and in French', async () => {
	for (const locale of ['en', 'fr']) {
		setLocale(locale);
		toasts.length = 0;
		ui.hostModal = false;
		importer.openKitImport('audio');
		last().props.kits.onLoad([MARA]);
		await twice();
		const audio = toasts.at(-1)[1];
		toasts.length = 0;
		ui.hostModal = false;
		importer.openKitImport();
		last().props.kits.onLoad([MARA]);
		await twice();
		const media = toasts.at(-1)[1];
		if (locale === 'en') {
			assert.equal(audio, '5 kit items left out: 1 text, 1 file deleted from the library, 3 not sounds');
			assert.equal(media, '3 kit items left out: 1 text, 1 file deleted from the library, 1 not an image or a video');
		} else {
			assert.equal(audio, '5 éléments du kit laissés : 1 texte, 1 fichier supprimé de la bibliothèque, 3 qui ne sont pas des sons');
			assert.equal(media, '3 éléments du kit laissés : 1 texte, 1 fichier supprimé de la bibliothèque, 1 qui n’est ni une image ni une vidéo');
		}
	}
	setLocale('en');
});

test('an item with no file whose missing flag is not set is still left as deleted, never sent as an origin without a file', async () => {
	importer.openKitImport();
	last().props.kits.onLoad([{ ...MARA, items: [item({ id: 'it_x', media_ref: null, missing: false })] }]);
	await twice();
	assert.equal(doc.assets.length, 0);
	assert.equal(resolved.length, 0);
	assert.deepEqual(toasts, [['warning', '1 kit item left out: 1 file deleted from the library']]);
});

test('a second kit picker while one is open, or a Library picker, opens nothing', () => {
	importer.openKitImport();
	assert.equal(mounted.length, 1);
	importer.openKitImport('audio');
	importer.pickKitMedia('image', 'Card', () => {});
	importer.pickKitMany('image', 'Add', () => {});
	assert.equal(mounted.length, 1);
});

test('a file the server resolves to another type than the kit said is not imported, and is counted as failed', async () => {
	server.lie = 'audio';
	importer.openKitImport();
	last().props.onConfirm(['kit:it_face'], [picked(byId('it_face'))]);
	await twice();
	assert.equal(doc.assets.length, 0);
	assert.deepEqual(toasts, [['warning', '1 file could not be imported']]);
});

test('a place that adds says when a file could not be imported', async () => {
	const got = [];
	importer.pickKitMany('image', 'Add an image', (ids) => got.push(...ids), () => got.push('dismissed'));
	last().props.onConfirm(['kit:it_x'], [picked(item({ id: 'it_x', media_ref: 'gone-1' }))]);
	await twice();
	assert.deepEqual(toasts, [['warning', '1 file could not be imported']]);
	assert.deepEqual(got, ['dismissed']);
});

test('a host without MediaPickerModal: a single slot or a place that adds hears it was dismissed', () => {
	delete components.MediaPickerModal;
	const got = [];
	importer.pickKitMedia('image', 'Card', () => got.push('picked'), () => got.push('single'));
	importer.pickKitMany('image', 'Add', () => got.push('picked'), () => got.push('many'));
	assert.deepEqual(got, ['single', 'many']);
});

test('the palette, the File and Audio menus get the kit imports, hidden on a host without MediaPickerModal, with no new shortcut', () => {
	const ids = ['import-kit', 'audio-import-kit'];
	const inMenu = (menuId, id) => menus.find((m) => m.id === menuId).groups.flat().filter(shown).some((c) => c.id === id);
	for (const id of ids) {
		assert.equal(commandById(id).keys, null);
		assert.equal(shown(commandById(id)), true);
	}
	assert.equal(inMenu('file', 'import-kit'), true);
	assert.equal(inMenu('audio', 'audio-import-kit'), true);
	assert.equal(commandById('import-kit').label, 'Import from a kit…');
	commandById('import-kit').run();
	assert.equal(last().name, 'MediaPickerModal');
	assert.deepEqual(last().props.mediaTypes, ['image', 'video']);
	close(last());
	commandById('audio-import-kit').run();
	assert.deepEqual(last().props.mediaTypes, ['audio']);
	close(last());
	delete components.MediaPickerModal;
	for (const id of ids) assert.equal(shown(commandById(id)), false);
	assert.equal(inMenu('file', 'import-kit'), false);
	assert.equal(inMenu('audio', 'audio-import-kit'), false);
	assert.equal(shown(commandById('import')), true);
});

const turns = async (n = 30) => {
	for (let i = 0; i < n; i += 1) await Promise.resolve();
};

test('a frame rate the library never answers delays the import by RATE_WAIT_MS at most: the video then enters without one, as when the call fails', async (t) => {
	server.rateHang = true;
	importer.openKitImport();
	last().props.onConfirm(['kit:it_walk'], [picked(byId('it_walk'))]);
	t.mock.timers.enable({ apis: ['setTimeout'] });
	await turns();
	assert.equal(doc.assets.length, 0);
	t.mock.timers.tick(importer.RATE_WAIT_MS - 1);
	await turns();
	assert.equal(doc.assets.length, 0);
	t.mock.timers.tick(1);
	await turns();
	t.mock.timers.reset();
	assert.equal(importer.RATE_WAIT_MS, 4000);
	assert.deepEqual(doc.assets.map((a) => [a.origin.itemId, a.fps]), [['up-video-2', null]]);
	assert.deepEqual(toasts, [['success', '1 file imported']]);
});

test('the command search shows, before anything is typed, the same commands with or without kits, and finds the two kit imports when asked', () => {
	const ids = (list) => list.map((c) => c.id);
	const withKits = ids(paletteCommands(''));
	delete components.MediaPickerModal;
	const without = ids(paletteCommands(''));
	components.MediaPickerModal = { mount() {}, update() {}, unmount() {} };
	assert.equal(without.length, PALETTE_SIZE);
	assert.deepEqual(withKits, without);
	assert.ok(without.includes('import-cuts'));
	assert.deepEqual(ids(paletteCommands('kit')), ['import-kit', 'audio-import-kit']);
	assert.deepEqual(ids(paletteCommands('KIT')), ['import-kit', 'audio-import-kit']);
	delete components.MediaPickerModal;
	assert.deepEqual(ids(paletteCommands('kit')), []);
});

test('a picker that adds (many) refuses to work without onpickall, and every one the page mounts has it, so a whole kit is never one undo step per item', () => {
	assert.throws(() => importer.requireAll(true, null), /needs onpickall/);
	assert.doesNotThrow(() => importer.requireAll(true, () => {}));
	assert.doesNotThrow(() => importer.requireAll(false, null));
	const components = join(dirname(fileURLToPath(import.meta.url)), '..', 'components');
	const tags = [];
	for (const dir of readdirSync(components)) {
		const folder = join(components, dir);
		if (!statSync(folder).isDirectory()) continue;
		for (const file of readdirSync(folder).filter((name) => name.endsWith('.svelte'))) {
			const text = readFileSync(join(folder, file), 'utf-8');
			for (const tag of text.match(/<(MediaPicker|AudioPicker)\s[\s\S]*?\/>/g) ?? []) tags.push([file, tag]);
		}
	}
	const many = tags.filter(([, tag]) => /\smany[\s/>]/.test(tag));
	assert.deepEqual(many.map(([file]) => file).sort(), ['BibleAside.svelte', 'ShotEditor.svelte', 'ShotEditor.svelte']);
	assert.deepEqual(many.filter(([, tag]) => !tag.includes('onpickall=')), []);
});

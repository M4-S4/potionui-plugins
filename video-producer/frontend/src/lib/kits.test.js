import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { emptyLeft, fromKitItem, fromPicked, gatherPicks, kitsAvailable, leftTotal, pickKey } from './kits.js';
import { COUNT, makeKitPicks, seededKits } from '../../../tests/fixtures/make_kit_picks.mjs';

const fixture = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'tests', 'fixtures', 'kit_picks.json'), 'utf-8'));

function item(extra = {}) {
	return { id: 'it_00000001', kit_id: 'kt_00000001', kind: 'image', name: 'face', position: 0, media_ref: 'up-1', text: null, url: '/api/media/uploads/face.png', thumbnail_url: null, width: 512, height: 512, duration_seconds: null, missing: false, created_at: '', ...extra };
}

const kitPicked = (kitItem) => ({ key: `kit:${kitItem.id}`, mediaType: kitItem.kind, filename: kitItem.name, origin: { kind: 'kit', kitId: kitItem.kit_id, itemId: kitItem.id }, kit: { id: kitItem.kit_id, name: 'Mara', handle: 'mara' }, kitItem });

test('kitsAvailable: only a host that offers MediaPickerModal shows the kit entries, so a core without kits keeps its pickers', () => {
	assert.equal(kitsAvailable(), false);
	globalThis.window = { __potionui: { components: { UploadLibraryModal: {} } } };
	try {
		assert.equal(kitsAvailable(), false);
		window.__potionui.components.MediaPickerModal = {};
		assert.equal(kitsAvailable(), true);
	} finally {
		delete globalThis.window;
	}
});

test('fromPicked: a kit item becomes a library origin of its media_ref, never of the kit item id', () => {
	assert.deepEqual(fromPicked(kitPicked(item())), { origin: { kind: 'library', itemId: 'up-1' }, filename: 'face', mediaType: 'image' });
	assert.deepEqual(fromPicked(kitPicked(item({ kind: 'audio', name: 'voice', media_ref: 'up-9' }))), { origin: { kind: 'library', itemId: 'up-9' }, filename: 'voice', mediaType: 'audio' });
});

test('fromPicked: a library file and a history file keep the origin the plugin already stores', () => {
	assert.deepEqual(fromPicked({ key: 'up-2', mediaType: 'video', filename: 'street.mp4', origin: { kind: 'library', itemId: 'up-2' }, item: {} }), { origin: { kind: 'library', itemId: 'up-2' }, filename: 'street.mp4', mediaType: 'video' });
	assert.deepEqual(fromPicked({ key: 'g1:f1', mediaType: 'image', filename: 'a.png', origin: { kind: 'history', generationId: 'g1', fileId: '01KF' } }), { origin: { kind: 'history', generationId: 'g1', fileId: '01KF' }, filename: 'a.png', mediaType: 'image' });
});

test('fromPicked: a text item and an item whose library file was deleted are left with their reason, and a shape the page does not know is left as unread', () => {
	assert.deepEqual(fromPicked(kitPicked(item({ kind: 'text', media_ref: null, url: null, text: 'Mara is tall.' }))), { left: 'text' });
	assert.deepEqual(fromPicked(kitPicked(item({ media_ref: null, url: null, missing: true }))), { left: 'missing' });
	assert.deepEqual(fromPicked(kitPicked(item({ missing: true }))), { left: 'missing' });
	assert.deepEqual(fromPicked({ key: 'kit:it_1', mediaType: null, filename: null, origin: { kind: 'kit', kitId: '', itemId: 'it_1' } }), { left: 'unread' });
	assert.deepEqual(fromPicked(null), { left: 'unread' });
	assert.deepEqual(fromKitItem(undefined), { left: 'unread' });
});

test('gatherPicks: the whole kit gives its accepted media in kit order and counts what it leaves, by reason', () => {
	const kit = {
		id: 'kt_1',
		items: [
			item({ id: 'it_c', name: 'coat', position: 2, media_ref: 'up-c' }),
			item({ id: 'it_t', kind: 'text', name: 'bio', position: 1, media_ref: null, url: null, text: 'Tall.' }),
			item({ id: 'it_a', name: 'face', position: 0, media_ref: 'up-a' }),
			item({ id: 'it_v', kind: 'video', name: 'walk', position: 3, media_ref: 'up-v' }),
			item({ id: 'it_m', name: 'gone', position: 4, media_ref: null, url: null, missing: true })
		]
	};
	const { picks, left } = gatherPicks({ kits: [kit] }, ['image']);
	assert.deepEqual(picks.map((p) => p.origin.itemId), ['up-a', 'up-c']);
	assert.deepEqual(left, { text: 1, missing: 1, kind: 1, unread: 0 });
	assert.equal(leftTotal(left), 3);
	assert.equal(leftTotal(emptyLeft()), 0);
});

test('gatherPicks: one file reached twice (two items, an item and its whole kit) gives one pick, the first', () => {
	const face = item({ id: 'it_a', media_ref: 'up-a' });
	const kit = { id: 'kt_1', items: [face, item({ id: 'it_b', name: 'face copy', position: 1, media_ref: 'up-a' }), item({ id: 'it_c', name: 'coat', position: 2, media_ref: 'up-c' })] };
	const { picks, left } = gatherPicks({ items: [kitPicked(face)], kits: [kit] }, ['image', 'video']);
	assert.deepEqual(picks.map((p) => [p.origin.itemId, p.filename]), [['up-a', 'face'], ['up-c', 'coat']]);
	assert.deepEqual(left, emptyLeft());
});

test('pickKey: the same key the importer uses for library and history origins', () => {
	assert.equal(pickKey({ kind: 'library', itemId: 'up-1' }), 'library:up-1');
	assert.equal(pickKey({ kind: 'history', generationId: 'g', fileId: 'f' }), 'history:g:f');
	assert.equal(pickKey({ kind: 'kit', kitId: 'k', itemId: 'i' }), null);
});

function oracle(kit, allowed) {
	const seen = new Set();
	return [...kit.items]
		.sort((a, b) => a.position - b.position)
		.filter((it) => it.kind !== 'text' && !it.missing && it.media_ref && allowed.includes(it.kind))
		.filter((it) => !seen.has(it.media_ref) && seen.add(it.media_ref))
		.map((it) => it.media_ref);
}

test(`gatherPicks: on ${COUNT} seeded kits of up to 50 mixed items, the picks are exactly the accepted media in kit order, each a library origin of its media_ref`, () => {
	const cases = seededKits();
	assert.equal(cases.length, COUNT);
	assert.ok(cases.some(({ kit }) => kit.items.length === 50));
	assert.ok(cases.some(({ kit }) => kit.items.some((it) => it.missing)));
	assert.ok(cases.some(({ kit }) => new Set(kit.items.filter((it) => it.media_ref).map((it) => it.media_ref)).size < kit.items.filter((it) => it.media_ref).length));
	for (const [n, { kit, allowed }] of cases.entries()) {
		const { picks, left } = gatherPicks({ kits: [kit] }, allowed);
		assert.deepEqual(picks.map((p) => p.origin.itemId), oracle(kit, allowed), `kit ${n}`);
		assert.ok(picks.every((p) => p.origin.kind === 'library' && allowed.includes(p.mediaType)), `kit ${n}`);
		assert.equal(left.text, kit.items.filter((it) => it.kind === 'text').length, `kit ${n} texts`);
		assert.equal(left.missing, kit.items.filter((it) => it.kind !== 'text' && it.missing).length, `kit ${n} missing`);
		assert.equal(left.kind, kit.items.filter((it) => it.kind !== 'text' && !it.missing && !allowed.includes(it.kind)).length, `kit ${n} kinds`);
	}
});

test('tests/fixtures/kit_picks.json, which the server tests validate, is what make_kit_picks.mjs writes from the seeded kits', () => {
	assert.deepEqual(fixture, makeKitPicks());
});

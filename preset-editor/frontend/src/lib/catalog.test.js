import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adminPresetUrl, countByKind, coverUrl, filterPresets, localPresets, normalizeCatalog, normalizePreset, sortPresets } from './catalog.js';

const raw = [
	{ id: 'krea', name: 'Krea 2', version: '1.0.0', origin: { kind: 'marketplace', plugin_id: null, path: 'Krea2' }, installed: false, engine: 'native', category: 'image', modes: ['txt2img', 'enhance'], media: { cover: 'public/examples/potion.webp' }, tags: ['image'] },
	{ id: 'mine', name: 'My preset', origin: { kind: 'local', plugin_id: null, path: 'Mine/v1' }, installed: true, modes: ['txt2img'] },
	{ id: 'rtx', name: 'RTX', origin: { kind: 'plugin', plugin_id: 'nvidia-rtx-upscale', path: 'RTX-Upscale' }, installed: true },
	{ id: 'old', name: 'Old', source: 'custom', installed: false },
	{ name: 'no id' },
	'junk'
];

test('normalizePreset reads the origin, the installation state and the cover', () => {
	const krea = normalizePreset(raw[0]);
	assert.deepEqual(krea, {
		id: 'krea', name: 'Krea 2', version: '1.0.0', kind: 'marketplace', pluginId: null, path: 'Krea2', installed: false,
		engine: 'native', category: 'image', modes: ['txt2img', 'enhance'], tags: ['image'], cover: 'public/examples/potion.webp', mirrorOf: null, editable: false
	});
	const rtx = normalizePreset(raw[2]);
	assert.equal(rtx.kind, 'plugin');
	assert.equal(rtx.pluginId, 'nvidia-rtx-upscale');
	assert.equal(rtx.cover, null);
});

test('a preset without an origin falls back to the source field', () => {
	assert.equal(normalizePreset(raw[3]).kind, 'local');
	assert.equal(normalizePreset({ id: 'x', source: 'official' }).kind, 'marketplace');
	assert.equal(normalizePreset({ id: 'x' }).name, 'x');
});

test('normalizeCatalog drops entries without an id', () => {
	assert.deepEqual(normalizeCatalog(raw).map((entry) => entry.id), ['krea', 'mine', 'rtx', 'old']);
	assert.deepEqual(normalizeCatalog(null), []);
});

test('only local presets are editable and localPresets lists them by name', () => {
	const entries = normalizeCatalog(raw);
	assert.deepEqual(entries.map((entry) => entry.editable), [false, true, false, true]);
	assert.deepEqual(localPresets(entries).map((entry) => entry.id), ['mine', 'old']);
});

const mirrored = [
	{ id: 'mine', name: 'My preset', origin: { kind: 'local', plugin_id: null, path: 'Mine/v1' }, installed: true, is_mirror: false, source_preset_id: null },
	{ id: 'mine-anime', name: 'My preset, anime', origin: { kind: 'local', plugin_id: null, path: 'Mine/v1' }, installed: true, is_mirror: true, source_preset_id: 'mine' },
	{ id: 'krea-dark', name: 'Krea dark', origin: { kind: 'marketplace', plugin_id: null, path: 'Krea2' }, installed: true, is_mirror: true, source_preset_id: 'krea' },
	{ id: 'gone', name: 'Gone', version: '', installed: true, is_mirror: true, source_preset_id: 'deleted-one', mirror_state: 'source_missing' }
];

test('a mirror of a local preset is not editable and stays out of the Edit menu', () => {
	const entries = normalizeCatalog(mirrored);
	assert.deepEqual(entries.map((entry) => [entry.id, entry.kind, entry.mirrorOf, entry.editable]), [
		['mine', 'local', null, true],
		['mine-anime', 'local', 'mine', false],
		['krea-dark', 'marketplace', 'krea', false],
		['gone', 'marketplace', 'deleted-one', false]
	]);
	assert.deepEqual(localPresets(entries).map((entry) => entry.id), ['mine']);
	assert.deepEqual(filterPresets(entries, { kind: 'local' }).map((entry) => entry.id), ['mine', 'mine-anime']);
});

test('a preset naming itself as its source is not a mirror', () => {
	const entry = normalizePreset({ id: 'mine', origin: { kind: 'local', path: 'Mine/v1' }, source_preset_id: 'mine' });
	assert.equal(entry.mirrorOf, null);
	assert.equal(entry.editable, true);
	assert.equal(normalizePreset({ id: 'x', origin: { kind: 'local' }, source_preset_id: '' }).editable, true);
});

test('filterPresets combines the kind, the installation state and the query', () => {
	const entries = normalizeCatalog(raw);
	assert.deepEqual(filterPresets(entries, { kind: 'local' }).map((e) => e.id), ['mine', 'old']);
	assert.deepEqual(filterPresets(entries, { installed: 'installed' }).map((e) => e.id), ['mine', 'rtx']);
	assert.deepEqual(filterPresets(entries, { installed: 'available' }).map((e) => e.id), ['krea', 'old']);
	assert.deepEqual(filterPresets(entries, { query: 'KREA' }).map((e) => e.id), ['krea']);
	assert.deepEqual(filterPresets(entries, { query: 'mine/v1' }).map((e) => e.id), ['mine']);
	assert.deepEqual(filterPresets(entries, { query: 'image', kind: 'marketplace' }).map((e) => e.id), ['krea']);
	assert.deepEqual(filterPresets(entries, { query: '  ' }).length, 4);
});

test('sortPresets orders by name regardless of case', () => {
	const sorted = sortPresets(normalizeCatalog([{ id: 'b', name: 'beta' }, { id: 'a', name: 'Alpha' }, { id: 'c', name: 'alpha' }]));
	assert.deepEqual(sorted.map((e) => e.id), ['a', 'c', 'b']);
});

test('countByKind counts every kind', () => {
	assert.deepEqual(countByKind(normalizeCatalog(raw)), { all: 4, local: 2, marketplace: 1, plugin: 1 });
});

test('coverUrl targets the core media route with an encoded path', () => {
	const entry = normalizePreset({ id: 'a b', media: { cover: 'public/examples/my cover.webp' } });
	assert.equal(coverUrl(entry), '/api/media/presets/a%20b/public/examples/my%20cover.webp?size=thumbnail');
	assert.equal(coverUrl(entry, 'small'), '/api/media/presets/a%20b/public/examples/my%20cover.webp?size=small');
	assert.equal(coverUrl(normalizePreset({ id: 'x' })), null);
});

test('adminPresetUrl opens the preset detail in Admin → Presets', () => {
	assert.equal(adminPresetUrl('my id'), '/admin?tab=presets&id=my%20id');
});

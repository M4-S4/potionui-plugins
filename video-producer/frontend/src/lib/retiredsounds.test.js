import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { clean, renderComponent, textOf } from './svelte-harness.js';
import { RETIRED_ASSET_KEYS, emptyDoc, migrate, newAsset, workshopSound } from './starter.js';

const t = (key) => key;
const CASE = JSON.parse(readFileSync(new URL('../../../tests/fixtures/retired_sound_migration.json', import.meta.url), 'utf8'));
const { doc, ui, dispose } = await import('./state.svelte.js');
const { allCommands } = await import('./commands.js');
const playback = await import('./playback.svelte.js');
const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;
const CONSOLE = new URL('../components/mixer/Console.svelte', import.meta.url).href;
const MIXER_PANEL = new URL('../components/panels/MixerPanel.svelte', import.meta.url).href;

after(() => dispose());

function oldDoc() {
	const doc = emptyDoc(t);
	const part = structuredClone(CASE.doc);
	doc.assets = part.assets;
	doc.audio = part.audio;
	doc.references = part.references;
	doc.lanes.forEach((lane, i) => {
		if (part.laneModes[i]) lane.automation = part.laneModes[i];
	});
	return doc;
}

test('migrate drops the workshop sounds with their items and leaves their references without media, as the server does', () => {
	const doc = oldDoc();
	const before = structuredClone(doc);
	const next = migrate(doc);
	assert.deepEqual(doc, before);
	assert.deepEqual(next.assets.map((a) => a.id), CASE.expected.assets);
	assert.deepEqual(next.audio.map((item) => item.id), CASE.expected.audio);
	assert.deepEqual(Object.fromEntries(next.references.map((r) => [r.id, r.assetId])), CASE.expected.references);
	assert.ok(next.assets.every((a) => RETIRED_ASSET_KEYS.every((key) => !(key in a))));
	assert.ok(next.lanes.every((lane) => !('automation' in lane)));
	assert.deepEqual(migrate(next), next);
});

test('a workshop sound names a synthesis and has no file; a new asset and a new lane carry none of the retired fields', () => {
	assert.deepEqual(CASE.doc.assets.filter(workshopSound).map((a) => a.id), ['workshop-voice', 'workshop-wind']);
	assert.equal(workshopSound({ ...CASE.doc.assets[1], src: '/api/media/uploads/wind.wav' }), false);
	assert.ok(RETIRED_ASSET_KEYS.every((key) => !(key in newAsset({ kind: 'audio' }))));
	assert.ok(emptyDoc(t).lanes.every((lane) => !('automation' in lane)));
});

test('the Sound design workshop, the browser synthesis and the Auto button are gone', async () => {
	const ids = allCommands.map((c) => c.id);
	for (const id of ['voice', 'sd-ambience', 'sd-foley', 'sd-texture', 'sd-impact', 'sd-music']) assert.equal(ids.includes(id), false, id);
	ui.modal = { type: 'sound' };
	assert.equal(clean(await renderComponent(MODALS)).trim(), '');
	ui.modal = null;
	for (const name of ['audition', 'SYNTH_BY_ROLE', 'createOscillator']) assert.equal(name in playback, false, name);
	const migrated = migrate(oldDoc());
	Object.assign(doc, migrated);
	const console = await renderComponent(CONSOLE);
	assert.doesNotMatch(console, /automation|mixer\.auto/i);
	const panel = await renderComponent(MIXER_PANEL);
	assert.doesNotMatch(panel, /automation|soundMetaPrepared/i);
	for (const sound of doc.assets.filter((a) => a.kind === 'audio' && a.src)) assert.ok(textOf(panel).includes(sound.name), sound.name);
});

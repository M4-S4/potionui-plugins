import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { RETIRED_ASSET_KEYS, emptyDoc, migrate, newAsset, workshopSound } from './starter.js';

const t = (key) => key;
const CASE = JSON.parse(readFileSync(new URL('../../../tests/fixtures/retired_sound_migration.json', import.meta.url), 'utf8'));
const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

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

test('the Sound design workshop, the browser synthesis and the Auto button are gone', () => {
	const commands = source('./commands.js');
	for (const id of ['voice', 'sd-ambience', 'sd-foley', 'sd-texture', 'sd-impact', 'sd-music']) assert.ok(!commands.includes(`command('${id}'`), id);
	assert.doesNotMatch(commands, /modal\('sound'/);
	assert.doesNotMatch(source('../components/modals/Modals.svelte'), /SoundDesign|type === 'sound'/);
	assert.doesNotMatch(source('./playback.svelte.js'), /createOscillator|SYNTH_BY_ROLE|audition/);
	assert.doesNotMatch(source('../components/mixer/Console.svelte'), /automation|mixer\.auto/);
	assert.doesNotMatch(source('../components/panels/MixerPanel.svelte'), /soundMetaPrepared/);
});

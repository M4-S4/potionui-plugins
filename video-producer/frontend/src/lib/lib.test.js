import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DOMAINS, LOCALES, mergeDomains, translate } from '../i18n/core.js';
import { isUlid, ulid, ulidTime } from './ulid.js';
import { emptyDoc, starterDoc } from './starter.js';
import { detectMac, eventKey, formatShortcut, isActivationTarget, isTypingTarget, parseShortcut } from './keyboard.js';
import { HOST_ALIASES, HOST_MISSING, HOST_VARIANTS, hostIconName, hostIcons, paths } from './icons.js';

test('ulid: 26 Crockford base32 characters, time first, random tail', () => {
	const id = ulid(1_700_000_000_000);
	assert.equal(id.length, 26);
	assert.ok(isUlid(id));
	assert.equal(ulidTime(id), 1_700_000_000_000);
	assert.ok(!/[ILOU]/.test(id));
	const many = new Set(Array.from({ length: 500 }, () => ulid()));
	assert.equal(many.size, 500);
	assert.ok(ulid(1000) < ulid(2000));
	assert.ok(!isUlid('c1'));
	assert.equal(ulidTime('nope'), null);
});

test('shortcuts: Mac glyphs in the source editor order, Ctrl/Alt/Shift elsewhere', () => {
	const names = { space: 'Espace', backspace: 'Retour arrière' };
	assert.equal(formatShortcut('alt+mod+k', { mac: true, names }), '⌥ ⌘ K');
	assert.equal(formatShortcut('shift+mod+z', { mac: true, names }), '⇧ ⌘ Z');
	assert.equal(formatShortcut('ctrl+mod+r', { mac: true, names }), '⌃ ⌘ R');
	assert.equal(formatShortcut('alt+backspace', { mac: true, names }), '⌥ ⌫');
	assert.equal(formatShortcut('space', { mac: true, names }), 'Espace');
	assert.equal(formatShortcut('mod+minus', { mac: true, names }), '⌘ −');
	assert.equal(formatShortcut('mod+,', { mac: true, names }), '⌘ ,');
	assert.equal(formatShortcut('alt+mod+k', { mac: false, names }), 'Ctrl+Alt+K');
	assert.equal(formatShortcut('shift+mod+z', { mac: false, names }), 'Ctrl+Shift+Z');
	assert.equal(formatShortcut('ctrl+mod+1', { mac: false, names }), 'Ctrl+Alt+1');
	assert.equal(formatShortcut('alt+backspace', { mac: false, names }), 'Alt+Retour arrière');
	assert.equal(formatShortcut('mod+plus', { mac: false, names }), 'Ctrl++');
	assert.equal(formatShortcut('a', { mac: false, names }), 'A');
	assert.equal(formatShortcut('', { mac: false }), '');
	assert.deepEqual([...parseShortcut('shift+mod+e').mods].sort(), ['mod', 'shift']);
	assert.equal(detectMac({ platform: 'MacIntel' }), true);
	assert.equal(detectMac({ userAgentData: { platform: 'Windows' }, platform: 'Win32' }), false);
});

test('keys: Alt combinations read the physical key, focus rules recognise fields and buttons', () => {
	assert.equal(eventKey({ key: '˚', code: 'KeyK', altKey: true }), 'k');
	assert.equal(eventKey({ key: '¡', code: 'Digit1', altKey: true }), '1');
	assert.equal(eventKey({ key: 'Z', code: 'KeyZ', altKey: false }), 'z');
	assert.equal(eventKey({ key: ' ', code: 'Space' }), ' ');
	assert.ok(isTypingTarget({ tagName: 'TEXTAREA' }));
	assert.ok(isTypingTarget({ tagName: 'DIV', isContentEditable: true }));
	assert.ok(!isTypingTarget({ tagName: 'BUTTON' }));
	assert.ok(!isTypingTarget(null));
	assert.ok(isActivationTarget({ closest: (selector) => (selector.includes('[role="tab"]') ? {} : null) }));
	assert.ok(!isActivationTarget({ closest: () => null }));
	assert.ok(!isActivationTarget(null));
});

test('icons: 76 source editor icons, 28 missing names plus 10 vp- variants for the host, 6 aliases', () => {
	assert.equal(Object.keys(paths).length, 76);
	assert.equal(HOST_MISSING.length, 28);
	assert.equal(HOST_VARIANTS.length, 10);
	assert.equal(Object.keys(HOST_ALIASES).length, 6);
	for (const name of [...HOST_MISSING, ...HOST_VARIANTS, ...Object.keys(HOST_ALIASES)]) assert.ok(paths[name], `${name} has no paths`);
	for (const unused of ['lock', 'mountain', 'dots', 'sun', 'moon']) assert.ok(!hostIcons().some(([name]) => name === unused));
	assert.equal(hostIconName('x'), 'close');
	assert.equal(hostIconName('alert'), 'warning');
	assert.equal(hostIconName('play'), 'vp-play');
	assert.equal(hostIconName('redo'), 'vp-redo');
	assert.equal(hostIconName('route'), 'route');
	assert.equal(hostIconName('film'), 'film');
	const registered = hostIcons().map(([name]) => name);
	assert.equal(registered.length, 38);
	assert.equal(new Set(registered).size, 38);
	assert.ok(hostIcons().every(([, d]) => Array.isArray(d) && d.length > 0));
});

const i18nDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'i18n');
const dictionaries = Object.fromEntries(
	LOCALES.map((locale) => [locale, mergeDomains(Object.fromEntries(DOMAINS.map((domain) => [domain, JSON.parse(readFileSync(join(i18nDir, locale, `${domain}.json`), 'utf-8'))])))])
);
function translator(locale, missing) {
	return (key, params) => translate(dictionaries, locale, key, params, (k, l) => missing.push(`${l}:${k}`));
}

test('starterDoc: five linked shots to generate, a title, a marker, four empty lanes, no media, unique ULIDs', () => {
	const missing = [];
	const fr = starterDoc(translator('fr', missing));
	const en = starterDoc(translator('en', missing));
	assert.deepEqual(missing, []);
	assert.equal(fr.name, 'Aube sur le port');
	assert.equal(en.name, 'Dawn at the harbour');
	assert.deepEqual([fr.fps, fr.aspect, fr.resolution, fr.direction.mode], [25, '16:9', '1080p', 'FL2VA']);
	assert.match(fr.synopsis, /^Un petit port de pêche au lever du jour\./);
	assert.match(en.synopsis, /^A small fishing harbour at daybreak\./);
	for (const key of ['univers', 'personnages', 'photographie', 'palette', 'rythme']) assert.ok(fr.direction[key].length > 40 && en.direction[key].length > 40, key);
	assert.equal(fr.clips.length, 5);
	assert.deepEqual(
		fr.clips.map((c) => [c.start, c.dur, c.stage, c.assetId, c.take]),
		[0, 5, 10, 15, 20].map((start) => [start, 5, 'todo', null, null])
	);
	assert.deepEqual(
		fr.clips.map((c) => c.label),
		['Le port endormi', 'Les mains du pêcheur', 'Le départ', 'Les goélands', 'Vers le large']
	);
	assert.equal(fr.prompts.length, 5);
	fr.prompts.forEach((p, i) => {
		assert.equal(p.shotId, fr.clips[i].id);
		assert.deepEqual([p.start, p.dur, p.strength], [fr.clips[i].start, 5, 75]);
		assert.ok(p.text.length > 60);
		assert.notEqual(p.text, en.prompts[i].text);
	});
	assert.match(fr.prompts[0].text, /^Plan large d’un petit port de pêche à l’aube/);
	assert.match(en.prompts[0].text, /^Wide shot of a small fishing harbour at dawn/);
	assert.deepEqual(
		fr.titles.map(({ text, sub, start, dur }) => [text, sub, start, dur]),
		[['Aube sur le port', 'un départ à l’aube', 0, 4]]
	);
	assert.equal(en.titles[0].sub, 'a departure at dawn');
	assert.deepEqual(
		fr.markers.map(({ time, label, kind }) => [time, label, kind]),
		[[fr.clips[2].start, 'Départ', 'marker']]
	);
	assert.equal(en.markers[0].label, 'Cast off');
	assert.deepEqual(
		fr.lanes.map((l) => [l.id, l.name, l.role]),
		[
			['A1', 'Dialogue', 'Dialogue'],
			['A2', 'Musique', 'Musique'],
			['A3', 'Ambiance', 'Ambiance'],
			['A4', 'Bruitages', 'SFX']
		]
	);
	assert.deepEqual(
		fr.aux.map((a) => [a.id, a.name]),
		[
			['R1', 'Réverbération'],
			['D1', 'Délai']
		]
	);
	for (const key of ['audio', 'frames', 'controls', 'plans3d', 'references', 'results', 'scenes', 'profiles']) assert.deepEqual(fr[key], [], key);
	assert.deepEqual([fr.engine.seed, fr.engine.variants, fr.engine.backend, fr.engine.loras], [48121, 2, 'local', []]);
	const ids = [...fr.clips, ...fr.prompts, ...fr.titles, ...fr.markers].map((x) => x.id);
	assert.ok(ids.every(isUlid));
	assert.equal(new Set(ids).size, ids.length);
	const other = starterDoc(translator('fr', missing));
	assert.ok(other.clips.every((c, i) => c.id !== fr.clips[i].id));
});

test('emptyDoc: an untitled project with no shot and the four empty lanes', () => {
	const missing = [];
	const fr = emptyDoc(translator('fr', missing));
	const en = emptyDoc(translator('en', missing));
	assert.deepEqual(missing, []);
	assert.equal(fr.name, 'Projet sans titre');
	assert.equal(en.name, 'Untitled project');
	assert.equal(fr.synopsis, '');
	for (const key of ['clips', 'prompts', 'titles', 'markers', 'audio', 'frames', 'results', 'scenes']) assert.deepEqual(fr[key], [], key);
	assert.deepEqual(
		en.lanes.map((l) => [l.id, l.name, l.role]),
		[
			['A1', 'Dialogue', 'Dialogue'],
			['A2', 'Music', 'Musique'],
			['A3', 'Ambience', 'Ambiance'],
			['A4', 'Sound effects', 'SFX']
		]
	);
	assert.equal(fr.direction.mode, 'FL2VA');
});

test('readiness: an FL2VA range without a frame warns instead of blocking, so the starter project generates as is', () => {
	const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'state.svelte.js'), 'utf-8');
	const readiness = source.slice(source.indexOf('export function readiness'), source.indexOf('export function startGeneration'));
	assert.match(readiness, /doc\.direction\.mode === 'FL2VA' && !items\.frames\.length\) warnings\.push\(t\('lib\.warn\.noFrame'\)\)/);
	assert.doesNotMatch(readiness, /missing\.push\([^)]*(needFrame|noFrame)/);
	assert.ok(!('lib.block.needFrame' in dictionaries.en) && !('lib.block.needFrame' in dictionaries.fr));
	assert.equal(dictionaries.en['lib.warn.noFrame'], 'No frame in the range: the shots will be generated from text only.');
	assert.equal(dictionaries.fr['lib.warn.noFrame'], 'Aucune frame dans la plage : les plans seront générés à partir du texte seul.');
	const missing = [];
	const doc = starterDoc(translator('en', missing));
	assert.equal(doc.direction.mode, 'FL2VA');
	assert.equal(doc.frames.length, 0);
	assert.ok(doc.prompts.every((p) => p.text.trim()));
});

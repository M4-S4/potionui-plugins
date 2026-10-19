import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DOMAINS, LOCALES, mergeDomains, translate } from '../i18n/core.js';
import { isUlid, ulid, ulidTime } from './ulid.js';
import { emptyDoc, migrate, newAsset, promptLanguageOf, starterDoc } from './starter.js';
import {
	activateOnKey,
	detectMac,
	eventKey,
	findShortcut,
	formatShortcut,
	isActivationKey,
	isActivationTarget,
	isSingleKey,
	isTypingTarget,
	matchShortcut,
	parseShortcut,
	requiredMods
} from './keyboard.js';
import { HOST_ALIASES, HOST_MISSING, HOST_VARIANTS, hostIconName, hostIcons, paths } from './icons.js';
import { closeLayer, closeTopLayer, isTopLayer, leaveLayer, openLayer } from './focus.js';

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
	assert.equal(eventKey({ key: 'Dead', code: 'BracketLeft', altKey: true }), '[');
	assert.equal(eventKey({ key: '}', code: 'BracketRight', altKey: true }), ']');
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
	for (const key of ['audio', 'frames', 'controls', 'plans3d', 'references', 'scenes', 'profiles', 'assets']) assert.deepEqual(fr[key], [], key);
	assert.ok(!('results' in fr), 'the document has no results field');
	assert.deepEqual([fr.engine.seed, fr.engine.variants, fr.engine.backend, fr.engine.preset, fr.engine.model, fr.engine.loras], [48121, 2, '', null, null, []]);
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
	for (const key of ['clips', 'prompts', 'titles', 'markers', 'audio', 'frames', 'scenes', 'assets']) assert.deepEqual(fr[key], [], key);
	assert.ok(!('results' in fr));
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

test('readiness: an FL2VA shot without a frame warns instead of blocking, so the starter project generates as is', () => {
	const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'production.svelte.js'), 'utf-8');
	const readiness = source.slice(source.indexOf('export function readiness'), source.indexOf('function blockedText'));
	assert.match(readiness, /for \(const block of est\.blocks\) missing\.push\(noteText\(block\)\)/);
	assert.match(readiness, /for \(const warning of est\.warnings\)/);
	assert.doesNotMatch(readiness, /missing\.push\([^)]*(needFrame|noFrame)/);
	assert.match(source, /code === 'fl2va_no_frame'\) return t\('generation\.warn\.noFrame'/);
	assert.ok(!('lib.block.needFrame' in dictionaries.en) && !('lib.block.needFrame' in dictionaries.fr));
	assert.equal(dictionaries.en['generation.warn.noFrame'], '“{shot}” has no linked frame: it will be generated from text only.');
	assert.equal(dictionaries.fr['generation.warn.noFrame'], '« {shot} » n’a pas de frame liée : il sera généré à partir du texte seul.');
	const missing = [];
	const doc = starterDoc(translator('en', missing));
	assert.equal(doc.direction.mode, 'FL2VA');
	assert.equal(doc.frames.length, 0);
	assert.ok(doc.prompts.every((p) => p.text.trim()));
});

test('readiness: a text-only engine that ignores a shot frame warns about that shot in both languages, as a warning rather than a note', () => {
	const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'production.svelte.js'), 'utf-8');
	assert.match(source, /code === 'text_only_preset'\) return t\('generation\.warn\.textOnly', \{ shot: shotName\(data\.shot_id\) \}\)/);
	assert.match(source, /const INFO_WARNINGS = \['time_unknown', 'vram_unknown'\];/);
	assert.equal(dictionaries.en['generation.warn.textOnly'], 'This engine generates from text only: the frames linked to “{shot}” will not be used.');
	assert.equal(dictionaries.fr['generation.warn.textOnly'], 'Ce moteur génère à partir du texte seul : les frames liées à « {shot} » ne seront pas utilisées.');
	const missing = [];
	assert.equal(translator('en', missing)('generation.warn.textOnly', { shot: 'Opening' }), 'This engine generates from text only: the frames linked to “Opening” will not be used.');
	assert.equal(translator('fr', missing)('generation.warn.textOnly', { shot: 'Ouverture' }), 'Ce moteur génère à partir du texte seul : les frames liées à « Ouverture » ne seront pas utilisées.');
	assert.deepEqual(missing, []);
});

test('migrate: the simulated scenes go, their 3D shots lose the scene, empty 3D captures go, old camera keys become pos/target', () => {
	const old = {
		name: 'Old',
		scenes: [
			{ id: 'sample', kind: 'sample', name: 'Sample scene' },
			{ id: 'file', kind: 'file', name: 'room.splat', file: '/data/room.splat' },
			{ id: 's1', kind: 'splatfile', name: 'Room', fileId: 'f1', format: 'ply', view: null }
		],
		plans3d: [
			{ id: 'p1', shotId: 'c1', sceneId: 'sample', name: 'Orbit', start: 0, dur: 5, keyframes: [{ id: 'k1', t: 0, az: 90, el: 0, dist: 10, focal: 30, height: 1.5 }] },
			{ id: 'p2', shotId: 'c2', sceneId: 's1', name: 'Kept', start: 5, dur: 3, keyframes: [] },
			{ id: 'p3', shotId: null, sceneId: 'file', name: 'File', start: 8, dur: 2, source: 'trajectory', preset: 'orbit', amount: 12, camera: null, keyframes: [] }
		],
		frames: [
			{ id: 'f1', shotId: 'c1', time: 1, assetId: null, role: 'Capture 3D', strength: 80 },
			{ id: 'f2', shotId: 'c1', time: 2, assetId: 'a1', role: 'Capture 3D', strength: 80 },
			{ id: 'f3', shotId: 'c1', time: 3, assetId: null, role: 'first', strength: 100 }
		],
		controls: [{ id: 'g1', source: 'scene3d', stale: false }]
	};
	const doc = migrate(old);
	assert.deepEqual(doc.scenes.map((s) => s.id), ['s1']);
	assert.deepEqual(doc.plans3d.map((p) => p.sceneId), [null, 's1', null]);
	assert.deepEqual(doc.frames.map((f) => f.id), ['f2', 'f3']);
	assert.deepEqual(doc.controls, old.controls);
	const [p1, p2, p3] = doc.plans3d;
	assert.deepEqual([p1.source, p1.preset, p1.amount, p1.camera], ['manual', null, null, null]);
	assert.deepEqual([p3.source, p3.preset, p3.amount], ['trajectory', 'orbit', 12]);
	assert.deepEqual(p2.keyframes, []);
	const [k] = p1.keyframes;
	assert.deepEqual([k.id, k.t, k.target, k.focal, k.roll], ['k1', 0, [0, 1.5, 0], 30, 0]);
	assert.ok(Math.abs(k.pos[0] - 10) < 1e-6 && Math.abs(k.pos[1] - 1.5) < 1e-6 && Math.abs(k.pos[2]) < 1e-6);
	assert.ok(!('az' in k));
	assert.equal(old.scenes.length, 3, 'the input is not changed');
	assert.deepEqual(migrate(doc), doc);
	assert.equal(migrate(null), null);
	const bare = { name: 'Bare' };
	assert.deepEqual(migrate(bare), bare);
	const fresh = emptyDoc(translator('en', []));
	assert.deepEqual(migrate(fresh), fresh);
});

test('newAsset: every field of the persisted asset contract, null when it does not apply', () => {
	const a = newAsset({ kind: 'image', name: 'still.png', src: '/api/media/uploads/still.png', origin: { kind: 'library', itemId: 'i1' } });
	assert.deepEqual(Object.keys(a), ['id', 'kind', 'name', 'src', 'origin', 'srcDur', 'width', 'height', 'fps', 'res', 'generated', 'quality', 'resultId', 'role', 'synth', 'transcript', 'character', 'lipSync']);
	assert.ok(isUlid(a.id));
	assert.deepEqual([a.srcDur, a.width, a.height, a.fps, a.res, a.quality, a.resultId, a.role, a.synth, a.transcript, a.character, a.lipSync], Array(12).fill(null));
	assert.equal(a.generated, false);
	assert.equal(newAsset().kind, 'video');
	assert.notEqual(newAsset().id, newAsset().id);
});

test('prompt language: a project setting, English by default, that only decides the language of the starter direction and prompts', () => {
	const missing = [];
	const fr = translator('fr', missing);
	const en = translator('en', missing);
	const doc = starterDoc(fr, en, 'en');
	assert.deepEqual(missing, []);
	assert.equal(doc.promptLanguage, 'en');
	assert.equal(doc.name, 'Aube sur le port');
	assert.match(doc.synopsis, /^Un petit port de pêche au lever du jour\./);
	assert.equal(doc.clips[0].label, 'Le port endormi');
	assert.equal(doc.titles[0].text, 'Aube sur le port');
	assert.match(doc.prompts[0].text, /^Wide shot of a small fishing harbour at dawn/);
	assert.deepEqual(doc.direction, starterDoc(en, en, 'en').direction);
	assert.match(starterDoc(fr, fr, 'fr').prompts[0].text, /^Plan large d’un petit port de pêche à l’aube/);
	assert.equal(starterDoc(fr, fr, 'fr').promptLanguage, 'fr');
	assert.equal(starterDoc(fr).promptLanguage, 'en');
	assert.equal(emptyDoc(fr).promptLanguage, 'en');
	assert.equal(emptyDoc(fr, 'fr').promptLanguage, 'fr');
	assert.deepEqual(['en', 'fr', 'de', undefined, null].map(promptLanguageOf), ['en', 'fr', 'en', 'en', 'en']);
});

test('window layers: Escape closes only the foreground window, a replaced window hands its return focus on', () => {
	const saved = globalThis.document;
	const calls = [];
	const box = (name) => ({ contains: (node) => node?.inside === name });
	const timeline = { inside: null };
	globalThis.document = { activeElement: timeline };
	try {
		const editor = openLayer(box('editor'), { refocus: () => calls.push('refocus editor'), close: () => calls.push('close editor') });
		assert.equal(editor.previous, timeline);
		document.activeElement = { inside: 'editor' };
		const library = openLayer(box('library'), { refocus: () => calls.push('refocus library'), close: () => calls.push('close library') });
		assert.ok(isTopLayer(library) && !isTopLayer(editor));
		leaveLayer(editor);
		assert.equal(closeTopLayer(), true);
		assert.deepEqual(calls, ['close library']);
		document.activeElement = null;
		closeLayer(editor);
		assert.equal(library.previous, timeline);
		assert.deepEqual(calls, ['close library', 'refocus library']);
		document.activeElement = { inside: 'library' };
		leaveLayer(library);
		assert.equal(closeTopLayer(), false);
		closeLayer(library);
		closeLayer(library);
		assert.deepEqual(calls, ['close library', 'refocus library']);
	} finally {
		globalThis.document = saved;
	}
});

const press = (key, { ctrl = false, meta = false, alt = false, shift = false, code, repeat = false } = {}) => ({ key, code, ctrlKey: ctrl, metaKey: meta, altKey: alt, shiftKey: shift, repeat });

test('shortcut match: a combination fires only with exactly the modifiers it declares', () => {
	assert.ok(matchShortcut(press('i', { ctrl: true }), 'mod+i', false));
	assert.ok(!matchShortcut(press('I', { ctrl: true, shift: true }), 'mod+i', false));
	assert.ok(!matchShortcut(press('J', { ctrl: true, shift: true }), 'mod+j', false));
	assert.ok(!matchShortcut(press('i', { ctrl: true, alt: true, code: 'KeyI' }), 'mod+i', false));
	assert.ok(!matchShortcut(press('i', { ctrl: true, meta: true }), 'mod+i', false));
	assert.ok(matchShortcut(press('i', { meta: true }), 'mod+i', true));
	assert.ok(!matchShortcut(press('ˆ', { meta: true, alt: true, code: 'KeyI' }), 'mod+i', true));
	assert.ok(!matchShortcut(press('∆', { meta: true, alt: true, code: 'KeyJ' }), 'mod+j', true));
	assert.ok(!matchShortcut(press('˚', { meta: true, alt: true, code: 'KeyK' }), 'mod+k', true));
	assert.ok(!matchShortcut(press('i', { ctrl: true }), 'mod+i', true));
	assert.ok(matchShortcut(press('k', { ctrl: true }), 'mod+k', false));
	assert.ok(!matchShortcut(press('k', { ctrl: true }), 'mod+k', true));
	assert.ok(matchShortcut(press('k', { meta: true }), 'mod+k', true));
	assert.ok(!matchShortcut(press('k', { ctrl: true, alt: true, code: 'KeyK' }), 'mod+k', false));
});

test('shortcut match: Ctrl+Alt on Windows and Linux, Control+Command on a Mac, Alt alone, plain keys', () => {
	assert.deepEqual(requiredMods(parseShortcut('ctrl+mod+1').mods, false), { ctrl: true, meta: false, alt: true, shift: false });
	assert.deepEqual(requiredMods(parseShortcut('ctrl+mod+1').mods, true), { ctrl: true, meta: true, alt: false, shift: false });
	assert.deepEqual(requiredMods(parseShortcut('alt+mod+g').mods, false), { ctrl: true, meta: false, alt: true, shift: false });
	assert.ok(matchShortcut(press('¡', { ctrl: true, alt: true, code: 'Digit1' }), 'ctrl+mod+1', false));
	assert.ok(!matchShortcut(press('1', { ctrl: true }), 'ctrl+mod+1', false));
	assert.ok(matchShortcut(press('1', { ctrl: true, meta: true }), 'ctrl+mod+1', true));
	assert.ok(!matchShortcut(press('1', { meta: true }), 'ctrl+mod+1', true));
	assert.ok(matchShortcut(press('g', { ctrl: true, alt: true, code: 'KeyG' }), 'alt+mod+g', false));
	assert.ok(!matchShortcut(press('g', { ctrl: true }), 'alt+mod+g', false));
	assert.ok(matchShortcut(press('[', { alt: true, code: 'BracketLeft' }), 'alt+[', false));
	assert.ok(matchShortcut(press('x', { alt: true, code: 'KeyX' }), 'alt+x', true));
	assert.ok(!matchShortcut(press('x', { alt: true, ctrl: true, code: 'KeyX' }), 'alt+x', true));
	assert.ok(matchShortcut(press('Backspace', { alt: true }), 'alt+backspace', true));
	assert.ok(!matchShortcut(press('Backspace', { alt: true }), 'backspace', true));
	assert.ok(matchShortcut(press('Backspace'), 'backspace', false));
	assert.ok(matchShortcut(press('a'), 'a', false));
	assert.ok(!matchShortcut(press('a', { shift: true }), 'a', false));
	assert.ok(!matchShortcut(press('A', { shift: true }), 'a', false));
	assert.ok(!matchShortcut(press('a', { ctrl: true }), 'a', false));
	assert.ok(!matchShortcut(press('a', { meta: true }), 'a', false));
	assert.ok(matchShortcut(press(' '), 'space', false));
	assert.ok(!matchShortcut(press(' ', { shift: true }), 'space', false));
	assert.ok(matchShortcut(press('Z', { ctrl: true, shift: true }), 'shift+mod+z', false));
	assert.ok(!matchShortcut(press('z', { ctrl: true }), 'shift+mod+z', false));
	assert.ok(!matchShortcut(press('z', { ctrl: true, shift: true }), 'mod+z', false));
	assert.ok(!matchShortcut(press('x'), '', false));
});

test('shortcut match: the shift of a punctuation key depends on the layout, so Ctrl+/ works on a French keyboard too', () => {
	assert.ok(matchShortcut(press('/', { ctrl: true }), 'mod+/', false));
	assert.ok(matchShortcut(press('/', { ctrl: true, shift: true }), 'mod+/', false));
	assert.ok(matchShortcut(press('/', { meta: true, shift: true }), 'mod+/', true));
	assert.ok(!matchShortcut(press('/', { ctrl: true, alt: true, code: 'Slash' }), 'mod+/', false));
	assert.ok(!matchShortcut(press('/'), 'mod+/', false));
	assert.ok(matchShortcut(press(',', { ctrl: true }), 'mod+,', false));
	assert.ok(!matchShortcut(press(',', { ctrl: true, alt: true }), 'mod+,', false));
});

test('findShortcut: the first binding that matches, nothing when no binding does', () => {
	const bindings = [
		{ spec: 'mod+z', id: 'undo' },
		{ spec: 'shift+mod+z', id: 'redo' },
		{ spec: 'a', id: 'tool' }
	];
	assert.equal(findShortcut(press('z', { ctrl: true }), bindings, false).id, 'undo');
	assert.equal(findShortcut(press('Z', { ctrl: true, shift: true }), bindings, false).id, 'redo');
	assert.equal(findShortcut(press('a'), bindings, false).id, 'tool');
	assert.equal(findShortcut(press('a', { alt: true, code: 'KeyA' }), bindings, false), null);
	assert.equal(findShortcut(press('z', { meta: true }), bindings, false), null);
});

test('single keys are the letters and digits alone; activation keys are Enter and Space on the element itself', () => {
	assert.ok(isSingleKey('a'));
	assert.ok(isSingleKey('1'));
	assert.ok(!isSingleKey('mod+a'));
	assert.ok(!isSingleKey('shift+a'));
	assert.ok(!isSingleKey('space'));
	assert.ok(!isSingleKey('backspace'));
	const target = {};
	const on = (key, extra = {}) => ({
		key,
		target,
		currentTarget: target,
		repeat: false,
		ctrlKey: false,
		metaKey: false,
		altKey: false,
		shiftKey: false,
		preventDefault() {
			this.prevented = true;
		},
		...extra
	});
	assert.ok(isActivationKey(on('Enter')));
	assert.ok(isActivationKey(on(' ')));
	assert.ok(!isActivationKey(on('a')));
	assert.ok(!isActivationKey(on('Enter', { ctrlKey: true })));
	assert.ok(!isActivationKey(on('Enter', { repeat: true })));
	assert.ok(!isActivationKey(on('Enter', { target: {} })));
	const calls = [];
	const space = on(' ');
	assert.equal(
		activateOnKey(space, () => calls.push('run')),
		true
	);
	assert.equal(space.prevented, true);
	const other = on('x');
	assert.equal(
		activateOnKey(other, () => calls.push('never')),
		false
	);
	assert.equal(other.prevented, undefined);
	assert.deepEqual(calls, ['run']);
});

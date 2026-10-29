import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { clean, renderComponent } from './svelte-harness.js';
import { findShortcut, formatShortcut, matchShortcut, parseShortcut, requiredMods } from './keyboard.js';

const here = dirname(fileURLToPath(import.meta.url));
const plugin = join(here, '..', '..', '..');
const { ui, dispose } = await import('./state.svelte.js');
const { allCommands, handleKeydown, pointerShortcuts } = await import('./commands.js');
const MODALS = new URL('../components/modals/Modals.svelte', import.meta.url).href;
const commands = allCommands.map((c) => ({ id: c.id, spec: c.keys, alias: c.alias, repeat: c.repeat, global: c.global }));

globalThis.document = { body: {}, querySelector: () => null };

after(() => {
	dispose();
	delete globalThis.document;
});
const bound = commands.filter((c) => c.spec);
const specs = bound.flatMap((c) => [c.spec, c.alias].filter(Boolean));
const SYMBOL = /^[^a-z0-9\s]$/;
const FIXED = ['delete', 'home', 'end', 'arrowleft', 'arrowright', 'shift+arrowleft', 'shift+arrowright', 'arrowup', 'arrowdown', 'shift+mod+arrowleft', 'shift+mod+arrowright', '<', '>', 'shift+r', 'enter'];

const BROWSER = [
	'mod+n',
	'mod+t',
	'mod+w',
	'mod+tab',
	'ctrl+tab',
	'shift+mod+n',
	'shift+mod+t',
	'shift+mod+w',
	'mod+l',
	'mod+f',
	'mod+c',
	'mod+v',
	'mod+x',
	'mod+a',
	'mod+p',
	'mod+r',
	'mod+q',
	'mod+h',
	'mod+plus',
	'mod+minus',
	'mod+0',
	'shift+mod+i',
	'shift+mod+j',
	'shift+mod+c',
	'shift+mod+k',
	'shift+mod+m',
	'alt+mod+i',
	'alt+mod+j',
	'alt+mod+k',
	'alt+mod+c',
	'alt+mod+u'
];

function eventFor(spec, mac, flip = null) {
	const { key, mods } = parseShortcut(spec);
	const need = requiredMods(mods, mac);
	const on = { ctrl: need.ctrl, meta: need.meta, alt: need.alt, shift: need.shift };
	if (flip) on[flip] = !on[flip];
	const named = { space: ' ', plus: '+', minus: '-', backspace: 'Backspace', delete: 'Delete', home: 'Home', arrowleft: 'ArrowLeft', arrowright: 'ArrowRight' }[key];
	const code = /^[a-z]$/.test(key) ? `Key${key.toUpperCase()}` : /^[0-9]$/.test(key) ? `Digit${key}` : key === '[' ? 'BracketLeft' : key === ']' ? 'BracketRight' : undefined;
	return { key: on.shift && key.length === 1 ? key.toUpperCase() : (named ?? key), code, ctrlKey: on.ctrl, metaKey: on.meta, altKey: on.alt, shiftKey: on.shift };
}

test('shortcuts: 42 commands carry a shortcut, each one different, and the others show none', () => {
	assert.equal(commands.length, 101);
	assert.deepEqual(
		bound.map((c) => c.id),
		[
			'prefs',
			'shortcuts',
			'palette',
			'open',
			'save',
			'import',
			'import-local',
			'export',
			'export-xml',
			'undo',
			'redo',
			'duplicate',
			'delete',
			'tool-select',
			'tool-range',
			'tool-blade',
			'blade',
			'audio-slice',
			'audio-join',
			'trim-start',
			'trim-end',
			'in',
			'out',
			'clear-range',
			'marker',
			'takes',
			'shot-editor',
			'promote',
			'fav',
			'reject',
			'unflag',
			'story-window',
			'generate',
			'queue',
			'play',
			'snap',
			'view-review',
			'view-direction',
			'view-bible',
			'view-references',
			'sidebar',
			'assistant'
		]
	);
	assert.deepEqual(
		commands.filter((c) => c.alias).map((c) => [c.id, c.spec, c.alias]),
		[['redo', 'shift+mod+z', 'mod+y']]
	);
	assert.equal(new Set(specs).size, specs.length);
	for (const spec of FIXED) assert.ok(!specs.includes(spec), `${spec} is a fixed key`);
	const labels = specs.map((spec) => formatShortcut(spec, { mac: false }));
	assert.equal(new Set(labels).size, labels.length, 'two commands would show the same combination on Windows and Linux');
	const macLabels = specs.map((spec) => formatShortcut(spec, { mac: true }));
	assert.equal(new Set(macLabels).size, macLabels.length, 'two commands would show the same combination on a Mac');
});

test('shortcuts: none belongs to the browser, none opens its developer tools, no Ctrl+digit', () => {
	for (const spec of specs) {
		assert.ok(!BROWSER.includes(spec), `${spec} belongs to the browser`);
		const { key, mods } = parseShortcut(spec);
		if (/^[0-9]$/.test(key)) assert.ok(spec === 'ctrl+mod+1' || /^alt\+[1-4]$/.test(spec), `${spec} is a digit combination`);
		if (mods.has('mod') && mods.has('alt')) assert.ok(!['i', 'j', 'k', 'c', 'u'].includes(key), `${spec} is a developer tools combination on a Mac`);
		if (mods.has('mod') && mods.has('shift')) assert.ok(!['i', 'j', 'c', 'k', 'm'].includes(key), `${spec} is a developer tools combination`);
	}
});

test('shortcuts: every shortcut that is shown fires with exactly its keys and with no other combination', () => {
	const bindings = [...specs, ...FIXED].map((spec) => ({ spec }));
	for (const mac of [false, true]) {
		for (const spec of specs) {
			const hit = findShortcut(eventFor(spec, mac), bindings, mac);
			assert.equal(hit?.spec, spec, `${spec} does not fire on ${mac ? 'a Mac' : 'Windows'}`);
			const { key, mods } = parseShortcut(spec);
			for (const flip of ['ctrl', 'meta', 'alt', 'shift']) {
				if (flip === 'shift' && SYMBOL.test(key) && !mods.has('shift')) continue;
				const other = findShortcut(eventFor(spec, mac, flip), bindings, mac);
				assert.notEqual(other?.spec, spec, `${spec} also fires with ${flip} flipped on ${mac ? 'a Mac' : 'Windows'}`);
			}
		}
	}
	assert.ok(matchShortcut(eventFor('mod+k', true), 'mod+k', true));
	assert.ok(!matchShortcut({ key: 'k', ctrlKey: true, metaKey: false, altKey: false, shiftKey: false }, 'mod+k', true));
});

test('shortcuts: the key handler looks every key up in the table of the commands, with the guards the guides describe', async () => {
	assert.deepEqual(commands.filter((c) => c.repeat).map((c) => c.id), ['undo', 'redo', 'delete']);
	assert.deepEqual(commands.filter((c) => c.global).map((c) => c.id), ['shortcuts', 'palette']);
	const press = (spec, extra = {}) => {
		const e = { ...eventFor(spec, false), target: null, repeat: false, prevented: false, preventDefault() { this.prevented = true; }, ...extra };
		handleKeydown(e, null);
		return e;
	};
	Object.assign(ui, { modal: null, paletteOpen: false, hostModal: false, singleKeyShortcuts: true, workspace: 'mixer', snapping: true, selection: null });
	press('n');
	assert.equal(ui.snapping, false);
	ui.singleKeyShortcuts = false;
	press('n');
	assert.equal(ui.snapping, false);
	ui.singleKeyShortcuts = true;
	press('n', { target: { tagName: 'INPUT', type: 'text' } });
	assert.equal(ui.snapping, false);
	ui.modal = { type: 'about' };
	press('n');
	assert.equal(ui.snapping, false);
	press('mod+k');
	assert.equal(ui.paletteOpen, true);
	Object.assign(ui, { paletteOpen: false, modal: null, hostModal: true });
	assert.equal(press('mod+g').prevented, true);
	press('n');
	assert.equal(ui.snapping, false);
	ui.hostModal = false;
	assert.deepEqual([press('n', { repeat: true }).prevented, ui.snapping], [true, false]);
	press('n');
	assert.equal(ui.snapping, true);
	assert.equal(press('arrowup').prevented, false);
	ui.workspace = 'storyboard';
	assert.equal(press('arrowup').prevented, true);
	ui.workspace = 'mixer';
	ui.modal = { type: 'shortcuts' };
	const html = clean(await renderComponent(MODALS));
	const redo = allCommands.find((c) => c.id === 'redo');
	assert.ok(html.includes(`<kbd class="vp-kbd text-xs">${redo.key}</kbd><kbd class="vp-kbd text-xs">${redo.aliasKey}</kbd>`));
	assert.equal((html.match(/<kbd class="vp-kbd text-xs">/g) ?? []).length, bound.length + bound.filter((c) => c.alias).length + pointerShortcuts().length);
	ui.modal = null;
});

function tableOf(file) {
	const text = readFileSync(join(plugin, 'docs', file), 'utf-8').replace(/\r\n/g, '\n');
	const start = text.indexOf('## 16.');
	const section = text.slice(start, text.indexOf('## 17.'));
	const rows = section
		.split('\n')
		.filter((line) => line.startsWith('|') && !line.startsWith('|---') && !/^\| (Shortcut|Raccourci) \|/.test(line))
		.map((line) => line.split('|').slice(1, 3).map((cell) => cell.trim()));
	return { heading: section.split('\n')[0], rows, section };
}

function names(locale) {
	const commandsJson = JSON.parse(readFileSync(join(here, '..', 'i18n', locale, 'commands.json'), 'utf-8'));
	return { space: commandsJson['kbd.space'], backspace: commandsJson['kbd.backspace'] };
}

const GUIDE_FIXED = {
	'user-guide.md': ['Esc', 'Delete', 'Left arrow', 'Right arrow', 'Home', 'End', 'Up arrow', 'Down arrow', 'Enter', '<', '>', 'Ctrl+Shift+Left arrow', 'Ctrl+Shift+Right arrow', 'Shift+R', 'Ctrl+click', 'Shift+click', 'Ctrl+Shift+click'],
	'user-guide.fr.md': ['Échap', 'Suppr', 'Flèche gauche', 'Flèche droite', 'Home', 'Fin', 'Flèche haut', 'Flèche bas', 'Entrée', '<', '>', 'Ctrl+Shift+Flèche gauche', 'Ctrl+Shift+Flèche droite', 'Shift+R', 'Ctrl+clic', 'Shift+clic', 'Ctrl+Shift+clic']
};

for (const [file, locale] of [
	['user-guide.md', 'en'],
	['user-guide.fr.md', 'fr']
]) {
	test(`shortcuts: the table of ${file} lists exactly the shortcuts that work`, () => {
		const { rows } = tableOf(file);
		const shown = rows.flatMap(([keys]) => keys.split(/,\s+/)).map((label) => label.replace(/\s*\(.*\)$/, ''));
		const expected = specs.map((spec) => formatShortcut(spec, { mac: false, names: names(locale) }));
		for (const label of expected) assert.ok(shown.includes(label), `${label} is missing from ${file}`);
		const known = new Set([...expected, ...GUIDE_FIXED[file], ...Array.from('ABRIOMNFU')]);
		for (const label of shown) assert.ok(known.has(label), `${label} in ${file} is not a working shortcut`);
	});
}

test('shortcuts: the two guides have the same section heading numbering and the same rows in the same order', () => {
	const en = tableOf('user-guide.md');
	const fr = tableOf('user-guide.fr.md');
	assert.match(en.heading, /^## 16\. Keyboard shortcuts$/);
	assert.match(fr.heading, /^## 16\. Raccourcis clavier$/);
	assert.equal(en.rows.length, fr.rows.length);
	const normal = (keys) => keys.replace(/Retour arrière/g, 'Backspace').replace(/Espace/g, 'Space').replace(/Échap/g, 'Esc').replace(/Suppr/g, 'Delete').replace(/Flèche gauche/g, 'Left arrow').replace(/Flèche droite/g, 'Right arrow').replace(/Flèche haut/g, 'Up arrow').replace(/Flèche bas/g, 'Down arrow').replace(/Entrée/g, 'Enter').replace(/Fin/g, 'End').replace(/clic\b/g, 'click').replace(/\(plans\)/g, '(shots)');
	assert.deepEqual(
		fr.rows.map(([keys]) => normal(keys)),
		en.rows.map(([keys]) => keys)
	);
	for (const { section } of [en, fr]) {
		assert.doesNotMatch(section, /Ctrl\+Alt\+K|Ctrl\+Alt\+J|1\/25/);
	}
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PLAYER, WORKSPACES, isPlayer } from './workspaces.js';
import { paths } from './icons.js';

const here = dirname(fileURLToPath(import.meta.url));
const source = (file) => readFileSync(join(here, file), 'utf-8');
const json = (locale, domain) => JSON.parse(source(`../i18n/${locale}/${domain}.json`));

test('workspaces: Play sits between Media and Director IA, six workspaces in all', () => {
	assert.deepEqual(
		WORKSPACES.map((w) => w.id),
		['media', 'play', 'director', 'storyboard', 'scene', 'mixer']
	);
	assert.equal(PLAYER, 'play');
	assert.ok(isPlayer('play'));
	assert.ok(!isPlayer('media'));
	for (const w of WORKSPACES) assert.ok(paths[w.icon], `${w.icon} is not an icon of the page`);
});

test('workspaces: the Window menu lists one command per workspace, in the order of the selector, with no shortcut', () => {
	const commands = source('commands.js');
	const listed = [...commands.matchAll(/command\('(ws-[a-z]+)', ws\('([a-z]+)'\)([^)]*)\)/g)];
	assert.deepEqual(
		listed.map((m) => [m[1], m[2]]),
		WORKSPACES.map((w) => [w.command, w.id])
	);
	for (const m of listed) assert.doesNotMatch(m[3], /keys/, `${m[1]} carries a shortcut`);
});

test('workspaces: the selector shows every workspace and no shortcut that the page does not bind', () => {
	const bar = source('../components/shell/ProjectBar.svelte');
	assert.match(bar, /\{#each WORKSPACES as w \(w\.id\)\}/);
	assert.doesNotMatch(bar, /ctrl\+\d|shortcutLabel\(w\./);
	for (const w of WORKSPACES) assert.match(bar, new RegExp(`t\\('shell\\.workspace\\.${w.id}'\\)`));
});

test('workspaces: every workspace and its command have a label in both languages, Play reads Lecture in French', () => {
	for (const locale of ['en', 'fr']) {
		const shell = json(locale, 'shell');
		const commands = json(locale, 'commands');
		for (const w of WORKSPACES) {
			assert.ok(shell[`workspace.${w.id}`], `${locale}: shell.workspace.${w.id} is missing`);
			assert.equal(commands[`cmd.${w.command}`], shell[`workspace.${w.id}`], `${locale}: the menu and the selector name ${w.id} differently`);
		}
	}
	assert.equal(json('en', 'shell')['workspace.play'], 'Play');
	assert.equal(json('fr', 'shell')['workspace.play'], 'Lecture');
});

test('workspaces: Play keeps only the viewer, the position bar and the status bar', () => {
	const page = source('../VideoProducerPage.svelte');
	assert.match(page, /const player = \$derived\(isPlayer\(ui\.workspace\)\);/);
	assert.match(page, /\{#if !player\}<LeftPanel \/>\{\/if\}/);
	assert.match(page, /\{#if !player\}<Inspector \/>\{\/if\}/);
	assert.match(page, /<Viewer \{player\} \/>/);
	const bottom = page.slice(page.indexOf('{#if player}'), page.indexOf('<StatusBar />'));
	assert.match(bottom, /^\{#if player\}\s*<PlayBar \/>\s*\{:else\}/);
	for (const part of ['<Splitter />', '<ProductionBar />', '<Timeline />', '<Console />']) assert.ok(bottom.indexOf(part) > bottom.indexOf('{:else}'), `${part} shows in Play`);
	const bar = source('../components/shell/ProjectBar.svelte');
	assert.equal(bar.match(/disabled: player,/g)?.length, 2);
});

test('workspaces: the viewer of Play shows the cut, never a preview, a comparison or a generation button', () => {
	const viewer = source('../components/viewer/Viewer.svelte');
	assert.match(viewer, /let \{ player = false \} = \$props\(\);/);
	assert.match(viewer, /const previewAsset = \$derived\(!player && /);
	assert.match(viewer, /const previewResult = \$derived\(!player && /);
	assert.match(viewer, /const compareRes = \$derived\(!player && /);
	assert.match(viewer, /\{#if !player\}\s*<div class="mt-1">\s*<HostUi name="Button" props=\{\{[^}]*startGeneration/);
});

test('workspaces: a mouse click on a workspace hands the keys back to the page, a key press keeps the focus on the tab', () => {
	const bar = source('../components/shell/ProjectBar.svelte');
	assert.match(bar, /function pick\(e, id\) \{\n\t\tui\.workspace = id;\n\t\tif \(e\.detail > 0\) e\.currentTarget\.blur\(\);\n\t\}/);
	assert.match(bar, /onclick=\{\(e\) => pick\(e, w\.id\)\}/);
});

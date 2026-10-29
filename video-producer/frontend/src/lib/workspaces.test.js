import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PLAYER, WORKSPACES, isPlayer } from './workspaces.js';
import { paths } from './icons.js';

const here = dirname(fileURLToPath(import.meta.url));
const source = (file) => readFileSync(join(here, file), 'utf-8');
const json = (locale, domain) => JSON.parse(source(`../i18n/${locale}/${domain}.json`));

test('workspaces: Media, Storyboard, Director AI, Mix and Play, in this order, five workspaces in all', () => {
	assert.deepEqual(
		WORKSPACES.map((w) => w.id),
		['media', 'storyboard', 'director', 'mixer', 'play']
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
	for (const locale of ['en', 'fr']) assert.equal(json(locale, 'shell')['workspace.director'], 'Director AI');
});

test('workspaces: Play keeps the viewer with the splitter and the timeline under it, without the side panels; only Director AI and Storyboard show the production deck', () => {
	const page = source('../VideoProducerPage.svelte');
	assert.match(page, /const player = \$derived\(isPlayer\(ui\.workspace\)\);/);
	assert.match(page, /\{#if !player\}\s*<div class="vp-drawer" data-vp-drawer="start"[^>]*>\s*<LeftPanel \/>\s*<\/div>\s*\{\/if\}/);
	assert.match(page, /\{#if !player\}\s*<div class="vp-drawer" data-vp-drawer="end"[^>]*>\s*<RightPanel \/>\s*<\/div>\s*\{\/if\}/);
	assert.match(page, /<Viewer \{player\} \/>/);
	assert.match(page, /<div>\s*\{#if !bare\}<Splitter \/>\{\/if\}\s*<\/div>/);
	assert.match(page, /<\/section>\s*\{#if generates\(\)\}<ProductionDeck \/>\{\/if\}\s*<StatusBar \/>/);
	assert.match(page, /const bare = \$derived\(band \|\| ui\.workspace === 'director'\);/);
	assert.match(source('state.svelte.js'), /export const generates = \(\) => ui\.workspace === 'director' \|\| ui\.workspace === 'storyboard';/);
	const bottom = page.slice(page.indexOf('<Splitter />'), page.indexOf('<ProductionDeck />'));
	assert.match(bottom, /<section class="min-h-0 overflow-hidden" style:height=\{`\$\{ui\[bottomKey\(\)\]\}px`\}/);
	assert.match(bottom, /\{#if ui\.bottomView === 'console'\}\s*<Console \/>\s*\{:else\}\s*<Timeline \/>/);
	assert.equal(bottom.match(/player/g), null);
	assert.match(bottom, /hidden=\{bare\}/);
	assert.doesNotMatch(page, /PlayBar|vp-playbar/);
	assert.ok(!existsSync(join(here, '../components/viewer/PlayBar.svelte')));
	assert.match(source('state.svelte.js'), /export const bottomKey = \(\) => \(ui\.bottomView === 'console' \? 'consoleH' : ui\.workspace === 'storyboard' \? 'storyH' : 'timelineH'\);/);
	const bar = source('../components/shell/ProjectBar.svelte');
	assert.equal(bar.match(/disabled: player,/g)?.length, 2);
});

test('workspaces: the viewer of Play shows the cut with its timecode and the shot under the playhead, never a preview or a comparison, and no viewer has a generation button', () => {
	const viewer = source('../components/viewer/Viewer.svelte');
	assert.match(viewer, /let \{ player = false \} = \$props\(\);/);
	assert.match(viewer, /const previewAsset = \$derived\(!player && /);
	assert.match(viewer, /const previewResult = \$derived\(!player && /);
	assert.match(viewer, /const compareRes = \$derived\(!player && /);
	assert.doesNotMatch(viewer, /startGeneration/);
	assert.match(viewer, /\{#if player && clip\}\s*<span class="ml-1 min-w-0 truncate text-sm text-fg-muted">\{t\('viewer\.shot', \{ index: doc\.clips\.indexOf\(clip\) \+ 1, count: doc\.clips\.length, name: clipLabel\(clip\) \}\)\}<\/span>/);
	assert.match(viewer, /\n\t\t\t<span class="vp-tc mr-1 text-md text-fg">\{tc\(ui\.playhead, doc\.fps\)\}<\/span>/);
	for (const locale of ['en', 'fr']) assert.ok(json(locale, 'viewer').shot, `${locale}: viewer.shot is missing`);
	assert.equal(json('fr', 'viewer').shot, 'Plan {index}/{count} · {name}');
});

test('workspaces: a mouse click on a workspace hands the keys back to the page, a key press keeps the focus on the tab', () => {
	const bar = source('../components/shell/ProjectBar.svelte');
	assert.match(bar, /function pick\(e, id\) \{\n\t\tui\.workspace = id;\n\t\tif \(e\.detail > 0\) e\.currentTarget\.blur\(\);\n\t\}/);
	assert.match(bar, /onclick=\{\(e\) => pick\(e, w\.id\)\}/);
});

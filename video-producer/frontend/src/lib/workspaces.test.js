import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent } from './svelte-harness.js';
import { PLAYER, WORKSPACES, isPlayer } from './workspaces.js';
import { paths } from './icons.js';
import enShell from '../i18n/en/shell.json' with { type: 'json' };
import frShell from '../i18n/fr/shell.json' with { type: 'json' };
import enCommands from '../i18n/en/commands.json' with { type: 'json' };
import frCommands from '../i18n/fr/commands.json' with { type: 'json' };
import enViewer from '../i18n/en/viewer.json' with { type: 'json' };
import frViewer from '../i18n/fr/viewer.json' with { type: 'json' };

const { ui, bottomKey, generates, dispose } = await import('./state.svelte.js');
const { allCommands } = await import('./commands.js');
const { t } = await import('../i18n/index.svelte.js');

const PROJECT_BAR = new URL('../components/shell/ProjectBar.svelte', import.meta.url).href;
const DICTIONARIES = { en: { shell: enShell, commands: enCommands, viewer: enViewer }, fr: { shell: frShell, commands: frCommands, viewer: frViewer } };
const json = (locale, domain) => DICTIONARIES[locale][domain];

after(() => dispose());

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

test('workspaces: the Window menu lists one command per workspace, in the order of the selector, with no shortcut, and each one opens its workspace', () => {
	const listed = allCommands.filter((c) => c.id.startsWith('ws-'));
	assert.deepEqual(listed.map((c) => c.id), WORKSPACES.map((w) => w.command));
	for (const c of listed) assert.equal(c.keys, null, `${c.id} carries a shortcut`);
	for (const w of WORKSPACES) {
		listed.find((c) => c.id === w.command).run();
		assert.equal(ui.workspace, w.id);
	}
	ui.workspace = 'storyboard';
});

test('workspaces: the selector shows every workspace as a tab named in the current language, the current one selected, without any shortcut', async () => {
	ui.workspace = 'director';
	const html = clean(await renderComponent(PROJECT_BAR));
	const group = html.slice(html.indexOf(`role="tablist" aria-label="${t('shell.workspace.group')}"`), html.indexOf('</div>', html.indexOf(`role="tablist" aria-label="${t('shell.workspace.group')}"`)));
	const tabs = [...group.matchAll(/<button type="button" role="tab" aria-selected="(true|false)" aria-label="([^"]*)"/g)].map((m) => [m[2], m[1] === 'true']);
	assert.deepEqual(
		tabs,
		WORKSPACES.map((w) => [t(`shell.workspace.${w.id}`), w.id === 'director'])
	);
	assert.doesNotMatch(group, /Ctrl\+|⌘/);
	ui.workspace = 'storyboard';
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

test('workspaces: Play is the only workspace of the player, Director AI and Storyboard are the ones that generate, and the bottom pane keeps one height per use', () => {
	assert.equal(isPlayer(PLAYER), true);
	for (const w of WORKSPACES) assert.equal(isPlayer(w.id), w.id === PLAYER, w.id);
	for (const [workspace, shown] of [['storyboard', true], ['director', true], ['media', false], ['mixer', false], [PLAYER, false]]) {
		ui.workspace = workspace;
		assert.equal(generates(), shown, workspace);
	}
	ui.bottomView = 'console';
	ui.workspace = 'storyboard';
	assert.equal(bottomKey(), 'consoleH');
	ui.bottomView = 'timeline';
	assert.equal(bottomKey(), 'storyH');
	ui.workspace = 'director';
	assert.equal(bottomKey(), 'timelineH');
	ui.workspace = PLAYER;
	assert.equal(bottomKey(), 'timelineH');
	ui.workspace = 'storyboard';
});

test('workspaces: the viewer of Play names the shot under the playhead in both languages', () => {
	for (const locale of ['en', 'fr']) assert.ok(json(locale, 'viewer').shot, `${locale}: viewer.shot is missing`);
	assert.equal(json('fr', 'viewer').shot, 'Plan {index}/{count} · {name}');
	assert.match(json('en', 'viewer').shot, /\{index\}\/\{count\}/);
});


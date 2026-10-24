import { t } from '../i18n/index.svelte.js';
import {
	ui,
	doc,
	undo,
	redo,
	deleteSelection,
	duplicateSelection,
	bladeAt,
	sliceAudio,
	joinAudio,
	addMarker,
	addAudioLane,
	toast,
	select,
	seqDuration,
	selected,
	act,
	clipAt,
	addShot,
	proposeShots,
	secs
} from './state.svelte.js';
import { startGeneration, cancelGeneration, openQueue, openEngineSettings, openResults, assembleChosen, promoteToFinal, busy, fitShot } from './production.svelte.js';
import { createProject as createProjectOnServer, flushSave } from './project.svelte.js';
import { openGallery, openImport, openLocalImport } from './importer.js';
import { ulid } from './ulid.js';
import { matchToPrevious } from './continuity.svelte.js';
import { openReferences } from './references.js';
import { chooseSceneFile } from './scene.svelte.js';
import { togglePlay, seek } from './playback.svelte.js';
import { chat, confirm } from './host.js';
import { detectMac, findShortcut, formatShortcut, hostOverlayOpen, isActivationTarget, isSingleKey, isTypingTarget } from './keyboard.js';
import { frameDuration } from './timebase.js';
import { closeTopLayer } from './focus.js';

export const IS_MAC = detectMac();

export function shortcutLabel(spec) {
	return formatShortcut(spec, { mac: IS_MAC, names: { space: t('commands.kbd.space'), backspace: t('commands.kbd.backspace') } });
}

function command(id, run, { keys = null, check = null, global = false, press = null, repeat = false, vars = null } = {}) {
	return {
		id,
		run,
		keys,
		check,
		global,
		press: press ?? run,
		repeat,
		menuId: null,
		get label() {
			return t(`commands.cmd.${id}`, vars?.());
		},
		get key() {
			return keys ? shortcutLabel(keys) : '';
		},
		get menu() {
			return this.menuId ? t(`shell.menu.${this.menuId}`) : '';
		}
	};
}

function menu(id, groups) {
	for (const group of groups) for (const item of group) item.menuId = id;
	return {
		id,
		groups,
		get label() {
			return t(`shell.menu.${id}`);
		}
	};
}

const ws = (w) => () => (ui.workspace = w);
const modal = (type, props = {}) => () => (ui.modal = { type, ...props });
const flag = (f) => () => {
	const s = ui.selection;
	if (s?.kind !== 'clip') return toast(t('lib.toast.selectShot'), 'warning');
	act(() => (selected().flag = f));
	toast(f === 'favori' ? t('lib.toast.flagFavorite') : f === 'rejet' ? t('lib.toast.flagRejected') : t('lib.toast.flagCleared'));
};
const nudgeTrim = (edge) => () => {
	const s = selected();
	if (!s || !('dur' in s)) return toast(t('lib.toast.selectTimelineItem'), 'warning');
	act(() => {
		const at = ui.playhead;
		if (edge === 'start' && at > s.start && at < s.start + s.dur) {
			s.dur -= at - s.start;
			if ('srcIn' in s) s.srcIn += at - s.start;
			s.start = at;
		} else if (edge === 'end' && at > s.start) {
			const before = s.dur;
			s.dur = at - s.start;
			if (doc.clips.includes(s)) fitShot(s, before);
		}
	});
};

const mixer = () => {
	ui.workspace = 'mixer';
	ui.bottomView = 'console';
};
const refs = (space) => () => openReferences(space);
const takes = () => {
	if (ui.selection?.kind !== 'clip') return toast(t('lib.toast.selectShotForTakes'), 'warning');
	ui.inspectorOpen = true;
};
const promote = () => {
	const c = ui.selection?.kind === 'clip' ? selected() : clipAt(ui.playhead);
	if (!c?.take) return toast(t('lib.toast.chooseDraft'), 'warning');
	promoteToFinal(c.take);
};
const match = () => {
	const c = ui.selection?.kind === 'clip' ? selected() : clipAt(ui.playhead);
	if (!c || doc.clips.indexOf(c) === 0) return toast(t('lib.toast.selectFollowingShot'), 'warning');
	matchToPrevious(c);
};
const newShot = () => {
	ui.workspace = 'storyboard';
	addShot(t('lib.default.shot'), '', 4, ui.selection?.kind === 'clip' ? ui.selection.id : null);
};
const gallery = () => {
	ui.workspace = 'media';
	ui.mediaCollection = 'all';
	openGallery();
};
const director = () => {
	ui.workspace = 'director';
	ui.dockTab = 'direction';
};
const synopsis = () => {
	ui.workspace = 'storyboard';
	proposeShots();
};
const scopes = () => {
	ui.inspectorOpen = true;
	ui.inspectorTab = 'color';
};
const cancelRunning = () => (busy() ? cancelGeneration() : toast(t('lib.toast.noRunning')));
const sceneNew = () => {
	ui.workspace = 'scene';
	ui.modal = { type: 'scene-new' };
};
const sceneImport = () => {
	ui.workspace = 'scene';
	chooseSceneFile();
};

export const menus = [
	menu('app', [
		[command('about', modal('about')), command('prefs', modal('prefs'), { keys: 'mod+,' })],
		[
			command('shortcuts', modal('shortcuts'), { keys: 'mod+/', global: true }),
			command('palette', () => (ui.paletteOpen = true), { keys: 'mod+k', global: true, press: () => (ui.paletteOpen = !ui.paletteOpen) })
		]
	]),
	menu('file', [
		[
			command('new-project', () => createProject()),
			command('open', modal('open'), { keys: 'mod+o' }),
			command('save', () => save(), { keys: 'mod+s' }),
			command('versions', modal('versions'))
		],
		[command('import', () => openImport(), { keys: 'mod+i' }), command('import-local', () => openLocalImport(), { keys: 'ctrl+mod+i' }), command('import-gallery', gallery), command('project-props', modal('project'))],
		[
			command('export', modal('export', { tab: 'video' }), { keys: 'mod+e' }),
			command('export-xml', modal('export', { tab: 'exchange' }), { keys: 'shift+mod+e' }),
			command('export-srt', modal('export', { tab: 'subtitles' }))
		]
	]),
	menu('edit', [
		[command('undo', undo, { keys: 'mod+z', repeat: true }), command('redo', redo, { keys: 'shift+mod+z', repeat: true })],
		[
			command('copy', () => toast(t('lib.toast.copied'))),
			command('paste', duplicateSelection),
			command('duplicate', duplicateSelection, { keys: 'mod+d' }),
			command('delete', deleteSelection, { keys: 'backspace', repeat: true })
		],
		[command('find', ws('media'))]
	]),
	menu('edit-timeline', [
		[
			command('tool-select', () => (ui.tool = 'select'), { keys: 'a', check: () => ui.tool === 'select' }),
			command('tool-range', () => (ui.tool = 'range'), { keys: 'r', check: () => ui.tool === 'range' }),
			command('tool-blade', () => (ui.tool = 'blade'), { keys: 'b', check: () => ui.tool === 'blade' })
		],
		[
			command('blade', () => bladeAt(), { keys: 'mod+b' }),
			command('audio-slice', () => sliceAudio(), { keys: 'shift+mod+b', vars: () => ({ dur: secs(ui.sliceSeconds) }) }),
			command('audio-join', joinAudio, { keys: 'alt+mod+b' }),
			command('trim-start', nudgeTrim('start'), { keys: 'alt+[' }),
			command('trim-end', nudgeTrim('end'), { keys: 'alt+]' }),
			command('duration', () => (ui.inspectorOpen = true))
		],
		[
			command('in', () => setInOut('in'), { keys: 'i' }),
			command('out', () => setInOut('out'), { keys: 'o' }),
			command('clear-range', () => (ui.range = null), { keys: 'alt+x' })
		],
		[command('marker', () => addMarker(), { keys: 'm' }), command('title', () => addTitle()), command('transition', () => crossfade())]
	]),
	menu('clip', [
		[command('new-shot', newShot), command('info', () => (ui.inspectorOpen = !ui.inspectorOpen)), command('reveal', ws('media'))],
		[command('takes', takes), command('promote', promote, { keys: 'shift+mod+g' })],
		[command('color', scopes), command('match', match), command('keyframes', ws('scene'))],
		[command('fav', flag('favori'), { keys: 'f' }), command('reject', flag('rejet'), { keys: 'alt+backspace' }), command('unflag', flag(null), { keys: 'u' })]
	]),
	menu('production', [
		[command('dir-global', director), command('synopsis', synopsis), command('continuity', director)],
		[
			command('generate', () => startGeneration(), { keys: 'mod+g' }),
			command('draft', () => (ui.production.quality = 'draft'), { check: () => ui.production.quality === 'draft' }),
			command('final', () => (ui.production.quality = 'final'), { check: () => ui.production.quality === 'final' }),
			command('queue', openQueue, { keys: 'alt+mod+g' }),
			command('cancel-generation', cancelRunning)
		],
		[command('results', openResults), command('assemble', assembleChosen)],
		[command('engine', openEngineSettings)]
	]),
	menu('audio', [
		[command('audio-add', addAudioLane), command('audio-import', () => openImport('audio')), command('audio-import-local', () => openLocalImport('audio')), command('audio-mixer', mixer)],
		[
			command('voice', modal('sound', { kind: 'Voix' })),
			command('sd-ambience', modal('sound', { kind: 'Ambiance' })),
			command('sd-foley', modal('sound', { kind: 'Bruitage' })),
			command('sd-texture', modal('sound', { kind: 'Texture' })),
			command('sd-impact', modal('sound', { kind: 'Impact' })),
			command('sd-music', modal('sound', { kind: 'Musique' }))
		]
	]),
	menu('view', [
		[
			command('play', togglePlay, { keys: 'space' }),
			command('loop', () => (ui.loop = !ui.loop), { check: () => ui.loop }),
			command('fullscreen', () => document.querySelector('#viewer-frame')?.requestFullscreen?.())
		],
		[
			command('guides', () => (ui.guides = !ui.guides), { check: () => ui.guides }),
			command('compare', openResults),
			command('scopes', scopes),
			command('meters', mixer)
		],
		[
			command('zoom-in', () => (ui.pxPerSec = Math.min(220, ui.pxPerSec * 1.25))),
			command('zoom-out', () => (ui.pxPerSec = Math.max(8, ui.pxPerSec / 1.25))),
			command('snap', () => (ui.snapping = !ui.snapping), { keys: 'n', check: () => ui.snapping })
		]
	]),
	menu('window', [
		[
			command('ws-media', ws('media')),
			command('ws-director', ws('director')),
			command('ws-story', ws('storyboard')),
			command('ws-scene', ws('scene')),
			command('ws-mixer', ws('mixer'))
		],
		[
			command('ref-all', refs('all')),
			command('ref-identity', refs('identite')),
			command('ref-3d', refs('decors3d')),
			command('ref-motion', refs('mouvement')),
			command('scene-new', sceneNew),
			command('scene-import', sceneImport)
		],
		[
			command('sidebar', () => (ui.sidebarOpen = !ui.sidebarOpen), { keys: 'ctrl+mod+1', check: () => ui.sidebarOpen }),
			command('inspector', () => (ui.inspectorOpen = !ui.inspectorOpen), { check: () => ui.inspectorOpen }),
			command('assistant', () => chat.open(), { keys: 'mod+j', check: () => chat.isOpen(), press: () => chat.toggle() }),
			command('library', modal('library', { target: null })),
			command('index', modal('index')),
			command('tasks', modal('tasks'))
		]
	]),
	menu('help', [
		[command('tour', modal('tour')), command('help-keys', modal('shortcuts')), command('help-find', () => (ui.paletteOpen = true))],
		[command('help-sim', modal('simulations'))]
	])
];

export const allCommands = menus.flatMap((m) => m.groups.flat());

export function commandById(id) {
	return allCommands.find((x) => x.id === id) ?? null;
}

export function runCommand(id) {
	commandById(id)?.run();
}

export async function createProject() {
	if (ui.playing) togglePlay();
	const saved = await flushSave();
	if (!saved) {
		const ok = await confirm({ title: t('lib.newProject.title'), message: t('lib.newProject.message', { name: doc.name }), variant: 'warning', confirmLabel: t('lib.newProject.confirm') });
		if (!ok) return;
	}
	await createProjectOnServer();
}

export async function save() {
	if (await flushSave()) toast(t('lib.toast.saved'));
}

export function setInOut(edge) {
	const at = ui.playhead;
	const r = ui.range ?? { in: at, out: Math.min(seqDuration(), at + 4) };
	if (edge === 'in') r.in = Math.min(at, r.out - 0.2);
	else r.out = Math.max(at, r.in + 0.2);
	ui.range = { ...r };
	ui.production.target = 'range';
}

export function addTitle() {
	const title = { id: ulid(), text: t('lib.default.title'), sub: '', start: ui.playhead, dur: 3 };
	act(() => doc.titles.push(title));
	select('title', title.id);
}

function crossfade() {
	const s = selected();
	if (ui.selection?.kind !== 'clip') return toast(t('lib.toast.selectShot'), 'warning');
	act(() => {
		s.fadeIn = Math.min(1, s.dur / 3);
		s.fadeOut = Math.min(1, s.dur / 3);
	});
	toast(t('lib.toast.fades'));
}

function escape() {
	if (ui.paletteOpen) ui.paletteOpen = false;
	else if (ui.modal) closeTopLayer() || (ui.modal = null);
	else if (ui.menuOpen) ui.menuOpen = null;
	else if (ui.preview || ui.compare) {
		ui.preview = null;
		ui.compare = null;
	} else select(null);
}

function stepShot(forward) {
	const i = doc.clips.findIndex((c) => c.id === ui.selection?.id);
	const next = doc.clips[Math.max(0, Math.min(doc.clips.length - 1, i < 0 ? 0 : i + (forward ? 1 : -1)))];
	if (!next) return;
	select('clip', next.id);
	seek(next.start + 0.01);
}

function arrow(forward, whole) {
	return () => {
		if (ui.workspace === 'storyboard') return stepShot(forward);
		seek(ui.playhead + (forward ? 1 : -1) * (whole ? 1 : frameDuration(doc.fps)));
	};
}

const fixedBindings = [
	{ spec: 'delete', run: () => deleteSelection(), repeat: true },
	{ spec: 'home', run: () => seek(0) },
	{ spec: 'arrowleft', run: arrow(false, false), repeat: true },
	{ spec: 'arrowright', run: arrow(true, false), repeat: true },
	{ spec: 'shift+arrowleft', run: arrow(false, true), repeat: true },
	{ spec: 'shift+arrowright', run: arrow(true, true), repeat: true }
];

const keymap = [
	...allCommands
		.filter((c) => c.keys)
		.map((c) => ({ spec: c.keys, run: c.press, global: c.global, repeat: c.repeat, single: isSingleKey(c.keys) })),
	...fixedBindings
];

function hasModifier(e) {
	return e.ctrlKey || e.metaKey || e.altKey || e.shiftKey;
}

export function handleKeydown(e, root) {
	const target = e.target;
	if (target && target !== document.body && root && !root.contains(target)) return;
	if (ui.hostModal || hostOverlayOpen()) return;
	if (e.key === 'Escape') {
		if (!hasModifier(e)) escape();
		return;
	}
	const hit = findShortcut(e, keymap, IS_MAC);
	if (!hit) return;
	if (!hit.global && (isTypingTarget(target) || ui.modal || ui.paletteOpen)) return;
	if (hit.single && !ui.singleKeyShortcuts) return;
	if (hit.spec === 'space' && isActivationTarget(target)) return;
	e.preventDefault();
	if (e.repeat && !hit.repeat) return;
	hit.run();
}

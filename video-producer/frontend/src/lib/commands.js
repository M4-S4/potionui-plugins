import { t } from '../i18n/index.svelte.js';
import {
	ui,
	doc,
	undo,
	redo,
	deleteSelection,
	duplicateSelection,
	bladeAt,
	addMarker,
	addAudioLane,
	toast,
	select,
	startGeneration,
	resumeGeneration,
	queueWindow,
	openResults,
	assembleChosen,
	seqDuration,
	selected,
	act,
	clipAt,
	addShot,
	proposeShots,
	promoteToFinal
} from './state.svelte.js';
import { createProject as createProjectOnServer, flushSave } from './project.svelte.js';
import { openGallery, openImport } from './importer.js';
import { ulid } from './ulid.js';
import { matchToPrevious } from './continuity.svelte.js';
import { openReferences } from './references.js';
import { togglePlay, seek } from './playback.svelte.js';
import { chat, confirm } from './host.js';
import { detectMac, eventKey, formatShortcut, hostOverlayOpen, isActivationTarget, isTypingTarget } from './keyboard.js';

export const IS_MAC = detectMac();

export function shortcutLabel(spec) {
	return formatShortcut(spec, { mac: IS_MAC, names: { space: t('commands.kbd.space'), backspace: t('commands.kbd.backspace') } });
}

function command(id, run, { keys = null, check = null, sim = false } = {}) {
	return {
		id,
		run,
		keys,
		check,
		sim,
		menuId: null,
		get label() {
			return t(`commands.cmd.${id}`);
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
		} else if (edge === 'end' && at > s.start) s.dur = at - s.start;
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
	const r = c && doc.results.find((x) => x.id === c.take);
	if (!r || r.quality !== 'draft') return toast(t('lib.toast.chooseDraft'), 'warning');
	promoteToFinal(r.id);
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
const resume = () => (ui.production.state === 'paused' ? resumeGeneration() : toast(t('lib.toast.noPaused')));

export const menus = [
	menu('app', [
		[command('about', modal('about')), command('prefs', modal('prefs'), { keys: 'mod+,' })],
		[command('shortcuts', modal('shortcuts'), { keys: 'alt+mod+k' }), command('palette', () => (ui.paletteOpen = true), { keys: 'mod+k' })]
	]),
	menu('file', [
		[
			command('new-project', () => createProject(), { keys: 'mod+n' }),
			command('open', modal('open'), { keys: 'mod+o' }),
			command('save', () => save(), { keys: 'mod+s' }),
			command('versions', modal('versions'))
		],
		[command('import', () => openImport(), { keys: 'mod+i' }), command('import-gallery', gallery), command('project-props', modal('project'), { keys: 'alt+mod+j' })],
		[
			command('export', modal('export', { tab: 'video' }), { keys: 'mod+e' }),
			command('export-xml', modal('export', { tab: 'exchange' }), { keys: 'shift+mod+e' }),
			command('export-srt', modal('export', { tab: 'subtitles' }))
		]
	]),
	menu('edit', [
		[command('undo', undo, { keys: 'mod+z' }), command('redo', redo, { keys: 'shift+mod+z' })],
		[
			command('copy', () => toast(t('lib.toast.copied')), { keys: 'mod+c' }),
			command('paste', duplicateSelection, { keys: 'mod+v' }),
			command('duplicate', duplicateSelection, { keys: 'mod+d' }),
			command('delete', deleteSelection, { keys: 'backspace' })
		],
		[command('find', ws('media'), { keys: 'mod+f' })]
	]),
	menu('edit-timeline', [
		[
			command('tool-select', () => (ui.tool = 'select'), { keys: 'a', check: () => ui.tool === 'select' }),
			command('tool-range', () => (ui.tool = 'range'), { keys: 'r', check: () => ui.tool === 'range' }),
			command('tool-blade', () => (ui.tool = 'blade'), { keys: 'b', check: () => ui.tool === 'blade' })
		],
		[
			command('blade', () => bladeAt(), { keys: 'mod+b' }),
			command('trim-start', nudgeTrim('start'), { keys: 'alt+[' }),
			command('trim-end', nudgeTrim('end'), { keys: 'alt+]' }),
			command('duration', () => (ui.inspectorOpen = true), { keys: 'ctrl+d' })
		],
		[
			command('in', () => setInOut('in'), { keys: 'i' }),
			command('out', () => setInOut('out'), { keys: 'o' }),
			command('clear-range', () => (ui.range = null), { keys: 'alt+x' })
		],
		[command('marker', () => addMarker(), { keys: 'm' }), command('title', () => addTitle(), { keys: 'ctrl+t' }), command('transition', () => crossfade(), { keys: 'mod+t' })]
	]),
	menu('clip', [
		[command('new-shot', newShot, { keys: 'alt+n' }), command('info', () => (ui.inspectorOpen = !ui.inspectorOpen), { keys: 'mod+4' }), command('reveal', ws('media'), { keys: 'shift+f' })],
		[command('takes', takes, { keys: 'mod+y' }), command('promote', promote, { keys: 'shift+mod+g' })],
		[command('color', scopes, { keys: 'mod+6' }), command('match', match, { keys: 'alt+mod+m' }), command('keyframes', ws('scene'), { keys: 'alt+k' })],
		[command('fav', flag('favori'), { keys: 'f' }), command('reject', flag('rejet'), { keys: 'alt+backspace' }), command('unflag', flag(null), { keys: 'u' })]
	]),
	menu('production', [
		[command('dir-global', director), command('synopsis', synopsis), command('continuity', director)],
		[
			command('generate', () => startGeneration(), { keys: 'mod+g' }),
			command('draft', () => (ui.production.quality = 'draft'), { check: () => ui.production.quality === 'draft' }),
			command('final', () => (ui.production.quality = 'final'), { check: () => ui.production.quality === 'final' }),
			command('queue', queueWindow, { keys: 'alt+mod+g' }),
			command('resume', resume)
		],
		[command('results', openResults, { keys: 'ctrl+mod+r' }), command('assemble', assembleChosen)],
		[
			command('advanced', modal('advanced', { step: 0 }), { keys: 'shift+mod+a' }),
			command('engine', modal('advanced', { step: 1 })),
			command('hybrid', modal('advanced', { step: 1, focus: 'hybrid' }))
		]
	]),
	menu('audio', [
		[command('audio-add', addAudioLane, { keys: 'alt+mod+n' }), command('audio-import', () => openImport('audio')), command('audio-mixer', mixer, { keys: 'mod+8' })],
		[
			command('voice', modal('sound', { kind: 'Voix' }), { keys: 'shift+mod+v' }),
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
			command('loop', () => (ui.loop = !ui.loop), { keys: 'mod+l', check: () => ui.loop }),
			command('fullscreen', () => document.querySelector('#viewer-frame')?.requestFullscreen?.(), { keys: 'shift+mod+f' })
		],
		[
			command('guides', () => (ui.guides = !ui.guides), { keys: 'ctrl+g', check: () => ui.guides }),
			command('compare', openResults, { keys: 'ctrl+mod+6' }),
			command('scopes', scopes, { keys: 'mod+7' }),
			command('meters', mixer, { keys: 'shift+mod+8' })
		],
		[
			command('zoom-in', () => (ui.pxPerSec = Math.min(220, ui.pxPerSec * 1.25)), { keys: 'mod+plus' }),
			command('zoom-out', () => (ui.pxPerSec = Math.max(8, ui.pxPerSec / 1.25)), { keys: 'mod+minus' }),
			command('snap', () => (ui.snapping = !ui.snapping), { keys: 'n', check: () => ui.snapping })
		]
	]),
	menu('window', [
		[
			command('ws-media', ws('media'), { keys: 'ctrl+1' }),
			command('ws-director', ws('director'), { keys: 'ctrl+2' }),
			command('ws-story', ws('storyboard'), { keys: 'ctrl+3' }),
			command('ws-scene', ws('scene'), { keys: 'ctrl+4' }),
			command('ws-mixer', ws('mixer'), { keys: 'ctrl+5' })
		],
		[
			command('ref-all', refs('all'), { keys: 'alt+mod+r' }),
			command('ref-identity', refs('identite')),
			command('ref-3d', refs('decors3d')),
			command('ref-motion', refs('mouvement')),
			command('splat', modal('splat'))
		],
		[
			command('sidebar', () => (ui.sidebarOpen = !ui.sidebarOpen), { keys: 'ctrl+mod+1', check: () => ui.sidebarOpen }),
			command('inspector', () => (ui.inspectorOpen = !ui.inspectorOpen), { keys: 'mod+4', check: () => ui.inspectorOpen }),
			command('assistant', () => chat.open(), { keys: 'mod+j', check: () => chat.isOpen() }),
			command('library', modal('library', { target: null }), { keys: 'shift+mod+l' }),
			command('index', modal('index'), { keys: 'shift+mod+2' }),
			command('tasks', modal('tasks'), { keys: 'mod+9' })
		]
	]),
	menu('help', [
		[command('tour', modal('tour')), command('help-keys', modal('shortcuts')), command('help-find', () => (ui.paletteOpen = true), { keys: 'mod+k' })],
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

function sidebarCombo(e) {
	return IS_MAC ? e.ctrlKey && e.metaKey : e.ctrlKey && e.altKey;
}

function escape() {
	if (ui.paletteOpen) ui.paletteOpen = false;
	else if (ui.modal) ui.modal = null;
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

export function handleKeydown(e, root) {
	const target = e.target;
	if (target && target !== document.body && root && !root.contains(target)) return;
	if (ui.hostModal || hostOverlayOpen()) return;
	if (e.key === 'Escape') return escape();
	const mod = e.metaKey || e.ctrlKey;
	const k = eventKey(e);
	if (mod && k === 'k') {
		e.preventDefault();
		if (e.altKey) ui.modal = { type: 'shortcuts' };
		else ui.paletteOpen = !ui.paletteOpen;
		return;
	}
	if (isTypingTarget(target) || ui.modal || ui.paletteOpen) return;
	const withMod = {
		z: () => (e.shiftKey ? redo() : undo()),
		s: () => save(),
		b: () => bladeAt(),
		d: () => duplicateSelection(),
		g: () => (e.shiftKey ? promote() : e.altKey ? queueWindow() : startGeneration()),
		e: () => (ui.modal = { type: 'export', tab: e.shiftKey ? 'exchange' : 'video' }),
		j: () => (e.altKey ? (ui.modal = { type: 'project' }) : chat.toggle()),
		i: () => openImport(),
		o: () => (ui.modal = { type: 'open' }),
		',': () => (ui.modal = { type: 'prefs' })
	};
	if (mod) {
		if (k === '1' && sidebarCombo(e)) {
			e.preventDefault();
			ui.sidebarOpen = !ui.sidebarOpen;
			return;
		}
		if (withMod[k]) {
			e.preventDefault();
			withMod[k]();
		}
		return;
	}
	if (ui.workspace === 'storyboard' && (k === 'arrowleft' || k === 'arrowright')) {
		e.preventDefault();
		return stepShot(k === 'arrowright');
	}
	const single = ui.singleKeyShortcuts && !e.altKey;
	const plain = {
		' ': () => togglePlay(),
		a: single && (() => (ui.tool = 'select')),
		r: single && (() => (ui.tool = 'range')),
		b: single && (() => (ui.tool = 'blade')),
		m: single && (() => addMarker()),
		i: single && (() => setInOut('in')),
		o: single && (() => setInOut('out')),
		n: single && (() => (ui.snapping = !ui.snapping)),
		backspace: () => deleteSelection(),
		delete: () => deleteSelection(),
		arrowleft: () => seek(ui.playhead - (e.shiftKey ? 1 : 1 / 25)),
		arrowright: () => seek(ui.playhead + (e.shiftKey ? 1 : 1 / 25)),
		home: () => seek(0)
	};
	const action = plain[k];
	if (!action) return;
	if (k === ' ' && isActivationTarget(target)) return;
	e.preventDefault();
	action();
}

import { formatNumber, t } from '../i18n/index.svelte.js';
import { emptyDoc, migrate, newAsset, newClip, promptLanguageOf } from './starter.js';
import { confirm, toast as hostToast } from './host.js';
import { ulid } from './ulid.js';
import { resetTakes } from './takes.svelte.js';
import { compileRules, conflictIds, namesCamera } from './rules.js';
import { dropPlanControls } from './scene3d/doc.js';
import { laneCode, laneFor, laneItemCount, newLaneId, newSound, removeLane } from './tracks.js';
import { touch } from './shots.js';
import sharedRules from './rules.json';

export { newAsset, newClip };

export const doc = $state(emptyDoc(t));

export const ui = $state({
	workspace: 'storyboard',
	dockTab: 'direction',
	dockFocus: null,
	refSpace: 'all',
	sidebarOpen: true,
	inspectorOpen: typeof window === 'undefined' || window.innerWidth >= 1360,
	bottomView: 'timeline',
	selection: null,
	playhead: 1.6,
	playing: false,
	loop: false,
	pxPerSec: 34,
	snapping: true,
	tool: 'select',
	range: null,
	consoleH: typeof window === 'undefined' ? 420 : Math.min(window.innerHeight - 370, Math.max(330, Math.round(window.innerHeight * 0.56))),
	storyH: typeof window === 'undefined' ? 260 : Math.max(200, Math.round(window.innerHeight * 0.29)),
	timelineH: typeof window === 'undefined' ? 320 : Math.min(420, Math.max(200, Math.round(window.innerHeight * (window.innerHeight < 820 ? 0.34 : 0.4)))),
	monitorVol: 0.8,
	muted: false,
	guides: false,
	drag: null,
	preview: null,
	compare: null,
	modal: null,
	menuOpen: null,
	paletteOpen: false,
	toasts: [],
	dirty: false,
	hostModal: false,
	singleKeyShortcuts: true,
	previewQuality: 'balanced',
	mediaQuery: '',
	mediaCollection: 'all',
	mixerFilter: 'Tous',
	scene: { current: null, pos: [0, 0, 0], target: [0, 0, -4], focal: 35, roll: 0, keyframe: null, seeded: null, preset: 'orbit', amounts: { orbit: 10, dolly: 15, crane: 10 } },
	production: {
		target: 'clip',
		mode: 'ai',
		state: 'ready',
		progress: 0,
		running: 0,
		step: '',
		lastCount: 0,
		quality: 'draft'
	},
	inspectorTab: 'video',
	hideRejected: false,
	quota: null,
	storyProposal: null,
	me: null,
	isAdmin: false
});

export function applyMe(me) {
	ui.me = {
		locale: me?.locale ?? null,
		isAdmin: me?.isAdmin === true,
		quota: me?.quota ?? null,
		version: me?.version ?? null,
		lastProjectId: me?.lastProjectId ?? null,
		engines: me?.engines ?? [],
		presets: me?.presets ?? [],
		features: me?.features ?? { upscaler: false },
		upscaleTargets: me?.upscaleTargets ?? [],
		ffmpeg: me?.ffmpeg ?? null,
		settings: me?.settings ?? { draftResolution: null, maxParallelJobs: null }
	};
	ui.isAdmin = ui.me.isAdmin;
	if (ui.me.quota?.limit > 0) ui.quota = { used: ui.me.quota.used, limit: ui.me.quota.limit };
}

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const round = (v, s = 0.1) => +(Math.round(v / s) * s).toFixed(3);

export const bottomKey = () => (ui.bottomView === 'console' ? 'consoleH' : ui.workspace === 'storyboard' ? 'storyH' : 'timelineH');

export function asset(id) {
	return id ? doc.assets?.find((a) => a.id === id) : undefined;
}

export function tc(sec, fps = 25) {
	const s = Math.max(0, sec);
	const f = Math.floor((s % 1) * fps + 1e-6);
	const whole = Math.floor(s);
	const p = (n) => String(n).padStart(2, '0');
	return `${p(Math.floor(whole / 3600))}:${p(Math.floor((whole % 3600) / 60))}:${p(whole % 60)}:${p(f)}`;
}
export const secs = (v) => `${formatNumber(+v, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;

export function seqDuration() {
	const ends = [...doc.clips.map((c) => c.start + c.dur), ...doc.audio.map((c) => c.start + c.dur), ...doc.titles.map((c) => c.start + c.dur)];
	return Math.max(1, ...ends);
}

const past = $state([]);
const future = $state([]);
const restoreListeners = new Set();
export function onRestore(listener) {
	restoreListeners.add(listener);
	return () => restoreListeners.delete(listener);
}
export const history = {
	get canUndo() {
		return past.length > 0;
	},
	get canRedo() {
		return future.length > 0;
	}
};
export function checkpoint() {
	past.push(JSON.stringify($state.snapshot(doc)));
	if (past.length > 100) past.shift();
	future.length = 0;
	ui.dirty = true;
}
function restore(json) {
	const d = JSON.parse(json);
	for (const k of Object.keys(d)) doc[k] = d[k];
	for (const listener of restoreListeners) listener();
}
export function undo() {
	if (!past.length) return;
	future.push(JSON.stringify($state.snapshot(doc)));
	restore(past.pop());
	toast(t('lib.toast.undone'));
}
export function redo() {
	if (!future.length) return;
	past.push(JSON.stringify($state.snapshot(doc)));
	restore(future.pop());
	toast(t('lib.toast.redone'));
}
export function discardLast() {
	if (past.length) restore(past.pop());
}
export function act(fn) {
	checkpoint();
	fn();
}

const HOST_LEVELS = { info: 'info', success: 'success', warning: 'warning', error: 'error', sim: 'info' };
const toastTimers = new Set();

export function toast(message, level = 'info', action) {
	const duration = level === 'sim' ? 4200 : 2800;
	if (!action && hostToast(HOST_LEVELS[level] ?? 'info', message, duration)) return;
	const id = ulid();
	ui.toasts.push({ id, message, level, action });
	const timer = setTimeout(() => {
		toastTimers.delete(timer);
		const i = ui.toasts.findIndex((x) => x.id === id);
		if (i >= 0) ui.toasts.splice(i, 1);
	}, duration);
	toastTimers.add(timer);
}

const collections = { clip: 'clips', audio: 'audio', title: 'titles', prompt: 'prompts', frame: 'frames', control: 'controls', plan3d: 'plans3d', marker: 'markers', reference: 'references' };
const LINKED = ['prompts', 'frames', 'controls', 'plans3d'];

export function select(kind, id) {
	ui.selection = kind ? { kind, id } : null;
	if (kind && ui.workspace !== 'mixer') ui.inspectorOpen = true;
}
export function selected() {
	const s = ui.selection;
	if (!s) return null;
	if (s.kind === 'lane') return doc.lanes.find((l) => l.id === s.id) ?? null;
	const list = doc[collections[s.kind]];
	return list?.find((x) => x.id === s.id) ?? null;
}
export function listOf(kind) {
	return doc[collections[kind]];
}

export const startOf = (item) => ('time' in item ? item.time : item.start);

export function clipAt(time) {
	return doc.clips.find((c) => time >= c.start && time < c.start + c.dur) ?? null;
}
export function shotIdAt(time) {
	return clipAt(time)?.id ?? null;
}
export function relink(item) {
	item.shotId = shotIdAt(startOf(item));
}

function linkedTo(shotId) {
	return LINKED.flatMap((key) => doc[key].filter((x) => x.shotId === shotId));
}
function shiftLinked(shotId, delta) {
	for (const item of linkedTo(shotId)) {
		if ('time' in item) item.time = round(item.time + delta, 0.04);
		else item.start = round(item.start + delta, 0.04);
	}
}
function removeWhere(list, test) {
	for (let i = list.length - 1; i >= 0; i--) if (test(list[i])) list.splice(i, 1);
}
function dropLinked(shotId) {
	for (const key of LINKED) removeWhere(doc[key], (x) => x.shotId === shotId);
	removeWhere(doc.references, (r) => r.scope?.type === 'shot' && r.scope.shotId === shotId);
}

export function relayout() {
	const before = new Map(doc.clips.map((c) => [c.id, c.start]));
	let at = 0;
	for (const c of doc.clips) {
		c.start = round(at, 0.04);
		at += c.dur;
	}
	for (const c of doc.clips) {
		const delta = c.start - (before.get(c.id) ?? c.start);
		if (Math.abs(delta) > 1e-6) shiftLinked(c.id, delta);
	}
}

export function deleteSelection() {
	const s = ui.selection;
	if (s?.kind === 'lane') return deleteLane(s.id);
	if (!s) return;
	const list = listOf(s.kind);
	const i = list.findIndex((x) => x.id === s.id);
	if (i < 0) return;
	act(() => {
		const [removed] = list.splice(i, 1);
		if (s.kind === 'clip') {
			dropLinked(removed.id);
			relayout();
		}
		if (s.kind === 'plan3d') dropPlanControls(doc.controls, removed.id);
	});
	ui.selection = null;
	toast(t('lib.toast.deleted'), 'info', { label: t('shell.toast.undo'), run: undo });
}

export function duplicateSelection() {
	const s = ui.selection;
	if (!s || s.kind === 'lane' || s.kind === 'reference') return;
	const list = listOf(s.kind);
	const i = list.findIndex((x) => x.id === s.id);
	if (i < 0) return;
	const copy = JSON.parse(JSON.stringify($state.snapshot(list[i])));
	copy.id = ulid();
	if (s.kind === 'plan3d') copy.keyframes = copy.keyframes.map((k) => ({ ...k, id: ulid() }));
	act(() => {
		if (s.kind === 'clip') {
			list.splice(i + 1, 0, copy);
			relayout();
		} else if ('time' in copy) {
			copy.time = round(copy.time + 1);
			if ('shotId' in copy) relink(copy);
			list.push(copy);
		} else {
			copy.start = round(copy.start + copy.dur);
			if ('shotId' in copy) relink(copy);
			list.push(copy);
		}
	});
	select(s.kind, copy.id);
	toast(t('lib.toast.duplicated'));
}

export function bladeAt(time = ui.playhead) {
	const s = ui.selection;
	if (s?.kind === 'audio') {
		const a = doc.audio.find((x) => x.id === s.id);
		if (a && time > a.start + 0.1 && time < a.start + a.dur - 0.1) {
			act(() => {
				const left = time - a.start;
				const b = { ...$state.snapshot(a), id: ulid(), start: round(time, 0.04), dur: a.dur - left, srcIn: a.srcIn + left, fadeIn: 0 };
				a.dur = left;
				a.fadeOut = 0;
				doc.audio.push(b);
			});
			return toast(t('lib.toast.audioSplit'));
		}
	}
	const c = clipAt(time);
	if (!c || time - c.start < 0.1 || c.start + c.dur - time < 0.1) return toast(t('lib.toast.splitOutside'), 'warning');
	act(() => {
		const left = time - c.start;
		const i = doc.clips.indexOf(c);
		const kept = round(left, 0.04);
		const b = { ...$state.snapshot(c), id: ulid(), start: round(c.start + kept, 0.04), dur: round(c.dur - left, 0.04), srcIn: c.srcIn + left, fadeIn: 0 };
		c.dur = kept;
		c.fadeOut = 0;
		doc.clips.splice(i + 1, 0, b);
		for (const item of linkedTo(c.id)) if (startOf(item) >= time) item.shotId = b.id;
		relayout();
	});
	toast(t('lib.toast.shotSplit'));
}

export function markerLabel(kind) {
	if (kind === 'favori') return t('lib.default.favorite');
	if (kind === 'marker') return t('lib.default.marker');
	return t('lib.default.rejected');
}

export function addMarker(kind = 'marker') {
	act(() => doc.markers.push({ id: ulid(), time: round(ui.playhead, 0.04), label: markerLabel(kind), kind }));
	toast(t('lib.toast.markerAdded'));
}

export function addAssetToTimeline(assetId, at = null) {
	const a = asset(assetId);
	if (!a) return;
	if (a.kind === 'audio') {
		let laneId = null;
		act(() => {
			laneId = laneForRole(a.role ?? 'Musique').id;
			doc.audio.push(newSound(assetId, laneId, round(at ?? ui.playhead, 0.04), a.srcDur));
		});
		toast(t('lib.toast.addedToLane', { name: a.name, lane: laneCode(doc.lanes, laneId) }));
		return;
	}
	const c = newClip({ assetId, dur: Math.min(5, a.srcDur ?? 5), label: a.name, stage: a.generated ? a.quality : 'source' });
	act(() => {
		const at2 = at ?? ui.playhead;
		let idx = doc.clips.findIndex((x) => at2 < x.start + x.dur / 2);
		if (idx < 0) idx = doc.clips.length;
		doc.clips.splice(idx, 0, c);
		relayout();
	});
	select('clip', c.id);
	toast(t('lib.toast.addedToCut', { name: a.name }));
}

function newPrompt(clip, text = '', strength = 75) {
	return { id: ulid(), shotId: clip.id, start: clip.start, dur: clip.dur, strength, text };
}

export function promptOf(clip) {
	if (!clip) return null;
	return doc.prompts.find((p) => p.shotId === clip.id) ?? null;
}

export function promptEdited(prompt, before) {
	if (!prompt?.shotId || String(prompt.text ?? '').trim() === String(before ?? '').trim()) return;
	touch(doc.clips.find((c) => c.id === prompt.shotId));
}

export function setPrompt(clip, text) {
	if (!clip) return null;
	const p = promptOf(clip);
	act(() => {
		if (p) {
			const before = p.text;
			p.text = text;
			promptEdited(p, before);
		} else doc.prompts.push(newPrompt(clip, text));
	});
	return promptOf(clip);
}

export function ensurePrompt(clip) {
	const existing = promptOf(clip);
	if (existing || !clip) return { prompt: existing, created: false };
	act(() => doc.prompts.push(newPrompt(clip)));
	return { prompt: promptOf(clip), created: true };
}

export function addPrompt(start = ui.playhead, dur = 4) {
	const p = { id: ulid(), shotId: shotIdAt(start), start: round(start, 0.04), dur, strength: 75, text: '' };
	act(() => doc.prompts.push(p));
	select('prompt', p.id);
	ui.modal = { type: 'prompt', id: p.id, isNew: true };
}

export function addFrame(assetId = clipAt(ui.playhead)?.assetId ?? null, time = ui.playhead, role = 'Transition') {
	const f = { id: ulid(), shotId: shotIdAt(time), time: round(time, 0.04), assetId, role, strength: 75 };
	act(() => doc.frames.push(f));
	select('frame', f.id);
	toast(t('lib.toast.frameAdded'));
}

export function addControl() {
	const c = { id: ulid(), shotId: shotIdAt(ui.playhead), name: t('lib.default.importedControl'), start: round(ui.playhead, 0.04), dur: 4, guidance: 60, source: 'import', stale: false };
	act(() => doc.controls.push(c));
	select('control', c.id);
	toast(t('lib.toast.controlAdded'));
}

function newLane(role = 'Ambiance') {
	const lane = {
		id: newLaneId(),
		name: t('lib.default.track', { n: doc.lanes.length + 1 }),
		role,
		vol: -6,
		pan: 0,
		mute: false,
		solo: false,
		automation: 'off',
		sends: { R1: -60, D1: -60 },
		inserts: [{ type: 'eq', on: false, low: 0, mid: 0, high: 0 }]
	};
	doc.lanes.push(lane);
	return lane;
}

export function laneForRole(role) {
	return laneFor(doc, role) ?? newLane(role);
}

export function addAudioLane() {
	act(() => newLane());
	toast(t('lib.toast.laneAdded', { id: laneCode(doc.lanes, doc.lanes.at(-1).id) }));
}

let confirmingLane = false;

export async function deleteLane(id) {
	const lane = doc.lanes.find((l) => l.id === id);
	if (!lane || confirmingLane) return false;
	const code = laneCode(doc.lanes, id);
	const count = laneItemCount(doc, id);
	confirmingLane = true;
	let ok = false;
	try {
		ok = await confirm({
			title: t('lib.lane.deleteTitle', { lane: code }),
			message: count ? t('lib.lane.deleteItems', { count, lane: code, name: lane.name }) : t('lib.lane.deleteEmpty', { lane: code, name: lane.name }),
			variant: 'danger',
			confirmLabel: t('lib.lane.deleteConfirm')
		});
	} finally {
		confirmingLane = false;
	}
	if (!ok || !doc.lanes.some((l) => l.id === id)) return false;
	let removed = 0;
	act(() => (removed = removeLane(doc, id).items.length));
	if (ui.selection && !selected()) ui.selection = null;
	toast(removed ? t('lib.toast.laneDeleted', { count: removed, lane: code }) : t('lib.toast.laneDeletedEmpty', { lane: code }), 'info', { label: t('shell.toast.undo'), run: undo });
	return true;
}

export function productionRange() {
	const p = ui.production;
	if (p.target === 'range' && ui.range) return [ui.range.in, ui.range.out];
	if (p.target === 'sequence') return [0, seqDuration()];
	const sel = selected();
	if (sel && 'start' in sel && 'dur' in sel && ui.selection.kind !== 'audio') return [sel.start, sel.start + sel.dur];
	const c = clipAt(ui.playhead) ?? doc.clips[0];
	return c ? [c.start, c.start + c.dur] : [0, 0];
}
export const overlaps = (s, d, [a, b]) => s < b && s + d > a;
export function shotsIn(range) {
	return doc.clips.filter((c) => overlaps(c.start, c.dur, range));
}
export function itemsIn(range) {
	const shots = new Set(shotsIn(range).map((c) => c.id));
	const inRange = (item, byTime) => (item.shotId ? shots.has(item.shotId) : byTime);
	return {
		prompts: doc.prompts.filter((p) => inRange(p, overlaps(p.start, p.dur, range))),
		frames: doc.frames.filter((f) => inRange(f, f.time >= range[0] && f.time <= range[1])),
		controls: doc.controls.filter((c) => inRange(c, overlaps(c.start, c.dur, range))),
		plans3d: doc.plans3d.filter((s) => inRange(s, overlaps(s.start, s.dur, range))),
		references: doc.references.filter((r) => r.scope.type === 'global' || (r.scope.type === 'shot' && shots.has(r.scope.shotId)))
	};
}

export function globalPrompt() {
	const d = doc.direction;
	return ['univers', 'personnages', 'photographie', 'palette', 'rythme']
		.map((k) => d[k]?.trim())
		.filter(Boolean)
		.join(' ');
}

const rules = compileRules(sharedRules);
const issueTexts = {
	noNeon: () => t('lib.issue.noNeon'),
	noText: () => t('lib.issue.noText'),
	naturalColors: () => t('lib.issue.naturalColors'),
	stableCamera: () => t('lib.issue.stableCamera')
};
export const ruleText = (id) => issueTexts[id]?.() ?? null;

function controlFor(p) {
	return doc.controls.find((c) => (p.shotId && c.shotId ? c.shotId === p.shotId : overlaps(c.start, c.dur, [p.start, p.start + p.dur])));
}

export function promptIssues(p) {
	if (!p) return [];
	const g = globalPrompt();
	const language = promptLanguageOf(doc.promptLanguage);
	const out = [];
	for (const id of conflictIds(rules, language, g, p.text)) out.push({ level: 'conflict', text: ruleText(id) ?? id });
	const ctrl = controlFor(p);
	if (ctrl && namesCamera(rules, language, p.text)) out.push({ level: 'control', text: t('lib.issue.controlCamera', { name: ctrl.name }) });
	if (!p.text.trim()) out.push({ level: 'missing', text: t('lib.issue.emptyPrompt') });
	return out;
}
export function allIssues() {
	return doc.prompts.flatMap((p) => promptIssues(p).map((i) => ({ ...i, prompt: p })));
}

export const sourceLength = (c) => asset(c?.assetId)?.srcDur ?? 60;
export const clipLabel = (c) => c?.label || asset(c?.assetId)?.name || t('lib.default.clip');

export function fmtDuration(sec) {
	if (sec < 60) return `${Math.max(1, Math.round(sec))} s`;
	const m = Math.floor(sec / 60);
	const r = Math.round(sec % 60);
	return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}` : `${m} min${r ? ` ${String(r).padStart(2, '0')}` : ''}`;
}

export function addShot(label = t('lib.default.shot'), prompt = '', dur = 4, after = null) {
	const c = newClip({ label, dur });
	act(() => {
		const i = after ? doc.clips.findIndex((x) => x.id === after) + 1 : doc.clips.length;
		doc.clips.splice(i, 0, c);
		relayout();
		if (prompt) doc.prompts.push(newPrompt(c, prompt));
	});
	select('clip', c.id);
	return c;
}

export function moveClip(from, to) {
	if (from === to) return;
	act(() => {
		const [m] = doc.clips.splice(from, 1);
		doc.clips.splice(to, 0, m);
		relayout();
	});
}

export function proposeShots() {
	const sentences = doc.synopsis
		.split(/(?<=[.!?])\s+/)
		.map((x) => x.trim())
		.filter(Boolean);
	ui.storyProposal = sentences.map((text, i) => {
		const head = text.replace(/[.!?]$/, '').split(/[:,]/)[0].trim();
		return { id: ulid(), keep: true, n: i + 1, label: head.length > 34 ? head.slice(0, 32) + '…' : head, prompt: text, dur: Math.max(3, Math.min(7, Math.round(text.length / 14))) };
	});
}
export function acceptProposal() {
	const list = (ui.storyProposal ?? []).filter((x) => x.keep);
	if (!list.length) return;
	act(() => {
		for (const sp of list) {
			const c = newClip({ label: sp.label, dur: sp.dur });
			doc.clips.push(c);
			relayout();
			doc.prompts.push(newPrompt(c, sp.prompt));
		}
	});
	ui.storyProposal = null;
	toast(t('lib.toast.shotsAdded', { count: list.length }), 'success');
}

export function replaceDoc(next) {
	const incoming = migrate({ ...next, assets: Array.isArray(next?.assets) ? next.assets : [] });
	delete incoming.results;
	for (const k of Object.keys(doc)) if (!(k in incoming)) delete doc[k];
	Object.assign(doc, incoming);
	past.length = 0;
	future.length = 0;
	Object.assign(ui, { selection: null, preview: null, compare: null, range: null, drag: null, storyProposal: null, dirty: false });
	Object.assign(ui.production, { state: 'ready', progress: 0, running: 0, step: '', lastCount: 0 });
	resetTakes();
	Object.assign(ui.scene, { current: null, keyframe: null, seeded: null });
	if (ui.playhead > seqDuration()) ui.playhead = 0;
}

export function dispose() {
	for (const id of toastTimers) clearTimeout(id);
	toastTimers.clear();
	ui.toasts.length = 0;
	ui.menuOpen = null;
	ui.paletteOpen = false;
	ui.modal = null;
}

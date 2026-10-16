import { formatNumber, t } from '../i18n/index.svelte.js';
import { backends, engineName } from './catalog.js';
import { emptyDoc, newAsset, newClip, promptLanguageOf } from './starter.js';
import { toast as hostToast } from './host.js';
import { ulid } from './ulid.js';

export { newAsset, newClip };

export const doc = $state(emptyDoc(t));

export const ui = $state({
	workspace: 'storyboard',
	dockTab: 'direction',
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
	scene: { current: null, az: -40, el: 18, dist: 14, focal: 28, height: 1.4, keyframe: null },
	production: {
		target: 'clip',
		mode: 'Génération IA',
		state: 'ready',
		progress: 0,
		step: '',
		queue: [],
		lastCount: 0,
		quality: 'draft',
		job: null
	},
	inspectorTab: 'video',
	quota: null,
	storyProposal: null,
	me: null,
	isAdmin: false
});

export function applyMe(me) {
	ui.me = { locale: me?.locale ?? null, isAdmin: me?.isAdmin === true, quota: me?.quota ?? null, version: me?.version ?? null, lastProjectId: me?.lastProjectId ?? null };
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
export const simulated = (what) => toast(t('lib.toast.simulated', { what }), 'sim');

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
	if (!s || s.kind === 'lane') return;
	const list = listOf(s.kind);
	const i = list.findIndex((x) => x.id === s.id);
	if (i < 0) return;
	act(() => {
		const [removed] = list.splice(i, 1);
		if (s.kind === 'clip') {
			dropLinked(removed.id);
			relayout();
		}
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
		const laneId = doc.lanes.find((l) => l.role === a.role)?.id ?? 'A2';
		act(() => doc.audio.push({ id: ulid(), assetId, lane: laneId, start: round(at ?? ui.playhead, 0.04), dur: Math.min(a.srcDur ?? 8, 8), srcIn: 0, fadeIn: 0.5, fadeOut: 0.5, gain: -6 }));
		toast(t('lib.toast.addedToLane', { name: a.name, lane: laneId }));
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

export function setPrompt(clip, text) {
	if (!clip) return null;
	const p = promptOf(clip);
	act(() => {
		if (p) p.text = text;
		else doc.prompts.push(newPrompt(clip, text));
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

export function addControl(source = 'import') {
	const name = source === 'scene3d' ? t('lib.default.guide3d', { name: doc.plans3d[0]?.name ?? t('lib.default.scene') }) : t('lib.default.importedControl');
	const c = { id: ulid(), shotId: shotIdAt(ui.playhead), name, start: round(ui.playhead, 0.04), dur: 4, guidance: 60, source, stale: false };
	act(() => doc.controls.push(c));
	select('control', c.id);
	toast(t('lib.toast.controlAdded'));
}

export function addAudioLane() {
	const n = doc.lanes.length + 1;
	act(() =>
		doc.lanes.push({
			id: `A${n}`,
			name: t('lib.default.track', { n }),
			role: 'Ambiance',
			vol: -6,
			pan: 0,
			mute: false,
			solo: false,
			automation: 'off',
			sends: { R1: -60, D1: -60 },
			inserts: [{ type: 'eq', on: false, low: 0, mid: 0, high: 0 }]
		})
	);
	toast(t('lib.toast.laneAdded', { id: `A${n}` }));
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

const conflicts = {
	fr: [
		{ global: /aucun n[ée]on|pas de n[ée]on|sans n[ée]on/i, local: /n[ée]on/i, why: () => t('lib.issue.noNeon') },
		{ global: /aucun texte|sans texte/i, local: /\btexte\b|sous-titre|logo/i, why: () => t('lib.issue.noText') },
		{ global: /couleurs naturelles/i, local: /monochrome|noir et blanc|fluo/i, why: () => t('lib.issue.naturalColors') },
		{ global: /cam[ée]ra stable|lente/i, local: /cam[ée]ra (à l’épaule|tremblée)|rapide|frénétique/i, why: () => t('lib.issue.stableCamera') }
	],
	en: [
		{ global: /\bno neons?\b|without neons?/i, local: /\bneons?\b/i, why: () => t('lib.issue.noNeon') },
		{ global: /\bno (on-screen )?text\b|without text/i, local: /\btext\b|subtitles?|\blogo/i, why: () => t('lib.issue.noText') },
		{ global: /natural colou?rs/i, local: /monochrome|black and white|black-and-white|fluo|fluorescent/i, why: () => t('lib.issue.naturalColors') },
		{ global: /(steady|stable) camera|\bslow\b/i, local: /handheld|shaky camera|\bfast\b|\brapid\b|frantic/i, why: () => t('lib.issue.stableCamera') }
	]
};
const cameraWords = {
	fr: /travelling|survol|panoramique|orbite|arc de cam|dolly|zoom|élévation|plan fixe|mouvement fluide|déplacement latéral/i,
	en: /tracking shot|travelling|flyover|fly-over|\bpan\b|panning|orbit|camera arc|dolly|zoom|crane|static shot|fluid movement|lateral move/i
};

function controlFor(p) {
	return doc.controls.find((c) => (p.shotId && c.shotId ? c.shotId === p.shotId : overlaps(c.start, c.dur, [p.start, p.start + p.dur])));
}

export function promptIssues(p) {
	if (!p) return [];
	const g = globalPrompt();
	const language = promptLanguageOf(doc.promptLanguage);
	const out = [];
	for (const c of conflicts[language]) if (c.global.test(g) && c.local.test(p.text)) out.push({ level: 'conflict', text: c.why() });
	const ctrl = controlFor(p);
	if (ctrl && cameraWords[language].test(p.text)) out.push({ level: 'control', text: t('lib.issue.controlCamera', { name: ctrl.name }) });
	if (!p.text.trim()) out.push({ level: 'missing', text: t('lib.issue.emptyPrompt') });
	return out;
}
export function allIssues() {
	return doc.prompts.flatMap((p) => promptIssues(p).map((i) => ({ ...i, prompt: p })));
}

export const sourceLength = (c) => asset(c?.assetId)?.srcDur ?? 60;
export const clipLabel = (c) => c?.label || asset(c?.assetId)?.name || t('lib.default.clip');
export const backend = () => backends.find((b) => b.id === doc.engine.backend) ?? backends[0];

export function ensureResultAsset(r) {
	const id = `gen-${r.id}`;
	if (asset(id)) return id;
	const c = doc.clips.find((x) => x.id === r.clipId);
	const name = r.quality === 'final' ? t('lib.default.takeFinal', { shot: clipLabel(c), variant: r.variant }) : t('lib.default.takeDraft', { shot: clipLabel(c), variant: r.variant });
	const [width, height] = r.quality === 'final' ? [1920, 1080] : [1280, 720];
	doc.assets.push(newAsset({ id, name, kind: 'video', srcDur: r.range[1] - r.range[0] + 2, width, height, fps: 25, res: `${width}×${height}`, generated: true, quality: r.quality, resultId: r.id }));
	return id;
}
export function seedResultAssets() {
	for (const r of doc.results) ensureResultAsset(r);
}

export function takesOf(clip) {
	return doc.results
		.filter((r) => r.clipId === clip?.id)
		.sort((a, b) => (a.quality === b.quality ? a.variant.localeCompare(b.variant) : a.quality === 'draft' ? -1 : 1));
}

export function useTake(clip, resultId, silent = false) {
	const r = doc.results.find((x) => x.id === resultId);
	if (!clip || !r) return;
	const apply = () => {
		clip.assetId = ensureResultAsset(r);
		clip.take = r.id;
		clip.srcIn = 0;
		clip.stage = r.quality;
		for (const o of takesOf(clip)) if (o.status === 'chosen' && o.id !== r.id) o.status = 'new';
		r.status = 'chosen';
	};
	silent ? apply() : act(apply);
	ui.preview = null;
	if (!silent) toast(r.quality === 'final' ? t('lib.toast.useTakeFinal', { shot: clipLabel(clip), variant: r.variant }) : t('lib.toast.useTakeDraft', { shot: clipLabel(clip), variant: r.variant }));
}

const factor = { '720p': 0.5, '1080p': 1, '4K': 2.6 };
export function estimate({ seconds, quality = ui.production.quality, variants = doc.engine.variants, be = backend() }) {
	const res = quality === 'final' ? doc.engine.resolution : '720p';
	const perSec = (quality === 'final' ? 16 : 3.5) * factor[res] * (doc.engine.steps / 30);
	const gpuSec = (seconds * variants * perSec) / be.speed;
	const vram = Math.round((quality === 'final' ? 14 : 8) * factor[res] * (variants > 2 ? 1.25 : 1) + 2);
	const quotaMin = (seconds * variants * perSec) / 60;
	return {
		gpuSec,
		vram,
		quotaMin,
		res,
		overVram: vram > be.vram,
		overQuota: !be.cost && !!ui.quota && ui.quota.used + quotaMin > ui.quota.limit,
		cost: be.cost ? (gpuSec / 60) * be.cost : 0
	};
}
export function fmtDuration(sec) {
	if (sec < 60) return `${Math.max(1, Math.round(sec))} s`;
	const m = Math.floor(sec / 60);
	const r = Math.round(sec % 60);
	return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}` : `${m} min${r ? ` ${String(r).padStart(2, '0')}` : ''}`;
}

export function jobClips(range = productionRange()) {
	const sel = ui.selection?.kind === 'clip' ? doc.clips.find((c) => c.id === ui.selection.id) : null;
	if (ui.production.target === 'clip') return [sel ?? clipAt(ui.playhead) ?? doc.clips[0]].filter(Boolean);
	const inRange = shotsIn(range);
	const toMake = inRange.filter((c) => c.stage !== 'source');
	return toMake.length ? toMake : inRange;
}
export function jobEstimate(opts = {}) {
	const clips = opts.clips ?? jobClips();
	return { clips, ...estimate({ seconds: clips.reduce((sum, c) => sum + c.dur, 0), quality: opts.quality, variants: opts.variants }) };
}

function clipsRange(clips) {
	return [Math.min(...clips.map((c) => c.start)), Math.max(...clips.map((c) => c.start + c.dur))];
}

let timer = null;
export function readiness(opts = {}) {
	const r = opts.clips?.length ? clipsRange(opts.clips) : productionRange();
	const items = itemsIn(r);
	const missing = [];
	const warnings = [];
	const mode = ui.production.mode;
	if (r[1] - r[0] <= 0.05) missing.push(t('lib.block.noRange'));
	if (mode !== 'Rendu 3D') {
		if (!globalPrompt() && !items.prompts.length) missing.push(t('lib.block.noDirection'));
		const empty = items.prompts.filter((p) => !p.text.trim());
		if (empty.length) missing.push(t('lib.block.emptyPrompts', { count: empty.length }));
	}
	if (mode !== 'Génération IA' && !items.plans3d.length) missing.push(t('lib.block.noPlan3d'));
	const est = jobEstimate({ clips: opts.clips, quality: opts.quality, variants: opts.variants });
	if (est.overVram) warnings.push(t('lib.warn.vram', { need: est.vram, engine: engineName(backend()), have: backend().vram }));
	if (mode !== 'Rendu 3D' && doc.direction.mode === 'FL2VA' && !items.frames.length) warnings.push(t('lib.warn.noFrame'));
	if (est.overQuota) missing.push(t('lib.block.quota', { used: Math.round(ui.quota.used + est.quotaMin), limit: ui.quota.limit }));
	return { range: r, items, missing, warnings, est };
}

export function startGeneration(opts = {}) {
	const p = ui.production;
	if (p.state === 'running' || p.state === 'paused') return toast(t('lib.toast.jobRunning'), 'warning');
	const { missing, warnings, range } = readiness(opts);
	if (missing.length) return toast(missing[0], 'warning');
	if (warnings.length) toast(warnings[0], 'warning');
	const quality = opts.quality ?? p.quality;
	const variants = opts.variants ?? doc.engine.variants;
	const clips = opts.clips ?? jobClips(range);
	const est = jobEstimate({ clips, quality, variants });
	p.job = { clips: clips.map((c) => c.id), quality, variants, parent: opts.parent ?? null, mode: p.mode, est };
	p.state = 'running';
	p.progress = 0;
	tick();
}
export function promoteToFinal(resultId) {
	const r = doc.results.find((x) => x.id === resultId);
	const c = doc.clips.find((x) => x.id === r?.clipId);
	if (c) startGeneration({ clips: [c], quality: 'final', variants: 1, parent: r.id });
}

function stepLabel(i) {
	return [t('lib.step.assemble'), t('lib.step.encode'), t('lib.step.denoise'), t('lib.step.stitch'), t('lib.step.post')][i];
}
function tick() {
	clearInterval(timer);
	const speed = ui.production.job?.quality === 'final' ? 1.4 : 2.6;
	timer = setInterval(() => {
		const p = ui.production;
		if (p.state !== 'running') return clearInterval(timer);
		p.progress = Math.min(100, p.progress + speed + Math.random() * 2.5);
		p.step = stepLabel(Math.min(4, Math.floor(p.progress / 20)));
		if (p.progress >= 100) {
			clearInterval(timer);
			finishGeneration();
		}
	}, 120);
}
export function pauseGeneration() {
	ui.production.state = 'paused';
}
export function resumeGeneration() {
	ui.production.state = 'running';
	tick();
}
export function cancelGeneration() {
	clearInterval(timer);
	ui.production.state = 'ready';
	ui.production.progress = 0;
	toast(t('lib.toast.cancelled'));
}


const lookKeys = ['warm', 'mist', 'cool', 'dusk', 'night'];
function finishGeneration() {
	const p = ui.production;
	const job = p.job;
	const parent = job.parent ? doc.results.find((r) => r.id === job.parent) : null;
	const now = new Date().toTimeString().slice(0, 5);
	let made = 0;
	act(() => {
		for (const id of job.clips) {
			const c = doc.clips.find((x) => x.id === id);
			if (!c) continue;
			const lp = promptOf(c) ?? doc.prompts.find((x) => !x.shotId && overlaps(x.start, x.dur, [c.start, c.start + c.dur]));
			const existing = takesOf(c).filter((r) => r.quality === job.quality).length;
			const fresh = [];
			for (let i = 0; i < job.variants; i++) {
				const r = {
					id: ulid(),
					clipId: c.id,
					quality: job.quality,
					variant: String.fromCharCode(65 + existing + i),
					assetId: null,
					look: parent?.look ?? lookKeys[(doc.results.length + i) % lookKeys.length],
					status: 'new',
					seed: parent?.seed ?? doc.engine.seed + doc.results.length + i,
					created: now,
					range: [c.start, c.start + c.dur],
					local: lp?.text ?? '—',
					parent: parent?.id ?? null,
					profile: doc.direction.mode,
					mode: job.mode,
					backend: doc.engine.backend
				};
				doc.results.push(r);
				ensureResultAsset(r);
				fresh.push(r);
				made++;
			}
			if (c.stage === 'todo' || parent) useTake(c, fresh[0].id, true);
		}
	});
	if (!backend().cost && ui.quota) ui.quota.used = Math.min(ui.quota.limit, ui.quota.used + job.est.quotaMin);
	p.state = 'done';
	p.lastCount = made;
	const message = parent ? t('lib.toast.finalReady') : job.quality === 'final' ? t('lib.toast.takesFinal', { count: made }) : t('lib.toast.takesDraft', { count: made });
	toast(message, 'success', { label: t('shell.toast.view'), run: () => openResults() });
}
export function openResults() {
	ui.workspace = 'director';
	ui.dockTab = 'results';
	ui.production.state = ui.production.state === 'done' ? 'ready' : ui.production.state;
}

export function queueWindow() {
	const { missing, range } = readiness();
	if (missing.length) return toast(missing[0], 'warning');
	ui.production.queue.push({ id: ulid(), range, mode: ui.production.mode, quality: ui.production.quality, label: `${secs(range[0])} → ${secs(range[1])}` });
	toast(t('lib.toast.queued'));
}

export function insertResult(id) {
	const r = doc.results.find((x) => x.id === id);
	if (!r) return;
	useTake(doc.clips.find((x) => x.id === r.clipId) ?? clipAt((r.range[0] + r.range[1]) / 2), id);
}

export function assembleChosen() {
	const chosen = doc.results.filter((r) => r.status === 'chosen');
	if (!chosen.length) return toast(t('lib.toast.chooseFirst'), 'warning');
	act(() => {
		for (const r of chosen) useTake(doc.clips.find((c) => c.id === r.clipId), r.id, true);
	});
	toast(t('lib.toast.assembled', { count: chosen.length }), 'success');
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

export function contextSnapshot() {
	const p = ui.production;
	return {
		workspace: ui.workspace,
		selection: ui.selection ? { ...ui.selection } : null,
		playhead: round(ui.playhead, 0.04),
		range: ui.range ? { in: ui.range.in, out: ui.range.out } : null,
		direction: $state.snapshot(doc.direction),
		promptLanguage: promptLanguageOf(doc.promptLanguage),
		synopsis: doc.synopsis,
		production: { target: p.target, mode: p.mode, quality: p.quality, state: p.state, progress: Math.round(p.progress), queue: p.queue.length }
	};
}

export function replaceDoc(next) {
	clearInterval(timer);
	timer = null;
	const incoming = { ...next, assets: Array.isArray(next?.assets) ? next.assets : [] };
	for (const k of Object.keys(doc)) if (!(k in incoming)) delete doc[k];
	Object.assign(doc, incoming);
	past.length = 0;
	future.length = 0;
	Object.assign(ui, { selection: null, preview: null, compare: null, range: null, drag: null, storyProposal: null, dirty: false });
	Object.assign(ui.production, { state: 'ready', progress: 0, step: '', queue: [], lastCount: 0, job: null });
	Object.assign(ui.scene, { current: null, keyframe: null });
	seedResultAssets();
	if (ui.playhead > seqDuration()) ui.playhead = 0;
}

export function dispose() {
	clearInterval(timer);
	timer = null;
	if (ui.production.state === 'running') ui.production.state = 'paused';
	for (const id of toastTimers) clearTimeout(id);
	toastTimers.clear();
	ui.toasts.length = 0;
	ui.menuOpen = null;
	ui.paletteOpen = false;
	ui.modal = null;
}

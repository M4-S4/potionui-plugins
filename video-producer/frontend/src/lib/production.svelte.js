import { formatNumber, t } from '../i18n/index.svelte.js';
import { ui, doc, act, toast, asset, newAsset, clipLabel, productionRange, shotsIn, itemsIn, globalPrompt, clipAt, secs } from './state.svelte.js';
import { project, getClient, flushSave, projectGone, onLoaded } from './project.svelte.js';
import { takeStore, setTakes, upsertTake, patchTake, removeTake, takeById, realTakesOf, flyingTakes } from './takes.svelte.js';
import { PROFILES, aggregate, canUpscale, engineOptions, isInFlight, migrateEngine, optionFor, presetProfiles, progressText, takeAsset } from './generation.js';
import { applyRenders, freshRender } from './scene.svelte.js';
import { confirm, openHostModal } from './host.js';
import { labelOf, marksOf, relabel } from './labels.js';
import { generationCounts } from './shots.js';
import { projectQuality, shotEngineOf } from './engine.js';
import { prioritized } from './queue.js';

const AI_MODE = 'ai';
const RENDER_MODE = 'render3d';
const HYBRID_MODE = 'render3d_ai';
const generates = (mode) => mode === AI_MODE || mode === HYBRID_MODE;
const ESTIMATE_DELAY = 500;
const POLL_EVERY = 5000;
const INFO_WARNINGS = ['time_unknown', 'vram_unknown'];

export const estimateState = $state({ key: null, data: null, loading: false, error: null });
export const queueState = $state({ slots: null, elsewhere: null, positions: {} });
const run = $state({ starting: false });

let alive = false;
let estimateTimer = null;
let estimateController = null;
let pendingKey = null;
let flyingKey = null;
let pollTimer = null;
let polling = false;
let refreshing = null;
let refreshTimer = null;
let closeDetails = null;
const subscriptions = new Map();
const session = new Set();

const gone = (error) => error?.code === 'project_not_found';

export function engineChoices() {
	return engineOptions(ui.me);
}

export function engineGroups() {
	const groups = [];
	for (const option of engineChoices()) {
		let group = groups.find((g) => g.label === option.group);
		if (!group) {
			group = { label: option.group, options: [] };
			groups.push(group);
		}
		group.options.push(option);
	}
	return groups;
}

export function currentEngine() {
	return optionFor(engineChoices(), doc.engine);
}

export function presetById(id) {
	return (ui.me?.presets ?? []).find((p) => p.id === id) ?? null;
}

export function backendName(id) {
	return (ui.me?.engines ?? []).find((e) => e.id === id)?.name ?? id ?? '—';
}

export function engineOptionLabel(preset, model = null) {
	const option = optionFor(engineChoices(), { preset, model });
	if (option) return option.label;
	return preset ? t('generation.engine.unavailable') : t('generation.engine.none');
}

export function engineLabel() {
	const option = currentEngine();
	if (option) return option.label;
	return doc.engine?.preset ? t('generation.engine.unavailable') : t('generation.engine.none');
}

export function selectEngine(key) {
	const option = engineChoices().find((o) => o.key === key);
	if (!option) return;
	act(() => {
		doc.engine.preset = option.preset;
		doc.engine.model = option.model;
		doc.engine.backend = option.backend;
	});
}

export function shotEngineText(clip) {
	const own = shotEngineOf(clip);
	const parts = [];
	if ('preset' in own) parts.push(engineOptionLabel(own.preset, own.model));
	if (own.profile) parts.push(own.profile);
	if (own.quality) parts.push(own.quality === 'final' ? t('lib.stage.final') : t('lib.stage.draft'));
	if (own.seed !== undefined) parts.push(t('generation.ownEngine.seed', { seed: own.seed }));
	return parts.length ? t('generation.ownEngine.tip', { details: parts.join(' · ') }) : '';
}

export function setProjectQuality(quality) {
	const next = quality === 'final' ? 'final' : 'draft';
	act(() => (doc.engine.quality = next));
	ui.production.quality = next;
}

export function openEngineSettings() {
	ui.workspace = 'director';
	ui.dockTab = 'direction';
	ui.dockFocus = 'engine';
	ui.modal = null;
}

export function openQueue() {
	ui.workspace = 'director';
	ui.dockTab = 'queue';
}

function syncEngine() {
	if (!doc.engine) return;
	const next = migrateEngine(doc.engine, ui.me);
	if (doc.engine.backend !== next.backend) doc.engine.backend = next.backend;
	if (doc.engine.preset !== next.preset) doc.engine.preset = next.preset;
	if (doc.engine.model !== next.model) doc.engine.model = next.model;
}

export function supportedProfiles() {
	const option = currentEngine();
	return option ? presetProfiles(option.info) : [...PROFILES];
}

export function takesOf(clip) {
	return clip ? realTakesOf(clip.id) : [];
}

export function findTake(id) {
	return id ? (takeById(id) ?? null) : null;
}

export function shotActivity(shotId) {
	return aggregate(realTakesOf(shotId));
}

export const busy = () => run.starting || flyingTakes().length > 0;
export const upscaleAvailable = (take) => canUpscale(take, ui.me);

function shotName(shotId) {
	const clip = doc.clips.find((c) => c.id === shotId);
	return clip ? clipLabel(clip) : '—';
}

function fieldNames(fields) {
	return (Array.isArray(fields) ? fields : []).map((f) => (typeof f === 'string' ? f : (f?.label ?? f?.name ?? ''))).filter(Boolean);
}

const minutes = (v) => formatNumber(v ?? 0, { maximumFractionDigits: 1 });

function noteText(note) {
	const text = baseNoteText(note);
	const shots = Array.isArray(note?.data?.shot_ids) ? note.data.shot_ids.map(shotName) : [];
	return shots.length ? t('generation.block.forShots', { shots: shots.join(', '), text }) : text;
}

function baseNoteText(note) {
	const data = note?.data ?? {};
	const code = note?.code;
	if (code === 'no_shots') return t('generation.block.noShots');
	if (code === 'no_preset') return t('generation.block.noPreset');
	if (code === 'profile_unsupported') return t('generation.block.profileUnsupported', { profile: data.profile ?? doc.direction.mode, engine: data.preset_id ? engineOptionLabel(data.preset_id, null) : engineLabel() });
	if (code === 'missing_models') return t('generation.block.missingModels', { fields: fieldNames(data.fields).join(', ') || '—' });
	if (code === 'quota_exceeded') {
		const quota = estimateState.data?.quota;
		return t('generation.block.quota', { need: minutes(data.needed_minutes ?? quota?.neededMinutes), remaining: minutes(data.remaining ?? quota?.remaining) });
	}
	if (code === 'no_model') return t('generation.block.noModel');
	if (code === 'no_references') return t('generation.block.noReferences', { shot: shotName(data.shot_id) });
	if (code === 'source_unavailable') return t('generation.block.sourceUnavailable');
	if (code === 'upscale_unsupported') return t('generation.block.upscaleUnsupported');
	if (code === 'vram_stream') return t('generation.warn.vramStream');
	if (code === 'vram_unknown') return t('generation.warn.vramUnknown');
	if (code === 'time_unknown') return t('generation.warn.timeUnknown');
	if (code === 'fl2va_no_frame') return t('generation.warn.noFrame', { shot: shotName(data.shot_id) });
	if (code === 'text_only_preset') return t('generation.warn.textOnly', { shot: shotName(data.shot_id) });
	if (code === 'duration_clamped') return t('generation.warn.durationClamped', { shot: shotName(data.shot_id), max: secs(Number(data.max) || 0) });
	if (code === 'stale_guide') return t('generation.warn.staleGuide', { shot: shotName(data.shot_id) });
	if (code === 'guide_needs_refs') return t('generation.warn.guideNeedsRefs', { shot: shotName(data.shot_id) });
	if (code === 'refs_preset_needed') return t('generation.block.refsPresetNeeded');
	if (code === 'layout_lora_missing') return t('generation.block.layoutLoraMissing', { file: data.file ?? '' });
	if (code === 'layout_no_frame') return t('generation.warn.layoutNoFrame', { shot: shotName(data.shot_id) });
	if (code === 'layout_guide_short') return t('generation.warn.layoutGuideShort', { shot: shotName(data.shot_id), covered: data.covered ?? '—', needed: data.needed ?? '—' });
	return note?.message || code || '';
}

function clipsRange(clips) {
	return [Math.min(...clips.map((c) => c.start)), Math.max(...clips.map((c) => c.start + c.dur))];
}

export function jobClips(range = productionRange()) {
	const sel = ui.selection?.kind === 'clip' ? doc.clips.find((c) => c.id === ui.selection.id) : null;
	if (ui.production.target === 'clip') return [sel ?? clipAt(ui.playhead) ?? doc.clips[0]].filter(Boolean);
	const inRange = shotsIn(range);
	const toMake = inRange.filter((c) => c.stage !== 'source');
	return toMake.length ? toMake : inRange;
}

function requestBody(clips, quality, counts, option) {
	const body = { shots: clips.map((c) => c.id), quality, variants: counts.variants, preset_id: option.preset, model_id: option.model };
	if (Object.keys(counts.shot_variants).length) body.shot_variants = counts.shot_variants;
	if (ui.production.mode === HYBRID_MODE) body.production = HYBRID_MODE;
	return body;
}

export function estimateRequest() {
	if (!project.id || !generates(ui.production.mode)) return null;
	const option = currentEngine();
	const clips = jobClips();
	if (!option || !clips.length) return null;
	if (ui.dirty || project.status === 'saving') return { hold: true };
	const body = requestBody(clips, ui.production.quality, generationCounts(clips, doc.engine), option);
	return { key: JSON.stringify([project.id, project.version, body]), projectId: project.id, body };
}

function applyQuota(quota) {
	if (!quota?.applies || quota.exempt || quota.limit === null || quota.limit <= 0) return;
	ui.quota = { used: quota.used ?? Math.max(0, quota.limit - (quota.remaining ?? quota.limit)), limit: quota.limit };
}

async function fireEstimate(request) {
	estimateController?.abort();
	const controller = new AbortController();
	estimateController = controller;
	flyingKey = request.key;
	estimateState.loading = true;
	const result = await getClient().estimate(request.projectId, request.body, controller.signal);
	if (estimateController !== controller) return;
	estimateController = null;
	flyingKey = null;
	estimateState.loading = false;
	if (!result.ok) {
		if (result.error.code === 'aborted') return;
		if (gone(result.error)) return projectGone(request.projectId);
		Object.assign(estimateState, { key: request.key, data: null, error: result.error });
		return;
	}
	Object.assign(estimateState, { key: request.key, data: result.data, error: null });
	applyQuota(result.data.quota);
}

function clearPending() {
	clearTimeout(estimateTimer);
	estimateTimer = null;
	pendingKey = null;
}

export function scheduleEstimate(request) {
	if (request?.hold) return clearPending();
	if (!request) {
		clearPending();
		estimateController?.abort();
		estimateController = null;
		flyingKey = null;
		Object.assign(estimateState, { key: null, data: null, loading: false, error: null });
		return;
	}
	if (request.key === pendingKey || request.key === flyingKey) return;
	if (request.key === estimateState.key && !estimateController) return clearPending();
	clearPending();
	pendingKey = request.key;
	estimateTimer = setTimeout(() => {
		estimateTimer = null;
		pendingKey = null;
		fireEstimate(request);
	}, ESTIMATE_DELAY);
}

export function readiness(opts = {}) {
	const range = opts.clips?.length ? clipsRange(opts.clips) : productionRange();
	const items = itemsIn(range);
	const missing = [];
	const warnings = [];
	const notes = [];
	const gaps = [];
	const mode = ui.production.mode;
	if (range[1] - range[0] <= 0.05) missing.push(t('lib.block.noRange'));
	if (mode !== RENDER_MODE) {
		if (!globalPrompt() && !items.prompts.length) missing.push(t('lib.block.noDirection'));
		const empty = items.prompts.filter((p) => !p.text.trim());
		if (empty.length) missing.push(t('lib.block.emptyPrompts', { count: empty.length }));
	}
	if (mode !== AI_MODE) {
		const clips = opts.clips ?? jobClips(range);
		const rendered = clips.filter((c) => freshRender(c.id));
		if (!rendered.length) missing.push(items.plans3d.length ? t('lib.block.noRender3d') : t('lib.block.noPlan3d'));
		else if (rendered.length < clips.length) warnings.push(t('lib.warn.unrendered', { count: clips.length - rendered.length }));
	}
	const noEngine = generates(mode) && !currentEngine();
	if (noEngine) missing.push(doc.engine?.preset ? t('generation.block.unavailable') : t('generation.block.noEngine'));
	const est = !opts.clips && !noEngine && generates(mode) ? estimateState.data : null;
	const request = est ? estimateRequest() : null;
	const fresh = Boolean(request && (request.hold || request.key === estimateState.key));
	if (est && fresh) {
		for (const block of est.blocks) missing.push(noteText(block));
		for (const warning of est.warnings) {
			(INFO_WARNINGS.includes(warning.code) ? notes : warnings).push(noteText(warning));
			if (warning.code === 'fl2va_no_frame' && warning.data?.shot_id) gaps.push(warning.data.shot_id);
		}
	}
	return { range, items, missing, warnings, notes, gaps, est, noEngine };
}

function blockedText(error) {
	const blocks = Array.isArray(error?.data?.blocks) ? error.data.blocks : [];
	return blocks.length ? noteText(blocks[0]) : t('generation.block.generic');
}

function failed(error, fallback) {
	if (gone(error)) {
		projectGone(project.id);
		return;
	}
	if (error?.code === 'blocked' || (error?.status === 409 && Array.isArray(error?.data?.blocks))) toast(blockedText(error), 'warning');
	else toast(fallback, 'error');
}

export async function startGeneration(opts = {}) {
	if (ui.production.mode === RENDER_MODE) {
		const { missing, range } = readiness(opts);
		if (missing.length) return toast(missing[0], 'warning');
		return applyRenders(opts.clips ?? jobClips(range));
	}
	if (run.starting) return;
	if (!opts.clips && busy()) return toast(t('lib.toast.jobRunning'), 'warning');
	const { missing, warnings, range } = readiness(opts);
	if (missing.length) return toast(missing[0], 'warning');
	const option = currentEngine();
	const clips = opts.clips ?? jobClips(range);
	if (!option || !clips.length) return;
	const quality = opts.quality ?? ui.production.quality;
	const counts = generationCounts(clips, doc.engine, opts.variants);
	run.starting = true;
	updateProduction();
	try {
		const saved = await flushSave();
		if (!saved || !project.id) return toast(t('generation.toast.saveFirst'), 'error');
		const projectId = project.id;
		const result = await getClient().generate(projectId, requestBody(clips, quality, counts, option));
		if (projectId !== project.id) return;
		if (!result.ok) return failed(result.error, t('generation.toast.startFailed'));
		for (const take of result.data) upsertTake(take);
		if (warnings.length) toast(warnings[0], 'warning');
	} finally {
		run.starting = false;
		track();
	}
}

export function promoteToFinal(takeId) {
	const take = findTake(takeId);
	if (!take || take.status !== 'done' || take.quality !== 'draft') return toast(t('lib.toast.chooseDraft'), 'warning');
	ui.modal = { type: 'final', take: take.id };
}

export async function makeFinal(takeId, method, target) {
	const take = takeById(takeId);
	if (!take) return false;
	const projectId = project.id;
	const result = await getClient().finalTake(projectId, take.id, method, target);
	if (projectId !== project.id) return false;
	if (!result.ok) {
		failed(result.error, t('generation.toast.finalFailed'));
		return false;
	}
	upsertTake(result.data);
	track();
	return true;
}

export async function cancelTake(take) {
	const result = await getClient().cancelTake(take.id);
	if (!result.ok) {
		if (result.error.status === 404 || result.error.status === 409) await refreshTakes();
		else toast(t('generation.toast.actionFailed'), 'error');
		return;
	}
	upsertTake(result.data);
	track();
}

export async function cancelGeneration() {
	const flying = flyingTakes();
	if (!flying.length) return;
	const results = await Promise.all(flying.map((take) => getClient().cancelTake(take.id)));
	let failures = 0;
	for (const result of results) {
		if (result.ok) upsertTake(result.data);
		else failures += 1;
	}
	if (failures) await refreshTakes();
	track();
	toast(failures ? t('generation.toast.actionFailed') : t('lib.toast.cancelled'), failures ? 'error' : 'info');
}

export async function prioritizeTake(take) {
	const priority = prioritized(takeStore.list, take.id);
	if (priority === null) return;
	const before = take.priority ?? 0;
	patchTake(take.id, { priority });
	const projectId = project.id;
	const result = await getClient().prioritizeTake(projectId, take.id);
	if (projectId !== project.id) return;
	if (!result.ok) {
		patchTake(take.id, { priority: before });
		if (gone(result.error)) return projectGone(projectId);
		if (result.error.status === 404 || result.error.status === 409) await refreshTakes();
		else toast(t('generation.toast.actionFailed'), 'error');
		return;
	}
	upsertTake(result.data);
	await poll();
}

export async function retryTake(take) {
	const result = await getClient().retryTake(take.id);
	if (!result.ok) return failed(result.error, t('generation.toast.actionFailed'));
	upsertTake(result.data);
	track();
}

function applyLabels(changes) {
	for (const [id, label] of Object.entries(changes)) patchTake(id, marksOf(label));
}

async function sendLabel(take, label) {
	const before = Object.fromEntries(realTakesOf(take.shotId).map((x) => [x.id, labelOf(x)]));
	applyLabels(relabel(takeStore.list, take.id, label));
	const projectId = project.id;
	const result = await getClient().labelTake(projectId, take.id, label);
	if (projectId !== project.id) return;
	if (result.ok) return void upsertTake(result.data);
	applyLabels(before);
	toast(t('generation.toast.actionFailed'), 'error');
}

export function labelTake(clip, take, label) {
	if (!take) return;
	if (label === 'final') return labelOf(take) === 'final' && clip?.take === take.id ? undefined : useTake(clip, take.id);
	if (labelOf(take) === 'final' || labelOf(take) === label) return;
	return sendLabel(take, label);
}

export async function deleteTake(take) {
	const ok = await confirm({
		title: t('generation.delete.title'),
		message: t('generation.delete.message', { shot: shotName(take.shotId), variant: take.variant }),
		variant: 'danger',
		confirmLabel: t('generation.delete.confirm')
	});
	if (!ok) return;
	const result = await getClient().deleteTake(project.id, take.id);
	if (!result.ok && result.error.status !== 404) return toast(t('generation.toast.actionFailed'), 'error');
	removeTake(take.id);
	if (ui.preview?.id === take.id) ui.preview = null;
	if (ui.compare?.includes(take.id)) ui.compare = ui.compare.filter((id) => id !== take.id);
	track();
	toast(t('generation.toast.deleted'));
}

export function showDetails(take) {
	const generationId = typeof take?.generationId === 'string' ? take.generationId.trim() : '';
	if (!generationId || ui.hostModal || closeDetails) return;
	const close = openHostModal('GenerationDetailsModal', {
		generationId,
		initialFileIndex: 0,
		onClosed: () => {
			closeDetails = null;
			ui.hostModal = false;
		}
	});
	if (!close) return toast(t('generation.toast.detailsMissing'), 'warning');
	closeDetails = close;
	ui.hostModal = true;
	ui.menuOpen = null;
	ui.paletteOpen = false;
}

function ensureTakeAsset(take) {
	const id = `gen-${take.id}`;
	if (asset(id)) return id;
	if (!take.url) return null;
	const clip = doc.clips.find((c) => c.id === take.shotId);
	const name = take.quality === 'final' ? t('lib.default.takeFinal', { shot: clipLabel(clip), variant: take.variant }) : t('lib.default.takeDraft', { shot: clipLabel(clip), variant: take.variant });
	doc.assets.push(newAsset(takeAsset(take, name)));
	return id;
}

function place(clip, take) {
	const id = ensureTakeAsset(take);
	if (!clip || !id) return false;
	clip.assetId = id;
	clip.take = take.id;
	clip.srcIn = 0;
	clip.stage = take.quality;
	return true;
}

function markChosen(take) {
	if (labelOf(take) !== 'final') sendLabel(take, 'final');
}

function applyDone(take) {
	if (take.status !== 'done' || !take.url || asset(`gen-${take.id}`)) return false;
	const clip = doc.clips.find((c) => c.id === take.shotId);
	if (clip && (clip.stage === 'todo' || take.quality === 'final')) {
		place(clip, take);
		markChosen(take);
	} else ensureTakeAsset(take);
	return true;
}

export function useTake(clip, takeId, silent = false) {
	const take = takeById(takeId);
	if (!clip || !take || take.status !== 'done' || !take.url) return;
	const apply = () => place(clip, take);
	if (silent) apply();
	else act(apply);
	markChosen(take);
	ui.preview = null;
	if (!silent) toast(take.quality === 'final' ? t('lib.toast.useTakeFinal', { shot: clipLabel(clip), variant: take.variant }) : t('lib.toast.useTakeDraft', { shot: clipLabel(clip), variant: take.variant }));
}

export function insertResult(id) {
	const take = takeById(id);
	if (!take) return;
	useTake(doc.clips.find((c) => c.id === take.shotId), id);
}

export function assembleChosen() {
	const chosen = takeStore.list.filter((x) => labelOf(x) === 'final' && x.status === 'done' && x.url && doc.clips.some((c) => c.id === x.shotId));
	if (!chosen.length) return toast(t('lib.toast.chooseFirst'), 'warning');
	act(() => {
		for (const take of chosen) place(doc.clips.find((c) => c.id === take.shotId), take);
	});
	toast(t('lib.toast.assembled', { count: chosen.length }), 'success');
}

export function toggleCompare(id) {
	const list = ui.compare ? [...ui.compare] : [];
	const i = list.indexOf(id);
	if (i >= 0) list.splice(i, 1);
	else list.push(id);
	ui.compare = list.slice(-2);
	ui.preview = null;
	if (ui.compare.length === 1) toast(t('generation.card.pickSecond'));
}

export function openResults() {
	ui.workspace = 'director';
	ui.dockTab = 'results';
	if (ui.production.state === 'done') ui.production.state = 'ready';
}

function doneMessage(done) {
	if (done.every((x) => x.parentTakeId && x.quality === 'final')) return t('lib.toast.finalReady');
	if (done.every((x) => x.quality === 'final')) return t('lib.toast.takesFinal', { count: done.length });
	return t('lib.toast.takesDraft', { count: done.length });
}

function updateProduction() {
	const p = ui.production;
	const agg = aggregate(takeStore.list);
	if (agg.state === 'running' || run.starting) {
		p.state = 'running';
		p.progress = agg.progress;
		p.running = agg.running;
		p.step = agg.step || (agg.running ? t('generation.state.running') : t('lib.status.queued'));
		return;
	}
	if (p.state !== 'running') return;
	const finished = [...session].map(takeById).filter(Boolean);
	session.clear();
	p.progress = 0;
	p.running = 0;
	p.step = '';
	const done = finished.filter((x) => x.status === 'done');
	const failedTakes = finished.filter((x) => x.status === 'failed');
	p.lastCount = done.length;
	p.state = done.length ? 'done' : 'ready';
	if (done.length) toast(doneMessage(done), 'success', { label: t('shell.toast.view'), run: () => openResults() });
	if (failedTakes.length) toast(t('generation.toast.failed', { count: failedTakes.length }), 'error', { label: t('shell.toast.view'), run: () => openResults() });
}

function onEvent(takeId, generationId, event) {
	if (!alive) return;
	if (event?.type === 'generation_status') {
		const take = takeById(takeId);
		if (!take || !isInFlight(take)) return;
		const progress = event.progress === null || event.progress === undefined ? NaN : Number(event.progress);
		patchTake(takeId, { status: 'running', progress: Number.isFinite(progress) ? progress : take.progress, step: progressText(event.message, event.current_step) || take.step });
		updateProduction();
		return;
	}
	subscriptions.get(generationId)?.();
	subscriptions.delete(generationId);
	clearTimeout(refreshTimer);
	refreshTimer = setTimeout(() => refreshTakes(), 300);
}

function subscribe(take) {
	const id = take.generationId;
	const follow = typeof window === 'undefined' ? null : window.__potionui?.generation?.subscribe;
	if (!id || subscriptions.has(id) || typeof follow !== 'function') return;
	const off = follow(id, (event) => onEvent(take.id, id, event));
	subscriptions.set(id, typeof off === 'function' ? off : () => {});
}

function unsubscribeAll() {
	for (const off of subscriptions.values()) off();
	subscriptions.clear();
}

function track() {
	if (!alive) return updateProduction();
	const flying = flyingTakes();
	const followed = new Set(flying.map((x) => x.generationId).filter(Boolean));
	for (const [id, off] of subscriptions) {
		if (followed.has(id)) continue;
		off();
		subscriptions.delete(id);
	}
	for (const take of flying) {
		session.add(take.id);
		subscribe(take);
	}
	if (flying.length && !pollTimer) {
		pollTimer = setInterval(poll, POLL_EVERY);
		poll();
	}
	if (!flying.length && pollTimer) {
		clearInterval(pollTimer);
		pollTimer = null;
	}
	if (!flying.length) Object.assign(queueState, { slots: null, elsewhere: null, positions: {} });
	updateProduction();
}

function applyAll() {
	let changed = false;
	for (const take of takeStore.list) changed = applyDone(take) || changed;
	return changed;
}

async function poll() {
	if (polling || !alive || !project.id) return;
	polling = true;
	const projectId = project.id;
	const result = await getClient().queue(projectId);
	polling = false;
	if (!alive || projectId !== project.id) return;
	if (!result.ok) {
		if (gone(result.error)) projectGone(projectId);
		return;
	}
	const seen = new Set(result.data.takes.map((x) => x.id));
	Object.assign(queueState, { slots: result.data.slots, elsewhere: result.data.elsewhere, positions: result.data.positions });
	for (const take of result.data.takes) upsertTake(take);
	if (flyingTakes().some((x) => !seen.has(x.id))) await refreshTakes();
	else track();
}

async function refreshTakes() {
	if (refreshing) return refreshing;
	const projectId = project.id;
	if (!projectId || !getClient()) return;
	const known = new Set(takeStore.list.map((x) => x.id));
	refreshing = (async () => {
		const result = await getClient().listTakes(projectId);
		if (!alive || projectId !== project.id) return;
		if (!result.ok) {
			if (gone(result.error)) projectGone(projectId);
			return;
		}
		const ids = new Set(result.data.map((x) => x.id));
		for (const take of [...takeStore.list]) if (known.has(take.id) && !ids.has(take.id)) removeTake(take.id);
		for (const take of result.data) upsertTake(take);
		applyAll();
		track();
	})();
	try {
		await refreshing;
	} finally {
		refreshing = null;
	}
}

async function openTakes(projectId) {
	stopTracking();
	session.clear();
	syncEngine();
	ui.production.quality = projectQuality(doc.engine);
	setTakes(projectId, []);
	takeStore.loaded = false;
	const result = await getClient().listTakes(projectId);
	if (!alive || projectId !== project.id) return;
	if (!result.ok) {
		takeStore.loaded = true;
		if (gone(result.error)) return projectGone(projectId);
		return toast(t('generation.toast.loadFailed'), 'warning');
	}
	setTakes(projectId, result.data);
	applyAll();
	track();
}

function stopTracking() {
	clearInterval(pollTimer);
	pollTimer = null;
	clearTimeout(refreshTimer);
	refreshTimer = null;
	unsubscribeAll();
}

export function startProduction() {
	alive = true;
	const off = onLoaded((p) => openTakes(p.id));
	return () => {
		off();
		alive = false;
		closeDetails?.();
		stopTracking();
		clearPending();
		estimateController?.abort();
		estimateController = null;
		flyingKey = null;
		session.clear();
	};
}

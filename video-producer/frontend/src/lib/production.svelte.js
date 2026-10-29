import { formatNumber, t } from '../i18n/index.svelte.js';
import { ui, doc, act, toast, asset, newAsset, clipLabel, productionRange, shotsIn, itemsIn, itemsOf, pickedClips, globalPrompt, clipAt, secs, onRestore, openDirector, generates, directorShot, relayout } from './state.svelte.js';
import { project, getClient, flushSave, projectGone, onLoaded } from './project.svelte.js';
import { takeStore, setTakes, upsertTake, patchTake, removeTake, takeById, realTakesOf, flyingTakes } from './takes.svelte.js';
import { PROFILES, aggregate, canUpscale, engineOptions, isInFlight, migrateEngine, optionFor, presetLabel, presetProfiles, progressText, takeAsset } from './generation.js';
import { confirm, openHostModal } from './host.js';
import { finalsToSync, labelOf, marksOf, relabel, releasedLabel } from './labels.js';
import { durationLimit, generationCounts, releaseOverrun, setSpeed } from './shots.js';
import { speedOf } from './cadence.js';
import { effectiveEngine, projectQuality, shotEngineOf } from './engine.js';
import { CONDITION, audioBehavior, shotSound } from './sound.js';
import { fieldTitle, presetFields } from './options.js';
import { prioritized } from './queue.js';
import { laneTitle } from './tracks.js';
import { clearRemoved, isRemoved, pruneRemoved } from './removedtakes.js';
import { LIMITS, SHEET, leastSeconds } from './reception.js';
import { withSendings } from './vreftracks.svelte.js';
import { loadRenditions, stopRenditions } from './renditions.svelte.js';

const ESTIMATE_DELAY = 500;
const POLL_EVERY = 5000;
const INFO_WARNINGS = ['time_unknown', 'vram_unknown', 'audio_condition'];

export const estimateState = $state({ key: null, data: null, loading: false, error: null });
export const queueState = $state({ slots: null, elsewhere: null, positions: {} });
const run = $state({ starting: 0 });
const UNDO_TOAST = 8000;

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
let launching = Promise.resolve();
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

function soundEngine(clip) {
	const engine = effectiveEngine(clip, doc);
	const option = optionFor(engineChoices(), engine);
	const preset = option ? { ...option.info, cloud: option.kind === 'cloud' || option.info.cloud } : null;
	return { preset, profile: engine.profile };
}

export function soundOf(clip) {
	const { preset, profile } = soundEngine(clip);
	return shotSound(doc, clip, preset, profile);
}

export function soundBehaviorOf(clip) {
	const { preset, profile } = soundEngine(clip);
	return audioBehavior(preset, profile);
}

export function presetById(id) {
	return (ui.me?.presets ?? []).find((p) => p.id === id) ?? null;
}

export function backendName(id) {
	return (ui.me?.engines ?? []).find((e) => e.id === id)?.name ?? id ?? '—';
}

const engineName = (presetId) => presetLabel(presetById(presetId)) || engineOptionLabel(presetId ?? null, null);

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
	withSendings(() =>
		act(() => {
			doc.engine.preset = option.preset;
			doc.engine.model = option.model;
			doc.engine.backend = option.backend;
		})
	);
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
	if (doc.engine.quality !== next) act(() => (doc.engine.quality = next));
	ui.production.quality = next;
}

export function openEngineSettings(preset = null) {
	ui.menuOpen = null;
	ui.modal = { type: 'engine', preset: typeof preset === 'string' && preset ? preset : null };
}

export function soundGuides() {
	return [{}, ...doc.clips].some((clip) => soundBehaviorOf(clip) === CONDITION);
}

function optionNames(presetId, names) {
	const fields = presetFields(presetById(presetId));
	return names.map((name) => fieldTitle(fields.find((f) => f.name === name) ?? { name })).join(', ');
}

export function openQueue() {
	if (!generates()) ui.workspace = 'director';
	ui.menuOpen = QUEUE_MENU;
}

export const QUEUE_MENU = 'queue';

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

export const busy = () => run.starting > 0 || flyingTakes().length > 0;
export const upscaleAvailable = (take) => canUpscale(take, ui.me);

function shotName(shotId) {
	const clip = doc.clips.find((c) => c.id === shotId);
	return clip ? clipLabel(clip) : '—';
}

function fieldNames(fields) {
	return (Array.isArray(fields) ? fields : []).map((f) => (typeof f === 'string' ? f : (f?.label ?? f?.name ?? ''))).filter(Boolean);
}

const minutes = (v) => formatNumber(v ?? 0, { maximumFractionDigits: 1 });

export function noteText(note) {
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
	if (code === 'upscaler_outdated') return t('generation.block.upscalerOutdated');
	if (code === 'upscaler_missing') return t('generation.block.upscalerMissing');
	if (code === 'interpolator_missing') return data.interpolator === 'rtx' ? t('generation.block.frameGenerationMissing') : t('generation.block.interpolatorMissing');
	if (code === 'cadence_unknown') return t('generation.block.cadenceUnknown');
	if (code === 'not_slower') return t('generation.block.notSlower');
	if (code === 'vram_stream') return t('generation.warn.vramStream');
	if (code === 'vram_unknown') return t('generation.warn.vramUnknown');
	if (code === 'time_unknown') return t('generation.warn.timeUnknown');
	if (code === 'fl2va_no_frame') return t('generation.warn.noFrame', { shot: shotName(data.shot_id) });
	if (code === 'text_only_preset') return t('generation.warn.textOnly', { shot: shotName(data.shot_id) });
	if (code === 'keep_framing_unavailable') return t('generation.warn.keepFramingUnavailable', { shot: shotName(data.shot_id) });
	if (code === 'keep_framing_last_frame') return t('generation.warn.keepFramingLast', { shot: shotName(data.shot_id) });
	if (code === 'action_undone') return t('generation.warn.actionUndone', { shot: shotName(data.shot_id) });
	if (code === 'duration_clamped') return t('generation.warn.durationClamped', { shot: shotName(data.shot_id), max: secs(Number(data.max) || 0) });
	if (code === 'audio_condition') return t('generation.warn.audioCondition', { shot: shotName(data.shot_id) });
	if (code === 'audio_mux') return t('generation.warn.audioMux', { shot: shotName(data.shot_id) });
	if (code === 'audio_ignored') return t('generation.warn.audioIgnored', { shot: shotName(data.shot_id) });
	if (code === 'audio_track_muted') return t('generation.warn.audioTrackMuted', { shot: shotName(data.shot_id), lane: laneTitle(doc.lanes, doc.lanes.find((l) => l.id === data.lane_id)) || '—' });
	if (code === 'audio_track_empty') return t('generation.warn.audioTrackEmpty', { shot: shotName(data.shot_id), lane: laneTitle(doc.lanes, doc.lanes.find((l) => l.id === data.lane_id)) || '—' });
	if (code === 'audio_track_silent') return t('generation.warn.audioTrackSilent', { shot: shotName(data.shot_id), lane: laneTitle(doc.lanes, doc.lanes.find((l) => l.id === data.lane_id)) || '—' });
	if (code === 'audio_track_trimmed') return t('generation.warn.audioTrackTrimmed', { shot: shotName(data.shot_id), limit: LIMITS.audio, lane: laneTitle(doc.lanes, doc.lanes.find((l) => l.id === data.lane_id)) || '—' });
	if (code === 'video_track_ignored') return t('generation.warn.videoTrackIgnored', { shot: shotName(data.shot_id), track: `vref${data.slot ?? ''}` });
	if (code === 'video_track_trimmed') return t('generation.warn.videoTrackTrimmed', { shot: shotName(data.shot_id), limit: LIMITS.video, track: `vref${data.slot ?? ''}` });
	if (code === 'video_track_short') return t('generation.warn.videoTrackShort', { shot: shotName(data.shot_id), track: `vref${data.slot ?? ''}`, seconds: secs(leastSeconds()) });
	if (code === 'video_track_missing') return t('generation.warn.videoTrackMissing', { shot: shotName(data.shot_id), track: `vref${data.slot ?? ''}` });
	if (code === 'video_tag_ignored') return t('generation.warn.videoTagIgnored', { shot: shotName(data.shot_id), track: `vref${data.slot ?? ''}` });
	if (code === 'vref_step_time') return t('generation.warn.vrefStepTime', { shot: shotName(data.shot_id), scale: formatNumber(Number(data.scale) || 1, { maximumFractionDigits: 1, minimumFractionDigits: 1 }), rows: formatNumber(Number(data.rows) || 0), base: formatNumber(Number(data.base_rows) || 0) });
	if (code === 'vref_rows_high') return t('generation.warn.vrefRowsHigh', { shot: shotName(data.shot_id), rows: formatNumber(Number(data.rows) || 0), limit: formatNumber(Number(data.limit) || 0) });
	if (code === 'video_ffmpeg_missing') return t('generation.block.videoFfmpeg');
	if (code === 'video_source_missing') return t('generation.block.videoSource', { shot: shotName(data.shot_id) });
	if (code === 'video_cut_failed' || code === 'video_store_failed') return t('generation.block.videoCut', { shot: shotName(data.shot_id) });
	if (code === 'audio_only_references') return t('generation.block.audioOnly', { shot: shotName(data.shot_id) });
	if (code === 'audio_ffmpeg_missing') return t('generation.block.audioFfmpeg');
	if (code === 'audio_source_missing') return t('generation.block.audioSource', { shot: shotName(data.shot_id) });
	if (code === 'audio_cut_failed' || code === 'audio_store_failed') return t('generation.block.audioCut', { shot: shotName(data.shot_id) });
	if (code === 'bible_label_missing') return t('generation.warn.bibleLabelMissing', { shot: shotName(data.shot_id), labels: (Array.isArray(data.labels) ? data.labels : []).join(', ') });
	if (code === 'prompt_too_long') return t('generation.warn.promptTooLong', { shot: shotName(data.shot_id), tokens: data.tokens ?? '—', limit: data.limit ?? '—' });
	if (code === 'reference_prompt_changed') return t('generation.warn.referenceChanged', { shot: shotName(data.shot_id) });
	if (code === 'reference_prompt_ignored') return t('generation.warn.referenceIgnored', { shot: shotName(data.shot_id) });
	if (code === 'reference_unlinked') return t('generation.warn.referenceUnlinked', { shot: shotName(data.shot_id), names: (Array.isArray(data.names) ? data.names : []).join(', '), count: Array.isArray(data.names) ? data.names.length : 1 });
	if (code === 'sheet_lora_missing') return t('generation.block.sheetLora', { file: data.file ?? '—' });
	if (code === 'sheet_no_image') return t('generation.block.sheetNoImage', { shot: shotName(data.shot_id) });
	if (code === 'sheet_final_size') return t('generation.block.sheetFinal', { shot: shotName(data.shot_id) });
	if (code === 'sheet_ffmpeg_missing') return t('generation.block.sheetFfmpeg');
	if (code === 'sheet_source_missing') return t('generation.block.sheetSource', { shot: shotName(data.shot_id) });
	if (code === 'sheet_failed') return t('generation.block.sheetFailed', { shot: shotName(data.shot_id) });
	if (code === 'sheet_card_without_image') return t('generation.warn.sheetCardWithoutImage', { shot: shotName(data.shot_id), label: data.label ?? '—' });
	if (code === 'sheet_crowded' && Array.isArray(data.left_out) && data.left_out.length) return t('generation.warn.sheetCrowded', { shot: shotName(data.shot_id), count: SHEET.characters, labels: data.left_out.join(', ') });
	if (code === 'sheet_crowded') return t('generation.warn.sheetSmall', { shot: shotName(data.shot_id), edge: data.edge ?? '—' });
	if (code === 'sheet_props_text_only') return t('generation.warn.sheetProps', { shot: shotName(data.shot_id), labels: (Array.isArray(data.labels) ? data.labels : []).join(', ') });
	if (code === 'sheet_off_bucket') return t('generation.warn.sheetOffBucket', { shot: shotName(data.shot_id), size: String(data.size ?? '—').replace('x', '×') });
	if (code === 'sheet_first_frame') return t('generation.warn.sheetFirstFrame', { shot: shotName(data.shot_id) });
	if (code === 'dialogue_ignored') return t('generation.warn.dialogueIgnored', { shot: shotName(data.shot_id) });
	if (code === 'dialogue_speaker_unknown') return t('generation.warn.dialogueSpeakerUnknown', { shot: shotName(data.shot_id) });
	if (code === 'dialogue_speaker_not_cast') return t('generation.warn.dialogueSpeakerNotCast', { shot: shotName(data.shot_id), labels: (Array.isArray(data.labels) ? data.labels : []).join(', ') });
	if (code === 'dialogue_too_long') return t('generation.warn.dialogueTooLong', { shot: shotName(data.shot_id), words: data.words ?? '—', limit: data.limit ?? '—' });
	if (code === 'dialogue_voice_not_sent') return t('generation.warn.dialogueVoiceNotSent', { shot: shotName(data.shot_id), labels: (Array.isArray(data.labels) ? data.labels : []).join(', ') });
	if (code === 'aspect_cropped') return t('generation.warn.aspectCropped', { engine: engineName(data.preset_id), made: data.made ?? '—', loss: data.loss ?? '—' });
	if (code === 'aspect_bars') return t('generation.warn.aspectBars', { engine: engineName(data.preset_id), made: data.made ?? '—' });
	if (code === 'aspect_unsupported') return t('generation.warn.aspectUnsupported', { engine: engineOptionLabel(data.preset_id ?? null, data.model_id ?? null), aspect: data.aspect ?? doc.aspect, made: data.made ?? '—' });
	if (code === 'size_unmeasured') return t('generation.warn.sizeUnmeasured', { size: String(data.size ?? '—').replace('x', '×'), measured: String(data.measured ?? '—').replace('x', '×') });
	if (code === 'engine_size_invalid') return t('generation.warn.sizeInvalid', { engine: engineName(data.preset_id), size: String(data.size ?? '—').replace('x', '×') });
	if (code === 'engine_option_invalid') return t('generation.warn.optionInvalid', { engine: presetLabel(presetById(data.preset_id)) || engineOptionLabel(data.preset_id, null), fields: optionNames(data.preset_id, Array.isArray(data.fields) ? data.fields : []) });
	return note?.message || code || '';
}

function clipsRange(clips) {
	return [Math.min(...clips.map((c) => c.start)), Math.max(...clips.map((c) => c.start + c.dur))];
}

export function jobClips(range = productionRange()) {
	const picked = pickedClips();
	if (picked.length) return picked;
	const sel = ui.selection?.kind === 'clip' ? doc.clips.find((c) => c.id === ui.selection.id) : null;
	const shot = directorShot();
	if (ui.production.target === 'clip' && shot !== undefined) return shot ? [shot] : [];
	if (ui.production.target === 'clip') return [sel ?? clipAt(ui.playhead) ?? doc.clips[0]].filter(Boolean);
	const inRange = shotsIn(range);
	const toMake = inRange.filter((c) => c.stage !== 'source');
	return toMake.length ? toMake : inRange;
}

function requestBody(clips, quality, counts, option) {
	const body = { shots: clips.map((c) => c.id), quality, variants: counts.variants, preset_id: option.preset, model_id: option.model };
	if (Object.keys(counts.shot_variants).length) body.shot_variants = counts.shot_variants;
	return body;
}

export function estimateRequest() {
	if (!project.id) return null;
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
	const picked = opts.clips?.length ? [] : pickedClips();
	const range = opts.clips?.length ? clipsRange(opts.clips) : picked.length ? clipsRange(picked) : productionRange();
	const items = picked.length ? itemsOf(picked) : itemsIn(range);
	const missing = [];
	const warnings = [];
	const notes = [];
	const gaps = [];
	if (range[1] - range[0] <= 0.05) missing.push(!opts.clips?.length && !picked.length && ui.production.target === 'clip' && directorShot() === null ? t('lib.block.noShot') : t('lib.block.noRange'));
	if (!globalPrompt() && !items.prompts.length) missing.push(t('lib.block.noDirection'));
	const empty = items.prompts.filter((p) => !p.text.trim());
	if (empty.length) missing.push(t('lib.block.emptyPrompts', { count: empty.length }));
	const noEngine = !currentEngine();
	if (noEngine) missing.push(doc.engine?.preset ? t('generation.block.unavailable') : t('generation.block.noEngine'));
	const est = !opts.clips && !noEngine ? estimateState.data : null;
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

export function startGeneration(opts = {}) {
	const { missing, warnings, range } = readiness(opts);
	if (missing.length) return toast(missing[0], 'warning');
	const option = currentEngine();
	const clips = opts.clips ?? jobClips(range);
	if (!option || !clips.length) return;
	const quality = opts.quality ?? ui.production.quality;
	const counts = generationCounts(clips, doc.engine, opts.variants);
	const again = clips.filter((c) => shotActivity(c.id).state === 'running').length;
	run.starting += 1;
	updateProduction();
	const job = launching.then(() => launch(requestBody(clips, quality, counts, option), warnings, again));
	launching = job.catch(() => {});
	return job.finally(() => {
		run.starting -= 1;
		track();
	});
}

async function launch(body, warnings, again) {
	const saved = await flushSave();
	if (!saved || !project.id) return toast(t('generation.toast.saveFirst'), 'error');
	const projectId = project.id;
	const result = await getClient().generate(projectId, body);
	if (projectId !== project.id) return;
	if (!result.ok) return failed(result.error, t('generation.toast.startFailed'));
	for (const take of result.data) upsertTake(take);
	if (result.data.length) queued(result.data, again);
	if (warnings.length) toast(warnings[0], 'warning');
}

function queued(created, again) {
	const ids = created.map((take) => take.id);
	const shots = new Set(created.map((take) => take.shotId)).size;
	const text = again ? t('generation.toast.queuedAgain', { count: shots, again }) : t('generation.toast.queued', { count: shots });
	toast(text, 'info', { label: t('shell.toast.undo'), run: () => cancelQueued(ids) }, UNDO_TOAST);
}

export async function cancelQueued(ids) {
	const flying = ids.map(takeById).filter((take) => take && isInFlight(take));
	if (!flying.length) return;
	const results = await Promise.all(flying.map((take) => getClient().cancelTake(take.id)));
	let failures = 0;
	for (const result of results) {
		if (result.ok) upsertTake(result.data);
		else failures += 1;
	}
	if (failures) await refreshTakes();
	track();
	toast(failures ? t('generation.toast.actionFailed') : t('generation.toast.queueUndone', { count: flying.length - failures }), failures ? 'error' : 'info');
}

export function promoteToFinal(takeId) {
	const take = findTake(takeId);
	if (!take || take.status !== 'done' || take.quality !== 'draft') return toast(t('lib.toast.chooseDraft'), 'warning');
	ui.modal = { type: 'final', take: take.id };
}

export async function makeFinal(takeId, method, target, upscaler = 'auto', rtxSource = 'compressed', conform = false) {
	const take = takeById(takeId);
	if (!take) return false;
	const projectId = project.id;
	const result = await getClient().finalTake(projectId, take.id, method, target, upscaler, rtxSource, conform);
	if (projectId !== project.id) return false;
	if (!result.ok) {
		failed(result.error, t('generation.toast.finalFailed'));
		return false;
	}
	upsertTake(result.data);
	track();
	if (conform) loadRenditions(projectId);
	return true;
}

export function followTakes(list) {
	for (const take of list) upsertTake(take);
	track();
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

function syncFinals() {
	for (const [id, label] of finalsToSync(doc.clips, takeStore.list)) {
		const take = takeById(id);
		if (take) sendLabel(take, label);
	}
}

function engineMax(clip) {
	return optionFor(engineChoices(), effectiveEngine(clip, doc))?.info.limits.maxDuration ?? null;
}

export function shotDurationLimit(clip) {
	return durationLimit(doc, clip, engineMax(clip));
}

export function setClipSpeed(clip, speed) {
	if (!clip || speedOf(clip) === speed) return;
	act(() => {
		const before = clip.dur;
		if (!setSpeed(doc, clip, speed, engineMax(clip))) return;
		fitShot(clip, before);
		relayout();
	});
}

export function releaseTake(released) {
	const take = takeById(released?.take);
	const label = releasedLabel(take);
	if (label) sendLabel(take, label);
}

export function settleRelease(clip, released) {
	if (!clip || !released) return;
	releaseTake(released);
	toast(t('lib.toast.takeReleased', { shot: clipLabel(clip) }));
}

export function fitShot(clip, before) {
	const released = releaseOverrun(doc, clip, before);
	settleRelease(clip, released);
	return released;
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

export function ensureTakeAsset(take) {
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
	clearRemoved(doc, take.id);
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
	if (take.status !== 'done' || !take.url || asset(`gen-${take.id}`) || isRemoved(doc, take.id)) return false;
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
	openDirector('review');
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
	if (agg.state === 'running' || run.starting > 0) {
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
	let changed = pruneRemoved(doc, takeStore.list);
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
	loadRenditions(projectId);
}

function stopTracking() {
	stopRenditions();
	clearInterval(pollTimer);
	pollTimer = null;
	clearTimeout(refreshTimer);
	refreshTimer = null;
	unsubscribeAll();
}

export function startProduction() {
	alive = true;
	const off = onLoaded((p) => openTakes(p.id));
	const offRestore = onRestore(syncFinals);
	return () => {
		off();
		offRestore();
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

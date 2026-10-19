import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, select, toast, undo, clamp, round, secs, shotIdAt, asset, newAsset, clipLabel } from './state.svelte.js';
import { project, getClient, flushSave, projectGone, onLoaded } from './project.svelte.js';
import { pause, seek } from './playback.svelte.js';
import { aspectOf } from './generation.js';
import { ulid } from './ulid.js';
import { placeSeamFrame, seamAsset } from './seam.js';
import { replaceAllowed } from './seam.svelte.js';
import {
	FPS,
	MIN_REFERENCE_SECONDS,
	PRESETS,
	cameraAt,
	cameraKeys,
	distance,
	focalToFov,
	frameCount,
	pose,
	presetAmount,
	presetBase,
	projectSize,
	renderPoses,
	renderSize,
	retime,
	sampleTimes,
	sourceView,
	trajectory
} from './scene3d/camera.js';
import { MAX_SCENE_FILE, SCENE_FILE_ACCEPT, cameraNode, gltfCameras, gltfJson, plyView, sceneFileKind, sceneName } from './scene3d/files.js';

const POLL_EVERY = 2000;
const RUNNING = ['queued', 'running'];
const BATCH_BYTES = 6 * 1024 * 1024;
const BATCH_FRAMES = 12;
const GLB_HEADER = 20;
const SPLAT_FORMAT = ['ply', 'spz', 'splat'];

export const sceneState = $state({
	engine: 'idle',
	status: 'idle',
	loadedId: null,
	loadedFile: null,
	error: null,
	info: {},
	render: null,
	capture: null,
	ends: null,
	uploading: false,
	saving: false
});

let stage = null;
let enginePromise = null;
let loadToken = 0;
let loading = null;
let pollTimer = null;
let renderController = null;
const submitting = new Set();
const gltfMeta = new Map();

export const projectAspect = () => aspectOf(doc.aspect, doc.resolution);
export const captureSize = () => projectSize(doc.resolution, projectAspect());
export const videoSize = () => renderSize(captureSize());
const fovFor = (cam, size) => ({ ...cam, fov: focalToFov(cam.focal, size.width / size.height) });

export function sceneOf(id) {
	return id ? (doc.scenes.find((s) => s.id === id) ?? null) : null;
}

export function planOf(id) {
	return id ? (doc.plans3d.find((p) => p.id === id) ?? null) : null;
}

export function currentPlan() {
	if (ui.selection?.kind === 'plan3d') return planOf(ui.selection.id);
	return doc.plans3d.find((p) => ui.playhead >= p.start && ui.playhead <= p.start + p.dur) ?? null;
}

export function currentScene() {
	return sceneOf(ui.scene.current) ?? sceneOf(currentPlan()?.sceneId) ?? doc.scenes[0] ?? null;
}

export function sceneReady(scene) {
	if (!scene) return false;
	if (scene.kind === 'splat') return scene.status === 'done' && Boolean(scene.fileId);
	return Boolean(scene.fileId);
}

export const sceneBusy = (scene) => scene?.kind === 'splat' && RUNNING.includes(scene.status);
export const scenesBusy = () => doc.scenes.some(sceneBusy);
export const sceneInfo = (scene) => (scene ? (sceneState.info[scene.id] ?? null) : null);
export const sourceOf = (scene) => sourceView(scene, sceneInfo(scene));

export function shotOfPlan(plan) {
	const id = plan?.shotId ?? (plan ? shotIdAt(plan.start) : null);
	return doc.clips.find((c) => c.id === id) ?? null;
}

export function controlOf(plan) {
	if (!plan) return null;
	const own = doc.controls.find((c) => c.planId === plan.id);
	if (own) return own;
	return doc.controls.find((c) => c.source === 'scene3d' && !c.planId && (plan.shotId && c.shotId ? c.shotId === plan.shotId : c.start === plan.start)) ?? null;
}

export function planOfControl(control) {
	if (!control || control.source !== 'scene3d') return null;
	return planOf(control.planId) ?? doc.plans3d.find((p) => controlOf(p) === control) ?? null;
}

export function markStale(plan) {
	const control = controlOf(plan);
	if (control && !control.stale) control.stale = true;
}

export function freshRender(shotId) {
	return doc.controls.find((c) => c.source === 'scene3d' && c.shotId === shotId && c.assetId && !c.stale && asset(c.assetId)) ?? null;
}

export function inPlan(plan) {
	return Boolean(plan && ui.playhead >= plan.start && ui.playhead <= plan.start + plan.dur);
}

export function following(plan = currentPlan()) {
	if (plan?.sceneId && plan.sceneId !== currentScene()?.id) return false;
	return Boolean(inPlan(plan) && plan.keyframes.length && (ui.playing || ui.scene.keyframe === null));
}

export function freeCamera() {
	return { pos: ui.scene.pos, target: ui.scene.target, focal: ui.scene.focal, roll: ui.scene.roll };
}

export function shownCamera() {
	const plan = currentPlan();
	return following(plan) ? cameraAt(plan, ui.playhead - plan.start) : freeCamera();
}

export function setFreeCamera(cam) {
	ui.scene.pos = [...cam.pos];
	ui.scene.target = [...cam.target];
	ui.scene.focal = clamp(cam.focal, 4, 400);
	ui.scene.roll = cam.roll ?? 0;
}

export function takeOver() {
	if (ui.playing) pause();
	const cam = shownCamera();
	setFreeCamera(cam);
	ui.scene.keyframe = 'free';
	return freeCamera();
}

export function seedCamera(scene) {
	if (!scene || ui.scene.seeded === scene.id) return;
	const info = sceneInfo(scene);
	if (scene.kind !== 'glb' && !scene.view && !info) return;
	if (scene.kind === 'glb' && !info) return;
	setFreeCamera(sourceOf(scene));
	ui.scene.seeded = scene.id;
}

export function resetToSource() {
	const scene = currentScene();
	if (!scene) return;
	if (ui.playing) pause();
	setFreeCamera(sourceOf(scene));
	ui.scene.keyframe = 'free';
}

export function showScene(scene) {
	if (!scene) return;
	ui.scene.current = scene.id;
	ui.workspace = 'scene';
}

export function loadEngine() {
	if (!enginePromise) {
		sceneState.engine = 'loading';
		enginePromise = import('./scene3d/engine.js').then(
			(engine) => {
				sceneState.engine = engine.webglAvailable() ? 'ready' : 'unsupported';
				return sceneState.engine === 'ready' ? engine : null;
			},
			() => {
				enginePromise = null;
				sceneState.engine = 'failed';
				return null;
			}
		);
	}
	return enginePromise;
}

export async function ensureStage() {
	if (stage) return stage;
	const engine = await loadEngine();
	if (!engine) return null;
	try {
		stage ??= engine.createStage();
	} catch {
		sceneState.engine = 'unsupported';
		return null;
	}
	return stage;
}

export const getStage = () => stage;

function forgetLoaded() {
	loadToken += 1;
	loading = null;
	stage?.unload();
	Object.assign(sceneState, { loadedId: null, loadedFile: null, status: 'idle', error: null });
}

async function readScene(scene, token) {
	const st = await ensureStage();
	if (!st || token !== loadToken) return null;
	const projectId = project.id;
	const fetched = await getClient().sceneFile(projectId, scene.fileId);
	if (token !== loadToken || projectId !== project.id) return null;
	if (!fetched.ok) throw Object.assign(new Error('fetch'), { code: fetched.error.code === 'project_not_found' ? 'project_not_found' : 'fetch_failed' });
	const bytes = new Uint8Array(fetched.data);
	const kind = scene.kind === 'glb' ? 'glb' : 'splat';
	const loaded = await st.load({ kind, bytes, format: scene.kind === 'splat' ? 'ply' : scene.format });
	if (!loaded || token !== loadToken) return null;
	const info = { bounds: loaded.bounds, count: loaded.count, camera: null };
	if (kind === 'glb') {
		const json = gltfJson(bytes);
		gltfMeta.set(scene.fileId, json);
		const first = gltfCameras(json)[0];
		const node = first ? cameraNode(json, first.name) : -1;
		if (node >= 0) {
			const [sample] = await st.sampleCamera(node, [0]);
			if (sample) info.camera = pose(cameraKeys([sample], projectAspect(), ulid)[0]);
		}
	} else if (!scene.view) {
		const view = plyView(bytes);
		if (view) scene.view = { fov: view.fov, aspect: view.aspect, depth: view.depth };
	}
	if (token !== loadToken) return null;
	sceneState.info[scene.id] = info;
	Object.assign(sceneState, { loadedId: scene.id, loadedFile: scene.fileId, status: 'ready', error: null });
	return st;
}

export function syncStage(scene = currentScene()) {
	if (!scene || !sceneReady(scene)) {
		if (sceneState.loadedId || loading) forgetLoaded();
		return Promise.resolve(null);
	}
	if (sceneState.loadedId === scene.id && sceneState.loadedFile === scene.fileId && sceneState.status === 'ready') return Promise.resolve(stage);
	const key = `${scene.id}:${scene.fileId}`;
	if (loading?.key === key) return loading.promise;
	const token = ++loadToken;
	Object.assign(sceneState, { status: 'loading', error: null });
	const promise = readScene(scene, token).catch((err) => {
		if (token !== loadToken) return null;
		if (err?.code === 'project_not_found') projectGone(project.id);
		Object.assign(sceneState, { status: 'failed', error: err?.code === 'fetch_failed' ? 'fetch_failed' : 'load_failed', loadedId: null, loadedFile: null });
		return null;
	});
	loading = { key, promise };
	promise.finally(() => {
		if (loading?.promise === promise) loading = null;
	});
	return promise;
}

export function retryLoad() {
	Object.assign(sceneState, { status: 'idle', error: null, loadedId: null, loadedFile: null });
	return syncStage();
}

export function newPlan() {
	const scene = currentScene();
	const start = round(ui.playhead, 0.04);
	const p = { id: ulid(), shotId: shotIdAt(start), sceneId: scene?.id ?? null, name: scene?.name ?? t('scene.default.plan'), start, dur: 5, source: 'manual', preset: null, amount: null, camera: null, keyframes: [] };
	act(() => doc.plans3d.push(p));
	select('plan3d', p.id);
	return p;
}

function toManual(plan) {
	if (plan.source === 'manual') return;
	Object.assign(plan, { source: 'manual', preset: null, amount: null, camera: null });
}

export function addKeyframe() {
	const plan = currentPlan() ?? newPlan();
	const at = round(clamp(ui.playhead - plan.start, 0, plan.dur), 0.04);
	const cam = shownCamera();
	const fields = { pos: [...cam.pos], target: [...cam.target], focal: +cam.focal.toFixed(3), roll: +(cam.roll ?? 0).toFixed(3) };
	let id = null;
	act(() => {
		toManual(plan);
		const existing = plan.keyframes.find((k) => Math.abs(k.t - at) < 0.05);
		if (existing) {
			Object.assign(existing, fields);
			id = existing.id;
		} else {
			id = ulid();
			plan.keyframes.push({ id, t: at, ...fields });
		}
		plan.keyframes.sort((a, b) => a.t - b.t);
		markStale(plan);
	});
	ui.scene.keyframe = id;
	toast(t('scene.toast.keyframe', { time: secs(at) }));
}

export function deleteKeyframe(plan, key) {
	act(() => {
		const i = plan.keyframes.indexOf(key);
		if (i >= 0) plan.keyframes.splice(i, 1);
		toManual(plan);
		markStale(plan);
	});
	if (ui.scene.keyframe === key.id) ui.scene.keyframe = null;
}

export function editKey(key, fields) {
	const plan = doc.plans3d.find((p) => p.keyframes.includes(key));
	Object.assign(key, fields);
	if (plan) {
		toManual(plan);
		markStale(plan);
	}
}

export function selectKey(plan, key, move = true) {
	setFreeCamera(key);
	ui.scene.keyframe = key.id;
	if (ui.selection?.id !== plan.id) select('plan3d', plan.id);
	if (move) seek(plan.start + key.t);
}

function planForPreset() {
	const plan = currentPlan() ?? newPlan();
	const scene = sceneOf(plan.sceneId) ?? currentScene();
	if (!scene) {
		toast(t('scene.toast.noScene'), 'warning');
		return null;
	}
	if (scene.kind === 'glb' && !sceneInfo(scene)) {
		toast(t('scene.toast.waitLoad'), 'warning');
		return null;
	}
	return { plan, scene };
}

function presetKeys(plan, scene, preset, amount) {
	return trajectory(preset, amount, presetBase(scene, freeCamera(), sceneInfo(scene)), plan.dur, ulid);
}

export function applyPreset(preset) {
	const target = planForPreset();
	if (!target) return;
	const { plan, scene } = target;
	const amount = presetAmount(preset, ui.scene.amounts[preset]);
	ui.scene.preset = preset;
	act(() => {
		Object.assign(plan, { sceneId: plan.sceneId ?? scene.id, source: 'trajectory', preset, amount, camera: null, keyframes: presetKeys(plan, scene, preset, amount) });
		markStale(plan);
	});
	ui.scene.keyframe = null;
	select('plan3d', plan.id);
	toast(t('scene.toast.preset', { preset: presetLabel(preset), plan: plan.name }));
}

export function setPresetAmount(preset, value) {
	const amount = presetAmount(preset, value);
	ui.scene.amounts[preset] = amount;
	const plan = currentPlan();
	if (!plan || plan.source !== 'trajectory' || plan.preset !== preset) return;
	const scene = sceneOf(plan.sceneId);
	if (!scene || (scene.kind === 'glb' && !sceneInfo(scene))) return;
	plan.amount = amount;
	plan.keyframes = presetKeys(plan, scene, preset, amount);
	markStale(plan);
}

export function presetLabel(preset) {
	if (preset === 'orbit') return t('scene.preset.orbit');
	if (preset === 'dolly') return t('scene.preset.dolly');
	return t('scene.preset.crane');
}

export function setPlanDur(plan, dur) {
	const next = Math.max(0.5, round(dur, 0.04));
	if (plan.source === 'trajectory') plan.keyframes = retime(plan.keyframes, plan.dur, next);
	plan.dur = next;
	markStale(plan);
}

export function setPlanScene(plan, sceneId) {
	act(() => {
		plan.sceneId = sceneId || null;
		markStale(plan);
	});
	if (sceneId) ui.scene.current = sceneId;
}

export async function useBlenderCamera(plan, name) {
	const scene = sceneOf(plan?.sceneId);
	if (!scene || scene.kind !== 'glb') return toast(t('scene.toast.noBlender'), 'warning');
	ui.scene.current = scene.id;
	const st = await syncStage(scene);
	const json = gltfMeta.get(scene.fileId);
	const camera = scene.cameras.find((c) => c.name === name);
	const node = json ? cameraNode(json, name) : -1;
	if (!st || !camera || node < 0) return toast(t('scene.toast.loadFailed'), 'error');
	const dur = camera.animated && camera.duration ? Math.max(0.5, round(camera.duration, 0.04)) : plan.dur;
	const samples = await st.sampleCamera(node, sampleTimes(camera.animated ? dur : 0));
	const target = planOf(plan.id);
	if (!target || !samples.length) return;
	act(() => {
		Object.assign(target, { source: 'blender', preset: null, amount: null, camera: name, dur, keyframes: cameraKeys(samples, projectAspect(), ulid) });
		markStale(target);
	});
	ui.scene.keyframe = null;
	toast(t('scene.toast.blender', { camera: name, count: target.keyframes.length }));
}

function applyJob(job) {
	const scene = doc.scenes.find((s) => s.kind === 'splat' && (s.id === job.sceneId || (job.id && s.jobId === job.id)));
	if (!scene) return;
	const before = scene.status;
	const done = job.status === 'done';
	const status = done && !job.fileId ? 'failed' : job.status === 'cancelled' ? 'failed' : job.status;
	const patch = { status, progress: done ? 100 : job.progress, jobId: job.id ?? scene.jobId };
	if (status === 'done') Object.assign(patch, { fileId: job.fileId, count: job.count, view: job.view, error: null });
	if (status === 'failed') patch.error = job.status === 'cancelled' ? 'cancelled' : done ? 'no_file' : job.error || 'failed';
	for (const [key, value] of Object.entries(patch)) if (JSON.stringify(scene[key]) !== JSON.stringify(value)) scene[key] = value;
	if (before === status || !RUNNING.includes(before)) return;
	if (status === 'done') toast(t('scene.toast.ready', { name: scene.name }), 'success');
	else if (status === 'failed' && patch.error !== 'cancelled') toast(t('scene.toast.failed', { name: scene.name }), 'error');
}

function lostJobs(jobs) {
	for (const scene of doc.scenes) {
		if (!sceneBusy(scene) || submitting.has(scene.id)) continue;
		if (jobs.some((j) => (scene.jobId && j.id === scene.jobId) || j.sceneId === scene.id)) continue;
		Object.assign(scene, { status: 'failed', error: 'lost' });
	}
}

async function tick() {
	pollTimer = null;
	const projectId = project.id;
	if (!projectId || !scenesBusy()) return;
	const result = await getClient().sceneJobs(projectId);
	if (projectId !== project.id) return;
	if (result.ok) {
		for (const job of result.data) applyJob(job);
		lostJobs(result.data);
	} else if (result.error.code === 'project_not_found') return projectGone(projectId);
	if (scenesBusy()) pollTimer = setTimeout(tick, POLL_EVERY);
}

export function pollScenes() {
	if (pollTimer || !scenesBusy()) return;
	pollTimer = setTimeout(tick, POLL_EVERY);
}

export function sceneErrorText(code) {
	if (code === 'cancelled') return t('scene.error.cancelled');
	if (code === 'lost') return t('scene.error.lost');
	if (code === 'quota_exceeded') return t('scene.error.quota');
	if (code === 'no_preset' || code === 'preset_unavailable') return t('scene.error.preset');
	if (code === 'asset_not_found' || code === 'source_unavailable') return t('scene.error.source');
	if (code === 'extract_failed') return t('scene.error.extract');
	if (code === 'save') return t('scene.error.save');
	return t('scene.error.generic');
}

async function submit(sceneId) {
	submitting.add(sceneId);
	try {
		const saved = await flushSave();
		const scene = sceneOf(sceneId);
		if (!scene) return;
		if (!saved || !project.id) {
			Object.assign(scene, { status: 'failed', error: 'save' });
			return toast(t('scene.toast.saveFirst'), 'error');
		}
		const projectId = project.id;
		const result = await getClient().sceneFromImage(projectId, { sceneId, assetId: scene.sourceAssetId, time: scene.sourceTime, name: scene.name });
		if (projectId !== project.id) return;
		const target = sceneOf(sceneId);
		if (!target) return;
		if (!result.ok) {
			if (result.error.code === 'project_not_found') return projectGone(projectId);
			Object.assign(target, { status: 'failed', error: result.error.code || 'failed' });
			return toast(sceneErrorText(result.error.code), 'error');
		}
		applyJob({ ...result.data, sceneId });
		toast(t('scene.toast.started', { name: target.name }));
	} finally {
		submitting.delete(sceneId);
		pollScenes();
	}
}

export function createSceneFromImage({ assetId, time = null, name = '' }) {
	const source = asset(assetId);
	if (!source || (source.kind !== 'image' && source.kind !== 'video')) return toast(t('scene.toast.noSource'), 'warning');
	const scene = {
		kind: 'splat',
		id: ulid(),
		name: name.trim() || source.name || t('scene.default.name'),
		sourceAssetId: assetId,
		sourceTime: source.kind === 'video' ? Math.max(0, Math.round((time ?? 0) * 1000) / 1000) : null,
		status: 'queued',
		progress: 0,
		jobId: null,
		fileId: null,
		count: null,
		view: null,
		error: null
	};
	act(() => doc.scenes.push(scene));
	showScene(scene);
	return submit(scene.id);
}

export function retryScene(scene) {
	if (scene?.kind !== 'splat' || sceneBusy(scene)) return;
	act(() => Object.assign(scene, { status: 'queued', progress: 0, error: null, jobId: null }));
	return submit(scene.id);
}

export async function cancelScene(scene) {
	if (!sceneBusy(scene)) return;
	if (!scene.jobId) {
		Object.assign(scene, { status: 'failed', error: 'cancelled' });
		return;
	}
	const projectId = project.id;
	const result = await getClient().cancelSceneJob(projectId, scene.jobId);
	if (projectId !== project.id) return;
	if (result.ok) applyJob({ ...result.data, sceneId: scene.id });
	else if (result.error.status === 404) Object.assign(scene, { status: 'failed', error: 'cancelled' });
	else toast(t('scene.toast.cancelFailed'), 'error');
}

export async function removeScene(scene) {
	if (!scene) return;
	if (sceneBusy(scene)) await cancelScene(scene);
	act(() => {
		const i = doc.scenes.indexOf(scene);
		if (i >= 0) doc.scenes.splice(i, 1);
		for (const plan of doc.plans3d) {
			if (plan.sceneId !== scene.id) continue;
			plan.sceneId = null;
			markStale(plan);
		}
	});
	if (ui.scene.current === scene.id) ui.scene.current = null;
	if (sceneState.loadedId === scene.id) forgetLoaded();
	toast(t('scene.toast.removed', { name: scene.name }), 'info', { label: t('shell.toast.undo'), run: undo });
}

async function gltfHead(file) {
	const head = new Uint8Array(await file.slice(0, GLB_HEADER).arrayBuffer());
	const view = new DataView(head.buffer);
	if (head.length === GLB_HEADER && view.getUint32(0, true) === 0x46546c67) return new Uint8Array(await file.slice(0, GLB_HEADER + view.getUint32(12, true)).arrayBuffer());
	return new Uint8Array(await file.arrayBuffer());
}

export function chooseSceneFile() {
	if (typeof document === 'undefined') return;
	const input = document.createElement('input');
	input.type = 'file';
	input.accept = SCENE_FILE_ACCEPT;
	input.onchange = () => {
		const file = input.files?.[0];
		if (file) uploadSceneFile(file);
	};
	input.click();
}

export async function uploadSceneFile(file) {
	const kind = sceneFileKind(file?.name);
	if (!kind) return toast(t('scene.toast.badFile'), 'warning');
	if (file.size > MAX_SCENE_FILE) return toast(t('scene.toast.tooLarge'), 'warning');
	if (sceneState.uploading) return;
	sceneState.uploading = true;
	try {
		const cameras = kind.kind === 'glb' ? gltfCameras(await gltfHead(file)) : [];
		const headerView = kind.format === 'ply' ? plyView(await file.slice(0, 65536).arrayBuffer()) : null;
		const saved = await flushSave();
		if (!saved || !project.id) return toast(t('scene.toast.saveFirst'), 'error');
		const projectId = project.id;
		const result = await getClient().uploadSceneFile(projectId, file, kind.kind);
		if (projectId !== project.id) return;
		if (!result.ok) {
			if (result.error.code === 'project_not_found') return projectGone(projectId);
			return toast(result.error.status === 413 ? t('scene.toast.tooLarge') : t('scene.toast.uploadFailed'), 'error');
		}
		const stored = result.data;
		const name = sceneName(file.name);
		const scene =
			kind.kind === 'glb'
				? { kind: 'glb', id: ulid(), name, fileId: stored.id, cameras }
				: { kind: 'splatfile', id: ulid(), name, fileId: stored.id, format: SPLAT_FORMAT.includes(stored.format) ? stored.format : kind.format, view: stored.view ?? headerView };
		act(() => doc.scenes.push(scene));
		showScene(scene);
		toast(t('scene.toast.imported', { name }), 'success');
	} finally {
		sceneState.uploading = false;
	}
}


function captureName(scene, clip) {
	return t('scene.capture.assetName', { scene: scene?.name ?? t('scene.default.name'), shot: clipLabel(clip) });
}

export async function prepareCapture() {
	const scene = currentScene();
	if (!sceneReady(scene)) {
		sceneState.capture = null;
		return toast(t('scene.toast.notReady'), 'warning');
	}
	const size = captureSize();
	const plan = currentPlan();
	const cam = shownCamera();
	const time = following(plan) ? ui.playhead - plan.start : 0;
	sceneState.capture = { busy: true, sceneId: scene.id, url: null, coverage: null, ...size };
	try {
		const st = await syncStage(scene);
		if (!st) throw new Error('load');
		const shot = await st.capture(fovFor(cam, size), size.width, size.height, time);
		if (sceneState.capture?.sceneId === scene.id) sceneState.capture = { busy: false, sceneId: scene.id, url: shot.url, coverage: shot.coverage, ...size };
	} catch {
		sceneState.capture = null;
		toast(t('scene.toast.captureFailed'), 'error');
	}
}

export function openCapture() {
	if (!sceneReady(currentScene())) return toast(t('scene.toast.notReady'), 'warning');
	ui.modal = { type: 'capture' };
	prepareCapture();
}

async function storeCapture(projectId, url, name) {
	const result = await getClient().capture(projectId, url, name);
	if (!result.ok) throw Object.assign(new Error('capture'), { code: result.error.code });
	return result.data;
}

export async function saveCapture(clipId, usage) {
	const shot = sceneState.capture;
	const clip = doc.clips.find((c) => c.id === clipId);
	if (!shot?.url || !clip || sceneState.saving) return false;
	const scene = sceneOf(shot.sceneId);
	if (usage !== 'reference' && !(await replaceAllowed(clip, usage))) return false;
	const projectId = project.id;
	const name = captureName(scene, clip);
	sceneState.saving = true;
	try {
		const media = await storeCapture(projectId, shot.url, name);
		if (projectId !== project.id) return false;
		const target = doc.clips.find((c) => c.id === clipId);
		if (!target) return false;
		act(() => {
			const image = seamAsset(media, name);
			if (usage === 'reference') {
				doc.assets.push(image);
				doc.references.push({ id: ulid(), name, space: 'decors3d', type: 'Capture 3D', assetId: image.id, role: '', scope: { type: 'shot', shotId: target.id } });
			} else placeSeamFrame(doc, target, usage, image, ulid, scene?.id ?? null);
		});
		const done = usage === 'reference' ? t('scene.toast.capturedRef', { shot: clipLabel(target) }) : usage === 'first' ? t('scene.toast.capturedFirst', { shot: clipLabel(target) }) : t('scene.toast.capturedLast', { shot: clipLabel(target) });
		toast(done, 'success', { label: t('shell.toast.undo'), run: undo });
		return true;
	} catch (err) {
		if (err?.code === 'project_not_found') projectGone(projectId);
		else toast(t('scene.toast.captureFailed'), 'error');
		return false;
	} finally {
		sceneState.saving = false;
	}
}

function attachRender(planId, media, size, frames) {
	const plan = planOf(planId);
	if (!plan) return;
	act(() => {
		const video = newAsset({ kind: 'video', name: media.filename || t('scene.render.name', { name: plan.name }), src: media.url, origin: { kind: 'library', itemId: media.itemId }, srcDur: frames / FPS, width: size.width, height: size.height, fps: FPS, res: `${size.width}×${size.height}` });
		doc.assets.push(video);
		const fields = { shotId: plan.shotId ?? shotIdAt(plan.start), start: plan.start, dur: plan.dur, source: 'scene3d', stale: false, planId: plan.id, assetId: video.id };
		const existing = controlOf(plan);
		if (existing) Object.assign(existing, fields);
		else doc.controls.push({ id: ulid(), name: t('lib.default.guide3d', { name: plan.name }), guidance: 65, ...fields });
	});
}

function renderCheck(plan) {
	const scene = sceneOf(plan?.sceneId);
	if (!plan || !scene) return toast(t('scene.toast.noScene'), 'warning');
	if (!sceneReady(scene)) return toast(t('scene.toast.notReady'), 'warning');
	if (!plan.keyframes.length) return toast(t('scene.toast.noKeys'), 'warning');
	ui.scene.current = scene.id;
	return scene;
}

export async function renderPlan(plan) {
	if (sceneState.render || sceneState.ends) return;
	const scene = renderCheck(plan);
	if (!scene?.id) return;
	if (plan.dur < MIN_REFERENCE_SECONDS) toast(t('scene.toast.short', { min: secs(MIN_REFERENCE_SECONDS) }), 'warning');
	const size = videoSize();
	const total = frameCount(plan.dur);
	const poses = renderPoses(plan).map((p) => fovFor(p, size));
	const projectId = project.id;
	const client = getClient();
	const controller = new AbortController();
	renderController = controller;
	sceneState.render = { planId: plan.id, done: 0, total, phase: 'loading' };
	let renderId = null;
	try {
		const st = await syncStage(scene);
		if (!st) throw Object.assign(new Error('load'), { code: 'load_failed' });
		sceneState.render.phase = 'rendering';
		const created = await client.createRender(projectId, { width: size.width, height: size.height, fps: FPS, frames: total, name: t('scene.render.name', { name: plan.name }) });
		if (!created.ok) throw Object.assign(new Error('create'), { code: created.error.code });
		renderId = created.data.id;
		let batch = [];
		let bytes = 0;
		let start = 0;
		const flush = async () => {
			if (!batch.length) return;
			const sent = await client.renderFrames(projectId, renderId, start, batch);
			if (!sent.ok) throw Object.assign(new Error('frames'), { code: sent.error.code });
			start += batch.length;
			batch = [];
			bytes = 0;
		};
		await st.render(poses, size.width, size.height, {
			fps: FPS,
			signal: controller.signal,
			onFrame: async (i, url) => {
				batch.push(url);
				bytes += url.length;
				if (sceneState.render) sceneState.render.done = i + 1;
				if (bytes >= BATCH_BYTES || batch.length >= BATCH_FRAMES) await flush();
			}
		});
		await flush();
		if (controller.signal.aborted) throw new DOMException('aborted', 'AbortError');
		sceneState.render.phase = 'encoding';
		const finished = await client.finishRender(projectId, renderId);
		if (!finished.ok) throw Object.assign(new Error('finish'), { code: finished.error.code });
		if (projectId !== project.id) return;
		renderId = null;
		attachRender(plan.id, finished.data, size, total);
		toast(t('scene.toast.rendered', { name: plan.name }), 'success', { label: t('shell.toast.undo'), run: undo });
	} catch (err) {
		if (renderId && projectId === project.id) client.deleteRender(projectId, renderId);
		if (err?.name === 'AbortError' || controller.signal.aborted) toast(t('scene.toast.renderCancelled'));
		else if (err?.code === 'project_not_found') projectGone(projectId);
		else toast(t('scene.toast.renderFailed'), 'error');
	} finally {
		if (renderController === controller) renderController = null;
		sceneState.render = null;
	}
}

export function cancelRender() {
	renderController?.abort();
}

export async function useStartEnd(plan) {
	if (sceneState.render || sceneState.ends) return;
	const scene = renderCheck(plan);
	if (!scene?.id) return;
	const clip = shotOfPlan(plan);
	if (!clip) return toast(t('scene.toast.noShot'), 'warning');
	if (!(await replaceAllowed(clip, ['first', 'last']))) return;
	const projectId = project.id;
	const size = captureSize();
	sceneState.ends = plan.id;
	try {
		const st = await syncStage(scene);
		if (!st) throw new Error('load');
		const placed = [];
		for (const [kind, time] of [
			['first', 0],
			['last', plan.dur]
		]) {
			const shot = await st.capture(fovFor(cameraAt(plan, time), size), size.width, size.height, time);
			const name = kind === 'first' ? t('scene.capture.firstName', { shot: clipLabel(clip) }) : t('scene.capture.lastName', { shot: clipLabel(clip) });
			placed.push({ kind, name, media: await storeCapture(projectId, shot.url, name) });
		}
		if (projectId !== project.id) return;
		const target = doc.clips.find((c) => c.id === clip.id);
		if (!target) return;
		act(() => {
			for (const { kind, name, media } of placed) placeSeamFrame(doc, target, kind, seamAsset(media, name), ulid, scene.id);
		});
		toast(t('scene.toast.ends', { shot: clipLabel(target) }), 'success', { label: t('shell.toast.undo'), run: undo });
	} catch (err) {
		if (err?.code === 'project_not_found') projectGone(projectId);
		else toast(t('scene.toast.captureFailed'), 'error');
	} finally {
		sceneState.ends = null;
	}
}

export function applyRenders(clips) {
	const pairs = clips.map((c) => [c, freshRender(c.id)]).filter(([, control]) => control);
	if (!pairs.length) return toast(t('lib.block.noRender3d'), 'warning');
	act(() => {
		for (const [clip, control] of pairs) Object.assign(clip, { assetId: control.assetId, srcIn: 0, take: null, stage: 'draft' });
	});
	toast(t('scene.toast.rendersPlaced', { count: pairs.length }), 'success', { label: t('shell.toast.undo'), run: undo });
}

export function cameraDistance(cam = shownCamera()) {
	return distance(cam.pos, cam.target);
}

export function presetSpec(preset) {
	return PRESETS[preset];
}

function resetScenes() {
	clearTimeout(pollTimer);
	pollTimer = null;
	renderController?.abort();
	gltfMeta.clear();
	forgetLoaded();
	Object.assign(sceneState, { info: {}, capture: null, ends: null });
	pollScenes();
}

onLoaded(resetScenes);

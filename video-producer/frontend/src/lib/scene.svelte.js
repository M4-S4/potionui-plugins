import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, toast, undo, clamp, asset, clipAt, clipLabel, onRestore } from './state.svelte.js';
import { project, getClient, flushSave, projectGone, onLoaded } from './project.svelte.js';
import { pause } from './playback.svelte.js';
import { aspectOf } from './generation.js';
import { ulid } from './ulid.js';
import { placeSeamFrame, seamAsset } from './seam.js';
import { replaceAllowed } from './seam.svelte.js';
import { FOCAL_RANGE, atSource, boundCamera, fitsFrame, focalToFov, holesMatter, lowestFocal, projectSize, sourceView } from './scene3d/camera.js';
import { CAPTURE_CELL, LIVE_CELL, LIVE_STRIDE } from './scene3d/streaks.js';
import { plyView } from './scene3d/files.js';
import { RUNNING, createPoller, jobScene, lostScene, orphanJobs, reusableScene } from './scene3d/jobs.js';

const POLL_EVERY = 2000;
const STREAK_DELAY = 250;

export const sceneState = $state({
	engine: 'idle',
	status: 'idle',
	loadedId: null,
	loadedFile: null,
	error: null,
	info: {},
	capture: null,
	progress: {},
	saving: false,
	streaks: null
});

let stage = $state.raw(null);
let enginePromise = null;
let loadToken = 0;
let loading = null;
let deferred = false;
let closed = false;
let streakTimer = null;
const submitting = new Set();
const liveJobs = new Map();
const poller = createPoller({ every: POLL_EVERY, run: tick, active: () => !closed && scenesBusy() });

export const projectAspect = () => aspectOf(doc.aspect, doc.resolution);
export const captureSize = () => projectSize(doc.resolution, projectAspect());
const fovFor = (cam, size) => ({ ...cam, fov: focalToFov(cam.focal, size.width / size.height) });
const viewable = (scene) => scene?.kind === 'splat' || scene?.kind === 'splatfile';

export const shownScenes = () => (doc.scenes ?? []).filter(viewable);

export function sceneOf(id) {
	return id ? (shownScenes().find((s) => s.id === id) ?? null) : null;
}

export const currentScene = () => sceneOf(ui.scene.current);
export const sceneFor = (assetId) => reusableScene(doc.scenes ?? [], assetId);

export function sceneReady(scene) {
	if (!viewable(scene)) return false;
	if (scene.kind === 'splat') return scene.status === 'done' && Boolean(scene.fileId);
	return Boolean(scene.fileId);
}

export const sceneBusy = (scene) => scene?.kind === 'splat' && RUNNING.includes(scene.status);
export const scenesBusy = () => (doc.scenes ?? []).some(sceneBusy);
export const sceneProgress = (scene) => (scene ? (sceneState.progress[scene.id] ?? scene.progress ?? 0) : 0);
export const sceneLocked = () => Boolean(sceneState.capture?.busy);
const heldScene = () => (sceneState.capture?.busy ? sceneState.capture.sceneId : null);
export const sceneInfo = (scene) => (scene ? (sceneState.info[scene.id] ?? null) : null);
export const sourceOf = (scene) => sourceView(scene, sceneInfo(scene));

export function freeCamera() {
	return { pos: ui.scene.pos, target: ui.scene.target, focal: ui.scene.focal, roll: ui.scene.roll };
}

export function setFreeCamera(cam) {
	ui.scene.pos = [...cam.pos];
	ui.scene.target = [...cam.target];
	ui.scene.focal = clamp(cam.focal, 4, 400);
	ui.scene.roll = cam.roll ?? 0;
}

export function seedCamera(scene) {
	if (!scene || ui.scene.seeded === scene.id) return;
	if (!scene.view && !sceneInfo(scene)) return;
	setFreeCamera(sourceOf(scene));
	ui.scene.seeded = scene.id;
}

function streaksAt(scene, cam, size, cell, stride) {
	if (!stage || !holesMatter(scene) || sceneState.loadedId !== scene?.id) return null;
	try {
		return stage.streaks(fovFor(cam, size), sourceOf(scene), size.width, size.height, cell, stride);
	} catch {
		return null;
	}
}

export function measureStreaks(scene) {
	clearTimeout(streakTimer);
	if (!scene || !holesMatter(scene)) return (sceneState.streaks = null);
	streakTimer = setTimeout(() => {
		streakTimer = null;
		if (closed || sceneLocked() || stage?.busy) return;
		sceneState.streaks = streaksAt(scene, freeCamera(), captureSize(), LIVE_CELL, LIVE_STRIDE);
	}, STREAK_DELAY);
}

export function originalAt(scene, cam = freeCamera()) {
	if (scene?.kind !== 'splat' || scene.sourceTime != null) return null;
	const picture = asset(scene.sourceAssetId);
	if (picture?.kind !== 'image' || !picture.src || !fitsFrame(picture, projectAspect())) return null;
	return atSource(cam, sourceOf(scene)) ? picture : null;
}

export function moveCamera(scene, next) {
	if (!scene) return;
	const source = sourceOf(scene);
	const cam = { ...next, focal: clamp(next.focal, lowestFocal(scene, source), FOCAL_RANGE[1]) };
	setFreeCamera(holesMatter(scene) ? boundCamera(cam, freeCamera(), source) : cam);
}

export function resetToSource(scene) {
	if (!scene) return;
	if (ui.playing) pause();
	setFreeCamera(sourceOf(scene));
}

function refuseWhileLocked() {
	if (!sceneLocked()) return false;
	toast(t('scene.toast.busy'), 'warning');
	return true;
}

export function pickScene(id) {
	if (ui.scene.current === id || refuseWhileLocked()) return;
	ui.scene.current = id;
}

export function openReframe() {
	const shot = (ui.selection?.kind === 'clip' ? doc.clips.find((c) => c.id === ui.selection.id) : null) ?? clipAt(ui.playhead);
	if (!shot) return toast(t('lib.toast.selectShot'), 'warning');
	ui.modal = { type: 'reframe', id: shot.id };
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
	if (stage || closed || sceneState.engine === 'lost') return stage;
	const engine = await loadEngine();
	if (!engine || closed || sceneState.engine === 'lost') return null;
	if (stage) return stage;
	try {
		stage = engine.createStage({ onLost: contextLost });
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

function dropStage() {
	const old = stage;
	stage = null;
	loadToken += 1;
	loading = null;
	try {
		old?.dispose();
	} catch {}
}

function contextLost() {
	dropStage();
	Object.assign(sceneState, { engine: 'lost', loadedId: null, loadedFile: null, status: 'idle', error: null });
}

export async function retryEngine() {
	if (sceneState.engine !== 'lost') return;
	sceneState.engine = 'ready';
	if (await ensureStage()) syncStage();
}

function release() {
	if (!deferred || sceneLocked() || stage?.busy) return;
	deferred = false;
	syncStage();
}

async function readScene(scene, token) {
	const st = await ensureStage();
	if (!st || token !== loadToken) return null;
	const projectId = project.id;
	const fetched = await getClient().sceneFile(projectId, scene.fileId);
	if (token !== loadToken || projectId !== project.id) return null;
	if (!fetched.ok) throw Object.assign(new Error('fetch'), { code: fetched.error.code === 'project_not_found' ? 'project_not_found' : 'fetch_failed' });
	const bytes = new Uint8Array(fetched.data);
	const loaded = await st.load({ bytes, format: scene.kind === 'splat' ? 'ply' : scene.format });
	if (!loaded || token !== loadToken) return null;
	if (!scene.view) {
		const view = plyView(bytes);
		if (view) scene.view = { fov: view.fov, aspect: view.aspect, depth: view.depth };
	}
	sceneState.info[scene.id] = { bounds: loaded.bounds, count: loaded.count };
	Object.assign(sceneState, { loadedId: scene.id, loadedFile: scene.fileId, status: 'ready', error: null });
	return st;
}

export function syncStage(target = currentScene()) {
	if (closed) return Promise.resolve(null);
	const scene = target && sceneReady(target) ? target : null;
	if (scene && stage && sceneState.loadedId === scene.id && sceneState.loadedFile === scene.fileId && sceneState.status === 'ready') return Promise.resolve(stage);
	if (stage?.busy || (sceneLocked() && scene?.id !== heldScene())) {
		deferred = true;
		return Promise.resolve(null);
	}
	if (!scene) {
		if (sceneState.loadedId || loading) forgetLoaded();
		return Promise.resolve(null);
	}
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

function applyJob(job, own = false) {
	const scene = jobScene(doc.scenes ?? [], job, own ? null : submitting);
	if (!scene) return;
	const before = scene.status;
	const done = job.status === 'done';
	const status = done && !job.fileId ? 'failed' : job.status === 'cancelled' ? 'failed' : job.status;
	const progress = done ? 100 : job.progress;
	const patch = { status, jobId: job.id ?? scene.jobId };
	if (status !== before) patch.progress = progress;
	if (status === 'done') Object.assign(patch, { fileId: job.fileId, count: job.count, view: job.view, error: null });
	if (status === 'failed') patch.error = job.status === 'cancelled' ? 'cancelled' : done ? 'no_file' : job.error || 'failed';
	for (const [key, value] of Object.entries(patch)) if (JSON.stringify(scene[key]) !== JSON.stringify(value)) scene[key] = value;
	if (RUNNING.includes(status)) {
		sceneState.progress[scene.id] = progress;
		if (patch.jobId) liveJobs.set(scene.id, patch.jobId);
	} else {
		delete sceneState.progress[scene.id];
		liveJobs.delete(scene.id);
	}
	if (before === status || !RUNNING.includes(before)) return;
	if (status === 'done') toast(t('scene.toast.ready', { name: scene.name }), 'success');
	else if (status === 'failed' && patch.error !== 'cancelled') toast(t('scene.toast.failed', { name: scene.name }), 'error');
}

function lostJobs(jobs) {
	for (const scene of doc.scenes ?? []) {
		if (!sceneBusy(scene) || submitting.has(scene.id) || !lostScene(scene, jobs)) continue;
		Object.assign(scene, { status: 'failed', error: 'lost' });
		delete sceneState.progress[scene.id];
		liveJobs.delete(scene.id);
	}
}

async function tick() {
	const projectId = project.id;
	if (!projectId || !scenesBusy()) return;
	const result = await getClient().sceneJobs(projectId);
	if (projectId !== project.id || closed) return;
	if (result.ok) {
		for (const job of result.data) applyJob(job);
		lostJobs(result.data);
	} else if (result.error.code === 'project_not_found') {
		projectGone(projectId);
		return false;
	}
}

export function pollScenes() {
	poller.arm();
}

function cancelOrphans() {
	const projectId = project.id;
	const client = getClient();
	if (!projectId || !client) return;
	for (const [sceneId, jobId] of orphanJobs(liveJobs, doc.scenes ?? [])) {
		liveJobs.delete(sceneId);
		delete sceneState.progress[sceneId];
		client.cancelSceneJob(projectId, jobId);
	}
}

export function sceneErrorText(code) {
	if (code === 'cancelled') return t('scene.error.cancelled');
	if (code === 'lost') return t('scene.error.lost');
	if (code === 'quota_exceeded') return t('scene.error.quota');
	if (code === 'no_preset' || code === 'preset_unavailable') return t('scene.error.preset');
	if (code === 'asset_not_found' || code === 'source_unavailable') return t('scene.error.source');
	if (code === 'extract_failed') return t('scene.error.extract');
	if (code === 'save') return t('scene.error.save');
	if (code === 'storage_full') return t('scene.error.storage');
	if (code === 'scene_jobs_busy') return t('scene.error.busy');
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
		const client = getClient();
		const result = await client.sceneFromImage(projectId, { sceneId, assetId: scene.sourceAssetId, time: scene.sourceTime, name: scene.name });
		if (projectId !== project.id) return;
		const target = sceneOf(sceneId);
		if (!target || !sceneBusy(target)) {
			if (result.ok && result.data?.id) client.cancelSceneJob(projectId, result.data.id);
			return;
		}
		if (!result.ok) {
			if (result.error.code === 'project_not_found') return projectGone(projectId);
			Object.assign(target, { status: 'failed', error: result.error.code || 'failed' });
			return toast(sceneErrorText(result.error.code), 'error');
		}
		applyJob({ ...result.data, sceneId }, true);
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
	act(() => {
		if (!Array.isArray(doc.scenes)) doc.scenes = [];
		doc.scenes.push(scene);
	});
	submit(scene.id);
	return scene;
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
	if (result.ok) applyJob({ ...result.data, sceneId: scene.id }, true);
	else if (result.error.status === 404) Object.assign(scene, { status: 'failed', error: 'cancelled' });
	else toast(t('scene.toast.cancelFailed'), 'error');
}

function captureName(scene, clip) {
	return t('scene.capture.assetName', { scene: scene?.name ?? t('scene.default.name'), shot: clipLabel(clip) });
}

export async function takeCapture(scene) {
	if (!sceneReady(scene)) {
		toast(t('scene.toast.notReady'), 'warning');
		return null;
	}
	if (refuseWhileLocked()) return null;
	const size = captureSize();
	const cam = freeCamera();
	const original = originalAt(scene, cam);
	if (original) return { sceneId: scene.id, url: original.src, coverage: 1, streaks: 0, width: original.width, height: original.height, assetId: original.id };
	sceneState.capture = { busy: true, sceneId: scene.id };
	try {
		const st = await syncStage(scene);
		if (!st) throw new Error('load');
		const shot = await st.capture(fovFor(cam, size), size.width, size.height);
		return { sceneId: scene.id, url: shot.url, coverage: shot.coverage, streaks: streaksAt(scene, cam, size, CAPTURE_CELL, 1), ...size };
	} catch {
		toast(t('scene.toast.captureFailed'), 'error');
		return null;
	} finally {
		sceneState.capture = null;
		release();
	}
}

async function storeCapture(projectId, url, name) {
	const result = await getClient().capture(projectId, url, name);
	if (!result.ok) throw Object.assign(new Error('capture'), { code: result.error.code });
	return result.data;
}

function placedText(clip, usages) {
	if (usages.length > 1) return t('scene.toast.capturedBoth', { shot: clipLabel(clip) });
	return usages[0] === 'first' ? t('scene.toast.capturedFirst', { shot: clipLabel(clip) }) : t('scene.toast.capturedLast', { shot: clipLabel(clip) });
}

export async function storeCaptures(clipId, shots, place = false) {
	const clip = doc.clips.find((c) => c.id === clipId);
	const taken = ['first', 'last'].filter((usage) => shots[usage]?.url);
	if (!clip || !taken.length || sceneState.saving) return null;
	if (place && !(await replaceAllowed(clip, taken))) return null;
	const projectId = project.id;
	sceneState.saving = true;
	try {
		const stored = [];
		for (const usage of taken) {
			const shot = shots[usage];
			const kept = shot.assetId ? asset(shot.assetId) : null;
			if (kept) {
				stored.push({ usage, sceneId: shot.sceneId, image: kept });
				continue;
			}
			const name = captureName(sceneOf(shot.sceneId), clip);
			const media = await storeCapture(projectId, shot.url, name);
			if (projectId !== project.id) return null;
			stored.push({ usage, sceneId: shot.sceneId, image: seamAsset(media, name) });
		}
		const target = doc.clips.find((c) => c.id === clipId);
		if (!target) return null;
		act(() => {
			for (const { usage, sceneId, image } of stored) {
				if (place) placeSeamFrame(doc, target, usage, image, ulid, sceneId);
				else if (!doc.assets.some((a) => a.id === image.id)) doc.assets.push(image);
			}
		});
		if (place) toast(placedText(target, taken), 'success', { label: t('shell.toast.undo'), run: undo });
		return stored;
	} catch (err) {
		if (err?.code === 'project_not_found') projectGone(projectId);
		else toast(err?.code === 'storage_full' ? t('scene.error.storage') : t('scene.toast.captureFailed'), 'error');
		return null;
	} finally {
		sceneState.saving = false;
	}
}

function resetScenes() {
	closed = false;
	clearTimeout(streakTimer);
	sceneState.streaks = null;
	poller.stop();
	liveJobs.clear();
	deferred = false;
	forgetLoaded();
	Object.assign(sceneState, { info: {}, progress: {}, capture: null });
	pollScenes();
}

export function disposeScenes() {
	closed = true;
	clearTimeout(streakTimer);
	sceneState.streaks = null;
	poller.stop();
	deferred = false;
	forgetLoaded();
	dropStage();
	liveJobs.clear();
	Object.assign(sceneState, { info: {}, progress: {}, capture: null });
	if (sceneState.engine === 'lost') sceneState.engine = 'ready';
}

onLoaded(resetScenes);
onRestore(cancelOrphans);

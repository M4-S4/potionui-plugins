import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, select, toast, simulated, clamp, round, secs, shotIdAt } from './state.svelte.js';
import { motionPresets, motionPresetLabel } from './catalog.js';
import { ulid } from './ulid.js';

export function currentPlan() {
	if (ui.selection?.kind === 'plan3d') return doc.plans3d.find((p) => p.id === ui.selection.id) ?? null;
	return doc.plans3d.find((p) => ui.playhead >= p.start && ui.playhead <= p.start + p.dur) ?? doc.plans3d[0] ?? null;
}

export function markGuidesStale() {
	for (const c of doc.controls) if (c.source === 'scene3d') c.stale = true;
}

export function cameraAt(plan, time) {
	const k = plan.keyframes;
	if (!k.length) return null;
	if (time <= k[0].t) return k[0];
	if (time >= k[k.length - 1].t) return k[k.length - 1];
	const i = k.findIndex((x) => x.t > time);
	const a = k[i - 1];
	const b = k[i];
	const u = (time - a.t) / (b.t - a.t);
	const s = u * u * (3 - 2 * u);
	const lerp = (p) => a[p] + (b[p] - a[p]) * s;
	return { az: lerp('az'), el: lerp('el'), dist: lerp('dist'), focal: lerp('focal'), height: lerp('height') };
}

export function currentScene() {
	return doc.scenes.find((s) => s.id === ui.scene.current) ?? doc.scenes[0] ?? null;
}

export function addSampleScene() {
	const existing = doc.scenes.find((s) => s.kind === 'sample');
	if (existing) {
		ui.scene.current = existing.id;
		return existing;
	}
	const scene = { id: ulid(), kind: 'sample', name: t('scene.sample.name') };
	act(() => doc.scenes.push(scene));
	ui.scene.current = scene.id;
	toast(t('scene.toast.sampleAdded'));
	return scene;
}

export function addFileScene(file) {
	const scene = { id: ulid(), kind: 'file', name: file.split(/[\\/]/).pop() || file, file };
	act(() => doc.scenes.push(scene));
	ui.scene.current = scene.id;
	return scene;
}

function defaultPlanName() {
	return currentScene()?.name ?? t('scene.default.plan');
}

export function newPlan() {
	const start = round(ui.playhead, 0.04);
	const p = { id: ulid(), shotId: shotIdAt(start), sceneId: currentScene()?.id ?? null, name: defaultPlanName(), start, dur: 5, keyframes: [] };
	act(() => doc.plans3d.push(p));
	select('plan3d', p.id);
	return p;
}

export function addKeyframe() {
	const plan = currentPlan() ?? newPlan();
	const at = round(clamp(ui.playhead - plan.start, 0, plan.dur), 0.04);
	const { az, el, dist, focal, height } = ui.scene;
	act(() => {
		const existing = plan.keyframes.find((k) => Math.abs(k.t - at) < 0.05);
		if (existing) Object.assign(existing, { az, el, dist, focal, height });
		else plan.keyframes.push({ id: ulid(), t: at, az, el, dist, focal, height });
		plan.keyframes.sort((a, b) => a.t - b.t);
		markGuidesStale();
	});
	toast(t('scene.toast.keyframe', { time: secs(at) }));
}

export function applyPreset(name) {
	const plan = currentPlan() ?? newPlan();
	act(() => {
		plan.keyframes = motionPresets[name].map((k) => ({ ...k, id: ulid(), t: round(k.t * plan.dur, 0.04) }));
		markGuidesStale();
	});
	select('plan3d', plan.id);
	toast(t('scene.toast.preset', { preset: motionPresetLabel(name), plan: plan.name }));
}

function guideFor(plan) {
	return doc.controls.find((x) => x.source === 'scene3d' && (plan.shotId && x.shotId ? x.shotId === plan.shotId : x.start === plan.start));
}

export function renderGuide() {
	const plan = currentPlan();
	if (!plan) return toast(t('scene.toast.noPlan'), 'warning');
	act(() => {
		let c = guideFor(plan);
		if (!c) {
			c = { id: ulid(), shotId: plan.shotId ?? shotIdAt(plan.start), name: t('lib.default.guide3d', { name: plan.name }), start: plan.start, dur: plan.dur, guidance: 65, source: 'scene3d', stale: false };
			doc.controls.push(c);
		}
		c.dur = plan.dur;
		c.stale = false;
	});
	simulated(t('scene.sim.guideRender'));
}

export function captureFrame() {
	const plan = currentPlan();
	const time = round(ui.playhead, 0.04);
	act(() => doc.frames.push({ id: ulid(), shotId: shotIdAt(time), time, assetId: null, role: 'Capture 3D', strength: 80 }));
	toast(plan ? t('scene.toast.capturedFor', { plan: plan.name }) : t('scene.toast.captured'));
}

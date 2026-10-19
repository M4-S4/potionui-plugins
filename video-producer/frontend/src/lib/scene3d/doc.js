const ASSET_LISTS = ['clips', 'audio', 'frames', 'references', 'controls'];

export function planSignature(plan) {
	if (!plan) return '';
	return JSON.stringify([plan.keyframes, plan.dur, plan.start, plan.sceneId ?? null, plan.amount ?? null, plan.preset ?? null, plan.camera ?? null]);
}

export function controlFor(controls, plan) {
	if (!plan) return null;
	const own = controls.find((c) => c.planId === plan.id);
	if (own) return own;
	return controls.find((c) => c.source === 'scene3d' && !c.planId && (plan.shotId && c.shotId ? c.shotId === plan.shotId : c.start === plan.start)) ?? null;
}

export function movePlan(controls, plan, shotId) {
	const next = shotId ?? null;
	if ((plan.shotId ?? null) === next) return null;
	const control = controlFor(controls, plan);
	plan.shotId = next;
	if (!control) return null;
	Object.assign(control, { shotId: next, planId: plan.id, stale: true });
	return control;
}

export function dropPlanControls(controls, planId) {
	let removed = 0;
	for (let i = controls.length - 1; i >= 0; i--) {
		if (controls[i]?.planId !== planId) continue;
		controls.splice(i, 1);
		removed += 1;
	}
	return removed;
}

export function assetInUse(doc, id) {
	if (!id) return false;
	if (ASSET_LISTS.some((key) => (doc[key] ?? []).some((item) => item?.assetId === id))) return true;
	return (doc.scenes ?? []).some((scene) => scene?.sourceAssetId === id);
}

export function pruneAsset(doc, id) {
	if (!id || assetInUse(doc, id)) return false;
	const i = (doc.assets ?? []).findIndex((a) => a?.id === id);
	if (i < 0) return false;
	doc.assets.splice(i, 1);
	return true;
}

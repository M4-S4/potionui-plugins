import { t } from '../i18n/index.svelte.js';
import { doc, act, toast, undo, clipLabel, onShotsAdded } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { onTake, takeStore } from './takes.svelte.js';
import { isRemoved } from './removedtakes.js';
import { engineChoices } from './production.svelte.js';
import { optionFor } from './generation.js';
import { effectiveEngine } from './engine.js';
import { frameErrorText, placeSeamFrame, previousShot, seamImage } from './seam.js';
import { chainOn, chainPlan, chainSource, chainState, chainWaiting, frameAsset, ignoresFirstFrame, placesTakeFrame, resetShotChain, seamChain, setShotChain, shotChained, stillAsset, takeFrameAsset } from './chain.js';

export const chainJobs = $state({ shots: [] });

export const chainBusy = (shotId) => chainJobs.shots.includes(shotId);

export function chainOf(clip) {
	const i = clip ? doc.clips.findIndex((c) => c.id === clip.id) : -1;
	return i > 0 ? chainState(doc, i) : null;
}

const assetName = (previous) => t('lib.chain.assetName', { shot: clipLabel(previous) });

async function extract(previous) {
	const saved = await flushSave();
	if (!saved || !project.id) {
		toast(t('lib.seam.saveFirst'), 'error');
		return null;
	}
	const projectId = project.id;
	const result = await getClient().endFrame(projectId, previous.id);
	if (projectId !== project.id) return null;
	if (result.ok) return result.data;
	if (result.error.code === 'project_not_found') projectGone(projectId);
	else toast(frameErrorText(result.error, t), result.error.status === 409 ? 'warning' : 'error');
	return null;
}

async function chainFrame(shotId, auto) {
	const clip = doc.clips.find((c) => c.id === shotId);
	const previous = clip ? previousShot(doc, shotId) : null;
	const source = previous ? chainSource(doc, previous) : null;
	if (!source) {
		if (!auto) toast(t('lib.chain.noMedia', { shot: clipLabel(previous) }), 'warning');
		return;
	}
	if (chainBusy(shotId)) return;
	let asset = source.at === null ? stillAsset(doc, source, assetName(previous)) : null;
	if (!asset) {
		chainJobs.shots.push(shotId);
		try {
			const frame = await extract(previous);
			if (frame) asset = frameAsset(frame.media, frame.source, assetName(previous));
		} finally {
			chainJobs.shots = chainJobs.shots.filter((id) => id !== shotId);
		}
	}
	const target = doc.clips.find((c) => c.id === shotId);
	if (!asset || !target) return;
	if (auto && (seamImage(doc, shotId, 'first') || previousShot(doc, shotId)?.id !== previous.id)) return;
	act(() => placeSeamFrame(doc, target, 'first', asset));
	const names = { shot: clipLabel(target), previous: clipLabel(previous) };
	toast(auto ? t('lib.chain.taken', names) : t('lib.seam.added', names), 'success', { label: t('shell.toast.undo'), run: undo });
}

export const takeEndFrame = (clip) => chainFrame(clip.id, false);

function chainShots(clips) {
	for (const clip of clips) {
		const source = chainPlan(doc, clip);
		if (!source) continue;
		if (source.at !== null) {
			queueMicrotask(() => chainFrame(clip.id, true));
			continue;
		}
		const previous = previousShot(doc, clip.id);
		placeSeamFrame(doc, clip, 'first', stillAsset(doc, source, assetName(previous)));
		toast(t('lib.chain.taken', { shot: clipLabel(clip), previous: clipLabel(previous) }), 'success');
	}
}

onShotsAdded(chainShots);

export function setShotChaining(clip, on) {
	const target = doc.clips.find((c) => c.id === clip?.id);
	const previous = target ? previousShot(doc, target.id) : null;
	if (!previous || shotChained(doc, target) === on) return;
	act(() => setShotChain(doc, target, on));
	const names = { shot: clipLabel(target), previous: clipLabel(previous) };
	toast(on ? t('lib.chain.shotOn', names) : t('lib.chain.shotOff', names), 'info', { label: t('shell.toast.undo'), run: undo });
	if (on && !seamImage(doc, target.id, 'first') && chainSource(doc, previous)) chainFrame(target.id, true);
}

export const toggleShotChaining = (clip) => setShotChaining(clip, !shotChained(doc, clip));

export function seamChainOf(clip) {
	const i = clip ? doc.clips.findIndex((c) => c.id === clip.id) : -1;
	if (i <= 0) return null;
	const option = optionFor(engineChoices(), effectiveEngine(doc.clips[i], doc));
	return seamChain(doc, i, takeStore.list, ignoresFirstFrame(option));
}

export function waitText(take) {
	if (!chainWaiting(take)) return '';
	const previous = doc.clips.find((c) => c.id === take.chain.previous);
	const shot = previous ? clipLabel(previous) : '—';
	const after = take.chain.after ? takeStore.list.find((x) => x.id === take.chain.after) : null;
	return after ? t('lib.chain.waitTake', { variant: after.variant, shot }) : t('lib.chain.waitFrame', { shot });
}

export function chainStatusText(state) {
	const previous = clipLabel(state.from);
	if (state.state === 'off') return t('storyboard.chain.off');
	if (state.state === 'textOnly') return t('storyboard.chain.textOnly');
	if (state.state === 'waiting') return waitText(state.take);
	if (state.state === 'own') return t('storyboard.chain.own');
	if (state.state === 'stale') return t('storyboard.chain.stale', { previous });
	if (state.state === 'fresh') return t('storyboard.chain.fresh', { previous });
	if (state.state === 'ready') return t('storyboard.chain.ready', { previous });
	return t('storyboard.chain.later', { previous });
}

export function shotWaitText(shotId) {
	const take = takeStore.list.find((x) => x.shotId === shotId && chainWaiting(x));
	return take ? waitText(take) : '';
}

export function followProjectChain(clip) {
	const target = doc.clips.find((c) => c.id === clip?.id);
	if (!target || typeof target.firstFromPrevious !== 'boolean') return;
	const before = shotChained(doc, target);
	act(() => resetShotChain(doc, target));
	const previous = previousShot(doc, target.id);
	if (!before && chainOn(doc) && previous && !seamImage(doc, target.id, 'first') && chainSource(doc, previous)) chainFrame(target.id, true);
}

const placed = new Set();

function placeTakeFrame(take, live) {
	if (placed.has(take?.id) || !placesTakeFrame(doc, take, takeStore.list, (id) => isRemoved(doc, id))) return;
	const target = doc.clips.find((c) => c.id === take.shotId);
	const previous = previousShot(doc, take.shotId);
	const asset = takeFrameAsset(doc, take, assetName(previous));
	if (!asset) return;
	placed.add(take.id);
	const apply = () => placeSeamFrame(doc, target, 'first', asset);
	if (!live) return apply();
	act(apply);
	toast(t('lib.chain.batchTaken', { shot: clipLabel(target), previous: clipLabel(previous), variant: take.variant }), 'success', { label: t('shell.toast.undo'), run: undo });
}

onTake(placeTakeFrame);

import { t } from '../i18n/index.svelte.js';
import { doc, act, toast, undo, clipLabel, onShotsAdded } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { placeSeamFrame, previousShot, seamImage } from './seam.js';
import { chainPlan, chainSource, chainState, frameAsset, stillAsset } from './chain.js';

export const chainJobs = $state({ shots: [] });

export const chainBusy = (shotId) => chainJobs.shots.includes(shotId);

export function chainOf(clip) {
	const i = clip ? doc.clips.findIndex((c) => c.id === clip.id) : -1;
	return i > 0 ? chainState(doc, i) : null;
}

const assetName = (previous) => t('lib.chain.assetName', { shot: clipLabel(previous) });

function errorText(error) {
	const code = error?.code;
	if (code === 'shot_not_found') return t('lib.seam.error.shot');
	if (code === 'no_media') return t('lib.chain.error.noMedia');
	if (code === 'ffmpeg_missing') return t('lib.chain.error.ffmpeg');
	if (code === 'extract_failed') return error?.data?.code === 'store_failed' ? t('lib.seam.error.store') : t('lib.seam.error.extract');
	return t('lib.seam.error.generic');
}

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
	else toast(errorText(result.error), result.error.status === 409 ? 'warning' : 'error');
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

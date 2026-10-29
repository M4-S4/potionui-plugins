import { t } from '../i18n/index.svelte.js';
import { doc, ui, act, toast, undo, clipLabel, secs } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { confirm } from './host.js';
import { PREVIOUS_LAST, frameErrorText, framesOf, placeSeamFrame, playheadPick, previousShot, seamAsset } from './seam.js';
import { chainSource } from './chain.js';
import { chainBusy, chainOf, takeEndFrame } from './chain.svelte.js';

export const seamState = $state({ busy: null });

export const extractable = (take) => Boolean(take && take.status === 'done' && take.generationId && take.fileId !== null && take.fileId !== undefined);

export function seamOffer(clip) {
	const prev = clip ? previousShot(doc, clip.id) : null;
	if (!prev) return null;
	const ready = Boolean(chainSource(doc, prev));
	const stale = chainOf(clip)?.state === 'stale';
	return { previous: prev, ready, stale, busy: seamState.busy === clip.id || chainBusy(clip.id), reason: ready ? '' : t('lib.chain.noMedia', { shot: clipLabel(prev) }) };
}

function replaceText(clip, kinds) {
	const shot = clipLabel(clip);
	if (kinds.length > 1) return { title: t('lib.seam.replaceBothTitle'), message: t('lib.seam.replaceBothMessage', { shot }) };
	if (kinds[0] === 'first') return { title: t('lib.seam.replaceFirstTitle'), message: t('lib.seam.replaceFirstMessage', { shot }) };
	return { title: t('lib.seam.replaceLastTitle'), message: t('lib.seam.replaceLastMessage', { shot }) };
}

export async function replaceAllowed(clip, kinds) {
	const taken = [kinds].flat().filter((kind) => framesOf(doc, clip.id, kind).some((f) => f.assetId));
	if (!taken.length) return true;
	return confirm({ ...replaceText(clip, taken), variant: 'warning', confirmLabel: t('lib.seam.replace'), cancelLabel: t('lib.seam.keep') });
}

function doneText(clip, kind, source) {
	return kind === 'first' ? t('lib.seam.extractedFirst', { shot: clipLabel(clip), time: secs(source.at) }) : t('lib.seam.extractedLast', { shot: clipLabel(clip), time: secs(source.at) });
}

export async function useSeamFrame(clip, source = PREVIOUS_LAST) {
	if (!clip || seamState.busy) return;
	if (source === PREVIOUS_LAST) {
		if (!previousShot(doc, clip.id)) return toast(t('lib.seam.noPrevious'), 'warning');
		if (chainOf(clip)?.state === 'stale' || (await replaceAllowed(clip, 'first'))) await takeEndFrame(clip);
		return;
	}
	const kind = source.kind;
	if (!(await replaceAllowed(clip, kind))) return;
	seamState.busy = clip.id;
	try {
		const saved = await flushSave();
		if (!saved || !project.id) return toast(t('lib.seam.saveFirst'), 'error');
		const projectId = project.id;
		const result = await getClient().seamFrame(projectId, clip.id, { takeId: source.takeId, at: source.at });
		if (projectId !== project.id) return;
		if (!result.ok) {
			if (result.error.code === 'project_not_found') return projectGone(projectId);
			return toast(frameErrorText(result.error, t), result.error.status === 409 ? 'warning' : 'error');
		}
		const target = doc.clips.find((c) => c.id === clip.id);
		if (!target) return;
		act(() => placeSeamFrame(doc, target, kind, seamAsset(result.data, t('lib.seam.assetName', { shot: clipLabel(target) }))));
		toast(doneText(target, kind, source), 'success', { label: t('shell.toast.undo'), run: undo });
	} finally {
		seamState.busy = null;
	}
}

export function extractAtPlayhead(take, clip) {
	if (!extractable(take) || !clip) return;
	const { kind, at } = playheadPick(clip, ui.playhead, clip.take === take.id);
	return useSeamFrame(clip, { takeId: take.id, at, kind });
}

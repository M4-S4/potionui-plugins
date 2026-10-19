import { t } from '../i18n/index.svelte.js';
import { doc, ui, act, toast, undo, clipLabel, secs } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { findTake } from './production.svelte.js';
import { realTakesOf, takeStore } from './takes.svelte.js';
import { confirm } from './host.js';
import { PREVIOUS_LAST, framesOf, placeSeamFrame, playheadPick, previousShot, seamAsset } from './seam.js';

export const seamState = $state({ busy: null });

export const extractable = (take) => Boolean(take && take.status === 'done' && take.generationId && take.fileId !== null && take.fileId !== undefined);

export function previousTake(clip) {
	const prev = clip ? previousShot(doc, clip.id) : null;
	if (!prev) return null;
	const chosen = findTake(prev.take);
	if (extractable(chosen)) return chosen;
	return [...realTakesOf(prev.id)].reverse().find(extractable) ?? null;
}

export function seamOffer(clip) {
	const prev = clip ? previousShot(doc, clip.id) : null;
	if (!prev) return null;
	const ready = !takeStore.loaded || Boolean(previousTake(clip));
	return { previous: prev, ready, busy: seamState.busy === clip.id, reason: ready ? '' : t('lib.seam.noPreviousTake', { shot: clipLabel(prev) }) };
}

function errorText(error) {
	const code = error?.code;
	if (code === 'shot_not_found') return t('lib.seam.error.shot');
	if (code === 'no_previous_take') return t('lib.seam.error.noTake');
	if (code === 'extract_failed') return error?.data?.code === 'store_failed' ? t('lib.seam.error.store') : t('lib.seam.error.extract');
	if (code === 'invalid_request') return t('lib.seam.error.invalid');
	return t('lib.seam.error.generic');
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

function doneText(clip, kind, source, previous) {
	if (source === PREVIOUS_LAST) return t('lib.seam.added', { shot: clipLabel(clip), previous: clipLabel(previous) });
	return kind === 'first' ? t('lib.seam.extractedFirst', { shot: clipLabel(clip), time: secs(source.at) }) : t('lib.seam.extractedLast', { shot: clipLabel(clip), time: secs(source.at) });
}

export async function useSeamFrame(clip, source = PREVIOUS_LAST) {
	if (!clip || seamState.busy) return;
	const fromTake = source !== PREVIOUS_LAST;
	const previous = previousShot(doc, clip.id);
	if (!fromTake && !previous) return toast(t('lib.seam.noPrevious'), 'warning');
	const kind = fromTake ? source.kind : 'first';
	if (!(await replaceAllowed(clip, kind))) return;
	seamState.busy = clip.id;
	try {
		const saved = await flushSave();
		if (!saved || !project.id) return toast(t('lib.seam.saveFirst'), 'error');
		const projectId = project.id;
		const result = await getClient().seamFrame(projectId, clip.id, fromTake ? { takeId: source.takeId, at: source.at } : PREVIOUS_LAST);
		if (projectId !== project.id) return;
		if (!result.ok) {
			if (result.error.code === 'project_not_found') return projectGone(projectId);
			return toast(errorText(result.error), result.error.status === 409 ? 'warning' : 'error');
		}
		const target = doc.clips.find((c) => c.id === clip.id);
		if (!target) return;
		act(() => placeSeamFrame(doc, target, kind, seamAsset(result.data, t('lib.seam.assetName', { shot: clipLabel(target) }))));
		toast(doneText(target, kind, source, previous), 'success', { label: t('shell.toast.undo'), run: undo });
	} finally {
		seamState.busy = null;
	}
}

export function extractAtPlayhead(take, clip) {
	if (!extractable(take) || !clip) return;
	const { kind, at } = playheadPick(clip, ui.playhead, clip.take === take.id);
	return useSeamFrame(clip, { takeId: take.id, at, kind });
}

import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, relayout, select, moveClip, promptOf, toast, clipLabel, secs, openDirector } from './state.svelte.js';
import { takesOf, findTake, shotDurationLimit, settleRelease, labelTake } from './production.svelte.js';
import { applyShotDraft, shotDraft, shotStale } from './shots.js';
import { identityTakes, seam } from './continuity.svelte.js';
import { seek } from './playback.svelte.js';
import { previewTake } from './monitor.svelte.js';
import { takeStore } from './takes.svelte.js';
import { reviewCounts, reviewFilterOf, reviewShots } from './director.js';
import { ulid } from './ulid.js';
import { BAND_STEP, ghostLayout, insertIndex, lastFailure, previewable } from './band.js';

export function selectedShot() {
	return ui.selection?.kind === 'clip' ? (doc.clips.find((c) => c.id === ui.selection.id) ?? null) : null;
}

export function pickShot(clip, seekTo = true) {
	if (!clip) return;
	const shown = ui.preview?.kind === 'result' ? findTake(ui.preview.id) : null;
	if (shown && shown.shotId !== clip.id) ui.preview = null;
	if (ui.seamCompare && ui.seamCompare !== clip.id) ui.seamCompare = null;
	select('clip', clip.id);
	if (seekTo) seek(clip.start + 0.01);
}

export function stepShot(delta) {
	if (!doc.clips.length) return;
	const i = doc.clips.findIndex((c) => c.id === selectedShot()?.id);
	const next = doc.clips[Math.max(0, Math.min(doc.clips.length - 1, i < 0 ? 0 : i + delta))];
	pickShot(next);
}

export function applyQuick(clip, patch) {
	if (!clip) return;
	const before = $state.snapshot(shotDraft(doc, clip, doc.engine));
	const draft = { ...$state.snapshot(before), ...patch };
	const limit = shotDurationLimit({ ...clip, engine: draft.engine });
	let released = null;
	act(() => {
		const result = applyShotDraft(doc, clip, before, draft, { makeId: ulid, maxDur: limit.max, engine: doc.engine });
		released = result.released;
		if (result.resized) relayout();
	});
	settleRelease(clip, released);
}

export function nudgeDuration(delta) {
	const clip = selectedShot();
	if (!clip) return;
	const before = clip.dur;
	applyQuick(clip, { dur: Math.max(BAND_STEP, before + delta) });
	if (clip.dur === before) toast(t('storyboard.band.durationLimit', { shot: clipLabel(clip), dur: secs(before) }), 'warning');
}

export function shiftShot(delta) {
	const clip = selectedShot();
	if (!clip) return;
	const from = doc.clips.indexOf(clip);
	const to = Math.max(0, Math.min(doc.clips.length - 1, from + delta));
	if (from !== to) moveClip(from, to);
}

export function cycleTake(delta) {
	const clip = selectedShot();
	if (!clip) return;
	const list = previewable(takesOf(clip), ui.hideRejected);
	if (!list.length) return toast(t('storyboard.band.noTake', { shot: clipLabel(clip) }), 'warning');
	const cur = ui.preview?.kind === 'result' ? list.findIndex((x) => x.id === ui.preview.id) : -1;
	const index = cur < 0 ? (delta < 0 ? list.length - 1 : 0) : (cur + delta + list.length) % list.length;
	previewTake(list[index]);
}

export function previewed() {
	const take = ui.preview?.kind === 'result' ? findTake(ui.preview.id) : null;
	return take && take.shotId === selectedShot()?.id ? take : null;
}

export function labelPreviewed(label) {
	const take = previewed();
	if (!take) return false;
	labelTake(selectedShot(), take, label);
	return true;
}

export function compareSeam(clip = selectedShot()) {
	if (!clip) return;
	const i = doc.clips.indexOf(clip);
	if (i <= 0) return toast(t('storyboard.band.noSeam'), 'warning');
	if (selectedShot()?.id !== clip.id) select('clip', clip.id);
	ui.preview = null;
	ui.compare = null;
	ui.seamCompare = ui.seamCompare === clip.id ? null : clip.id;
}

export function compareSeamTakes(clip) {
	const pair = identityTakes(clip);
	if (!pair) return;
	ui.workspace = 'storyboard';
	ui.storyView = 'band';
	select('clip', clip.id);
	ui.seamCompare = null;
	ui.preview = null;
	ui.compare = pair;
}

export function showInReview(clip) {
	if (!clip) return;
	const filter = reviewFilterOf(ui.reviewFilter, reviewCounts(doc.clips, takeStore.list));
	if (!reviewShots(doc.clips, takeStore.list, filter).includes(clip)) ui.reviewFilter = 'all';
	openDirector('review');
	pickShot(clip);
	ui.reveal = clip.id;
}

export function openSeam(clip) {
	ui.workspace = 'storyboard';
	ui.storyView = 'band';
	pickShot(clip);
	ui.compare = null;
	ui.preview = null;
	ui.seamCompare = clip.id;
}

export function proposalLayout() {
	if (!ui.storyOpen || ui.storyTab !== 'cut' || !ui.storyProposal?.length) return null;
	const layout = ghostLayout(doc.clips, ui.storyProposal, insertIndex(doc.clips, ui.storyAt, selectedShot()?.id ?? null));
	return layout.ghosts.length ? layout : null;
}

export function bandChecks() {
	const out = [];
	doc.clips.forEach((clip, i) => {
		const s = i > 0 ? seam(i) : null;
		for (const issue of s?.issues ?? []) out.push({ kind: 'seam', clip, issue, text: issue.text });
		const takes = takesOf(clip);
		const failed = lastFailure(takes);
		if (failed) out.push({ kind: 'failed', clip, take: failed, text: t('storyboard.check.failed', { shot: clipLabel(clip), variant: failed.variant ?? '' }) });
		if (shotStale(clip, takes)) out.push({ kind: 'stale', clip, text: t('storyboard.check.stale', { shot: clipLabel(clip) }) });
		if (!clip.assetId && !promptOf(clip)?.text?.trim()) out.push({ kind: 'prompt', clip, text: t('storyboard.check.prompt', { shot: clipLabel(clip) }) });
	});
	return out;
}

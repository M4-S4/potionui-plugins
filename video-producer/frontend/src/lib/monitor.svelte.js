import { ui, doc, asset, clipAt, select, bandView, directorView } from './state.svelte.js';
import { findTake } from './production.svelte.js';
import { seek } from './playback.svelte.js';
import { shownShots } from './monitor.js';

const reviewing = () => ui.workspace === 'director' && directorView() === 'review';

function bringUnder(clip) {
	if (ui.selection?.kind !== 'clip' || ui.selection.id !== clip.id) select('clip', clip.id);
	if (clipAt(ui.playhead)?.id !== clip.id) seek(clip.start + 0.01);
}

export function showShot(clip) {
	const live = clip ? doc.clips.find((c) => c.id === clip.id) : null;
	if (!live) return;
	const seam = bandView() ? ui.seamCompare : null;
	const view = { clips: doc.clips, playhead: ui.playhead, preview: ui.preview, compare: ui.compare, seam };
	const shown = shownShots(view, { take: findTake, asset }).includes(live.id);
	if (seam && shown) return;
	if (!shown) {
		ui.preview = null;
		ui.compare = null;
	}
	if (ui.seamCompare && ui.seamCompare !== live.id) ui.seamCompare = null;
	if (reviewing()) ui.reviewMonitor = true;
	bringUnder(live);
}

export function previewTake(take) {
	if (!take || take.status !== 'done' || !take.url) return;
	const clip = doc.clips.find((c) => c.id === take.shotId);
	if (clip) bringUnder(clip);
	ui.seamCompare = null;
	ui.compare = null;
	ui.preview = { kind: 'result', id: take.id };
}

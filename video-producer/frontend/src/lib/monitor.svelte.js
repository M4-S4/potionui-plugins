import { ui, doc, asset, clipAt, select, bandView } from './state.svelte.js';
import { findTake } from './production.svelte.js';
import { seek } from './playback.svelte.js';
import { shownShots } from './monitor.js';

export function showShot(clip) {
	const live = clip ? doc.clips.find((c) => c.id === clip.id) : null;
	if (!live) return;
	const seam = bandView() && ui.seamCompare === live.id ? live.id : null;
	const view = { clips: doc.clips, playhead: ui.playhead, preview: ui.preview, compare: ui.compare, seam };
	if (!shownShots(view, { take: findTake, asset }).includes(live.id)) {
		ui.preview = null;
		ui.compare = null;
	}
	if (ui.seamCompare && ui.seamCompare !== live.id) ui.seamCompare = null;
	if (ui.selection?.kind !== 'clip' || ui.selection.id !== live.id) select('clip', live.id);
	if (clipAt(ui.playhead)?.id !== live.id) seek(live.start + 0.01);
}

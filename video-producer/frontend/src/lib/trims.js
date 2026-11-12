import { ui, doc, relayout, round, clamp, sourceLength, limitNote } from './state.svelte.js';
import { shotDurationLimit, fitShot } from './production.svelte.js';
import { speedOf } from './cadence.js';
import { chained, headTrim, playedLengths, tailTrim } from './dissolve.js';
import { dragText, snap, trimText } from './timeline.js';

function noteLimit(played) {
	const note = limitNote(played);
	if (note && ui.drag) dragText(`${ui.drag.text} · ${note}`, ui.drag.limit);
}

const scale = () => ui.pxPerSec;

export function shotTrim(c, edge) {
	const max = sourceLength(c);
	const range = shotDurationLimit(c);
	const d0 = c.dur;
	const in0 = c.srcIn;
	const start0 = c.start;
	const speed = speedOf(c);
	const exact = chained(doc.clips);
	const played = playedLengths(doc.clips);
	return {
		onMove: (dx) => {
			const dt = dx / scale();
			let limit = false;
			if (edge === 'start' && exact) {
				const next = headTrim(in0, d0, speed, dt);
				limit = next.srcIn <= 0.001;
				c.srcIn = next.srcIn;
				c.dur = next.dur;
			} else if (edge === 'start') {
				const nIn = clamp(in0 + dt * speed, 0, in0 + (d0 - 0.4) * speed);
				limit = nIn <= 0.001;
				c.srcIn = round(nIn, 0.04);
				c.dur = round(d0 - (nIn - in0) / speed, 0.04);
			} else {
				const nd = clamp(d0 + dt, 0.4, range.max);
				limit = nd >= range.max - 0.001;
				c.dur = exact ? tailTrim(start0, round(start0 + d0 + dt, 0.04), range.max) : round(nd, 0.04);
			}
			relayout();
			trimText(range, max, d0, c.dur, limit);
			noteLimit(played);
		},
		onEnd: () => {
			if (edge === 'end' && fitShot(c, d0)) relayout();
		}
	};
}

export function bandTrim(c) {
	const range = shotDurationLimit(c);
	const max = sourceLength(c);
	const d0 = c.dur;
	const start0 = c.start;
	const exact = chained(doc.clips);
	const played = playedLengths(doc.clips);
	return {
		onMove: (dx) => {
			const end = ui.snapping ? snap((exact ? start0 : c.start) + d0 + dx / scale(), c.id) : { t: (exact ? start0 : c.start) + d0 + dx / scale(), at: null };
			const nd = clamp(end.t - c.start, 0.4, range.max);
			const limit = nd >= range.max - 0.001;
			c.dur = exact ? tailTrim(start0, ui.snapping ? end.t : round(end.t, 0.04), range.max) : round(nd, 0.04);
			relayout();
			if (ui.drag) ui.drag.at = end.at;
			trimText(range, max, d0, c.dur, limit);
			noteLimit(played);
		},
		onEnd: () => {
			if (fitShot(c, d0)) relayout();
		}
	};
}

export function setShotDuration(item, v) {
	const before = item.dur;
	item.dur = round(clamp(v, 0.4, shotDurationLimit(item).max), 0.04);
	fitShot(item, before);
	relayout();
}

export function setShotIn(item, v) {
	const max = sourceLength(item);
	item.srcIn = round(clamp(v, 0, max - 0.4), 0.04);
	const fit = Math.min(item.dur, (max - item.srcIn) / speedOf(item));
	item.dur = chained(doc.clips) ? +fit.toFixed(6) : fit;
	relayout();
}

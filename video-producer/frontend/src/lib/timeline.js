import { ui, doc, checkpoint, discardLast, round } from './state.svelte.js';

let release = null;

export function cancelDrag() {
	release?.();
	ui.drag = null;
}

function capturePointer(e) {
	try {
		e.currentTarget?.setPointerCapture?.(e.pointerId);
	} catch {}
}

export function drag(e, { onMove, onEnd, onClick, onCancel, undoable = true }) {
	if (e.button !== 0) return;
	e.stopPropagation();
	cancelDrag();
	capturePointer(e);
	const id = e.pointerId;
	const x0 = e.clientX;
	const y0 = e.clientY;
	let started = false;
	const mine = (ev) => ev.pointerId === id;
	const move = (ev) => {
		if (!mine(ev)) return;
		const dx = ev.clientX - x0;
		const dy = ev.clientY - y0;
		if (!started) {
			if (Math.hypot(dx, dy) < 3) return;
			started = true;
			if (undoable) checkpoint();
		}
		ui.drag = { ...(ui.drag ?? {}), x: ev.clientX, y: ev.clientY };
		onMove(dx, dy, ev);
	};
	const up = (ev) => {
		if (!mine(ev)) return;
		release();
		if (started) onEnd?.(ev);
		else onClick?.(ev);
		ui.drag = null;
	};
	const cancel = (ev) => {
		if (!mine(ev)) return;
		release();
		if (started) {
			if (undoable) discardLast();
			onCancel?.(ev);
		}
		ui.drag = null;
	};
	release = () => {
		window.removeEventListener('pointermove', move);
		window.removeEventListener('pointerup', up);
		window.removeEventListener('pointercancel', cancel);
		release = null;
	};
	window.addEventListener('pointermove', move);
	window.addEventListener('pointerup', up);
	window.addEventListener('pointercancel', cancel);
}

export function snapTargets(excludeId) {
	const t = [0, ui.playhead];
	for (const c of doc.clips) if (c.id !== excludeId) t.push(c.start, c.start + c.dur);
	for (const list of [doc.audio, doc.prompts, doc.titles])
		for (const x of list) if (x.id !== excludeId) t.push(x.start, x.start + x.dur);
	for (const f of doc.frames) if (f.id !== excludeId) t.push(f.time);
	for (const m of doc.markers) t.push(m.time);
	if (ui.range) t.push(ui.range.in, ui.range.out);
	return t;
}

export function snap(time, excludeId) {
	if (!ui.snapping) return { t: round(time, 0.04), at: null };
	const tol = 8 / ui.pxPerSec;
	let best = null;
	for (const c of snapTargets(excludeId)) {
		const d = Math.abs(c - time);
		if (d < tol && (!best || d < Math.abs(best - time))) best = c;
	}
	return best == null ? { t: round(time, 0.04), at: null } : { t: best, at: best };
}

export function snapMove(start, dur, id) {
	const a = snap(start, id);
	if (a.at != null) return { start: a.t, at: a.at };
	const b = snap(start + dur, id);
	if (b.at != null) return { start: b.t - dur, at: b.at };
	return { start: round(start, 0.04), at: null };
}

export function rulerStep(pps) {
	for (const s of [0.5, 1, 2, 5, 10, 15, 30, 60]) if (s * pps >= 64) return s;
	return 120;
}

export function waveform(seed, width, height, srcIn, pps, kind) {
	const pts = [];
	const step = 3;
	const mid = height / 2;
	let s = 0;
	for (const ch of seed) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
	for (let x = 0; x <= width; x += step) {
		const t = srcIn + x / pps;
		const n = Math.sin(t * 7.1 + s) * 0.5 + Math.sin(t * 2.3 + s * 0.7) * 0.3 + Math.sin(t * 19.7 + s * 1.3) * 0.2;
		let amp;
		if (kind === 'steps') amp = Math.max(0.05, Math.pow(Math.max(0, Math.sin(t * Math.PI * 1.8)), 6));
		else if (kind === 'voice') amp = Math.max(0.05, Math.abs(Math.sin(t * 4.2 + s)) * (0.4 + 0.6 * Math.abs(n)));
		else if (kind === 'wind') amp = 0.35 + 0.3 * Math.abs(n);
		else amp = 0.45 + 0.25 * n;
		pts.push([x, Math.max(0.5, amp * (mid - 2))]);
	}
	return polygon(pts, mid);
}

function polygon(pts, mid) {
	const top = pts.map(([x, a]) => `${x},${mid - a}`).join(' ');
	const bottom = pts
		.slice()
		.reverse()
		.map(([x, a]) => `${x},${mid + a}`)
		.join(' ');
	return `${top} ${bottom}`;
}

export function peakWaveform(peaks, width, height, srcIn, pps) {
	const pts = [];
	const step = 3;
	const mid = height / 2;
	const { rate, values } = peaks;
	for (let x = 0; x <= width; x += step) {
		const from = Math.max(0, Math.floor((srcIn + x / pps) * rate));
		const to = Math.max(from + 1, Math.floor((srcIn + (x + step) / pps) * rate));
		let amp = 0;
		for (let i = from; i < to && i < values.length; i++) amp = Math.max(amp, values[i]);
		pts.push([x, Math.max(0.5, amp * (mid - 2))]);
	}
	return polygon(pts, mid);
}

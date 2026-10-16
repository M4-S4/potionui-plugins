import { t } from '../i18n/index.svelte.js';
import { doc, asset, act, toast, clamp, round, clipLabel } from './state.svelte.js';
import { clipFilter } from './look.js';

const stats = $state({});
const pending = new Set();

function measure(key, src, filter) {
	if (!src) return null;
	if (pending.has(key)) return stats[key] ?? null;
	pending.add(key);
	const img = new Image();
	img.onload = () => {
		const c = document.createElement('canvas');
		c.width = 48;
		c.height = 27;
		const g = c.getContext('2d', { willReadFrequently: true });
		if (!g) return;
		g.filter = filter;
		g.drawImage(img, 0, 0, 48, 27);
		const d = g.getImageData(0, 0, 48, 27).data;
		let r = 0;
		let gr = 0;
		let b = 0;
		for (let i = 0; i < d.length; i += 4) {
			r += d[i];
			gr += d[i + 1];
			b += d[i + 2];
		}
		const n = d.length / 4;
		r /= n * 255;
		gr /= n * 255;
		b /= n * 255;
		stats[key] = { lum: 0.2126 * r + 0.7152 * gr + 0.0722 * b, warm: r - b };
	};
	img.src = src;
	return null;
}

export function colorOf(clip) {
	const a = asset(clip.assetId);
	const filter = clipFilter(clip);
	const key = `${a?.id}|${filter}`;
	return stats[key] ?? measure(key, a?.src, filter);
}

const takeOf = (clip) => {
	const a = asset(clip.assetId);
	return a?.generated ? (doc.results.find((r) => r.id === a.resultId) ?? null) : null;
};

const identityScore = (a, b) => {
	const ra = takeOf(a);
	const rb = takeOf(b);
	if (!ra || !rb) return null;
	return ra.look === rb.look ? 0.94 : 0.78;
};

export function seam(i) {
	const a = doc.clips[i - 1];
	const b = doc.clips[i];
	if (!a || !b) return null;
	const ca = colorOf(a);
	const cb = colorOf(b);
	const out = { from: a, to: b, issues: [], pending: !ca || !cb, measured: false };
	if (ca && cb) {
		const dl = cb.lum - ca.lum;
		const dw = cb.warm - ca.warm;
		if (Math.abs(dl) > 0.12) out.issues.push({ kind: 'lum', text: dl > 0 ? t('lib.continuity.brighter', { shot: clipLabel(b) }) : t('lib.continuity.darker', { shot: clipLabel(b) }), fix: true });
		if (Math.abs(dw) > 0.1) out.issues.push({ kind: 'warm', text: dw > 0 ? t('lib.continuity.warmer', { shot: clipLabel(b) }) : t('lib.continuity.cooler', { shot: clipLabel(b) }), fix: true });
	}
	const id = identityScore(a, b);
	out.measured = !out.pending || id != null;
	if (id != null && id < 0.85) out.issues.push({ kind: 'identity', text: t('lib.continuity.identity', { from: clipLabel(a), to: clipLabel(b), score: Math.round(id * 100) }), fix: false });
	return out;
}

export function seams() {
	return doc.clips
		.slice(1)
		.map((_, k) => seam(k + 1))
		.filter(Boolean);
}

export function matchToPrevious(clip) {
	const i = doc.clips.indexOf(clip);
	const prev = doc.clips[i - 1];
	const ca = prev && colorOf(prev);
	const cb = colorOf(clip);
	if (!ca || !cb) return toast(t('lib.continuity.pending'), 'warning');
	act(() => {
		clip.exposure = round(clamp(clip.exposure + (ca.lum - cb.lum) * 5, -2, 2), 0.05);
		clip.temperature = Math.round(clamp(clip.temperature + (ca.warm - cb.warm) * 320, -100, 100));
		clip.preset = 'Raccord';
	});
	toast(t('lib.continuity.matched', { shot: clipLabel(clip), previous: clipLabel(prev) }), 'success');
}

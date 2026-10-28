import { t } from '../i18n/index.svelte.js';
import { doc, asset, act, toast, undo, clamp, round, clipLabel } from './state.svelte.js';
import { drawGraded, filterOf, lookSteps } from './grade.js';
import { lutOf } from './match.js';
import { realThumb } from './media.js';
import { findTake } from './production.svelte.js';
import { takeStore } from './takes.svelte.js';
import { LUM_GAP, WARM_GAP, colorPlanOf, seamPick, seamSourceOf } from './continuity.js';
import { chainState } from './chain.js';
import { chainBusy } from './chain.svelte.js';
import { showShot } from './monitor.svelte.js';
import { currentLooks } from './looks.svelte.js';
import { chainDrifts, lowSeam, percent, seamLook } from './looks.js';

const stats = $state({});
const pending = new Set();

function measure(key, src, steps, lut) {
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
		const d = drawGraded(g, img, 48, 27, steps, lut);
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

function measured(clip, a, src) {
	const steps = lookSteps(clip);
	const filter = filterOf(steps);
	const lut = lutOf(clip);
	const key = `${a?.id}|${src}|${filter}|${lut?.key ?? ''}`;
	return stats[key] ?? measure(key, src, steps, lut);
}

export function colorOf(clip) {
	const a = asset(clip.assetId);
	return measured(clip, a, realThumb(a));
}

const sideColor = (clip, image) => (image ? measured(clip, image, image.src) : colorOf(clip));

function seamSides(i) {
	const pick = seamPick(doc, i, takeStore.list);
	if (!pick) return null;
	return { from: sideColor(doc.clips[i - 1], pick.last), to: sideColor(doc.clips[i], pick.first), source: seamSourceOf(pick) };
}

const takeOf = (clip) => {
	const a = asset(clip.assetId);
	return a?.generated ? findTake(a.resultId) : null;
};

function lookOf(a, b) {
	const looks = currentLooks();
	const found = seamLook(looks, a, b);
	return found ? { seam: found, low: lowSeam(looks, found) } : null;
}

export function seam(i) {
	const a = doc.clips[i - 1];
	const b = doc.clips[i];
	if (!a || !b) return null;
	const sides = seamSides(i);
	const ca = sides.from;
	const cb = sides.to;
	const out = { from: a, to: b, issues: [], pending: !ca || !cb, measured: false, source: sides.source };
	if (ca && cb) {
		const dl = cb.lum - ca.lum;
		const dw = cb.warm - ca.warm;
		if (Math.abs(dl) > LUM_GAP) out.issues.push({ kind: 'lum', text: dl > 0 ? t('lib.continuity.brighter', { shot: clipLabel(b) }) : t('lib.continuity.darker', { shot: clipLabel(b) }), fix: true });
		if (Math.abs(dw) > WARM_GAP) out.issues.push({ kind: 'warm', text: dw > 0 ? t('lib.continuity.warmer', { shot: clipLabel(b) }) : t('lib.continuity.cooler', { shot: clipLabel(b) }), fix: true });
	}
	const look = lookOf(a, b);
	out.measured = !out.pending || look?.seam.status === 'done';
	if (look?.low) out.issues.push({ kind: 'identity', text: t('lib.continuity.identity', { from: clipLabel(a), to: clipLabel(b), score: percent(look.seam.score) }), fix: false, score: look.seam.score });
	const chain = chainState(doc, i);
	if (chain?.state === 'stale') out.issues.push({ kind: 'chain_stale', text: t('lib.chain.stale', { shot: clipLabel(b), previous: clipLabel(a) }), fix: false });
	if (chain?.state === 'offer' && !chainBusy(b.id)) out.issues.push({ kind: 'chain_offer', text: t('lib.chain.offer', { shot: clipLabel(b), previous: clipLabel(a) }), fix: false });
	const drift = chain ? chainDrifts(currentLooks(), a, b)[0] : null;
	if (drift) out.issues.push({ kind: 'chain_drift', text: t('lib.chain.drift', { shot: clipLabel(b), previous: clipLabel(a), name: drift.label, score: percent(drift.score) }), fix: false, score: drift.score });
	return out;
}

export function seams() {
	return doc.clips
		.slice(1)
		.map((_, k) => seam(k + 1))
		.filter(Boolean);
}

function seamSource(shotId) {
	const i = doc.clips.findIndex((c) => c.id === shotId);
	return seamSourceOf(i > 0 ? seamPick(doc, i, takeStore.list) : null);
}

export function seamTip(shotId) {
	const source = seamSource(shotId);
	if (source === 'frames') return t('assistant.review.measuredFramesTip');
	if (source === 'last') return t('assistant.review.measuredLastTip');
	if (source === 'first') return t('assistant.review.measuredFirstTip');
	return t('assistant.review.measuredThumbsTip');
}

function correct(clip, from, to) {
	clip.exposure = round(clamp(clip.exposure + (from.lum - to.lum) * 5, -2, 2), 0.05);
	clip.temperature = Math.round(clamp(clip.temperature + (from.warm - to.warm) * 320, -100, 100));
	clip.preset = 'Raccord';
}

export function matchToPrevious(clip) {
	const i = doc.clips.indexOf(clip);
	const prev = doc.clips[i - 1];
	const sides = i > 0 ? seamSides(i) : null;
	const ca = sides?.from;
	const cb = sides?.to;
	if (!ca || !cb) return toast(t('lib.continuity.pending'), 'warning');
	act(() => correct(clip, ca, cb));
	showShot(clip);
	toast(t('lib.continuity.matched', { shot: clipLabel(clip), previous: clipLabel(prev) }), 'success');
}

export function colorPlan() {
	const pairs = doc.clips.slice(1).map((_, k) => seamSides(k + 1));
	return colorPlanOf(pairs).map((step) => ({ ...step, clip: doc.clips[step.index + 1] }));
}

export const colorIssues = () => seams().filter((s) => s.issues.some((x) => x.fix)).length;

export function matchAll() {
	const plan = colorPlan();
	if (!plan.length) return toast(t('lib.continuity.pending'), 'warning');
	act(() => {
		for (const step of plan) correct(step.clip, step.from, step.to);
	});
	showShot(plan[0].clip);
	toast(t('lib.continuity.matchedAll', { count: plan.length }), 'success', { label: t('shell.toast.undo'), run: undo });
}

export function identityTakes(clip) {
	const i = doc.clips.indexOf(clip);
	const a = i > 0 ? takeOf(doc.clips[i - 1]) : null;
	const b = takeOf(clip);
	return a && b ? [a.id, b.id] : null;
}

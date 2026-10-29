import { t, formatNumber } from '../i18n/index.svelte.js';
import { doc, asset, act, toast, undo, clipLabel, secs } from './state.svelte.js';
import { takeStore } from './takes.svelte.js';
import { realThumb } from './media.js';
import { videoFrame } from './sources.svelte.js';
import { frameStem, seamPick, takeStems } from './continuity.js';
import { roleKind } from './seam.js';
import { DEFAULT_STRENGTH, gapOf, labStats, movedStats, transferOf } from './match.js';
import { showShot } from './monitor.svelte.js';
import { CONTINUATION, shotVideoTracks } from './reception.js';
import { trackItemsOf } from './vrefs.js';
import { vrefLabel } from './vreftracks.js';
import { sourceSeconds } from './cadence.js';

const SAMPLE = 128;
const TIMEOUT = 20000;
const SEEK_FLOOR = 0.001;
const LAST_FRAME = 0.04;
const TAKE_POINTS = [0.15, 0.5, 0.85];
const EDGE = 1e-6;

export const matchState = $state({ busy: null });

export const anchorKey = (anchor) => (anchor ? `${anchor.kind}:${anchor.id}` : '');

const imageOf = (id) => {
	const a = id ? asset(id) : null;
	return a?.kind === 'image' && a.src ? a : null;
};

function frameName(frame) {
	const kind = roleKind(frame.role);
	if (kind === 'first') return t('inspector.match.anchorFirst');
	if (kind === 'last') return t('inspector.match.anchorLast');
	return t('inspector.match.anchorFrame', { role: frame.role || t('inspector.match.keyframe'), time: secs(frame.time) });
}

function previousAnchor(clip, index) {
	const prev = doc.clips[index - 1];
	const media = prev ? asset(prev.assetId) : null;
	if (!prev || !media || media.kind === 'audio' || !media.src) return null;
	const image = seamPick(doc, index, takeStore.list)?.last ?? null;
	const at = (prev.srcIn ?? 0) + Math.max(0, sourceSeconds(prev) - LAST_FRAME);
	return { kind: 'previous', id: prev.id, label: t('inspector.match.anchorPrevious', { shot: clipLabel(prev) }), image, media: image ? null : media, at };
}

export function suiteAnchors(clip) {
	if (!clip) return [];
	return shotVideoTracks(doc, clip, clip.dur)
		.filter((x) => x.status === 'ready' && x.track.role === CONTINUATION)
		.flatMap((x) => {
			const end = x.window[1];
			const item = trackItemsOf(doc, x.track.id).find((i) => i.start < end - EDGE && i.start + i.dur > end - EDGE);
			const media = item ? asset(item.assetId) : null;
			if (!media?.src || media.kind !== 'video') return [];
			const at = (item.srcIn ?? 0) + Math.max(0, end - item.start - LAST_FRAME);
			return [{ kind: 'vref', id: x.track.id, slot: x.slot, label: t('inspector.match.anchorVref', { label: vrefLabel(x.slot) }), image: null, media, at }];
		});
}

export function anchorsOf(clip) {
	const index = clip ? doc.clips.indexOf(clip) : -1;
	if (index < 0) return [];
	const own = takeStems(doc, clip, takeStore.list);
	const previous = index > 0 ? doc.clips[index - 1] : null;
	const before = previous ? takeStems(doc, previous, takeStore.list) : new Set();
	const list = [];
	for (const frame of doc.frames ?? []) {
		const image = frame.shotId === clip.id ? imageOf(frame.assetId) : null;
		const stem = image ? frameStem(image.name) : null;
		if (!image || own.has(stem)) continue;
		const carried = before.has(stem) || (previous !== null && image.frameOf?.shotId === previous.id);
		list.push({ kind: 'keyframe', id: frame.id, label: carried ? t('inspector.match.carried', { name: frameName(frame) }) : frameName(frame), image, first: roleKind(frame.role) === 'first', carried });
	}
	for (const reference of doc.references ?? []) {
		const image = imageOf(reference.assetId);
		const shot = reference.scope?.type === 'shot';
		if (!image || (shot && reference.scope.shotId !== clip.id)) continue;
		list.push({ kind: 'reference', id: reference.id, label: t('inspector.match.anchorReference', { name: reference.name || image.name }), image, own: shot });
	}
	list.push(...suiteAnchors(clip));
	const last = previous ? previousAnchor(clip, index) : null;
	if (last) list.push(last);
	return list;
}

function rank(anchor) {
	if (anchor.kind === 'keyframe' && !anchor.carried) return anchor.first ? 0 : 1;
	if (anchor.kind === 'vref') return 0.5;
	if (anchor.kind === 'reference' && anchor.own) return 2;
	if (anchor.kind === 'previous') return 3;
	if (anchor.kind === 'keyframe') return 4;
	return 5;
}

export function defaultAnchor(anchors) {
	return anchors.reduce((best, anchor) => (best && rank(best) <= rank(anchor) ? best : anchor), null);
}

export function storedAnchor(clip, anchors) {
	const match = clip?.match;
	return match ? (anchors.find((a) => a.kind === match.anchor && a.id === match.anchorId) ?? null) : null;
}

export function anchorThumb(anchor) {
	if (!anchor) return null;
	if (anchor.image) return anchor.image.src;
	return videoFrame(anchor.media, anchor.at) ?? realThumb(anchor.media);
}

function timed(start, fallback) {
	return new Promise((resolve) => {
		let done = false;
		const finish = (value) => {
			if (done) return;
			done = true;
			clearTimeout(timer);
			resolve(value);
		};
		const timer = setTimeout(() => finish(fallback), TIMEOUT);
		start(finish);
	});
}

const fit = (w, h) => (w >= h ? [SAMPLE, Math.max(1, Math.round((SAMPLE * h) / w))] : [Math.max(1, Math.round((SAMPLE * w) / h)), SAMPLE]);

function grab(source, w, h) {
	if (!w || !h) return null;
	const canvas = document.createElement('canvas');
	[canvas.width, canvas.height] = fit(w, h);
	const g = canvas.getContext('2d', { willReadFrequently: true });
	if (!g) return null;
	g.drawImage(source, 0, 0, canvas.width, canvas.height);
	return g.getImageData(0, 0, canvas.width, canvas.height).data;
}

function imagePixels(src) {
	return timed((finish) => {
		const img = new Image();
		img.decoding = 'async';
		img.onload = () => {
			try {
				finish([grab(img, img.naturalWidth, img.naturalHeight)].filter(Boolean));
			} catch {
				finish([]);
			}
		};
		img.onerror = () => finish([]);
		img.src = src;
	}, []);
}

function videoPixels(src, times) {
	return timed((finish) => {
		const video = document.createElement('video');
		const found = [];
		let step = 0;
		video.muted = true;
		video.playsInline = true;
		video.preload = 'auto';
		const done = () => {
			video.removeAttribute('src');
			video.load();
			finish(found);
		};
		video.onloadedmetadata = () => (video.currentTime = Math.max(SEEK_FLOOR, times[0]));
		video.onseeked = () => {
			try {
				const data = grab(video, video.videoWidth, video.videoHeight);
				if (data) found.push(data);
			} catch {
				return done();
			}
			step += 1;
			if (step >= times.length) return done();
			video.currentTime = Math.max(SEEK_FLOOR, times[step]);
		};
		video.onerror = done;
		video.src = src;
	}, []);
}

export function takeTimes(clip, media) {
	const start = clip.srcIn ?? 0;
	const end = typeof media?.srcDur === 'number' ? Math.max(0, media.srcDur - LAST_FRAME) : Infinity;
	return TAKE_POINTS.map((p) => +Math.min(start + sourceSeconds(clip) * p, end).toFixed(3));
}

function takePixels(clip) {
	const media = asset(clip.assetId);
	if (!media?.src || media.kind === 'audio') return Promise.resolve([]);
	return media.kind === 'image' ? imagePixels(media.src) : videoPixels(media.src, takeTimes(clip, media));
}

function anchorPixels(anchor) {
	if (anchor.image) return imagePixels(anchor.image.src);
	return anchor.media.kind === 'image' ? imagePixels(anchor.media.src) : videoPixels(anchor.media.src, [anchor.at]);
}

const deltaText = (value) => formatNumber(value, { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export function matchGaps(match) {
	const moves = transferOf(match);
	const before = gapOf(match?.source, match?.target);
	const after = moves ? gapOf(movedStats(match.source, moves), match.target) : before;
	return before ? { before, after } : null;
}

export async function autoMatch(clip, anchor) {
	if (!clip || matchState.busy) return;
	const chosen = anchor ?? defaultAnchor(anchorsOf(clip));
	if (!chosen) return toast(t('inspector.match.noAnchor'), 'warning');
	const assetId = clip.assetId;
	matchState.busy = clip.id;
	try {
		const [target, source] = await Promise.all([anchorPixels(chosen), takePixels(clip)]).then((sets) => sets.map(labStats));
		const live = doc.clips.find((c) => c.id === clip.id);
		if (!live || live.assetId !== assetId) return;
		if (!target || !source) return toast(t('inspector.match.failed'), 'error');
		const strength = live.match?.strength ?? DEFAULT_STRENGTH;
		act(() => (live.match = { anchor: chosen.kind, anchorId: chosen.id, assetId, strength, source, target }));
		showShot(live);
		const gaps = matchGaps(live.match);
		toast(t('inspector.match.done', { shot: clipLabel(live), before: deltaText(gaps.before.delta), after: deltaText(gaps.after.delta) }), 'success', { label: t('shell.toast.undo'), run: undo });
	} finally {
		matchState.busy = null;
	}
}

export function matchToSuite(clip, trackId) {
	const anchor = suiteAnchors(clip).find((a) => a.id === trackId);
	if (!anchor) return toast(t('inspector.match.noAnchor'), 'warning');
	return autoMatch(clip, anchor);
}

export function clearMatch(clip) {
	if (!clip?.match) return;
	act(() => delete clip.match);
	showShot(clip);
}

export function setDeflicker(clip, on) {
	act(() => {
		if (on) clip.deflicker = true;
		else delete clip.deflicker;
	});
}

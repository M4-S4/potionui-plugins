import { asset } from './state.svelte.js';
import { videoFrame, videoThumb } from './sources.svelte.js';
import { findTake } from './production.svelte.js';

export function realThumb(a) {
	if (!a?.src) return null;
	if (a.kind === 'image') return a.src;
	if (a.kind === 'video') return videoThumb(a);
	return null;
}

export function takeThumb(take) {
	if (!take) return null;
	if (take.thumbUrl) return take.thumbUrl;
	const own = asset(`gen-${take.id}`);
	if (own?.src) return realThumb(own);
	return take.url ? videoThumb({ src: take.url, origin: null, srcDur: take.durationS }) : null;
}

export function clipThumb(c) {
	const a = asset(c?.assetId);
	if (!a || a.kind === 'audio') return null;
	return realThumb(a);
}

export function shotFrame(c) {
	const a = asset(c?.assetId);
	if (!a || a.kind === 'audio') return null;
	return videoFrame(a, c.srcIn ?? 0) ?? assetThumb(a);
}

export function assetThumb(a) {
	if (!a) return null;
	if (a.src) return realThumb(a);
	if (!a.generated || !a.resultId) return null;
	return takeThumb(findTake(a.resultId));
}

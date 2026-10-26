import { framesOf } from './seam.js';

const FRAME_NAME = /^(.+)-frame-(?:last|-?\d[\d.e+-]*s)\.png$/i;

export const LUM_GAP = 0.12;
export const WARM_GAP = 0.1;

export const colorsApart = (from, to) => Math.abs(to.lum - from.lum) > LUM_GAP || Math.abs(to.warm - from.warm) > WARM_GAP;

export function colorPlanOf(pairs) {
	const plan = [];
	let carry = null;
	pairs.forEach((pair, index) => {
		if (!pair?.from || !pair?.to) {
			carry = null;
			return;
		}
		const from = carry ? { lum: pair.from.lum + carry.lum, warm: pair.from.warm + carry.warm } : pair.from;
		if (!colorsApart(from, pair.to)) {
			carry = null;
			return;
		}
		plan.push({ index, from, to: pair.to });
		carry = { lum: from.lum - pair.to.lum, warm: from.warm - pair.to.warm };
	});
	return plan;
}

function decoded(value) {
	try {
		return decodeURIComponent(value);
	} catch {
		return value;
	}
}

export function fileStem(url) {
	const name = decoded(
		String(url ?? '')
			.split(/[?#]/)[0]
			.split('/')
			.filter(Boolean)
			.pop() ?? ''
	);
	const dot = name.lastIndexOf('.');
	return dot > 0 ? name.slice(0, dot) : name;
}

export function frameStem(name) {
	return String(name ?? '').match(FRAME_NAME)?.[1] ?? null;
}

export function takeStems(doc, shot, takes = []) {
	const own = doc.assets?.find((a) => a.id === shot.assetId);
	const urls = takes.filter((take) => take.shotId === shot.id).map((take) => take.url);
	if (own?.kind === 'video' && (own.generated || own.origin?.kind === 'history')) urls.push(own.src);
	return new Set(urls.map(fileStem).filter(Boolean));
}

function seamAssets(doc, shotId, kind) {
	return framesOf(doc, shotId, kind)
		.map((f) => (f.assetId ? doc.assets?.find((a) => a.id === f.assetId) : null))
		.filter((a) => a?.kind === 'image' && a.src);
}

const takenFrom = (image, stems) => stems.has(frameStem(image.name));
const sameImage = (image, others) => others.some((other) => other.id === image.id || other.src === image.src);

export function seamPick(doc, index, takes = []) {
	const from = doc.clips[index - 1];
	const to = doc.clips[index];
	if (!from || !to) return null;
	const fromStems = takeStems(doc, from, takes);
	const toStems = takeStems(doc, to, takes);
	const previousLast = seamAssets(doc, from.id, 'last');
	const last = previousLast.find((image) => takenFrom(image, fromStems)) ?? null;
	const first = seamAssets(doc, to.id, 'first').find((image) => !sameImage(image, previousLast) && !takenFrom(image, fromStems) && takenFrom(image, toStems)) ?? null;
	return { last, first };
}

export function seamSourceOf(pick) {
	if (pick?.last && pick?.first) return 'frames';
	if (pick?.last) return 'last';
	if (pick?.first) return 'first';
	return 'thumbs';
}

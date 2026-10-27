import table from './formatstable.js';

export const FORMATS = table.formats.map((item) => item.id);
export const FORMAT_GROUPS = Object.fromEntries(table.formats.map((item) => [item.id, item.group]));
export const DEFAULT_FORMAT = table.defaultFormat;
export const CUSTOM = table.custom;
export const RESOLUTIONS = { ...table.resolutions };
export const RESOLUTION_NAMES = Object.keys(table.resolutions);
export const DEFAULT_RESOLUTION = table.defaultResolution;
export const BOX = table.box[0] / table.box[1];
export const SOCIAL_FORMATS = [...table.social.formats];
export const SOCIAL_DEFAULT = table.social.default;
export const FRAMINGS = [...table.framing.modes];
export const DEFAULT_FRAMING = table.framing.default;
export const EXACT_LOSS = table.framing.exact;
export const CROP_LOSS = table.framing.crop;
export const SIZES = table.sizes;
export const ENGINES = table.engines;
export const AUTO = 'auto';
export const CROP = 'crop';
export const BARS = 'bars';
export const EXACT = 'exact';
export const DRAFT = 'draft';
export const FINAL = 'final';
export const QUALITIES = [DRAFT, FINAL];

const SCALE = 1e9;
const FORMAT = new RegExp(`^([0-9]+(?:\\.[0-9]{1,${CUSTOM.decimals}})?):([0-9]+(?:\\.[0-9]{1,${CUSTOM.decimals}})?)$`);
const SIZE = /^\s*([0-9]+)\s*[x×]\s*([0-9]+)\s*$/;
const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const key = (value) => Math.floor(value * SCALE + 0.5);

export const halfUp = (value) => Math.floor(value + 0.5);
export const even = (value) => Math.max(2, 2 * halfUp(value / 2));

export function ratioOf(value) {
	const text = typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value)) ? String(value).trim() : '';
	for (const separator of [':', '/', 'x']) {
		const parts = text.split(separator);
		if (parts.length !== 2) continue;
		if (!parts.every((part) => /^\s*[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?\s*$/.test(part))) return null;
		const width = Number(parts[0]);
		const height = Number(parts[1]);
		return Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0 ? width / height : null;
	}
	return null;
}

export function formatValue(value) {
	const text = typeof value === 'string' ? value.trim() : '';
	if (FORMATS.includes(text)) return text;
	const match = FORMAT.exec(text);
	if (match) {
		const width = Number(match[1]);
		const height = Number(match[2]);
		if (width > 0 && height > 0 && width / height >= CUSTOM.minRatio && width / height <= CUSTOM.maxRatio) return text;
	}
	return DEFAULT_FORMAT;
}

export const resolutionValue = (value) => (typeof value === 'string' && Object.hasOwn(RESOLUTIONS, value) ? value : DEFAULT_RESOLUTION);

export const framingOf = (doc) => (FRAMINGS.includes(doc?.framing) ? doc.framing : DEFAULT_FRAMING);

export function parseSize(value) {
	const match = typeof value === 'string' ? SIZE.exec(value) : null;
	if (!match) return null;
	const width = Number(match[1]);
	const height = Number(match[2]);
	return width > 0 && height > 0 ? [width, height] : null;
}

export const sizeText = (size) => `${size[0]}x${size[1]}`;

const valueOf = (option) => (isObject(option) ? option.value : option);
const sizesOf = (options) => (Array.isArray(options) ? options : []).map((option) => parseSize(valueOf(option))).filter(Boolean);
const bounded = (size) => size !== null && size.every((side) => side >= SIZES.min && side <= SIZES.max);

export function sizesValue(value) {
	const kept = {};
	if (!isObject(value)) return kept;
	for (const [presetId, chosen] of Object.entries(value)) {
		if (!presetId || !isObject(chosen)) continue;
		const entry = {};
		for (const quality of QUALITIES) {
			const size = parseSize(chosen[quality]);
			if (size !== null && bounded(size)) entry[quality] = sizeText(size);
		}
		if (Object.keys(entry).length) kept[presetId] = entry;
	}
	return kept;
}

export function chosenSize(doc, presetId, quality) {
	const sizes = isObject(doc?.engine) ? sizesValue(doc.engine.sizes) : {};
	return sizes[presetId ?? '']?.[quality] ?? null;
}

export function migrateFormats(doc) {
	if (!isObject(doc)) return doc;
	const next = { ...doc };
	if ('aspect' in next) next.aspect = formatValue(next.aspect);
	if ('resolution' in next) next.resolution = resolutionValue(next.resolution);
	if ('framing' in next && !FRAMINGS.includes(next.framing)) delete next.framing;
	if (isObject(next.engine) && 'sizes' in next.engine) {
		const { sizes, ...rest } = next.engine;
		const kept = sizesValue(sizes);
		next.engine = Object.keys(kept).length ? { ...rest, sizes: kept } : rest;
	}
	return next;
}

export const engineOf = (presetId) => Object.values(ENGINES).find((engine) => engine.presets.includes(presetId)) ?? {};
export const gridOf = (presetId) => Number(engineOf(presetId).grid || SIZES.grid);
export const snap = (value, multiple) => Math.max(1, Math.ceil(value / multiple - 0.5)) * multiple;
export const snapSize = (size, multiple) => [snap(size[0], multiple), snap(size[1], multiple)];
const same = (a, b) => a[0] === b[0] && a[1] === b[1];

export function sizeProblem(size, presetId) {
	if (!bounded(size)) return 'bounds';
	const engine = engineOf(presetId);
	const ratio = size[0] / size[1];
	if ('minRatio' in engine && !(ratio >= engine.minRatio && ratio <= engine.maxRatio)) return 'ratio';
	if ('maxPixels' in engine && size[0] * size[1] > engine.maxPixels) return 'area';
	return null;
}

const logRatio = (size) => Math.log(size[0] / size[1]);
const area = (size) => size[0] * size[1];

export function families(sizes) {
	const unique = [];
	for (const size of sizes) if (!unique.some((other) => same(other, size))) unique.push(size);
	const found = [];
	for (const size of [...unique].sort((a, b) => area(b) - area(a))) {
		const family = found.find((f) => key(Math.abs(logRatio(size) - logRatio(f[0]))) <= key(SIZES.tolerance));
		if (family) family.push(size);
		else found.push([size]);
	}
	return found;
}

export function workingFamily(options, ratio, presetId = null) {
	const sizes = sizesOf(options).map((size) => snapSize(size, gridOf(presetId)));
	const found = families(sizes);
	if (!found.length) return [];
	const top = Math.max(...sizes.map(area));
	const eligible = found.filter((family) => area(family[0]) >= SIZES.finalShare * top && Math.min(...family.map(area)) <= SIZES.draftMax);
	const pool = eligible.length ? eligible : found;
	const target = Math.log(ratio);
	return pool.reduce((best, family) => (key(Math.abs(logRatio(family[0]) - target)) < key(Math.abs(logRatio(best[0]) - target)) ? family : best));
}

const oriented = (size, landscape) => (size[0] >= size[1] === landscape ? size : [size[1], size[0]]);

export function draftSize(options, setting, ratio, presetId = null) {
	const wanted = parseSize(setting);
	if (wanted === null) return null;
	const family = workingFamily(options, ratio, presetId);
	if (!family.length) return sizeText(snapSize(oriented(wanted, ratio >= 1), gridOf(presetId)));
	const turned = snapSize(oriented(wanted, family[0][0] >= family[0][1]), gridOf(presetId));
	if (family.some((size) => same(size, turned))) return sizeText(turned);
	const target = area(turned);
	return sizeText(
		family.reduce((best, size) => {
			const d = Math.abs(area(size) - target);
			const b = Math.abs(area(best) - target);
			return d < b || (d === b && area(size) < area(best)) ? size : best;
		})
	);
}

export function finalSize(options, ratio, presetId = null) {
	const family = workingFamily(options, ratio, presetId);
	return family.length ? sizeText(family[0]) : null;
}

export function pickSize(options, ratio, quality, setting, chosen = null, presetId = null) {
	const automatic = () => (quality === FINAL ? finalSize(options, ratio, presetId) : draftSize(options, setting, ratio, presetId));
	const size = parseSize(chosen);
	if (size !== null) {
		const snapped = snapSize(size, gridOf(presetId));
		const problem = sizeProblem(snapped, presetId);
		if (problem === null) return { size: sizeText(snapped), chosen, refused: null, problem: null };
		return { size: automatic(), chosen: null, refused: chosen, problem };
	}
	return { size: automatic(), chosen: null, refused: null, problem: null };
}

export const loss = (takeRatio, frameRatio) => 1 - Math.min(takeRatio, frameRatio) / Math.max(takeRatio, frameRatio);

export function fit(takeRatio, frameRatio, framing = DEFAULT_FRAMING) {
	const lost = key(loss(takeRatio, frameRatio));
	if (lost <= key(EXACT_LOSS)) return EXACT;
	if (framing === CROP || framing === BARS) return framing;
	return lost <= key(CROP_LOSS) ? CROP : BARS;
}

export function deliverySize(ratio, resolution) {
	const base = typeof resolution === 'string' && Object.hasOwn(RESOLUTIONS, resolution) ? RESOLUTIONS[resolution] : RESOLUTIONS[DEFAULT_RESOLUTION];
	const long = base * BOX;
	let width;
	let height;
	if (ratio >= 1) [width, height] = ratio >= BOX ? [long, long / ratio] : [base * ratio, base];
	else [width, height] = 1 / ratio >= BOX ? [long * ratio, long] : [base, base / ratio];
	return [even(width), even(height)];
}

export function closestFormat(values, ratio) {
	const found = (Array.isArray(values) ? values : []).map((value) => [String(value), ratioOf(value)]).filter(([, value]) => value !== null);
	if (!found.length) return null;
	const distance = (item) => key(Math.abs(Math.log(item[1]) - Math.log(ratio)));
	return found.reduce((best, item) => (distance(item) < distance(best) ? item : best))[0];
}

export function ratioText(ratio) {
	const known = closestFormat(FORMATS, ratio);
	if (known !== null && fit(ratioOf(known) ?? ratio, ratio) === EXACT) return known;
	return `${ratio.toFixed(2)}:1`;
}

export function timeScale(measured, wanted) {
	const old = parseSize(measured);
	const next = parseSize(wanted);
	if (old === null || next === null) return null;
	return (area(next) / area(old)) ** SIZES.timeExponent;
}

export function nearestMeasured(measured, wanted) {
	const target = parseSize(wanted);
	const sizes = (Array.isArray(measured) ? measured : []).map((text) => [String(text), parseSize(String(text))]).filter(([, size]) => size !== null);
	if (target === null || !sizes.length) return null;
	const distance = (item) => key(Math.abs(Math.log(area(item[1]) / area(target))));
	return sizes.reduce((best, item) => {
		const d = distance(item);
		const b = distance(best);
		return d < b || (d === b && area(item[1]) > area(best[1])) ? item : best;
	})[0];
}

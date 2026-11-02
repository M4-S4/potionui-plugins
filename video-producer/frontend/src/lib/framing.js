import { BARS, CUSTOM, EXACT, FORMATS, FORMAT_GROUPS, SIZES, deliverySize, fit, formatValue, framingOf, gridOf, loss, parseSize, pickSize, ratioOf, sizeProblem, sizeText, snapSize, timeScale, workingFamily } from './formats.js';

export const GROUPS = ['cinema', 'screen', 'social'];
export const CUSTOM_GROUP = 'custom';
export const BASE_SIZE = '832x480';
export const TIERS = [
	['high', 750000],
	['mid', 460000],
	['low', 280000],
	['small', 0]
];

const area = (size) => size[0] * size[1];
const same = (a, b) => Boolean(a && b) && a[0] === b[0] && a[1] === b[1];
const NUMBER = new RegExp(`^[0-9]+(?:\\.[0-9]{1,${CUSTOM.decimals}})?$`);
const WHOLE = /^[0-9]+$/;

export function sizeOf(item) {
	if (!item) return null;
	const width = Number(item.width);
	const height = Number(item.height);
	if (width > 0 && height > 0) return [width, height];
	return parseSize(item.resolution);
}

export const filmRatio = (doc) => ratioOf(formatValue(doc?.aspect)) ?? 16 / 9;

export function framed(size, doc) {
	if (!size || !(size[0] > 0 && size[1] > 0)) return null;
	const ratio = size[0] / size[1];
	const film = filmRatio(doc);
	return { mode: fit(ratio, film, framingOf(doc)), loss: loss(ratio, film), ratio };
}

export const fitClass = (mode) => (mode === BARS ? 'object-contain' : 'object-cover');

export const percent = (share) => Math.round(share * 100);

export function glyph(ratio, max = 14, box = 24) {
	const [width, height] = ratio >= 1 ? [max, max / ratio] : [max * ratio, max];
	return { x: (box - width) / 2, y: (box - height) / 2, width, height };
}

export function formatSections(doc) {
	const current = formatValue(doc?.aspect);
	const row = (id) => ({ value: id, ratio: ratioOf(id), size: deliverySize(ratioOf(id), doc?.resolution) });
	const sections = GROUPS.map((group) => ({ id: group, rows: FORMATS.filter((id) => FORMAT_GROUPS[id] === group).map(row) }));
	if (!FORMATS.includes(current)) sections.push({ id: CUSTOM_GROUP, rows: [row(current)] });
	return sections;
}

export function customFormat(width, height) {
	const parts = [String(width ?? '').trim(), String(height ?? '').trim()];
	if (!parts.every((part) => NUMBER.test(part)) || parts.some((part) => !(Number(part) > 0))) return { ok: false, error: 'invalid' };
	const value = `${parts[0]}:${parts[1]}`;
	return formatValue(value) === value ? { ok: true, value } : { ok: false, error: 'range' };
}

export function tierOf(size) {
	return TIERS.find(([, min]) => area(size) >= min)[0];
}

export const costOf = (size) => timeScale(BASE_SIZE, sizeText(size));

export function measuredFor(me, presetId, backendId) {
	const sizes = me?.measured?.[presetId]?.[backendId];
	return Array.isArray(sizes) ? sizes : [];
}

export function sizeSections({ preset, ratio, quality, setting = null, chosen = null, measured = null, framing = null }) {
	const options = (preset?.resolutions ?? []).map((option) => option.value);
	const presetId = preset?.id ?? null;
	const auto = pickSize(options, ratio, quality, setting, null, presetId).size;
	const family = workingFamily(options, ratio, presetId);
	const sizes = [...family];
	const picked = parseSize(chosen);
	const own = picked ? snapSize(picked, gridOf(presetId)) : null;
	if (own && !sizes.some((size) => same(size, own))) sizes.push(own);
	const rows = sizes
		.sort((a, b) => area(b) - area(a))
		.map((size) => {
			const shown = fit(size[0] / size[1], ratio, framing ?? undefined);
			return {
				value: sizeText(size),
				size,
				ratio: size[0] / size[1],
				tier: tierOf(size),
				cost: costOf(size),
				measured: measured === null ? null : measured.includes(sizeText(size)),
				fit: shown,
				loss: loss(size[0] / size[1], ratio),
				own: !family.some((other) => same(other, size))
			};
		});
	const sections = TIERS.map(([tier]) => ({ id: tier, rows: rows.filter((row) => row.tier === tier) })).filter((section) => section.rows.length);
	return { auto, rows, sections };
}

export function customSize(width, height, presetId) {
	const parts = [String(width ?? '').trim(), String(height ?? '').trim()];
	if (!parts.every((part) => WHOLE.test(part))) return { ok: false, error: 'invalid' };
	const size = parts.map(Number);
	if (!size.every((side) => side >= SIZES.min && side <= SIZES.max)) return { ok: false, error: 'bounds' };
	const sent = snapSize(size, gridOf(presetId));
	const problem = sizeProblem(sent, presetId);
	if (problem !== null) return { ok: false, error: problem, value: sizeText(sent) };
	return { ok: true, value: sizeText(sent), snapped: !same(sent, size) };
}

export function engineSize(engine, presetId, quality, value) {
	const sizes = { ...(engine.sizes ?? {}) };
	const entry = { ...(sizes[presetId] ?? {}) };
	if (value) entry[quality] = value;
	else delete entry[quality];
	if (Object.keys(entry).length) sizes[presetId] = entry;
	else delete sizes[presetId];
	if (Object.keys(sizes).length) engine.sizes = sizes;
	else delete engine.sizes;
}

export function sameSizes(a, b) {
	const flat = (sizes) => Object.entries(sizes ?? {}).flatMap(([preset, entry]) => Object.entries(entry ?? {}).map(([quality, size]) => `${preset}|${quality}|${size}`)).sort();
	return flat(a).join('\n') === flat(b).join('\n');
}

export function formatChange(clips, takeOf, doc) {
	const counts = { crop: 0, bars: 0 };
	for (const clip of clips ?? []) {
		const shown = clip?.take ? framed(sizeOf(takeOf(clip.take)), doc) : null;
		if (shown && shown.mode !== EXACT) counts[shown.mode] += 1;
	}
	return counts;
}

export function changedRatio(take, size) {
	const made = sizeOf(take);
	const now = parseSize(size);
	return Boolean(made && now) && fit(made[0] / made[1], now[0] / now[1]) !== EXACT;
}

export function exportFrame(doc, format, resolution, ratio) {
	const wanted = format === 'social' ? ratioOf(ratio) : filmRatio(doc);
	return deliverySize(wanted ?? filmRatio(doc), resolution);
}

export function largestTake(clips, takeOf) {
	let found = null;
	for (const clip of clips ?? []) {
		const size = clip?.take ? sizeOf(takeOf(clip.take)) : null;
		if (size && (!found || area(size) > area(found))) found = size;
	}
	return found;
}

export function upscaled(take, frame, mode = EXACT) {
	if (!take || !frame) return false;
	const scales = [frame[0] / take[0], frame[1] / take[1]];
	return (mode === BARS ? Math.min(...scales) : Math.max(...scales)) > 1;
}

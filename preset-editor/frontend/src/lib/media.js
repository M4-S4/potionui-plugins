import { MEDIA_EXTENSIONS } from './files.js';

export const MEDIA_ACCEPT = MEDIA_EXTENSIONS.join(',');
export const ROLES = ['cover', 'gallery'];

function text(value) {
	return value === null || value === undefined ? '' : String(value);
}

export function isVideo(path) {
	return /\.(mp4|webm)$/i.test(text(path));
}

export function formatBytes(size) {
	if (!Number.isFinite(size) || size < 0) return '';
	if (size < 1024) return `${size} B`;
	if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
	return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function galleryRows(items) {
	return (Array.isArray(items) ? items : [])
		.filter((item) => item && typeof item === 'object')
		.map((item) => ({ src: text(item.src), caption: text(item.caption), mode: text(item.mode), prompt: text(item.prompt), seed: text(item.seed) }));
}

export function galleryBody(rows) {
	return (Array.isArray(rows) ? rows : []).map((row) => {
		const body = { src: text(row.src) };
		const caption = text(row.caption).trim();
		const mode = text(row.mode).trim();
		const prompt = text(row.prompt).trim();
		const seed = text(row.seed).trim();
		if (caption) body.caption = caption;
		if (prompt) body.prompt = prompt;
		if (/^\d+$/.test(seed)) body.seed = Number(seed);
		if (mode) body.mode = mode;
		return body;
	});
}

export function rowsChanged(rows, items) {
	return JSON.stringify(galleryBody(rows)) !== JSON.stringify(galleryBody(galleryRows(items)));
}

export function moveItem(list, from, to) {
	if (!Array.isArray(list) || from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
	const copy = [...list];
	const [item] = copy.splice(from, 1);
	copy.splice(to, 0, item);
	return copy;
}

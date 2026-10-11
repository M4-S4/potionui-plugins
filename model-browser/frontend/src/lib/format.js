// Display helpers for the Model Browser page: sizes, counts, speeds, dates, placeholder tints and
// CivitAI thumbnail urls. No Svelte in here, so the logic is unit tested with `node --test`
// (see format.test.js).

const BYTE_UNITS = ['KB', 'MB', 'GB', 'TB', 'PB'];

/** A whole number written without a trailing `.0`: 1.0 -> '1', 1.25 -> '1.3' (one decimal). */
function oneDecimal(value) {
	const text = value.toFixed(1);
	return text.endsWith('.0') ? text.slice(0, -2) : text;
}

/**
 * A size in bytes for people, in binary units with one decimal: 239_600_000 -> '228.5 MB',
 * 1536 -> '1.5 KB', 512 -> '512 B'. Empty string for anything that is not a size.
 *
 * @param {unknown} bytes
 * @returns {string}
 */
export function formatBytes(bytes) {
	if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) return '';
	if (bytes < 1024) return `${Math.round(bytes)} B`;
	let value = bytes;
	let unit = -1;
	while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
		value /= 1024;
		unit += 1;
	}
	// 1023.96 KB rounds to '1024.0 KB': show it as the next unit instead.
	if (Number(value.toFixed(1)) >= 1024 && unit < BYTE_UNITS.length - 1) {
		value /= 1024;
		unit += 1;
	}
	return `${value.toFixed(1)} ${BYTE_UNITS[unit]}`;
}

/**
 * A count in a few characters: 999 -> '999', 1234 -> '1.2k', 457_123 -> '457k',
 * 1_500_000 -> '1.5M', 23_000_000 -> '23M'. Empty string for anything that is not a count.
 *
 * @param {unknown} count
 * @returns {string}
 */
export function formatCount(count) {
	if (typeof count !== 'number' || !Number.isFinite(count) || count < 0) return '';
	const n = Math.round(count);
	if (n < 1000) return String(n);
	if (n < 10_000) return `${oneDecimal(n / 1000)}k`;
	if (n < 999_500) return `${Math.round(n / 1000)}k`;
	if (n < 10_000_000) return `${oneDecimal(n / 1_000_000)}M`;
	if (n < 999_500_000) return `${Math.round(n / 1_000_000)}M`;
	return `${oneDecimal(n / 1_000_000_000)}B`;
}

/**
 * A transfer speed: 4_404_019 -> '4.2 MB/s'. Empty string when unknown or zero.
 *
 * @param {unknown} bytesPerSecond
 * @returns {string}
 */
export function formatSpeed(bytesPerSecond) {
	if (typeof bytesPerSecond !== 'number' || !Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return '';
	return `${formatBytes(bytesPerSecond)}/s`;
}

/**
 * A progress fraction (0 to 1, as the core's downloads report it) as a whole percentage, clamped.
 *
 * @param {unknown} fraction
 * @returns {number | null}  null when unknown.
 */
export function percent(fraction) {
	if (typeof fraction !== 'number' || !Number.isFinite(fraction)) return null;
	return Math.max(0, Math.min(100, Math.floor(fraction * 100)));
}

/**
 * A date for people ('Oct 11, 2026'), or '' when the text is not a date.
 *
 * @param {unknown} value  ISO text or a timestamp.
 * @param {string} [locale]  Defaults to the browser's.
 * @returns {string}
 */
export function formatDate(value, locale) {
	if (value === null || value === undefined || value === '') return '';
	const date = new Date(/** @type {any} */ (value));
	if (Number.isNaN(date.getTime())) return '';
	try {
		return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' });
	} catch {
		return date.toISOString().slice(0, 10);
	}
}

/** `n word` or `n words`. */
export function plural(count, word, many = `${word}s`) {
	return `${count} ${count === 1 ? word : many}`;
}

function hash(seed) {
	let h = 5381;
	for (let i = 0; i < seed.length; i += 1) h = (h * 33) ^ seed.charCodeAt(i);
	return h >>> 0;
}

const VIZ_SLOTS = 8;
const ANGLES = [135, 45, -45, -135];

/**
 * Inline `background` for a tile without an image: a faint tint drawn from the app's own
 * `--viz-*` palette, the same per name every time (the app's model cards do the same).
 *
 * @param {string} seed
 * @returns {string}
 */
export function placeholderStyle(seed) {
	const h = hash(String(seed ?? ''));
	const slot = (h % VIZ_SLOTS) + 1;
	const angle = ANGLES[Math.floor(h / VIZ_SLOTS) % ANGLES.length];
	return `background: linear-gradient(${angle}deg, rgb(var(--viz-${slot}) / 0.12), transparent 65%), rgb(var(--surface-3));`;
}

const CIVITAI_IMAGE_HOST = 'image.civitai.com';
// The options segment of a CivitAI image url: `original=true`, `width=450`, `width=450,optimized=true`.
const CIVITAI_OPTIONS = /^[a-z]+=[\w.]+(?:,[a-z]+=[\w.]+)*$/i;

/**
 * A smaller rendition of a CivitAI image: its CDN resizes on the fly when the options segment of
 * the url (`/original=true/`) says `width=<n>`. Any other url is returned unchanged, as are
 * CivitAI videos (`kind: 'video'`), whose transcoding options differ.
 *
 * @param {string | null | undefined} url
 * @param {number} width
 * @param {string} [kind]  'image' (default) or 'video'.
 * @returns {string | null}
 */
export function thumbUrl(url, width, kind = 'image') {
	if (typeof url !== 'string' || !url) return null;
	if (kind === 'video' || !(width > 0)) return url;
	let parsed;
	try {
		parsed = new URL(url);
	} catch {
		return url;
	}
	if (parsed.protocol !== 'https:' || parsed.hostname !== CIVITAI_IMAGE_HOST) return url;
	const parts = parsed.pathname.split('/');
	// /<account>/<uuid>/<options>/<name>: the options are the segment before the file name.
	if (parts.length < 5) return url;
	const index = parts.length - 2;
	if (!CIVITAI_OPTIONS.test(parts[index])) return url;
	parts[index] = `width=${Math.round(width)}`;
	parsed.pathname = parts.join('/');
	return parsed.toString();
}

/** First letter upper case: 'lora' -> 'Lora'; used for PotionUI type names. */
export function capitalize(text) {
	if (typeof text !== 'string' || !text) return '';
	return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A PotionUI model type for people: 'text_encoder' -> 'Text encoder', 'lora' -> 'LoRA'. */
export function modelTypeLabel(type) {
	if (typeof type !== 'string' || !type) return '';
	const special = { lora: 'LoRA', vae: 'VAE', llm: 'LLM', vfi: 'VFI', unet: 'UNet', controlnet: 'ControlNet', instantid: 'InstantID', insightface: 'InsightFace' };
	if (special[type]) return special[type];
	return capitalize(type.replace(/_/g, ' '));
}

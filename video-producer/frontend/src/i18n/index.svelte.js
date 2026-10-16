import en from './en.json';
import fr from './fr.json';
import {
	DEFAULT_LOCALE,
	LOCALES,
	detectLocale,
	formatBytes as bytesIn,
	formatDate as dateIn,
	formatDuration as durationIn,
	formatNumber as numberIn,
	formatTimecode,
	hasKey,
	normalizeLocale,
	translate
} from './core.js';

const DICTIONARIES = { en, fr };
const reported = new Set();

let current = $state(DEFAULT_LOCALE);

function reportMissing(key, locale, fellBack) {
	if (process.env.NODE_ENV === 'production') return;
	const id = `${locale}:${key}`;
	if (reported.has(id)) return;
	reported.add(id);
	console.warn(
		fellBack
			? `[video-producer] missing "${key}" in ${locale}.json, using en.json`
			: `[video-producer] unknown translation key "${key}"`
	);
}

export { LOCALES, detectLocale, formatTimecode };

export function getLocale() {
	return current;
}

export function setLocale(value) {
	const next = normalizeLocale(value);
	if (next) current = next;
	return current;
}

export function t(key, params) {
	return translate(DICTIONARIES, current, key, params, reportMissing);
}

export function has(key) {
	return hasKey(DICTIONARIES, current, key);
}

export function formatNumber(value, options) {
	return numberIn(current, value, options);
}

export function formatDate(value, options) {
	return dateIn(current, value, options);
}

export function formatDuration(seconds) {
	return durationIn(current, seconds);
}

export function formatBytes(bytes) {
	return bytesIn(current, bytes);
}

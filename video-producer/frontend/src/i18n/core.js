export const LOCALES = ['en', 'fr'];
export const DEFAULT_LOCALE = 'en';
export const DOMAINS = [
	'shell',
	'commands',
	'lib',
	'panels',
	'storyboard',
	'viewer',
	'timeline',
	'references',
	'inspector',
	'production',
	'mixer',
	'modals',
	'library',
	'starter',
	'project',
	'generation',
	'assistant',
	'exports',
	'keyframes'
];

export function mergeDomains(domains) {
	const merged = {};
	for (const [domain, entries] of Object.entries(domains)) {
		for (const [key, value] of Object.entries(entries ?? {})) merged[`${domain}.${key}`] = value;
	}
	return merged;
}

const PLACEHOLDER = /\{(\w+)\}/g;
const formatters = new Map();

export function normalizeLocale(value) {
	if (typeof value !== 'string') return null;
	const base = value.trim().toLowerCase().split(/[-_]/)[0];
	return LOCALES.includes(base) ? base : null;
}

export function detectLocale(saved, navigatorLanguage) {
	const stored = normalizeLocale(saved);
	if (stored) return stored;
	if (typeof navigatorLanguage === 'string' && navigatorLanguage.toLowerCase().startsWith('fr')) return 'fr';
	return DEFAULT_LOCALE;
}

function cached(kind, locale, options, create) {
	const id = `${kind}|${locale}|${JSON.stringify(options ?? {})}`;
	let formatter = formatters.get(id);
	if (!formatter) {
		formatter = create();
		formatters.set(id, formatter);
	}
	return formatter;
}

function pluralRules(locale) {
	return cached('plural', locale, null, () => new Intl.PluralRules(locale));
}

function lookup(dictionaries, locale, key, count) {
	const dictionary = dictionaries[locale];
	if (!dictionary) return undefined;
	if (typeof count === 'number' && Number.isFinite(count)) {
		const category = pluralRules(locale).select(count);
		const plural = dictionary[`${key}.${category}`] ?? dictionary[`${key}.other`];
		if (typeof plural === 'string') return plural;
	}
	const value = dictionary[key];
	return typeof value === 'string' ? value : undefined;
}

export function hasKey(dictionaries, locale, key) {
	return lookup(dictionaries, locale, key, 0) !== undefined || lookup(dictionaries, DEFAULT_LOCALE, key, 0) !== undefined;
}

function interpolate(template, params, locale) {
	if (!params) return template;
	return template.replace(PLACEHOLDER, (match, name) => {
		if (!(name in params)) return match;
		const value = params[name];
		return typeof value === 'number' ? formatNumber(locale, value) : String(value ?? '');
	});
}

export function translate(dictionaries, locale, key, params, onMissing) {
	const count = params?.count;
	const own = lookup(dictionaries, locale, key, count);
	if (own !== undefined) return interpolate(own, params, locale);
	const fallback = locale === DEFAULT_LOCALE ? undefined : lookup(dictionaries, DEFAULT_LOCALE, key, count);
	onMissing?.(key, locale, fallback !== undefined);
	return fallback === undefined ? key : interpolate(fallback, params, DEFAULT_LOCALE);
}

export function formatNumber(locale, value, options) {
	const number = Number(value);
	if (!Number.isFinite(number)) return '';
	return cached('number', locale, options, () => new Intl.NumberFormat(locale, options)).format(number);
}

export function formatDate(locale, value, options = { dateStyle: 'medium', timeStyle: 'short' }) {
	const date = value instanceof Date ? value : new Date(value);
	if (Number.isNaN(date.getTime())) return '';
	return cached('date', locale, options, () => new Intl.DateTimeFormat(locale, options)).format(date);
}

const RELATIVE_UNITS = [
	['year', 31536000],
	['month', 2592000],
	['week', 604800],
	['day', 86400],
	['hour', 3600],
	['minute', 60],
	['second', 1]
];

export function formatRelative(locale, value, now = Date.now()) {
	const date = value instanceof Date ? value : new Date(value ?? NaN);
	if (Number.isNaN(date.getTime())) return '';
	const diff = Math.min(0, (date.getTime() - now) / 1000);
	const [name, size] = RELATIVE_UNITS.find(([, seconds]) => -diff >= seconds) ?? RELATIVE_UNITS[RELATIVE_UNITS.length - 1];
	return cached('relative', locale, null, () => new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })).format(Math.round(diff / size), name);
}

function unit(locale, value, name, display = 'short') {
	return formatNumber(locale, value, { style: 'unit', unit: name, unitDisplay: display, maximumFractionDigits: 1 });
}

export function formatDuration(locale, seconds) {
	const total = Math.max(0, Math.round(Number(seconds) || 0));
	const hours = Math.floor(total / 3600);
	const minutes = Math.floor((total % 3600) / 60);
	const rest = total % 60;
	const parts = [];
	if (hours) parts.push(unit(locale, hours, 'hour'));
	if (minutes) parts.push(unit(locale, minutes, 'minute'));
	if (rest && !hours) parts.push(unit(locale, rest, 'second'));
	if (!parts.length) parts.push(unit(locale, 0, 'second'));
	return parts.join(' ');
}

export function formatTimecode(seconds, fps = 25) {
	const rate = Number.isFinite(fps) && fps > 0 ? fps : 25;
	const value = Math.max(0, Number(seconds) || 0);
	const whole = Math.floor(value);
	const frames = Math.min(Math.ceil(rate) - 1, Math.floor((value - whole) * rate + 1e-6));
	const pad = (n) => String(n).padStart(2, '0');
	return `${pad(Math.floor(whole / 3600))}:${pad(Math.floor((whole % 3600) / 60))}:${pad(whole % 60)}:${pad(frames)}`;
}

const BYTE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte', 'terabyte'];

export function formatBytes(locale, bytes) {
	const value = Math.max(0, Number(bytes) || 0);
	const index = value < 1 ? 0 : Math.min(Math.floor(Math.log(value) / Math.log(1024)), BYTE_UNITS.length - 1);
	if (index === 0) return unit(locale, Math.round(value), 'byte', 'long');
	return unit(locale, value / 1024 ** index, BYTE_UNITS[index]);
}

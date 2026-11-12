export const KINDS = ['local', 'marketplace', 'plugin'];

export const KIND_LABELS = { local: 'Local', marketplace: 'Marketplace', plugin: 'Plugin' };

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function kindOf(raw) {
	const kind = raw.origin?.kind;
	if (KINDS.includes(kind)) return kind;
	return raw.source === 'custom' ? 'local' : 'marketplace';
}

function mirrorSource(raw) {
	const source = raw.source_preset_id;
	return typeof source === 'string' && source && source !== raw.id ? source : null;
}

export function normalizePreset(raw) {
	if (!isObject(raw) || typeof raw.id !== 'string' || !raw.id) return null;
	const kind = kindOf(raw);
	const mirrorOf = mirrorSource(raw);
	return {
		id: raw.id,
		name: typeof raw.name === 'string' && raw.name ? raw.name : raw.id,
		version: typeof raw.version === 'string' ? raw.version : '',
		kind,
		pluginId: typeof raw.origin?.plugin_id === 'string' ? raw.origin.plugin_id : null,
		path: typeof raw.origin?.path === 'string' ? raw.origin.path : '',
		installed: raw.installed === true,
		engine: typeof raw.engine === 'string' ? raw.engine : '',
		category: typeof raw.category === 'string' ? raw.category : '',
		modes: Array.isArray(raw.modes) ? raw.modes.filter((mode) => typeof mode === 'string') : [],
		tags: Array.isArray(raw.tags) ? raw.tags.filter((tag) => typeof tag === 'string') : [],
		cover: typeof raw.media?.cover === 'string' && raw.media.cover ? raw.media.cover : null,
		mirrorOf,
		editable: kind === 'local' && !mirrorOf
	};
}

export function normalizeCatalog(data) {
	return (Array.isArray(data) ? data : []).map(normalizePreset).filter(Boolean);
}

export function sortPresets(entries) {
	return [...entries].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }) || a.id.localeCompare(b.id));
}

function matchesQuery(entry, query) {
	const needle = query.trim().toLowerCase();
	if (!needle) return true;
	return [entry.id, entry.name, entry.path, entry.engine, ...entry.tags].some((value) => value.toLowerCase().includes(needle));
}

export function filterPresets(entries, { query = '', kind = 'all', installed = 'all' } = {}) {
	return entries.filter(
		(entry) =>
			(kind === 'all' || entry.kind === kind) &&
			(installed === 'all' || (installed === 'installed') === entry.installed) &&
			matchesQuery(entry, query)
	);
}

export function localPresets(entries) {
	return sortPresets(entries.filter((entry) => entry.editable));
}

export function countByKind(entries) {
	const counts = { all: entries.length, local: 0, marketplace: 0, plugin: 0 };
	for (const entry of entries) counts[entry.kind] += 1;
	return counts;
}

export function coverUrl(entry, size = 'thumbnail') {
	if (!entry?.cover) return null;
	const path = entry.cover.split('/').map(encodeURIComponent).join('/');
	return `/api/media/presets/${encodeURIComponent(entry.id)}/${path}?size=${encodeURIComponent(size)}`;
}

export function adminPresetUrl(presetId) {
	return `/admin?tab=presets&id=${encodeURIComponent(presetId)}`;
}

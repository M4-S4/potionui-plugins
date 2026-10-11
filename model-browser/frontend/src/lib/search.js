// The search state of the Model Browser page: what the URL query string holds (so a reload
// restores it), the query of `GET /{source}/search`, the filter chips, and how pages of results
// are merged. No Svelte in here: tested with `node --test` (see search.test.js).
//
// State: { source, q, types: string[], baseModel, sort, period, model }
//   - `sort` / `period` '' mean the source's default (its first option);
//   - `model` is the id of the model whose detail panel is open ('' when none).

/** Results asked per page (the API takes 1 to 50; a page may hold more). */
export const DEFAULT_LIMIT = 24;

/** The query string keys of the page URL. Other keys in the URL are left alone. */
export const URL_KEYS = {
	source: 'source',
	q: 'q',
	type: 'type',
	base: 'base',
	sort: 'sort',
	period: 'period',
	model: 'model'
};

/** Rail icons (names of the app's icon library) for the known sources. */
const SOURCE_ICONS = {
	civitai: 'palette',
	huggingface: 'smile',
	openmodeldb: 'database',
	civarchive: 'library'
};

/**
 * How the UI names things when `GET /sources` does not say (OpenModelDB sends its own):
 * - `types_label` and `base_models_label` name the two groups of the filter popover ("Architecture"
 *   and "Scale"), which filter by `types` and `base_models`;
 * - `base_model_label` names the base model line of a version in the detail panel ("Architecture":
 *   its `base_model` is like "ESRGAN 4x"). It is not `base_models_label`.
 */
export const DEFAULT_TYPES_LABEL = 'Types';
export const DEFAULT_BASE_MODELS_LABEL = 'Base model';
export const DEFAULT_BASE_MODEL_LABEL = 'Base model';

const SHA256 = /^[0-9a-f]{64}$/;

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function text(value) {
	return typeof value === 'string' ? value : '';
}

/** A state with nothing chosen. */
export function emptyState(source = '') {
	return { source, q: '', types: [], baseModel: '', sort: '', period: '', model: '' };
}

/**
 * The sources of `GET /sources` that are on, each with its option lists present and the names it
 * gives things (`types_label`, `base_models_label` for the two filter groups, `base_model_label`
 * for the base model of a version: the defaults when missing or blank).
 *
 * @param {unknown} sources
 * @returns {{ id: string, label: string, types: {value: string, label: string}[], base_models: {value: string, label: string}[],
 *             sorts: {value: string, label: string}[], periods: {value: string, label: string}[], search_help: string,
 *             types_label: string, base_models_label: string, base_model_label: string }[]}
 */
export function enabledSources(sources) {
	if (!Array.isArray(sources)) return [];
	const options = (list) =>
		(Array.isArray(list) ? list : [])
			.filter((option) => isObject(option) && typeof option.value === 'string' && option.value)
			.map((option) => ({ value: option.value, label: text(option.label) || option.value }));
	return sources
		.filter((source) => isObject(source) && typeof source.id === 'string' && source.id && source.enabled !== false)
		.map((source) => ({
			id: source.id,
			label: text(source.label) || source.id,
			types: options(source.types),
			base_models: options(source.base_models),
			sorts: options(source.sorts),
			periods: options(source.periods),
			search_help: text(source.search_help),
			types_label: text(source.types_label).trim() || DEFAULT_TYPES_LABEL,
			base_models_label: text(source.base_models_label).trim() || DEFAULT_BASE_MODELS_LABEL,
			base_model_label: text(source.base_model_label).trim() || DEFAULT_BASE_MODEL_LABEL
		}));
}

/** The rail sections of `LibraryPage` for these sources. */
export function sourceSections(sources) {
	return sources.map((source) => ({ id: source.id, label: source.label, icon: SOURCE_ICONS[source.id] ?? 'globe' }));
}

/** The source's default sort and period: their first option ('' when it has none). */
export function sourceDefaults(info) {
	return { sort: info?.sorts?.[0]?.value ?? '', period: info?.periods?.[0]?.value ?? '' };
}

/**
 * The state written in a query string, unchecked (see `normalizeState`).
 *
 * @param {string | URLSearchParams} search  `location.search`, with or without '?'.
 */
export function decodeState(search) {
	const params = search instanceof URLSearchParams ? search : new URLSearchParams(String(search ?? ''));
	return {
		source: params.get(URL_KEYS.source) ?? '',
		q: params.get(URL_KEYS.q) ?? '',
		types: [...new Set(params.getAll(URL_KEYS.type).filter(Boolean))],
		baseModel: params.get(URL_KEYS.base) ?? '',
		sort: params.get(URL_KEYS.sort) ?? '',
		period: params.get(URL_KEYS.period) ?? '',
		model: params.get(URL_KEYS.model) ?? ''
	};
}

function hasOption(list, value) {
	return Array.isArray(list) && list.some((option) => option.value === value);
}

/**
 * A state the current sources accept: an unknown source becomes the first one, filters the
 * source does not offer are dropped, a sort or period equal to the default becomes ''.
 *
 * @param {ReturnType<typeof emptyState>} state
 * @param {ReturnType<typeof enabledSources>} sources
 */
export function normalizeState(state, sources) {
	const info = sources.find((source) => source.id === state.source) ?? sources[0];
	if (!info) return { ...emptyState(''), q: text(state.q) };
	const defaults = sourceDefaults(info);
	const sort = hasOption(info.sorts, state.sort) && state.sort !== defaults.sort ? state.sort : '';
	const period = hasOption(info.periods, state.period) && state.period !== defaults.period ? state.period : '';
	return {
		source: info.id,
		q: text(state.q),
		types: (state.types ?? []).filter((type, index, all) => hasOption(info.types, type) && all.indexOf(type) === index),
		baseModel: hasOption(info.base_models, state.baseModel) ? state.baseModel : '',
		sort,
		period,
		model: text(state.model)
	};
}

/**
 * The state after picking another source: the text stays, the filters (which belong to a source)
 * and the open model go.
 */
export function switchSource(state, sourceId) {
	return { ...emptyState(sourceId), q: state.q };
}

/**
 * The query string key and value that open the requests drawer: the link of the request
 * notifications (`/plugins/model-browser?tab=requests`, backend notifications.py). The page acts
 * on it once and takes it out of the URL, so a reload does not open the drawer again.
 */
export const REQUESTS_LINK = { key: 'tab', value: 'requests' };

/** Whether a query string (with or without '?', or URLSearchParams) asks for the requests drawer. */
export function wantsRequestsTab(search) {
	const params = search instanceof URLSearchParams ? search : new URLSearchParams(String(search ?? ''));
	return params.getAll(REQUESTS_LINK.key).includes(REQUESTS_LINK.value);
}

/** A query string (no '?') without `tab=requests`; every other key and value kept, in order. */
export function withoutRequestsTab(search) {
	const params = search instanceof URLSearchParams ? search : new URLSearchParams(String(search ?? ''));
	const kept = new URLSearchParams();
	for (const [key, value] of params) {
		if (key !== REQUESTS_LINK.key || value !== REQUESTS_LINK.value) kept.append(key, value);
	}
	return kept.toString();
}

/**
 * The page's query string for a state (no '?'), defaults left out, any key the page does not
 * own kept from `currentSearch` (but never `tab=requests`, which is acted on once).
 *
 * @param {ReturnType<typeof emptyState>} state
 * @param {string} [currentSearch]
 * @returns {string}
 */
export function encodeState(state, currentSearch = '') {
	const params = new URLSearchParams(withoutRequestsTab(currentSearch));
	for (const key of Object.values(URL_KEYS)) params.delete(key);
	if (state.source) params.set(URL_KEYS.source, state.source);
	if (state.q) params.set(URL_KEYS.q, state.q);
	for (const type of state.types ?? []) params.append(URL_KEYS.type, type);
	if (state.baseModel) params.set(URL_KEYS.base, state.baseModel);
	if (state.sort) params.set(URL_KEYS.sort, state.sort);
	if (state.period) params.set(URL_KEYS.period, state.period);
	if (state.model) params.set(URL_KEYS.model, state.model);
	return params.toString();
}

/**
 * The query string of `GET /{source}/search` for a state (no '?'): `types` repeated, the base
 * model as `base_models`, sort and period always explicit (the default when '').
 *
 * @param {ReturnType<typeof emptyState>} state
 * @param {ReturnType<typeof enabledSources>[number] | undefined} info
 * @param {{ cursor?: string | null, limit?: number }} [page]
 * @returns {string}
 */
export function searchRequest(state, info, { cursor = null, limit = DEFAULT_LIMIT } = {}) {
	const params = new URLSearchParams();
	const q = text(state.q).trim();
	if (q) params.set('q', q);
	for (const type of state.types ?? []) params.append('types', type);
	if (state.baseModel) params.append('base_models', state.baseModel);
	const defaults = sourceDefaults(info);
	const sort = state.sort || defaults.sort;
	if (sort) params.set('sort', sort);
	const period = info?.periods?.length ? state.period || defaults.period : '';
	if (period) params.set('period', period);
	if (cursor) params.set('cursor', cursor);
	params.set('limit', String(Math.max(1, Math.min(50, Math.round(limit) || DEFAULT_LIMIT))));
	return params.toString();
}

/**
 * What identifies the results of a state (not the open model): two states with the same key
 * show the same results, so the page does not search again, and an answer for an older key is
 * dropped.
 */
export function searchKey(state) {
	return JSON.stringify([
		state.source,
		text(state.q).trim(),
		[...(state.types ?? [])].sort(),
		state.baseModel ?? '',
		state.sort ?? '',
		state.period ?? ''
	]);
}

/** `items` followed by the items of `next` whose id is not there yet (a new array). */
export function mergeItems(items, next) {
	const seen = new Set(items.map((item) => `${item.source}\u0000${item.id}`));
	const merged = [...items];
	for (const item of Array.isArray(next) ? next : []) {
		if (!isObject(item) || item.id === undefined || item.id === null) continue;
		const key = `${item.source}\u0000${item.id}`;
		if (seen.has(key)) continue;
		seen.add(key);
		merged.push(item);
	}
	return merged;
}

function labelOf(list, value) {
	return list?.find((option) => option.value === value)?.label ?? value;
}

/**
 * The active filters as chips (`LibraryFilterChipRow`): each type, the base model, a period other
 * than the default. A chip is the value alone, with no group name in front of it (so the source's
 * `types_label` / `base_models_label` have no place here). The sort is not a filter (it has its
 * own select).
 *
 * @returns {{ key: string, label: string }[]}
 */
export function filterChips(state, info) {
	const chips = (state.types ?? []).map((type) => ({ key: `type:${type}`, label: labelOf(info?.types, type) }));
	if (state.baseModel) chips.push({ key: 'base', label: labelOf(info?.base_models, state.baseModel) });
	if (state.period) chips.push({ key: 'period', label: labelOf(info?.periods, state.period) });
	return chips;
}

/** The state without the filter a chip stands for. */
export function removeChip(state, key) {
	if (key.startsWith('type:')) {
		const type = key.slice('type:'.length);
		return { ...state, types: state.types.filter((value) => value !== type) };
	}
	if (key === 'base') return { ...state, baseModel: '' };
	if (key === 'period') return { ...state, period: '' };
	return state;
}

/** The state without any filter (text and sort stay). */
export function clearFilters(state) {
	return { ...state, types: [], baseModel: '', period: '' };
}

/** The state with a type added (`on`) or removed. */
export function toggleType(state, value, on) {
	const rest = (state.types ?? []).filter((type) => type !== value);
	return { ...state, types: on ? [...rest, value] : rest };
}

/**
 * The options whose label or value contains `query` (any case), in their order.
 *
 * @param {{ value: string, label: string }[]} options
 * @param {string} query
 */
export function matchOptions(options, query) {
	const needle = text(query).trim().toLowerCase();
	if (!needle) return [...(options ?? [])];
	return (options ?? []).filter(
		(option) => option.label.toLowerCase().includes(needle) || option.value.toLowerCase().includes(needle)
	);
}

/** The SHA256 of the items whose installed state is not known yet (for `POST /installed`). */
export function unknownInstalledHashes(items) {
	const hashes = new Set();
	for (const item of items) {
		if (item?.installed === true || item?.installed === false) continue;
		const sha = typeof item?.primary_sha256 === 'string' ? item.primary_sha256.toLowerCase() : '';
		if (SHA256.test(sha)) hashes.add(sha);
	}
	return [...hashes];
}

/** The items with `installed` filled from a `POST /installed` answer (`{sha256: bool}`). */
export function applyInstalled(items, installed) {
	if (!isObject(installed)) return items;
	let changed = false;
	const next = items.map((item) => {
		const sha = typeof item?.primary_sha256 === 'string' ? item.primary_sha256.toLowerCase() : '';
		if (!sha || typeof installed[sha] !== 'boolean' || item.installed === installed[sha]) return item;
		changed = true;
		return { ...item, installed: installed[sha] };
	});
	return changed ? next : items;
}

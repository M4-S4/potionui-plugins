// What the signed-in user may do in the Model Browser, read from `GET /me` (backend
// routes_permissions.py). The page shows or hides its actions from this; every route still
// checks on the server (PLAN.md section 4). No Svelte in here: tested with `node --test`
// (see capabilities.test.js).

import { modelTypeLabel } from './format.js';

/** The four capabilities a group can grant (PLAN.md section 4.1). */
export const CAPABILITIES = ['browse', 'request', 'download', 'approve'];

/**
 * PotionUI's model types (`MODEL_TYPES` of the core, src/platform/filesystem/model_types.py),
 * in the core's order: what a download can be filed as when the user's permissions do not
 * narrow it down. `/me` only lists the types of a restricted user.
 */
export const MODEL_TYPES = [
	'checkpoint',
	'diffusion_model',
	'lora',
	'embedding',
	'upscaler',
	'vae',
	'controlnet',
	'adetailer',
	'text_encoder',
	'unet',
	'insightface',
	'facerestore',
	'instantid',
	'detection_segm',
	'detection_bbox',
	'mediapipe',
	'llm',
	'vfi',
	'refmod',
	'model_patch',
	'geometry_estimation'
];

const GIB = 1024 ** 3;
const NSFW_CEILINGS = ['allowed', 'blur', 'blocked'];
const NSFW_MODES = ['blur', 'show', 'hide'];

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function strings(value) {
	return Array.isArray(value) ? [...new Set(value.filter((item) => typeof item === 'string' && item))] : [];
}

/**
 * @typedef {object} Params  What bounds a user's downloads, or their requests.
 * @property {string[]} sources
 * @property {string[]} model_types  Empty: every type.
 * @property {number | null} max_file_gb  null: no limit.
 * @property {'user' | 'group'} assign_to
 * @property {boolean} unrestricted  An admin: nothing applies.
 */

/**
 * @typedef {object} Me
 * @property {{ id: string, username: string, is_admin: boolean }} user
 * @property {string[]} capabilities
 * @property {Params & { allow_remote: boolean }} params  Direct downloads: merged from the groups
 *           that grant `download`.
 * @property {Params} request_params  Requests: merged from the groups that grant `request`;
 *           `params` (without `allow_remote`) when the server sends none.
 * @property {{ ceiling: 'allowed' | 'blur' | 'blocked', mode: 'blur' | 'show' | 'hide',
 *              allowed_modes: string[], max_level: number | null, hide_poi: boolean, setting_key: string }} nsfw
 * @property {{ id: string, name: string }[]} groups
 * @property {{ open_count: number | null }} requests  The open requests the user may decide on
 *           (0 for those who may not); null when the server does not say.
 */

/** One parameter view of `/me` (`params` or `request_params`), every field of the right type. */
function normalizeParams(value) {
	const params = isObject(value) ? value : {};
	const gb = params.max_file_gb;
	return {
		sources: strings(params.sources),
		model_types: strings(params.model_types),
		max_file_gb: typeof gb === 'number' && Number.isFinite(gb) && gb > 0 ? gb : null,
		assign_to: params.assign_to === 'group' ? 'group' : 'user',
		unrestricted: params.unrestricted === true
	};
}

/**
 * The `data` of `GET /me` with every field present and of the right type. What is missing or
 * malformed falls back to the most restrictive value: no capability, no remote, NSFW hidden.
 *
 * @param {unknown} data
 * @returns {Me}
 */
export function normalizeMe(data) {
	const source = isObject(data) ? data : {};
	const user = isObject(source.user) ? source.user : {};
	const nsfw = isObject(source.nsfw) ? source.nsfw : {};
	const requests = isObject(source.requests) ? source.requests : {};
	const isAdmin = user.is_admin === true;
	const params = normalizeParams(source.params);
	const requestParams = isObject(source.request_params) ? normalizeParams(source.request_params) : { ...params };

	const ceiling = NSFW_CEILINGS.includes(nsfw.ceiling) ? nsfw.ceiling : 'blocked';
	let allowedModes = strings(nsfw.allowed_modes).filter((mode) => NSFW_MODES.includes(mode));
	if (ceiling === 'blocked' || allowedModes.length === 0) allowedModes = ['hide'];
	const mode = NSFW_MODES.includes(nsfw.mode) && allowedModes.includes(nsfw.mode) ? nsfw.mode : allowedModes[0];

	return {
		user: {
			id: user.id === undefined || user.id === null ? '' : String(user.id),
			username: typeof user.username === 'string' ? user.username : '',
			is_admin: isAdmin
		},
		capabilities: strings(source.capabilities).filter((capability) => CAPABILITIES.includes(capability)),
		params: { ...params, allow_remote: isObject(source.params) && source.params.allow_remote === true },
		request_params: { ...requestParams, unrestricted: requestParams.unrestricted || params.unrestricted },
		nsfw: {
			ceiling,
			mode,
			allowed_modes: allowedModes,
			max_level: typeof nsfw.max_level === 'number' ? nsfw.max_level : null,
			hide_poi: nsfw.hide_poi === true,
			setting_key: typeof nsfw.setting_key === 'string' && nsfw.setting_key ? nsfw.setting_key : 'media_nsfw_filter_mode'
		},
		groups: (Array.isArray(source.groups) ? source.groups : [])
			.filter((group) => isObject(group) && group.id !== undefined && group.id !== null && group.id !== '')
			.map((group) => ({ id: String(group.id), name: typeof group.name === 'string' && group.name ? group.name : String(group.id) })),
		requests: {
			open_count:
				typeof requests.open_count === 'number' && Number.isFinite(requests.open_count) && requests.open_count >= 0
					? Math.floor(requests.open_count)
					: null
		}
	};
}

/** Whether an admin answer: every capability, no parameter applies. */
export function isUnrestricted(me) {
	return me?.params?.unrestricted === true || me?.user?.is_admin === true;
}

/**
 * Whether the user holds a capability (an admin holds them all).
 *
 * @param {Me | null | undefined} me
 * @param {string} capability
 */
export function can(me, capability) {
	if (!me) return false;
	if (isUnrestricted(me)) return true;
	return Array.isArray(me.capabilities) && me.capabilities.includes(capability);
}

/**
 * The parameter view that bounds one purpose: `download` reads `params` (direct downloads),
 * `request` reads `request_params` (requests; `params` when there are none).
 *
 * @param {Me | null | undefined} me
 * @param {'download' | 'request'} [purpose]
 * @returns {Params | null}
 */
export function paramsFor(me, purpose = 'download') {
	if (purpose === 'request') return me?.request_params ?? me?.params ?? null;
	return me?.params ?? null;
}

/**
 * The model types the user may file a download as (or ask for, with `purpose: 'request'`), and
 * which one the dialog starts on.
 *
 * Every PotionUI type for an admin or when the parameters list none; otherwise the listed ones.
 * The source's suggestion (`mbType`, null when the source does not map it) comes first and is
 * selected when allowed; otherwise nothing is selected and the user must choose.
 *
 * @param {Me | null | undefined} me
 * @param {string | null | undefined} mbType
 * @param {{ purpose?: 'download' | 'request' }} [options]
 * @returns {{ types: string[], selected: string, suggestionAllowed: boolean }}
 */
export function allowedTypes(me, mbType, { purpose = 'download' } = {}) {
	const listed = paramsFor(me, purpose)?.model_types ?? [];
	const all = isUnrestricted(me) || listed.length === 0;
	let types = all ? [...MODEL_TYPES] : MODEL_TYPES.filter((type) => listed.includes(type));
	// A type the core added since this list was written is still offered when the admin allowed it.
	if (!all) types = [...types, ...listed.filter((type) => !MODEL_TYPES.includes(type))];
	const suggestion = typeof mbType === 'string' && mbType ? mbType : '';
	const suggestionAllowed = suggestion !== '' && types.includes(suggestion);
	if (suggestionAllowed) types = [suggestion, ...types.filter((type) => type !== suggestion)];
	return { types, selected: suggestionAllowed ? suggestion : '', suggestionAllowed };
}

/** Whether the download dialog offers a target group: admins, and users whose groups say `assign_to: group`. */
export function canChooseGroup(me) {
	return isUnrestricted(me) || me?.params?.assign_to === 'group';
}

/** Whether the download dialog offers a remote backend as the destination. */
export function canChooseRemote(me) {
	return isUnrestricted(me) || me?.params?.allow_remote === true;
}

/** Whether the user's download permissions cover this source. */
export function canDownloadFrom(me, source) {
	if (!can(me, 'download')) return false;
	return isUnrestricted(me) || (me?.params?.sources ?? []).includes(source);
}

/** Whether the user may ask for a file of this source: their request parameters (`request_params`) list it. */
export function canRequestFrom(me, source) {
	if (!can(me, 'request')) return false;
	return isUnrestricted(me) || (paramsFor(me, 'request')?.sources ?? []).includes(source);
}

/**
 * Why the user may not ask for a file, or '' when they may, by their request parameters:
 * `capability` (no `request`), `source` (not one of their sources), `type` (the source's
 * suggested type is not one they may ask for; a file without a suggestion is typed in the
 * dialog), `size` (over their size limit; an unknown size is left to the server).
 *
 * @param {Me | null | undefined} me
 * @param {{ source?: string, type?: string | null, sizeBytes?: number | null }} [file]
 * @returns {'' | 'capability' | 'source' | 'type' | 'size'}
 */
export function requestBlock(me, { source = '', type = null, sizeBytes = null } = {}) {
	if (!can(me, 'request')) return 'capability';
	if (isUnrestricted(me)) return '';
	if (!canRequestFrom(me, source)) return 'source';
	const types = paramsFor(me, 'request')?.model_types ?? [];
	if (typeof type === 'string' && type && types.length > 0 && !types.includes(type)) return 'type';
	if (exceedsSizeLimit(me, sizeBytes, { purpose: 'request' })) return 'size';
	return '';
}

/**
 * `requestBlock` for people, under a disabled Request button: 'Not allowed from CivitAI',
 * 'Checkpoint models not allowed', 'Over your 2 GB limit'; '' when the user may ask.
 *
 * @param {Me | null | undefined} me
 * @param {{ source?: string, type?: string | null, sizeBytes?: number | null }} [file]
 * @param {string} [sourceLabel]  The source's name for people.
 */
export function requestBlockReason(me, file = {}, sourceLabel = '') {
	switch (requestBlock(me, file)) {
		case 'capability':
			return 'You may not ask for models';
		case 'source':
			return `Not allowed from ${sourceLabel || file.source || 'this source'}`;
		case 'type':
			return `${modelTypeLabel(file.type) || file.type} models not allowed`;
		case 'size':
			return `Over your ${paramsFor(me, 'request')?.max_file_gb} GB limit`;
		default:
			return '';
	}
}

/**
 * What a file row offers this user:
 * - `download`: the Download button (the download parameters, `params`, decide on the source; the
 *   dialog checks the type and the size);
 * - `request`: the Request button (RequestDialog), when the request parameters (`request_params`:
 *   source, suggested type, size) allow the file, for a user who may not download at all, or whose
 *   download parameters exclude the source;
 * - `source-blocked`: they may download, but not from this source, and may not ask for the file;
 * - `request-blocked`: they may only ask, and their request parameters exclude the file;
 * - `none`: browse only, no button.
 *
 * @param {Me | null | undefined} me
 * @param {string} source
 * @param {{ type?: string | null, sizeBytes?: number | null }} [file]  The source's suggested
 *        PotionUI type (`mb_type`) and the file's size.
 * @returns {'download' | 'source-blocked' | 'request' | 'request-blocked' | 'none'}
 */
export function fileAction(me, source, { type = null, sizeBytes = null } = {}) {
	const askable = can(me, 'request') && !requestBlock(me, { source, type, sizeBytes });
	if (can(me, 'download')) {
		if (canDownloadFrom(me, source)) return 'download';
		return askable ? 'request' : 'source-blocked';
	}
	if (can(me, 'request')) return askable ? 'request' : 'request-blocked';
	return 'none';
}

/**
 * `fileAction` with the reason shown under a disabled button ('' for the others).
 *
 * @param {Me | null | undefined} me
 * @param {string} source
 * @param {{ type?: string | null, sizeBytes?: number | null }} [file]
 * @param {string} [sourceLabel]
 * @returns {{ action: ReturnType<typeof fileAction>, reason: string }}
 */
export function fileActionInfo(me, source, file = {}, sourceLabel = '') {
	const action = fileAction(me, source, file);
	if (action === 'source-blocked') return { action, reason: `Not allowed from ${sourceLabel || source || 'this source'}` };
	if (action === 'request-blocked') return { action, reason: requestBlockReason(me, { ...file, source }, sourceLabel) };
	return { action, reason: '' };
}

/**
 * The largest file the user may download (or ask for, with `purpose: 'request'`), in bytes; null
 * without a limit.
 *
 * @param {Me | null | undefined} me
 * @param {{ purpose?: 'download' | 'request' }} [options]
 */
export function sizeLimitBytes(me, { purpose = 'download' } = {}) {
	if (isUnrestricted(me)) return null;
	const gb = paramsFor(me, purpose)?.max_file_gb;
	return typeof gb === 'number' && gb > 0 ? gb * GIB : null;
}

/**
 * Whether a file of `sizeBytes` is over the user's limit for that purpose (an unknown size never
 * is: the server decides).
 *
 * @param {Me | null | undefined} me
 * @param {unknown} sizeBytes
 * @param {{ purpose?: 'download' | 'request' }} [options]
 */
export function exceedsSizeLimit(me, sizeBytes, { purpose = 'download' } = {}) {
	const limit = sizeLimitBytes(me, { purpose });
	return limit !== null && typeof sizeBytes === 'number' && sizeBytes > limit;
}

/**
 * The choices of the "assign to" select: the user themselves first (value '': no
 * `assign_group_id` is sent; an admin sees every model anyway), then their groups.
 *
 * @param {Me | null | undefined} me
 * @returns {{ id: string, name: string }[]}
 */
export function groupChoices(me) {
	return [{ id: '', name: 'Me' }, ...(me?.groups ?? [])];
}

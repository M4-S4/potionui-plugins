// What the signed-in user may do in the Model Browser, read from `GET /me` (backend
// routes_permissions.py). The page shows or hides its actions from this; every route still
// checks on the server (PLAN.md section 4). No Svelte in here: tested with `node --test`
// (see capabilities.test.js).

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
 * @typedef {object} Me
 * @property {{ id: string, username: string, is_admin: boolean }} user
 * @property {string[]} capabilities
 * @property {{ sources: string[], model_types: string[], max_file_gb: number | null,
 *              assign_to: 'user' | 'group', allow_remote: boolean, unrestricted: boolean }} params
 * @property {{ ceiling: 'allowed' | 'blur' | 'blocked', mode: 'blur' | 'show' | 'hide',
 *              allowed_modes: string[], max_level: number | null, hide_poi: boolean, setting_key: string }} nsfw
 * @property {{ id: string, name: string }[]} groups
 */

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
	const params = isObject(source.params) ? source.params : {};
	const nsfw = isObject(source.nsfw) ? source.nsfw : {};
	const unrestricted = params.unrestricted === true;
	const isAdmin = user.is_admin === true;

	const ceiling = NSFW_CEILINGS.includes(nsfw.ceiling) ? nsfw.ceiling : 'blocked';
	let allowedModes = strings(nsfw.allowed_modes).filter((mode) => NSFW_MODES.includes(mode));
	if (ceiling === 'blocked' || allowedModes.length === 0) allowedModes = ['hide'];
	const mode = NSFW_MODES.includes(nsfw.mode) && allowedModes.includes(nsfw.mode) ? nsfw.mode : allowedModes[0];

	const maxFileGb = typeof params.max_file_gb === 'number' && Number.isFinite(params.max_file_gb) && params.max_file_gb > 0
		? params.max_file_gb
		: null;

	return {
		user: {
			id: user.id === undefined || user.id === null ? '' : String(user.id),
			username: typeof user.username === 'string' ? user.username : '',
			is_admin: isAdmin
		},
		capabilities: strings(source.capabilities).filter((capability) => CAPABILITIES.includes(capability)),
		params: {
			sources: strings(params.sources),
			model_types: strings(params.model_types),
			max_file_gb: maxFileGb,
			assign_to: params.assign_to === 'group' ? 'group' : 'user',
			allow_remote: params.allow_remote === true,
			unrestricted
		},
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
			.map((group) => ({ id: String(group.id), name: typeof group.name === 'string' && group.name ? group.name : String(group.id) }))
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
 * The model types the user may file a download as, and which one the dialog starts on.
 *
 * Every PotionUI type for an admin or when the user's permissions list none; otherwise the
 * listed ones. The source's suggestion (`mbType`, null when the source does not map it) comes
 * first and is selected when allowed; otherwise nothing is selected and the user must choose.
 *
 * @param {Me | null | undefined} me
 * @param {string | null | undefined} mbType
 * @returns {{ types: string[], selected: string, suggestionAllowed: boolean }}
 */
export function allowedTypes(me, mbType) {
	const listed = me?.params?.model_types ?? [];
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

/**
 * What a file row offers this user:
 * - `download`: the Download button;
 * - `source-blocked`: they may download, but not from this source (a disabled button says why);
 * - `request`: they may only ask an admin (phase 5: a disabled "Request (coming soon)");
 * - `none`: browse only, no button.
 *
 * @param {Me | null | undefined} me
 * @param {string} source
 * @returns {'download' | 'source-blocked' | 'request' | 'none'}
 */
export function fileAction(me, source) {
	if (can(me, 'download')) return canDownloadFrom(me, source) ? 'download' : 'source-blocked';
	if (can(me, 'request')) return 'request';
	return 'none';
}

/** The largest file the user may download, in bytes; null without a limit. */
export function sizeLimitBytes(me) {
	if (isUnrestricted(me)) return null;
	const gb = me?.params?.max_file_gb;
	return typeof gb === 'number' && gb > 0 ? gb * GIB : null;
}

/** Whether a file of `sizeBytes` is over the user's limit (an unknown size never is: the server decides). */
export function exceedsSizeLimit(me, sizeBytes) {
	const limit = sizeLimitBytes(me);
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

// NSFW on the page (PLAN.md section 5). The server is the authority: it drops what a user may not
// see and sends NSFW images to a user in blur mode *without their url* (a blurhash instead);
// `GET /{source}/models/{id}/nsfw-media` hands the urls out on a "reveal" click. This module
// only decides what the page draws and which display modes it offers. No Svelte in here:
// tested with `node --test` (see nsfw.test.js).

/** The display modes of the core's `media_nsfw_filter_mode` setting, in the app's own order. */
export const MODES = ['blur', 'show', 'hide'];

export const MODE_LABELS = { blur: 'Blur', show: 'Show', hide: 'Hide' };

const CEILING_RANK = { allowed: 0, blur: 1, blocked: 2 };

/**
 * The NSFW part of a normalised `/me` (see capabilities.normalizeMe), with safe defaults.
 *
 * @param {any} me
 * @returns {{ ceiling: string, mode: string, allowed: string[], locked: boolean, settingKey: string }}
 */
export function nsfwInfo(me) {
	const nsfw = me?.nsfw ?? {};
	const ceiling = nsfw.ceiling in CEILING_RANK ? nsfw.ceiling : 'blocked';
	const allowed = ceiling === 'blocked' ? ['hide'] : (nsfw.allowed_modes ?? []).filter((mode) => MODES.includes(mode));
	return {
		ceiling,
		mode: effectiveMode(me),
		allowed: allowed.length ? allowed : ['hide'],
		locked: ceiling === 'blocked',
		settingKey: typeof nsfw.setting_key === 'string' && nsfw.setting_key ? nsfw.setting_key : 'media_nsfw_filter_mode'
	};
}

/**
 * The mode the server applies: the user's, pulled down to what the ceiling allows
 * (`backend/nsfw_filter.display_mode`): `blocked` -> hide, `blur` + show -> blur.
 *
 * @param {any} me
 * @returns {'blur' | 'show' | 'hide'}
 */
export function effectiveMode(me) {
	const nsfw = me?.nsfw ?? {};
	const ceiling = nsfw.ceiling in CEILING_RANK ? nsfw.ceiling : 'blocked';
	if (ceiling === 'blocked') return 'hide';
	const mode = MODES.includes(nsfw.mode) ? nsfw.mode : 'hide';
	if (ceiling === 'blur' && mode === 'show') return 'blur';
	return mode;
}

/**
 * The segments of the NSFW mode control: the three modes in the app's order, those the ceiling
 * does not allow disabled. Empty when the ceiling is `blocked`: there is nothing to choose and the
 * page says "Hidden by policy" instead.
 *
 * @param {any} me
 * @returns {{ id: string, label: string, disabled: boolean }[]}
 */
export function effectiveModes(me) {
	const info = nsfwInfo(me);
	if (info.locked) return [];
	return MODES.map((id) => ({ id, label: MODE_LABELS[id], disabled: !info.allowed.includes(id) }));
}

/** Why a mode is not offered, for its tooltip; '' when it is. */
export function modeHint(me, mode) {
	const info = nsfwInfo(me);
	if (info.allowed.includes(mode)) return '';
	if (info.locked) return 'Your content policy hides NSFW media';
	return 'Your content policy allows blurred NSFW media at most';
}

/**
 * Whether a "click to reveal" applies to this image: an NSFW image the server sent without its
 * url, to a user in blur mode whose ceiling is not `blocked` (`nsfw-media` answers 404 then).
 *
 * @param {any} image  An `Image` of the API (`{id, url, blurhash, nsfw, ...}`).
 * @param {any} me
 */
export function isRevealable(image, me) {
	if (!image || image.nsfw !== true || image.url) return false;
	const info = nsfwInfo(me);
	return !info.locked && effectiveMode(me) === 'blur';
}

/**
 * What a media box draws for an image:
 * - `media`: the image or video itself (it has a url, or was revealed);
 * - `blurred`: the blurhash (or a plain tile without one) under an NSFW label, revealable or not;
 * - `empty`: nothing to show (no url and not NSFW: a placeholder).
 *
 * @param {any} image
 * @param {string | null | undefined} revealedUrl  The url `nsfw-media` gave for it, if any.
 * @returns {'media' | 'blurred' | 'empty'}
 */
export function mediaState(image, revealedUrl) {
	if (!image) return 'empty';
	if (image.url || revealedUrl) return 'media';
	return image.nsfw ? 'blurred' : 'empty';
}

/**
 * Remembers the answers of `nsfw-media`, one request per model, and maps the urls to the
 * blurred images by their `id` (backend `Image.id`: the CivitAI image id, a hash of the url for
 * Hugging Face).
 *
 * `fetchMedia(source, modelId)` resolves to the client's `{ ok, data: { images } }` or
 * `{ ok: false, error }`. A failed request is forgotten, so the next click asks again.
 *
 * @param {(source: string, modelId: string) => Promise<any>} fetchMedia
 */
export function createRevealCache(fetchMedia) {
	/** @type {Map<string, Promise<{ ok: true, urls: Map<string, string> } | { ok: false, error: any }>>} */
	const requests = new Map();

	function load(source, modelId) {
		const key = `${source}\u0000${modelId}`;
		let pending = requests.get(key);
		if (!pending) {
			pending = Promise.resolve()
				.then(() => fetchMedia(source, modelId))
				.then((result) => {
					if (!result?.ok) {
						requests.delete(key);
						return { ok: false, error: result?.error ?? { message: 'Could not reveal the media' } };
					}
					const urls = new Map();
					for (const image of result.data?.images ?? []) {
						if (image && image.id !== null && image.id !== undefined && typeof image.url === 'string' && image.url) {
							urls.set(String(image.id), image.url);
						}
					}
					return { ok: true, urls };
				})
				.catch((err) => {
					requests.delete(key);
					return { ok: false, error: { message: err instanceof Error ? err.message : 'Could not reveal the media' } };
				});
			requests.set(key, pending);
		}
		return pending;
	}

	return {
		/** Every url of a model's NSFW images, by image id. */
		urls: load,
		/**
		 * The url of one image: `{ url }`, `{ url: null }` when the answer does not hold it (an
		 * image without id, or no longer NSFW-only), or `{ error }`.
		 */
		async urlFor(source, modelId, imageId) {
			const result = await load(source, modelId);
			if (!result.ok) return { error: result.error };
			const url = imageId === null || imageId === undefined ? null : result.urls.get(String(imageId)) ?? null;
			return { url };
		},
		/** Forget every answer (the display mode changed). */
		reset() {
			requests.clear();
		}
	};
}

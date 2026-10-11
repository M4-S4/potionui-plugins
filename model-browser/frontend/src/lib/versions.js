// The versions of a model detail, for the sources that send only some of them in full. CivArchive
// answers a model with the version asked for in full and the others as shells: `partial: true`, a
// name and a date, `files: []`, `images: []`. A shell is fetched when it comes on screen, with the
// composite id `<model id>:<version id>` on the usual detail route; the answer is a full model
// detail whose first version is the one asked for (its `id` is the plain model id), and
// `mergeVersion` puts that version in the drawer's detail. The previews of a version are revealed
// through its composite id too (`mediaModelId`): the server holds the files and the images of the
// version it was asked for only. CivitAI, Hugging Face and OpenModelDB never set `partial`, so
// none of this applies to them. No Svelte in here: tested with `node --test` (see versions.test.js).

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Whether a version is a shell: its files and previews are not in the detail yet. */
export function isPartial(version) {
	return isObject(version) && version.partial === true;
}

/** Whether some version of a detail is a shell: the versions of that model are asked for one by one. */
export function hasPartialVersions(detail) {
	return Array.isArray(detail?.versions) && detail.versions.some(isPartial);
}

/** `<model id>:<version id>`: the id that asks the server for one version in full. */
export function versionRef(modelId, versionId) {
	return `${modelId}:${versionId}`;
}

/**
 * The id `nsfw-media` is asked with for the previews of `version`. With `byVersion` (the versions
 * of the detail come one by one) it is the version's own composite id, whichever version it is: the
 * server holds the images of the version it was asked for, not those of the model's latest one.
 * Otherwise it is the model's id, as for every source that sends all its versions in full.
 *
 * @param {{ id: string | number }} detail
 * @param {{ id: string } | null | undefined} version
 * @param {boolean} byVersion
 */
export function mediaModelId(detail, version, byVersion) {
	return byVersion && version ? versionRef(detail.id, version.id) : detail.id;
}

function refused(message) {
	return { ok: false, error: { status: 0, code: 'invalid_response', message, retryAfter: null } };
}

/**
 * The detail with version `versionId` replaced by the full one of `answer` (the answer of
 * `GET /{source}/models/<model id>:<version id>`): same place in the list, the other versions and
 * every other field of the detail kept as they are, `partial` cleared. A new object: `detail` is
 * not changed. An answer that does not hold that version in full (not an object, another model, no
 * version with that id, that version still a shell) is refused with an `ApiError`-shaped error and
 * changes nothing.
 *
 * @param {any} detail     The drawer's detail.
 * @param {string | number} versionId  The version that was asked for.
 * @param {any} answer     The model detail the server answered.
 * @returns {{ ok: true, detail: any } | { ok: false, error: { status: number, code: string, message: string, retryAfter: null } }}
 */
export function mergeVersion(detail, versionId, answer) {
	const id = String(versionId ?? '');
	const versions = Array.isArray(detail?.versions) ? detail.versions : [];
	const index = versions.findIndex((entry) => String(entry?.id) === id);
	if (!id || index < 0) return refused('This version is not in the list any more');
	if (!isObject(answer) || !Array.isArray(answer.versions)) return refused('Unexpected answer from the server');
	if (answer.id != null && detail.id != null && String(answer.id) !== String(detail.id)) {
		return refused('The server answered for another model');
	}
	const loaded = answer.versions.find((entry) => isObject(entry) && String(entry.id) === id);
	if (!loaded) return refused('The server did not send this version');
	if (isPartial(loaded)) return refused('The server sent this version without its files');
	return {
		ok: true,
		detail: { ...detail, versions: versions.map((entry, position) => (position === index ? { ...loaded, partial: false } : entry)) }
	};
}

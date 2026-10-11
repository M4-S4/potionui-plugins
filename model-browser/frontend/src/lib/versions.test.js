import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getModel, getNsfwMedia } from './client.js';
import { hasPartialVersions, isPartial, mediaModelId, mergeVersion, versionRef } from './versions.js';

// The shapes of backend/sources/civarchive.py: the version asked for in full, first; the others as
// shells (`partial: true`, a name and a date, no file, no image).
function full(id, extra = {}) {
	return {
		id,
		name: `Version ${id}`,
		base_model: 'SDXL 1.0',
		trigger_words: [`trigger ${id}`],
		created_at: '2024-05-01',
		early_access: false,
		nsfw: false,
		images: [{ id: Number(id), url: `https://example.test/${id}.jpg`, nsfw: false }],
		files: [{ id: `file-${id}`, name: `model-${id}.safetensors`, primary: true }],
		partial: false,
		...extra
	};
}

function shell(id, extra = {}) {
	return {
		id,
		name: `Version ${id}`,
		base_model: null,
		trigger_words: [],
		created_at: '2023-01-01',
		early_access: false,
		nsfw: false,
		images: [],
		files: [],
		partial: true,
		...extra
	};
}

/** The drawer's detail: version 300 (the one the drawer opened on) in full, 200 and 100 as shells. */
function drawerDetail() {
	return {
		source: 'civarchive',
		id: '78291',
		name: 'A model',
		description_html: '<p>About</p>',
		gated: false,
		versions: [full('300'), shell('200'), shell('100')]
	};
}

/** What the server answers for `78291:<id>`: that version first, in full, the others as shells. */
function answerFor(id) {
	const others = ['300', '200', '100'].filter((other) => other !== id);
	return { ...drawerDetail(), versions: [full(id), ...others.map((other) => shell(other))] };
}

test('only partial: true makes a version a shell', () => {
	assert.equal(isPartial(shell('1')), true);
	for (const version of [full('1'), { id: '1' }, { id: '1', partial: false }, { id: '1', partial: 'true' }, { id: '1', partial: 1 }, null, undefined, 'x', []]) {
		assert.equal(isPartial(version), false);
	}
	assert.equal(hasPartialVersions(drawerDetail()), true);
	// The other sources send no flag (or false) on any version, whatever their files and images hold.
	assert.equal(hasPartialVersions({ versions: [{ id: '1', files: [], images: [] }, { id: '2', partial: false }] }), false);
	assert.equal(hasPartialVersions({ versions: [] }), false);
	assert.equal(hasPartialVersions({}), false);
	assert.equal(hasPartialVersions(null), false);
});

test('versionRef and mediaModelId: a version of its own id only when the versions come one by one', () => {
	assert.equal(versionRef('78291', '83095'), '78291:83095');
	assert.equal(versionRef(78291, 83095), '78291:83095');
	const detail = drawerDetail();
	// CivArchive: every version, the one that came in full included, is revealed through its own id
	// (the server holds the images of the version it was asked for).
	assert.equal(mediaModelId(detail, detail.versions[0], true), '78291:300');
	assert.equal(mediaModelId(detail, detail.versions[1], true), '78291:200');
	// The other sources, and a detail whose versions all came in full: the model id, as before.
	assert.equal(mediaModelId(detail, detail.versions[1], false), '78291');
	assert.equal(mediaModelId({ id: 58390 }, { id: '1' }, false), 58390);
	// No version on screen: the model id.
	assert.equal(mediaModelId(detail, null, true), '78291');
});

test('mergeVersion puts the full version in the place of its shell and keeps everything else', () => {
	const detail = drawerDetail();
	const snapshot = structuredClone(detail);
	const result = mergeVersion(detail, '200', answerFor('200'));
	assert.equal(result.ok, true);
	const merged = result.detail;
	// Same order; version 200 is the full one: its files, its previews, no longer a shell.
	assert.deepEqual(
		merged.versions.map((version) => version.id),
		['300', '200', '100']
	);
	assert.deepEqual(merged.versions[1], full('200'));
	assert.equal(merged.versions[1].partial, false);
	assert.equal(merged.versions[1].files.length, 1);
	assert.equal(merged.versions[1].images.length, 1);
	// The others are the very same objects: the full 300 is not replaced by the shell 300 that the
	// answer lists, and the shell 100 stays a shell.
	assert.equal(merged.versions[0], detail.versions[0]);
	assert.equal(merged.versions[2], detail.versions[2]);
	assert.equal(isPartial(merged.versions[0]), false);
	assert.equal(isPartial(merged.versions[2]), true);
	// The fields of the model are those of the detail of the drawer, and the input is left alone.
	assert.equal(merged.name, 'A model');
	assert.equal(merged.description_html, '<p>About</p>');
	assert.notEqual(merged, detail);
	assert.notEqual(merged.versions, detail.versions);
	assert.deepEqual(detail, snapshot);
});

test('mergeVersion clears partial, even when the full version carries no flag', () => {
	const answer = answerFor('200');
	delete answer.versions[0].partial;
	const merged = mergeVersion(drawerDetail(), '200', answer).detail;
	assert.equal(merged.versions[1].partial, false);
	assert.equal(isPartial(merged.versions[1]), false);
});

test('versions merged one after the other all stay merged', () => {
	let detail = drawerDetail();
	for (const id of ['100', '200']) {
		const result = mergeVersion(detail, id, answerFor(id));
		assert.equal(result.ok, true);
		detail = result.detail;
	}
	assert.deepEqual(
		detail.versions.map((version) => [version.id, isPartial(version), version.files.length]),
		[
			['300', false, 1],
			['200', false, 1],
			['100', false, 1]
		]
	);
	// No shell is left: only the flag the page took when the detail came still says that the
	// previews are revealed version by version.
	assert.equal(hasPartialVersions(detail), false);
	assert.equal(mediaModelId(detail, detail.versions[2], true), '78291:100');
});

test('mergeVersion compares ids as text', () => {
	const result = mergeVersion(drawerDetail(), 200, { ...answerFor('200'), id: 78291 });
	assert.equal(result.ok, true);
	assert.equal(result.detail.versions[1].partial, false);
});

test('mergeVersion refuses an answer that does not hold the version in full, and changes nothing', () => {
	const detail = drawerDetail();
	const snapshot = structuredClone(detail);
	// The refusal is shaped like the errors of the client, with a message for people.
	const refusal = (result) => {
		assert.equal(result.ok, false);
		assert.deepEqual(Object.keys(result.error).sort(), ['code', 'message', 'retryAfter', 'status']);
		assert.equal(result.error.status, 0);
		assert.equal(result.error.code, 'invalid_response');
		assert.ok(result.error.message);
		return result.error.message;
	};
	// The server answered for another version (here the latest, 300): 200 is a shell in it.
	assert.match(refusal(mergeVersion(detail, '200', answerFor('300'))), /without its files/);
	// ... or does not list the version at all.
	assert.match(refusal(mergeVersion(detail, '200', { ...answerFor('300'), versions: [full('300')] })), /did not send/);
	assert.match(refusal(mergeVersion(detail, '200', { ...answerFor('200'), versions: [] })), /did not send/);
	// Another model.
	assert.match(refusal(mergeVersion(detail, '200', { ...answerFor('200'), id: '99' })), /another model/);
	// Not a model detail.
	for (const answer of [null, undefined, 'text', 7, [], {}, { versions: 'x' }]) {
		assert.match(refusal(mergeVersion(detail, '200', answer)), /Unexpected answer/);
	}
	// A version the drawer does not list (or a drawer with no detail).
	assert.match(refusal(mergeVersion(detail, '999', answerFor('999'))), /not in the list/);
	assert.match(refusal(mergeVersion(detail, '', answerFor('200'))), /not in the list/);
	assert.match(refusal(mergeVersion(null, '200', answerFor('200'))), /not in the list/);
	assert.deepEqual(detail, snapshot);
});

test('a shell is asked for by its composite id on the detail route, and its previews on the same id', async () => {
	const asked = [];
	const api = {
		get: async (path) => {
			asked.push(path);
			return { success: true, data: path.endsWith('/nsfw-media') ? { images: [] } : answerFor('200') };
		}
	};
	const detail = drawerDetail();
	// Taken once, from the detail as it comes: later merges clear the flags of the shells.
	const byVersion = hasPartialVersions(detail);
	const shown = await getModel(api, detail.source, versionRef(detail.id, '200'));
	assert.equal(shown.ok, true);
	const merged = mergeVersion(detail, '200', shown.data);
	assert.equal(merged.ok, true);
	await getNsfwMedia(api, detail.source, mediaModelId(merged.detail, merged.detail.versions[1], byVersion));
	// The colon stays in one path segment, sent as %3A and decoded by the route parameter model_id.
	assert.deepEqual(asked, ['/civarchive/models/78291%3A200', '/civarchive/models/78291%3A200/nsfw-media']);
});

test('a detail without shells (CivitAI, Hugging Face, OpenModelDB) keeps its old ways', () => {
	const detail = {
		source: 'civitai',
		id: 58390,
		versions: [
			{ id: '1', files: [{ id: 'a' }], images: [] },
			{ id: '2', files: [], images: [], partial: false }
		]
	};
	assert.equal(hasPartialVersions(detail), false);
	assert.equal(detail.versions.some(isPartial), false);
	assert.equal(mediaModelId(detail, detail.versions[1], hasPartialVersions(detail)), 58390);
});

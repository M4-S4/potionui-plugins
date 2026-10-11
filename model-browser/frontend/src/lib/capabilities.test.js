import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	MODEL_TYPES,
	allowedTypes,
	can,
	canChooseGroup,
	canChooseRemote,
	canDownloadFrom,
	exceedsSizeLimit,
	fileAction,
	groupChoices,
	normalizeMe,
	sizeLimitBytes
} from './capabilities.js';

// The shape of backend/routes_permissions.py's GET /me.
function meData(overrides = {}) {
	return {
		user: { id: 'u1', username: 'alice', is_admin: false },
		capabilities: ['browse', 'request'],
		params: { sources: [], model_types: [], max_file_gb: null, assign_to: 'user', allow_remote: false, unrestricted: false },
		nsfw: { ceiling: 'allowed', mode: 'blur', allowed_modes: ['blur', 'show', 'hide'], max_level: 2, hide_poi: false, setting_key: 'media_nsfw_filter_mode' },
		...overrides
	};
}

const ADMIN = normalizeMe(
	meData({
		user: { id: 'a1', username: 'root', is_admin: true },
		capabilities: ['approve', 'browse', 'download', 'request'],
		params: { sources: [], model_types: [], max_file_gb: null, assign_to: 'user', allow_remote: false, unrestricted: true },
		groups: [{ id: 'all_admins', name: 'All Admins' }]
	})
);

const DOWNLOADER = normalizeMe(
	meData({
		capabilities: ['browse', 'download', 'request'],
		params: {
			sources: ['civitai', 'huggingface'],
			model_types: ['embedding', 'lora'],
			max_file_gb: 2,
			assign_to: 'group',
			allow_remote: true,
			unrestricted: false
		},
		groups: [{ id: 'g1', name: 'Artists' }, { id: 'g2' }]
	})
);

const BROWSER = normalizeMe(meData({ capabilities: ['browse'] }));
const REQUESTER = normalizeMe(meData());

test('normalizeMe keeps a well formed answer', () => {
	assert.deepEqual(DOWNLOADER.user, { id: 'u1', username: 'alice', is_admin: false });
	assert.deepEqual(DOWNLOADER.capabilities, ['browse', 'download', 'request']);
	assert.deepEqual(DOWNLOADER.params, {
		sources: ['civitai', 'huggingface'],
		model_types: ['embedding', 'lora'],
		max_file_gb: 2,
		assign_to: 'group',
		allow_remote: true,
		unrestricted: false
	});
	assert.deepEqual(DOWNLOADER.nsfw, {
		ceiling: 'allowed',
		mode: 'blur',
		allowed_modes: ['blur', 'show', 'hide'],
		max_level: 2,
		hide_poi: false,
		setting_key: 'media_nsfw_filter_mode'
	});
	assert.deepEqual(DOWNLOADER.groups, [{ id: 'g1', name: 'Artists' }, { id: 'g2', name: 'g2' }]);
});

test('normalizeMe falls back to the most restrictive values', () => {
	const me = normalizeMe(null);
	assert.deepEqual(me.capabilities, []);
	assert.equal(me.params.unrestricted, false);
	assert.equal(me.params.allow_remote, false);
	assert.equal(me.params.max_file_gb, null);
	assert.equal(me.params.assign_to, 'user');
	assert.equal(me.nsfw.ceiling, 'blocked');
	assert.equal(me.nsfw.mode, 'hide');
	assert.deepEqual(me.nsfw.allowed_modes, ['hide']);
	assert.deepEqual(me.groups, []);
	assert.equal(me.nsfw.setting_key, 'media_nsfw_filter_mode');
});

test('normalizeMe drops unknown capabilities, bad groups and bad sizes', () => {
	const me = normalizeMe(
		meData({
			capabilities: ['browse', 'manage', 7, 'browse'],
			params: { max_file_gb: -3, assign_to: 'everyone' },
			groups: [null, { name: 'no id' }, { id: 5, name: 'Five' }, 'x']
		})
	);
	assert.deepEqual(me.capabilities, ['browse']);
	assert.equal(me.params.max_file_gb, null);
	assert.equal(me.params.assign_to, 'user');
	assert.deepEqual(me.groups, [{ id: '5', name: 'Five' }]);
});

test('normalizeMe bounds the NSFW mode by the modes the ceiling allows', () => {
	const blocked = normalizeMe(meData({ nsfw: { ceiling: 'blocked', mode: 'show', allowed_modes: ['blur', 'show'] } }));
	assert.equal(blocked.nsfw.mode, 'hide');
	assert.deepEqual(blocked.nsfw.allowed_modes, ['hide']);

	const blur = normalizeMe(meData({ nsfw: { ceiling: 'blur', mode: 'show', allowed_modes: ['blur', 'hide'] } }));
	assert.equal(blur.nsfw.mode, 'blur');

	const odd = normalizeMe(meData({ nsfw: { ceiling: 'sideways', mode: 'show', allowed_modes: ['show'] } }));
	assert.equal(odd.nsfw.ceiling, 'blocked');
	assert.equal(odd.nsfw.mode, 'hide');
});

test('can: admins hold everything, others what /me lists', () => {
	for (const capability of ['browse', 'request', 'download', 'approve']) assert.equal(can(ADMIN, capability), true);
	assert.equal(can(DOWNLOADER, 'download'), true);
	assert.equal(can(DOWNLOADER, 'approve'), false);
	assert.equal(can(BROWSER, 'browse'), true);
	assert.equal(can(BROWSER, 'request'), false);
	assert.equal(can(null, 'browse'), false);
	assert.equal(can(normalizeMe({}), 'browse'), false);
});

test('allowedTypes offers every type to an admin, the suggestion first and selected', () => {
	const result = allowedTypes(ADMIN, 'lora');
	assert.equal(result.types.length, MODEL_TYPES.length);
	assert.equal(result.types[0], 'lora');
	assert.equal(result.selected, 'lora');
	assert.equal(result.suggestionAllowed, true);
});

test('allowedTypes limits a restricted user to their types', () => {
	assert.deepEqual(allowedTypes(DOWNLOADER, 'lora'), { types: ['lora', 'embedding'], selected: 'lora', suggestionAllowed: true });
	assert.deepEqual(allowedTypes(DOWNLOADER, 'checkpoint'), { types: ['lora', 'embedding'], selected: '', suggestionAllowed: false });
});

test('allowedTypes makes the user choose when the source has no suggestion', () => {
	assert.deepEqual(allowedTypes(DOWNLOADER, null), { types: ['lora', 'embedding'], selected: '', suggestionAllowed: false });
	const everyType = allowedTypes(REQUESTER, null);
	assert.equal(everyType.types.length, MODEL_TYPES.length);
	assert.equal(everyType.selected, '');
});

test('allowedTypes keeps a listed type the page does not know yet', () => {
	const me = normalizeMe(meData({ capabilities: ['download'], params: { model_types: ['lora', 'hologram'] } }));
	assert.deepEqual(allowedTypes(me, 'hologram').types, ['hologram', 'lora']);
});

test('canChooseGroup and canChooseRemote', () => {
	assert.equal(canChooseGroup(ADMIN), true);
	assert.equal(canChooseGroup(DOWNLOADER), true);
	assert.equal(canChooseGroup(REQUESTER), false);
	assert.equal(canChooseRemote(ADMIN), true);
	assert.equal(canChooseRemote(DOWNLOADER), true);
	assert.equal(canChooseRemote(BROWSER), false);
	assert.equal(canChooseRemote(null), false);
});

test('fileAction depends on the capabilities and the sources allowed', () => {
	assert.equal(fileAction(ADMIN, 'civarchive'), 'download');
	assert.equal(fileAction(DOWNLOADER, 'civitai'), 'download');
	assert.equal(fileAction(DOWNLOADER, 'openmodeldb'), 'source-blocked');
	assert.equal(fileAction(REQUESTER, 'civitai'), 'request');
	assert.equal(fileAction(BROWSER, 'civitai'), 'none');
	assert.equal(canDownloadFrom(DOWNLOADER, 'huggingface'), true);
	assert.equal(canDownloadFrom(REQUESTER, 'civitai'), false);
});

test('size limits apply to restricted users only, in GiB', () => {
	assert.equal(sizeLimitBytes(ADMIN), null);
	assert.equal(sizeLimitBytes(DOWNLOADER), 2 * 1024 ** 3);
	assert.equal(exceedsSizeLimit(DOWNLOADER, 2 * 1024 ** 3), false);
	assert.equal(exceedsSizeLimit(DOWNLOADER, 2 * 1024 ** 3 + 1), true);
	assert.equal(exceedsSizeLimit(DOWNLOADER, null), false);
	assert.equal(exceedsSizeLimit(ADMIN, 10 ** 13), false);
	assert.equal(exceedsSizeLimit(REQUESTER, 10 ** 13), false);
});

test('groupChoices puts the user first', () => {
	assert.deepEqual(groupChoices(DOWNLOADER), [
		{ id: '', name: 'Me' },
		{ id: 'g1', name: 'Artists' },
		{ id: 'g2', name: 'g2' }
	]);
	assert.deepEqual(groupChoices(BROWSER), [{ id: '', name: 'Me' }]);
});

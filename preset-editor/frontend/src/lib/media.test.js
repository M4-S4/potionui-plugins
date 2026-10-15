import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MEDIA_ACCEPT, formatBytes, galleryBody, galleryRows, isVideo, moveItem, rowsChanged } from './media.js';

test('gallery rows round-trip the manifest items and drop blank attributes', () => {
	const items = [{ src: 'public/examples/a.webp', caption: 'A', seed: 7 }, { src: 'public/examples/b.mp4', mode: 'txt2video', prompt: 'p' }];
	const rows = galleryRows(items);
	assert.deepEqual(rows[0], { src: 'public/examples/a.webp', caption: 'A', mode: '', prompt: '', seed: '7' });
	assert.deepEqual(galleryBody(rows), items);
	assert.equal(rowsChanged(rows, items), false);
	rows[0].caption = ' A ';
	rows[0].seed = 'x';
	assert.deepEqual(galleryBody(rows)[0], { src: 'public/examples/a.webp', caption: 'A' });
	assert.equal(rowsChanged(rows, items), true);
	assert.deepEqual(galleryRows(null), []);
	assert.deepEqual(galleryRows([null, 'x', { src: 'public/c.png' }]), [{ src: 'public/c.png', caption: '', mode: '', prompt: '', seed: '' }]);
});

test('moveItem reorders within bounds and leaves the list alone otherwise', () => {
	const list = ['a', 'b', 'c'];
	assert.deepEqual(moveItem(list, 0, 2), ['b', 'c', 'a']);
	assert.deepEqual(moveItem(list, 2, 0), ['c', 'a', 'b']);
	assert.equal(moveItem(list, 0, 3), list);
	assert.equal(moveItem(list, -1, 0), list);
	assert.equal(moveItem(list, 1, 1), list);
	assert.deepEqual(list, ['a', 'b', 'c']);
});

test('media helpers describe files', () => {
	assert.equal(isVideo('public/cover.MP4'), true);
	assert.equal(isVideo('public/cover.webp'), false);
	assert.equal(formatBytes(512), '512 B');
	assert.equal(formatBytes(2048), '2 KB');
	assert.equal(formatBytes(3 * 1024 * 1024 + 1), '3.0 MB');
	assert.equal(formatBytes(NaN), '');
	assert.equal(MEDIA_ACCEPT, '.jpg,.jpeg,.png,.webp,.gif,.mp4,.webm');
});

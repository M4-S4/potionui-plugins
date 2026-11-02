import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LOCAL_KINDS, UPLOAD_EXTENSIONS, UPLOAD_PURPOSE, acceptFor, dragVerdict, extensionOf, fileKind, hasFiles, importQueue, rowKinds, sortFiles, uploadForm, uploadType } from './upload.js';
import { coreUpload, createClient } from './api.js';

const file = (name, type = '', size = 4) => new File([new Uint8Array(size)], name, { type });

test('upload: a file kind comes from its extension, in any case, among the extensions PotionUI accepts', () => {
	assert.equal(extensionOf('Harbour.At.Dawn.MP4'), '.mp4');
	assert.equal(extensionOf('notes'), '');
	assert.equal(extensionOf('dir.v2/notes'), '');
	assert.deepEqual(['a.JPG', 'b.webm', 'c.Flac', 'd.svg', 'e.glb', 'f', 'g.tar.gz'].map(fileKind), ['image', 'video', 'audio', null, null, null, null]);
	const all = Object.values(UPLOAD_EXTENSIONS).flat();
	assert.equal(new Set(all).size, all.length);
	assert.ok(all.every((ext) => /^\.[a-z0-9]+$/.test(ext)));
});

test('upload: the picker filter lists images, videos and audio for the media, audio alone for the mixer', () => {
	const media = acceptFor(LOCAL_KINDS.media).split(',');
	const audio = acceptFor(LOCAL_KINDS.audio).split(',');
	assert.deepEqual(media, [...UPLOAD_EXTENSIONS.image, ...UPLOAD_EXTENSIONS.video, ...UPLOAD_EXTENSIONS.audio]);
	assert.deepEqual(audio, UPLOAD_EXTENSIONS.audio);
	assert.ok(!audio.includes('.png'));
});

test('upload: files are sorted into accepted ones, with their kind, and refused ones', () => {
	const files = [file('a.png'), file('b.mov'), file('c.wav'), file('d.pdf'), file('e')];
	const media = sortFiles(files, LOCAL_KINDS.media);
	assert.deepEqual(
		media.accepted.map(({ file: f, kind }) => [f.name, kind]),
		[
			['a.png', 'image'],
			['b.mov', 'video'],
			['c.wav', 'audio']
		]
	);
	assert.deepEqual(media.rejected.map((f) => f.name), ['d.pdf', 'e']);
	const audio = sortFiles(files, LOCAL_KINDS.audio);
	assert.deepEqual(audio.accepted.map(({ file: f }) => f.name), ['c.wav']);
	assert.deepEqual(sortFiles(null, LOCAL_KINDS.media), { accepted: [], rejected: [] });
});

test('upload: the type sent is the browser’s when it matches the kind, else the one of the extension', () => {
	assert.equal(uploadType(file('a.png', 'image/png')), 'image/png');
	assert.equal(uploadType(file('b.mkv', '')), 'video/x-matroska');
	assert.equal(uploadType(file('c.m4a', 'application/octet-stream')), 'audio/mp4');
	assert.equal(uploadType(file('d.flac', 'audio/x-flac')), 'audio/x-flac');
	assert.equal(uploadType(file('e.pdf', 'application/pdf')), 'application/pdf');
});

test('upload: the form carries the file, typed, under its own name, and the library purpose', async () => {
	const form = uploadForm(file('Take 1.mkv', '', 9));
	const sent = form.get('file');
	assert.equal(sent.name, 'Take 1.mkv');
	assert.equal(sent.type, 'video/x-matroska');
	assert.equal(sent.size, 9);
	assert.equal(form.get('purpose'), UPLOAD_PURPOSE);
	assert.equal(UPLOAD_PURPOSE, 'user_upload');
	const typed = file('a.png', 'image/png');
	assert.equal(uploadForm(typed).get('file').type, 'image/png');
});

const transfer = (types, items = []) => ({ types, items: items.map((type) => ({ kind: 'file', type })) });

test('upload: a drag says whether it carries files and whether the target takes them', () => {
	assert.equal(hasFiles(transfer(['Files'])), true);
	assert.equal(hasFiles(transfer(['text/x-asset'])), false);
	assert.equal(hasFiles(null), false);
	assert.equal(dragVerdict(transfer(['text/x-asset']), LOCAL_KINDS.media), null);
	assert.equal(dragVerdict(transfer(['Files'], ['image/png']), LOCAL_KINDS.media), 'accept');
	assert.equal(dragVerdict(transfer(['Files'], ['image/png']), LOCAL_KINDS.audio), 'reject');
	assert.equal(dragVerdict(transfer(['Files'], ['application/pdf', 'audio/wav']), LOCAL_KINDS.audio), 'accept');
	assert.equal(dragVerdict(transfer(['Files'], ['']), LOCAL_KINDS.audio), 'accept');
	assert.equal(dragVerdict(transfer(['Files'], []), LOCAL_KINDS.audio), 'accept');
});

test('upload: the video track and the frames row take images and videos, an audio track audio, the other rows nothing', () => {
	assert.deepEqual(rowKinds({ id: 'v1' }), ['image', 'video']);
	assert.deepEqual(rowKinds({ id: 'frames' }), ['image', 'video']);
	assert.deepEqual(rowKinds({ id: 'A2', lane: { id: 'A2' } }), ['audio']);
	assert.deepEqual(rowKinds({ id: 'titles' }), []);
});

function queue({ uploads = {}, resolves = {} } = {}) {
	const log = [];
	const states = new Map();
	return {
		log,
		states,
		options: {
			allowed: LOCAL_KINDS.media,
			update: (entry, patch) => {
				states.set(entry.id, { ...states.get(entry.id), ...patch });
				if ('progress' in patch && patch.status === undefined) log.push(`progress ${entry.id} ${patch.progress}`);
			},
			upload: async (entry, onProgress) => {
				log.push(`upload ${entry.id}`);
				onProgress(50);
				await Promise.resolve();
				log.push(`uploaded ${entry.id}`);
				return uploads[entry.id] ?? { ok: true, data: { filename: `${entry.id}.bin` } };
			},
			resolve: async (filename) => {
				log.push(`resolve ${filename}`);
				return resolves[filename] ?? { ok: true, data: { mediaType: 'image', url: `/api/media/uploads/${filename}`, filename, origin: { kind: 'library', itemId: `item-${filename}` } } };
			}
		}
	};
}

test('upload: the queue sends one file at a time, reports its progress, then resolves it', async () => {
	const q = queue();
	const results = await importQueue([{ id: 'a' }, { id: 'b' }], q.options);
	assert.deepEqual(q.log, ['upload a', 'progress a 50', 'uploaded a', 'resolve a.bin', 'upload b', 'progress b 50', 'uploaded b', 'resolve b.bin']);
	assert.deepEqual(results.map((r) => r.media.origin.itemId), ['item-a.bin', 'item-b.bin']);
	assert.deepEqual(q.states.get('a'), { status: 'done', progress: 100 });
});

test('upload: a refused upload, a lost item and a kind the target does not take each fail on their own', async () => {
	const q = queue({
		uploads: { a: { ok: false, error: { status: 403, code: 'storage_limit', message: 'Storage plan full' } }, d: { ok: true, data: {} } },
		resolves: {
			'b.bin': { ok: false, error: { status: 404, code: 'media_not_found' } },
			'c.bin': { ok: true, data: { mediaType: 'audio', url: '/x', filename: 'c', origin: { kind: 'library', itemId: 'i' } } }
		}
	});
	const results = await importQueue([{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }, { id: 'e' }], { ...q.options, allowed: ['image'] });
	assert.deepEqual(
		results.map((r) => r.error?.code ?? 'ok'),
		['storage_limit', 'media_not_found', 'unsupported_media', 'invalid_response', 'ok']
	);
	assert.ok(!q.log.includes('resolve a.bin'));
	assert.equal(q.states.get('a').status, 'failed');
	assert.equal(q.states.get('e').status, 'done');
});

test('upload: a cancelled file is skipped and an aborted one ends cancelled', async () => {
	const q = queue({ uploads: { b: { ok: false, error: { status: 0, code: 'aborted' } } } });
	const results = await importQueue([{ id: 'a', cancelled: true }, { id: 'b' }, { id: 'c' }], q.options);
	assert.deepEqual(results.map((r) => r.error?.code ?? 'ok'), ['aborted', 'aborted', 'ok']);
	assert.ok(!q.log.includes('upload a'));
	assert.equal(q.states.get('b').status, 'cancelled');
});

function hostApi(answer, seen = []) {
	return {
		seen,
		async fetchRawFromApp(path, init) {
			seen.push([path, init]);
			return answer(init);
		}
	};
}

test('coreUpload: posts the form to PotionUI through the host fetch and reports the progress', async () => {
	const progress = [];
	const api = hostApi((init) => {
		init.onUploadProgress(5, 20);
		init.onUploadProgress(20, 20);
		init.onUploadProgress(3, 0);
		return new Response(JSON.stringify({ success: true, data: { filename: '9b1c.mp4', url: '/api/media/uploads/9b1c.mp4' } }), { status: 200 });
	});
	const controller = new AbortController();
	const result = await coreUpload(api, '/api/media/upload', 'FORM', { onProgress: (p) => progress.push(p), signal: controller.signal });
	assert.deepEqual(result, { ok: true, data: { filename: '9b1c.mp4', url: '/api/media/uploads/9b1c.mp4' } });
	const [[path, init]] = api.seen;
	assert.deepEqual([path, init.method, init.body, init.signal], ['/api/media/upload', 'POST', 'FORM', controller.signal]);
	assert.equal('headers' in init, false);
	assert.deepEqual(progress, [25, 100]);
});

test('coreUpload: an error answer, a lost connection and an abort become failures', async () => {
	const answer = (status, body) => hostApi(() => new Response(body, { status }));
	const refused = await coreUpload(answer(403, JSON.stringify({ detail: { success: false, error: 'storage_limit', message: 'full' } })), '/u', null);
	assert.deepEqual([refused.ok, refused.error.status, refused.error.code, refused.error.message], [false, 403, 'storage_limit', 'full']);
	const hostRefusal = await coreUpload(answer(400, JSON.stringify({ detail: { error: 'upload_failed', message: 'Only image, video, and audio files are allowed' } })), '/u', null);
	assert.equal(hostRefusal.error.code, 'upload_failed');
	const tooLarge = await coreUpload(answer(413, '<html>'), '/u', null);
	assert.deepEqual([tooLarge.error.status, tooLarge.error.code], [413, 'unknown']);
	const expired = await coreUpload(answer(401, JSON.stringify({ detail: 'Not authenticated' })), '/u', null);
	assert.deepEqual([expired.error.status, expired.error.code], [401, 'unauthorized']);
	const lost = await coreUpload(hostApi(() => Promise.reject(new TypeError('Network Error'))), '/u', null);
	assert.equal(lost.error.code, 'network_error');
	const aborted = await coreUpload(hostApi(() => Promise.reject(new DOMException('The operation was aborted', 'AbortError'))), '/u', null);
	assert.equal(aborted.error.code, 'aborted');
	const early = new AbortController();
	early.abort();
	const untouched = hostApi(() => new Response('{}'));
	assert.equal((await coreUpload(untouched, '/u', null, { signal: early.signal })).error.code, 'aborted');
	assert.deepEqual(untouched.seen, []);
	assert.equal((await coreUpload({ getToken: () => 'tok' }, '/u', null)).error.code, 'no_api');
});

test('client: an uploaded file is resolved by its stored name', async () => {
	const calls = [];
	const media = { kind: 'library', media_type: 'audio', url: '/api/media/uploads/a.wav', filename: 'Rain.wav', origin: { kind: 'library', itemId: 'i1' } };
	const client = createClient({
		async request(method, path, data) {
			calls.push([method, path, data]);
			return { success: true, data: { media } };
		}
	});
	const result = await client.uploadedMedia('a.wav');
	assert.deepEqual(calls, [['POST', '/media/uploaded', { filename: 'a.wav' }]]);
	assert.deepEqual(result.data, { kind: 'library', mediaType: 'audio', url: '/api/media/uploads/a.wav', filename: 'Rain.wav', origin: { kind: 'library', itemId: 'i1' } });
});

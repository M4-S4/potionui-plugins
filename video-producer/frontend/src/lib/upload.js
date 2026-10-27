export const UPLOAD_EXTENSIONS = {
	image: ['.bmp', '.gif', '.jpeg', '.jpg', '.png', '.webp'],
	video: ['.avi', '.mkv', '.mov', '.mp4', '.webm'],
	audio: ['.aac', '.flac', '.m4a', '.mp3', '.ogg', '.wav']
};

const MIME_TYPES = {
	'.bmp': 'image/bmp',
	'.gif': 'image/gif',
	'.jpeg': 'image/jpeg',
	'.jpg': 'image/jpeg',
	'.png': 'image/png',
	'.webp': 'image/webp',
	'.avi': 'video/x-msvideo',
	'.mkv': 'video/x-matroska',
	'.mov': 'video/quicktime',
	'.mp4': 'video/mp4',
	'.webm': 'video/webm',
	'.aac': 'audio/aac',
	'.flac': 'audio/flac',
	'.m4a': 'audio/mp4',
	'.mp3': 'audio/mpeg',
	'.ogg': 'audio/ogg',
	'.wav': 'audio/wav'
};

export const LOCAL_KINDS = { media: ['image', 'video', 'audio'], audio: ['audio'] };
export const UPLOAD_PURPOSE = 'user_upload';

export function extensionOf(name) {
	const match = /\.[^./\\]+$/.exec(String(name ?? ''));
	return match ? match[0].toLowerCase() : '';
}

export function fileKind(name) {
	const ext = extensionOf(name);
	return Object.keys(UPLOAD_EXTENSIONS).find((kind) => UPLOAD_EXTENSIONS[kind].includes(ext)) ?? null;
}

export function acceptFor(kinds) {
	return kinds.flatMap((kind) => UPLOAD_EXTENSIONS[kind] ?? []).join(',');
}

export function uploadType(file) {
	const kind = fileKind(file?.name);
	const type = String(file?.type ?? '');
	return kind && type.startsWith(`${kind}/`) ? type : (MIME_TYPES[extensionOf(file?.name)] ?? type);
}

export function sortFiles(files, kinds) {
	const accepted = [];
	const rejected = [];
	for (const file of Array.from(files ?? [])) {
		const kind = fileKind(file?.name);
		if (kind && kinds.includes(kind)) accepted.push({ file, kind });
		else rejected.push(file);
	}
	return { accepted, rejected };
}

export function hasFiles(dataTransfer) {
	return Array.from(dataTransfer?.types ?? []).includes('Files');
}

export function dragVerdict(dataTransfer, kinds) {
	if (!hasFiles(dataTransfer)) return null;
	const types = Array.from(dataTransfer.items ?? [])
		.filter((item) => item.kind === 'file')
		.map((item) => String(item.type ?? ''));
	if (!types.length || types.some((type) => !type)) return 'accept';
	return types.some((type) => kinds.some((kind) => type.startsWith(`${kind}/`))) ? 'accept' : 'reject';
}

export function rowKinds(row) {
	if (row?.vtrack) return ['video'];
	if (row?.lane) return ['audio'];
	if (row?.id === 'v1' || row?.id === 'frames') return ['image', 'video'];
	return [];
}

export function uploadForm(file) {
	const form = new FormData();
	const type = uploadType(file);
	form.append('file', type && type !== file.type ? new File([file], file.name, { type }) : file, file.name);
	form.append('purpose', UPLOAD_PURPOSE);
	return form;
}

export async function importQueue(entries, { upload, resolve, update, allowed }) {
	const results = [];
	for (const entry of entries) {
		if (entry.cancelled) {
			results.push({ entry, error: { code: 'aborted' } });
			continue;
		}
		update(entry, { status: 'uploading', progress: 0 });
		const sent = await upload(entry, (progress) => update(entry, { progress }));
		const filename = sent.ok ? sent.data?.filename : null;
		const found = filename ? await resolve(filename) : sent;
		const media = found?.ok ? found.data : null;
		const error = !sent.ok ? sent.error : !filename ? { code: 'invalid_response' } : !found?.ok ? found?.error : !media || !allowed.includes(media.mediaType) ? { code: 'unsupported_media' } : null;
		update(entry, error ? { status: error.code === 'aborted' ? 'cancelled' : 'failed', error } : { status: 'done', progress: 100 });
		results.push(error ? { entry, error } : { entry, media });
	}
	return results;
}

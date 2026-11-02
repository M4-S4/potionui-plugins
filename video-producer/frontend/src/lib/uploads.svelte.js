import { ulid } from './ulid.js';

const LINGER = { done: 1500, cancelled: 1500, failed: 6000 };
const entries = new Map();

export const uploads = $state({ items: [] });

export function trackUploads(accepted) {
	const made = accepted.map(({ file, kind }) => ({ id: ulid(), file, kind, controller: new AbortController(), cancelled: false }));
	for (const entry of made) entries.set(entry.id, entry);
	uploads.items.push(...made.map(({ id, file, kind }) => ({ id, name: file.name, kind, size: file.size, progress: 0, status: 'waiting', error: null })));
	return made;
}

export function updateUpload(entry, patch) {
	const item = uploads.items.find((x) => x.id === entry.id);
	if (!item) return;
	Object.assign(item, patch);
	if (LINGER[item.status]) {
		entries.delete(item.id);
		setTimeout(() => dismissUpload(item.id), LINGER[item.status]);
	}
}

export function dismissUpload(id) {
	const i = uploads.items.findIndex((x) => x.id === id);
	if (i >= 0) uploads.items.splice(i, 1);
}

export function cancelUpload(id) {
	const entry = entries.get(id);
	if (!entry) return;
	entry.cancelled = true;
	entry.controller.abort();
	if (uploads.items.find((x) => x.id === id)?.status === 'waiting') updateUpload(entry, { status: 'cancelled' });
}

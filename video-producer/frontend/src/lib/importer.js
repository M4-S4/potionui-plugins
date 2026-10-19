import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, asset, newAsset, toast } from './state.svelte.js';
import { getClient } from './project.svelte.js';
import { normalizeOrigin } from './api.js';
import { openHostModal } from './host.js';
import { probeMedia } from './sources.svelte.js';

const KINDS = { media: ['image', 'video'], audio: ['audio'] };
const probing = new Set();
const probed = new Set();

function open(name, props, allowed) {
	if (ui.hostModal) return;
	const close = openHostModal(name, {
		...props,
		multiple: true,
		selectedKeys: [],
		selectableMediaTypes: allowed,
		onConfirm: (keys, items) => importItems(items, allowed),
		onClosed: () => (ui.hostModal = false)
	});
	if (!close) return toast(t('project.toast.pickerMissing'), 'warning');
	ui.hostModal = true;
	ui.menuOpen = null;
	ui.paletteOpen = false;
}

export function openImport(kind = 'media') {
	const allowed = KINDS[kind] ?? KINDS.media;
	open('UploadLibraryModal', { title: kind === 'audio' ? t('project.import.titleAudio') : t('project.import.titleMedia'), mediaType: kind === 'audio' ? 'audio' : undefined }, allowed);
}

export function openGallery() {
	open('GenerationHistoryModal', { title: t('project.import.titleGallery') }, KINDS.media);
}

export function libraryAvailable() {
	return typeof window !== 'undefined' && Boolean(window.__potionui?.components?.UploadLibraryModal);
}

export function openLibrary(title) {
	open('UploadLibraryModal', { title, mediaType: 'video' }, ['video']);
}

export function pickImage(title, onPicked) {
	if (ui.hostModal) return;
	const close = openHostModal('UploadLibraryModal', {
		title,
		mediaType: 'image',
		onSelect: async (item) => {
			close?.();
			const id = await importImage(item?.id ? { origin: { kind: 'library', itemId: item.id }, filename: item.original_filename || item.filename } : null);
			if (id) onPicked(id);
		},
		onClosed: () => (ui.hostModal = false)
	});
	if (!close) return toast(t('project.toast.pickerMissing'), 'warning');
	ui.hostModal = true;
}

async function importImage(item) {
	const origin = normalizeOrigin(item?.origin);
	const key = originKey(origin);
	if (!key) return null;
	const existing = doc.assets.find((a) => originKey(a.origin) === key);
	if (existing) return existing.id;
	const result = await getClient()?.resolveMedia(origin);
	const media = result?.ok ? result.data : null;
	if (!media || media.mediaType !== 'image') {
		toast(t('project.toast.importFailed', { count: 1 }), 'warning');
		return null;
	}
	const made = newAsset({ kind: 'image', name: media.filename || item.filename || t('project.import.untitled'), src: media.url, origin });
	act(() => doc.assets.push(made));
	probeAsset(made.id);
	return made.id;
}

const originKey = (o) => (o?.kind === 'history' ? `history:${o.generationId}:${o.fileId}` : o?.kind === 'library' ? `library:${o.itemId}` : null);

function fpsOf(item) {
	const fps = Number(item?.item?.fps);
	return Number.isFinite(fps) && fps > 0 ? fps : null;
}

async function importItems(items, allowed) {
	const client = getClient();
	if (!client || !items?.length) return;
	const seen = new Set(doc.assets.map((a) => originKey(a.origin)).filter(Boolean));
	const picked = [];
	let present = 0;
	for (const item of items) {
		const origin = normalizeOrigin(item?.origin);
		const key = originKey(origin);
		if (key && seen.has(key)) {
			present += 1;
			continue;
		}
		if (key) seen.add(key);
		picked.push({ item, origin });
	}
	const results = await Promise.all(picked.map(({ origin }) => (origin ? client.resolveMedia(origin) : null)));
	const made = [];
	let failed = 0;
	results.forEach((result, i) => {
		const media = result?.ok ? result.data : null;
		if (!media || !allowed.includes(media.mediaType)) {
			failed += 1;
			return;
		}
		made.push(newAsset({ kind: media.mediaType, name: media.filename || picked[i].item.filename || t('project.import.untitled'), src: media.url, origin: picked[i].origin, fps: fpsOf(picked[i].item) }));
	});
	if (made.length) {
		act(() => doc.assets.push(...made));
		ui.mediaCollection = 'all';
		for (const a of made) probeAsset(a.id);
	}
	const imported = t('project.toast.imported', { count: made.length });
	if (made.length && present) toast(t('project.toast.importSummary', { imported, present: t('project.toast.alreadyPresent', { count: present }) }), 'success');
	else if (made.length) toast(imported, 'success');
	else if (present) toast(t('project.toast.alreadyPresent', { count: present }), 'info');
	if (failed) toast(t('project.toast.importFailed', { count: failed }), 'warning');
}

export function needsProbe(a) {
	if (!a?.src || probed.has(a.id) || probing.has(a.id)) return false;
	if (a.kind === 'image') return a.width === null;
	if (a.kind === 'video') return a.srcDur === null || a.width === null;
	return a.srcDur === null;
}

export async function probeAsset(id) {
	const a = asset(id);
	if (!needsProbe(a)) return;
	probing.add(id);
	const info = await probeMedia(a);
	probing.delete(id);
	probed.add(id);
	const target = asset(id);
	if (!info || !target) return;
	if (info.srcDur !== null) target.srcDur = info.srcDur;
	if (info.width && info.height) {
		target.width = info.width;
		target.height = info.height;
		target.res = `${info.width}×${info.height}`;
	}
}

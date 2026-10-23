import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, asset, newAsset, toast, round, addFrame, addAssetToTimeline } from './state.svelte.js';
import { getClient, project } from './project.svelte.js';
import { normalizeOrigin } from './api.js';
import { openHostModal } from './host.js';
import { probeMedia } from './sources.svelte.js';
import { LOCAL_KINDS, acceptFor, fileKind, importQueue, sortFiles, uploadForm } from './upload.js';
import { trackUploads, updateUpload } from './uploads.svelte.js';
import { ulid } from './ulid.js';
import { laneCode } from './tracks.js';

const KINDS = { media: ['image', 'video'], audio: ['audio'] };
const probing = new Map();
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

export function pickMedia(kind, title, onPicked) {
	if (ui.hostModal) return;
	const close = openHostModal('UploadLibraryModal', {
		title,
		mediaType: kind,
		onSelect: async (item) => {
			close?.();
			const id = await importPicked(item?.id ? { origin: { kind: 'library', itemId: item.id }, filename: item.original_filename || item.filename } : null, kind);
			if (id) onPicked(id);
		},
		onClosed: () => (ui.hostModal = false)
	});
	if (!close) return toast(t('project.toast.pickerMissing'), 'warning');
	ui.hostModal = true;
}

export const pickImage = (title, onPicked) => pickMedia('image', title, onPicked);

async function importPicked(item, kind) {
	const origin = normalizeOrigin(item?.origin);
	const key = originKey(origin);
	if (!key) return null;
	const existing = doc.assets.find((a) => originKey(a.origin) === key);
	if (existing) return existing.id;
	const result = await getClient()?.resolveMedia(origin);
	const media = result?.ok ? result.data : null;
	if (!media || media.mediaType !== kind) {
		toast(t('project.toast.importFailed', { count: 1 }), 'warning');
		return null;
	}
	const made = newAsset({ kind, name: media.filename || item.filename || t('project.import.untitled'), src: media.url, origin });
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
	addAssets(made);
	report(made.length, present, failed);
}

function addAssets(made) {
	if (!made.length) return;
	act(() => doc.assets.push(...made));
	ui.mediaCollection = 'all';
	for (const a of made) probeAsset(a.id);
}

function report(made, present, failed) {
	const imported = t('project.toast.imported', { count: made });
	if (made && present) toast(t('project.toast.importSummary', { imported, present: t('project.toast.alreadyPresent', { count: present }) }), 'success');
	else if (made) toast(imported, 'success');
	else if (present) toast(t('project.toast.alreadyPresent', { count: present }), 'info');
	if (failed) toast(t('project.toast.importFailed', { count: failed }), 'warning');
}

let chain = Promise.resolve();

export function openLocalImport(kind = 'media') {
	if (typeof document === 'undefined') return;
	const kinds = LOCAL_KINDS[kind] ?? LOCAL_KINDS.media;
	const input = document.createElement('input');
	input.type = 'file';
	input.multiple = true;
	input.accept = acceptFor(kinds);
	input.onchange = () => importFiles(input.files, kinds);
	ui.menuOpen = null;
	ui.paletteOpen = false;
	input.click();
}

export function pickLocalMedia(kind, onPicked) {
	if (typeof document === 'undefined') return;
	const input = document.createElement('input');
	input.type = 'file';
	input.accept = acceptFor([kind]);
	input.onchange = () => importFiles(input.files, [kind], { pick: onPicked, kind });
	input.click();
}

export const pickLocalImage = (onPicked) => pickLocalMedia('image', onPicked);

function refusal(rejected, target) {
	const params = { count: rejected.length, name: rejected[0].name };
	if (!rejected.every((f) => fileKind(f.name))) return t('project.upload.unsupported', params);
	if (target?.pick) return target.kind === 'audio' ? t('project.upload.soundOnly', params) : t('project.upload.imageOnly', params);
	return target ? t('timeline.toast.dropHint') : t('project.upload.audioOnly', params);
}

export function importFiles(files, kinds = LOCAL_KINDS.media, target = null) {
	const { accepted, rejected } = sortFiles(files, kinds);
	if (rejected.length) toast(refusal(rejected, target), 'warning');
	if (!accepted.length) return Promise.resolve();
	const entries = trackUploads(accepted);
	const run = chain.then(() => uploadAll(entries, kinds, target));
	chain = run.catch(() => {});
	return run;
}

function failureReason(error) {
	if (error?.code === 'unsupported_media' || error?.status === 415) return t('project.upload.reasonType');
	if (error?.status === 413) return t('project.upload.reasonSize');
	if (error?.code === 'network_error') return t('project.upload.reasonNetwork');
	return error?.message || t('project.upload.reasonServer');
}

async function uploadAll(entries, kinds, target) {
	const client = getClient();
	const projectId = project.id;
	const results = await importQueue(entries, {
		upload: (entry, onProgress) => (client ? client.uploadMedia(uploadForm(entry.file), { onProgress, signal: entry.controller.signal }) : { ok: false, error: { code: 'no_api' } }),
		resolve: (filename) => client.uploadedMedia(filename),
		update: updateUpload,
		allowed: kinds
	});
	if (project.id !== projectId) return;
	const byOrigin = new Map(doc.assets.map((a) => [originKey(a.origin), a]).filter(([key]) => key));
	const made = [];
	const placed = [];
	let present = 0;
	for (const { entry, media, error } of results) {
		if (error) {
			if (error.code !== 'aborted') toast(t('project.upload.failed', { name: entry.file.name, reason: failureReason(error) }), 'error');
			continue;
		}
		const key = originKey(media.origin);
		let a = key ? byOrigin.get(key) : null;
		if (a) present += 1;
		else {
			a = newAsset({ kind: media.mediaType, name: media.filename || entry.file.name || t('project.import.untitled'), src: media.url, origin: media.origin });
			made.push(a);
			if (key) byOrigin.set(key, a);
		}
		placed.push(a.id);
	}
	addAssets(made);
	if (target?.pick) {
		report(made.length, present, 0);
		if (placed.length) target.pick(placed[0]);
	} else if (target) await placeAll(placed, target);
	else report(made.length, present, 0);
}

async function placeAll(ids, target) {
	let at = target.at;
	for (const id of ids) {
		await probeAsset(id).catch(() => {});
		const end = placeAsset(id, target.row, at);
		if (end !== null) at = end;
	}
}

export function placeAsset(id, row, at) {
	const a = asset(id);
	if (!a) return null;
	const start = round(at, 0.04);
	if (row.id === 'frames' && a.kind !== 'audio') {
		addFrame(id, start);
		return start;
	}
	if (row.lane && a.kind === 'audio') {
		const dur = Math.min(8, a.srcDur ?? 8);
		act(() => doc.audio.push({ id: ulid(), assetId: id, lane: row.id, start, dur, srcIn: 0, fadeIn: 0.5, fadeOut: 0.5, gain: -6 }));
		toast(t('timeline.toast.dropped', { name: a.name, lane: laneCode(doc.lanes, row.id) }));
		return start + dur;
	}
	if (row.id === 'v1' && a.kind !== 'audio') {
		addAssetToTimeline(id, start);
		const clip = doc.clips.find((c) => c.id === ui.selection?.id);
		return clip ? clip.start + clip.dur : start;
	}
	toast(t('timeline.toast.dropHint'), 'warning');
	return null;
}

export function needsProbe(a) {
	if (!a?.src || probed.has(a.id) || probing.has(a.id)) return false;
	if (a.kind === 'image') return a.width === null;
	if (a.kind === 'video') return a.srcDur === null || a.width === null;
	return a.srcDur === null;
}

export function probeAsset(id) {
	if (probing.has(id)) return probing.get(id);
	const a = asset(id);
	if (!needsProbe(a)) return Promise.resolve();
	const run = probe(id, a);
	probing.set(id, run);
	return run;
}

async function probe(id, a) {
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

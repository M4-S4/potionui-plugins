// The downloads tray: what each row of `GET /downloads` looks like, when to poll, and which rows
// finished during the session (for a toast). Rows are `{ pending, download }`: `pending` is the
// plugin's row (backend pending.py: status queued -> indexed -> assigned -> enriched, or failed),
// `download` the core's download record or null (status pending, downloading, paused, completed,
// failed, cancelled; progress 0 to 1). No Svelte in here: tested with `node --test`
// (see downloads.test.js).

import { formatBytes, formatSpeed, percent } from './format.js';

/** How often the tray asks again while a row is unfinished. */
export const POLL_INTERVAL_MS = 5000;

/** Rows the tray asks for. */
export const LIST_LIMIT = 30;

const PENDING_UNFINISHED = new Set(['queued', 'indexed', 'assigned']);
const PENDING_FINAL = new Set(['enriched', 'failed']);
const DOWNLOAD_UNFINISHED = new Set(['pending', 'downloading', 'paused']);

function isObject(value) {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** The rows of a `GET /downloads` answer that have a pending row. */
export function normalizeRows(data) {
	return (Array.isArray(data) ? data : []).filter((row) => isObject(row) && isObject(row.pending) && rowKey(row));
}

/** A row's identity: the pending row's key (a SHA256, or `nohash:<url>`). */
export function rowKey(row) {
	const key = row?.pending?.sha256;
	return typeof key === 'string' ? key : '';
}

/**
 * Whether a row is still moving: its pending row is queued, indexed or assigned, or the core
 * download is pending, downloading or paused. A pending row that is enriched or failed is done,
 * whatever the core download says.
 */
export function isUnfinished(row) {
	const pending = row?.pending?.status;
	if (PENDING_FINAL.has(pending)) return false;
	return PENDING_UNFINISHED.has(pending) || DOWNLOAD_UNFINISHED.has(row?.download?.status);
}

/** Whether the tray should poll again. */
export function shouldPoll(rows) {
	return rows.some(isUnfinished);
}

/** How many rows are unfinished (the count on the tray button). */
export function activeCount(rows) {
	return rows.filter(isUnfinished).length;
}

/** The model name of a row (or its file name). */
export function rowTitle(row) {
	const name = row?.pending?.info?.model?.name;
	if (typeof name === 'string' && name) return name;
	return row?.pending?.file_name || row?.download?.filename || 'Download';
}

/** The file of a row, with the version when known: 'detailTweaker.safetensors · v1.0'. */
export function rowSubtitle(row) {
	const file = row?.pending?.file_name || row?.download?.filename || '';
	const versions = row?.pending?.info?.model?.versions;
	const version = Array.isArray(versions) && versions.length ? versions[0]?.name : '';
	return [file, version].filter(Boolean).join(' · ');
}

/**
 * What the tray shows for a row.
 *
 * @returns {{ label: string, tone: 'neutral' | 'info' | 'signal' | 'warning' | 'success' | 'danger',
 *             progress: number | null, sizeText: string, speedText: string, error: string }}
 */
export function rowStatus(row) {
	const pending = row?.pending ?? {};
	const download = isObject(row?.download) ? row.download : null;
	const base = { progress: null, sizeText: '', speedText: '', error: '' };
	const downloaded = download?.downloaded_bytes;
	const total = download?.total_bytes;
	const sizeText =
		typeof total === 'number' && total > 0
			? `${formatBytes(typeof downloaded === 'number' ? downloaded : 0)} / ${formatBytes(total)}`
			: formatBytes(downloaded);

	switch (pending.status) {
		case 'enriched':
			return { ...base, label: 'Ready', tone: 'success', sizeText: typeof total === 'number' ? formatBytes(total) : '' };
		case 'failed':
			return { ...base, label: 'Failed', tone: 'danger', error: pending.error || download?.error_message || '' };
		case 'assigned':
			return { ...base, label: 'Filling in details', tone: 'info' };
		case 'indexed':
			return { ...base, label: 'Assigning', tone: 'info' };
		case 'queued':
			break;
		default:
			return { ...base, label: pending.status ? String(pending.status) : 'Unknown', tone: 'neutral' };
	}

	switch (download?.status) {
		case 'downloading':
			return {
				...base,
				label: 'Downloading',
				tone: 'signal',
				progress: percent(download.progress),
				sizeText,
				speedText: formatSpeed(download.speed_bytes_per_sec)
			};
		case 'paused':
			return { ...base, label: 'Paused', tone: 'warning', progress: percent(download.progress), sizeText };
		case 'completed':
			return { ...base, label: 'Indexing', tone: 'info', progress: 100, sizeText };
		case 'failed':
			return { ...base, label: 'Failed', tone: 'danger', error: download.error_message || pending.error || '' };
		case 'cancelled':
			return { ...base, label: 'Cancelled', tone: 'neutral', error: download.error_message || '' };
		default:
			return { ...base, label: 'Waiting', tone: 'neutral' };
	}
}

/**
 * Note a download just started (the `pending` row of a `POST /downloads` answer), so that its
 * end is reported even when it finishes before the next poll sees it unfinished.
 *
 * @param {Map<string, string>} seen
 * @param {any} pending
 * @returns {Map<string, string>}  A new map.
 */
export function noteStarted(seen, pending) {
	const next = new Map(seen);
	if (isObject(pending) && typeof pending.sha256 === 'string' && pending.sha256) {
		next.set(pending.sha256, typeof pending.status === 'string' ? pending.status : 'queued');
	}
	return next;
}

/**
 * The rows that reached `enriched` or `failed` since the last poll. A row first seen already
 * finished (before the session, or before the page loaded) is not reported.
 *
 * @param {Map<string, string>} seen  Last known pending status per row key.
 * @param {any[]} rows
 * @returns {{ events: { kind: 'done' | 'failed', key: string, row: any }[], seen: Map<string, string> }}
 */
export function detectTransitions(seen, rows) {
	const next = new Map(seen);
	const events = [];
	for (const row of rows) {
		const key = rowKey(row);
		if (!key) continue;
		const status = row.pending.status;
		const previous = seen.get(key);
		if (PENDING_FINAL.has(status) && previous !== undefined && !PENDING_FINAL.has(previous)) {
			events.push({ kind: status === 'enriched' ? 'done' : 'failed', key, row });
		}
		next.set(key, status);
	}
	return { events, seen: next };
}

/** The toast for a finished row. */
export function transitionToast(event) {
	const name = rowTitle(event.row);
	if (event.kind === 'done') return { level: 'success', message: `${name} is ready in your models` };
	const error = rowStatus(event.row).error;
	return { level: 'error', message: error ? `${name}: download failed (${error})` : `${name}: download failed` };
}

/**
 * The toast for the answer of `POST /downloads`.
 *
 * @param {any} data  `{ pending, download, already_installed, already_queued }`
 * @param {{ id: string, name: string }[]} [groups]  To name a target group.
 * @returns {{ level: 'success' | 'info', message: string }}
 */
export function startToast(data, groups = []) {
	const pending = isObject(data?.pending) ? data.pending : {};
	const file = pending.file_name || 'The file';
	if (data?.already_installed) {
		const target = typeof pending.assign_to === 'string' ? pending.assign_to : '';
		if (target.startsWith('group:')) {
			const id = target.slice('group:'.length);
			const name = groups.find((group) => group.id === id)?.name ?? id;
			return { level: 'success', message: `${file} is already installed, now assigned to the group ${name}` };
		}
		if (target.startsWith('user:')) return { level: 'success', message: `${file} is already installed, now assigned to you` };
		return { level: 'info', message: `${file} is already installed` };
	}
	if (data?.already_queued) return { level: 'info', message: `${file} is already being downloaded` };
	return { level: 'success', message: `Download started: ${file}` };
}

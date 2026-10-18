import { EXCHANGE } from './exchange.js';

export const VIDEO_FORMATS = ['master', 'web', 'social', 'archive'];
export const REAL_FORMATS = ['web', 'social'];
export const RESOLUTIONS = ['720p', '1080p', '4K'];
export const JOB_STATES = ['queued', 'running', 'done', 'failed', 'cancelled'];
export const JOB_STEPS = ['assemble', 'mix', 'transcode', 'store'];
export const EXPORT_ERROR_CODES = ['ffmpeg_unavailable', 'nothing_to_export', 'export_running', 'export_quota', 'not_ready', 'invalid_request', 'invalid_doc', 'ffmpeg_failed', 'transcode_failed', 'store_failed', 'cancelled'];
export const POLL_EVERY = 1000;
export const BACKGROUND_POLL_EVERY = 3000;
export const README_HREF = '/admin?tab=docs&doc=plugin%2Fvideo-producer%2FREADME';
export const FALLBACK_NAME = 'video-producer';
const LETTERS = { œ: 'oe', Œ: 'Oe', æ: 'ae', Æ: 'Ae', ß: 'ss', ẞ: 'SS', ø: 'o', Ø: 'O' };

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => (typeof value === 'string' ? value : '');
const number = (value) => (value === null || value === undefined || value === '' || !Number.isFinite(Number(value)) ? null : Number(value));
const idText = (value) => (typeof value === 'number' && Number.isFinite(value) ? String(value) : text(value) || null);

export const isRealFormat = (format) => REAL_FORMATS.includes(format);
export const isJobActive = (job) => job?.status === 'queued' || job?.status === 'running';

export function slugify(name) {
	const spaced = String(name ?? '')
		.trim()
		.replace(/\s+/g, '_') || FALLBACK_NAME;
	const ascii = spaced
		.replace(/[œŒæÆßẞøØ]/g, (letter) => LETTERS[letter])
		.normalize('NFKD')
		.replace(/[\u0080-\uffff]/g, '');
	return ascii.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._]+|[._]+$/g, '') || FALLBACK_NAME;
}

export const exchangeFile = (name, format) => `${slugify(name)}.${EXCHANGE[format].ext}`;
export const videoFile = (name, resolution) => `${slugify(name).slice(0, 80).replace(/[._]+$/, '') || FALLBACK_NAME}_${resolution}.mp4`;

export function exchangePath(projectId, format, media = 'path') {
	return `/projects/${encodeURIComponent(projectId)}/exports/${format}${media === 'name' ? '?media=name' : ''}`;
}

export const jobPath = (jobId) => `/exports/${encodeURIComponent(jobId)}`;
export const jobFilePath = (jobId) => `${jobPath(jobId)}/file`;

function normalizeFile(value) {
	if (!isObject(value) || !text(value.name)) return null;
	return { name: value.name, size: number(value.size), url: text(value.url) || null };
}

function normalizeJobMedia(value) {
	if (!isObject(value) || !idText(value.item_id)) return null;
	return { kind: text(value.kind) || 'library', itemId: idText(value.item_id), url: text(value.url) || null };
}

function normalizeJobError(value) {
	if (!isObject(value) || !text(value.code)) return null;
	return { code: value.code, message: text(value.message) };
}

export function normalizeJob(value) {
	if (!isObject(value) || !idText(value.id)) return null;
	const progress = number(value.progress);
	return {
		id: idText(value.id),
		projectId: idText(value.project_id),
		format: text(value.format) || null,
		resolution: text(value.resolution) || null,
		status: JOB_STATES.includes(value.status) ? value.status : 'queued',
		progress: progress === null ? 0 : Math.min(100, Math.max(0, progress)),
		step: JOB_STEPS.includes(value.step) ? value.step : null,
		file: normalizeFile(value.file),
		media: normalizeJobMedia(value.media),
		error: normalizeJobError(value.error),
		createdAt: text(value.created_at) || null,
		finishedAt: text(value.finished_at) || null
	};
}

export function sortJobs(jobs) {
	return [...jobs].sort((a, b) => String(b.createdAt ?? '').localeCompare(String(a.createdAt ?? '')));
}

export function currentJob(jobs) {
	return jobs.find(isJobActive) ?? null;
}

export function mergeJob(jobs, job) {
	const others = jobs.filter((x) => x.id !== job.id);
	return sortJobs([job, ...others]);
}

export function historyOf(jobs, job) {
	if (!job) return jobs;
	return [job, ...jobs.filter((x) => x.id !== job.id)];
}

export function pollDelay({ followed, shown }) {
	if (!followed) return 0;
	return shown ? POLL_EVERY : BACKGROUND_POLL_EVERY;
}

export const finishedNow = (before, job) => Boolean(before && job && before.id === job.id && isJobActive(before) && job.status === 'done');

export function filenameFrom(disposition) {
	const value = String(disposition ?? '');
	const encoded = value.match(/filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/);
	if (encoded) {
		try {
			return decodeURIComponent(encoded[1].trim());
		} catch {
			return encoded[1].trim();
		}
	}
	const plain = value.match(/filename\s*=\s*"?([^";]+)"?/);
	return plain ? plain[1].trim() : null;
}

export const lastSegment = (path) =>
	String(path ?? '')
		.split('?')[0]
		.split('/')
		.filter(Boolean)
		.pop() || null;

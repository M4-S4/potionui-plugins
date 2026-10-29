import { t } from '../i18n/index.svelte.js';
import { doc, ui, toast, clipLabel } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { MAKERS, srtCues } from './exchange.js';
import { EXPORT_ERROR_CODES, currentJob, exchangeFile, exchangePath, finishedNow, isJobActive, jobFilePath, mergeJob, pollDelay, sortJobs, videoFile } from './exports.js';
import { confirm } from './host.js';
import { libraryAvailable, openLibrary } from './importer.js';

export const exportState = $state({ projectId: null, job: null, jobs: [], loaded: false, starting: false, busy: null });

let pollTimer = null;
let pollEvery = 0;
let polling = false;
let watching = false;
let live = false;

const options = () => ({ label: clipLabel });
const gone = (error) => error?.code === 'project_not_found';

export const exchangeText = (format) => MAKERS[format](doc, options());
export const subtitleCues = () => srtCues(doc);
export const canShowLibrary = () => libraryAvailable();

const knownError = (code) => EXPORT_ERROR_CODES.includes(code);

export function exportErrorText(error) {
	const code = error?.code;
	if (knownError(code)) return t(`exports.error.${code}`);
	if (code === 'job_not_found' || code === 'not_found') return t('exports.failed.gone');
	return t('exports.failed.retry');
}

export function jobErrorText(job) {
	const error = job?.error;
	if (knownError(error?.code)) return t(`exports.error.${error.code}`);
	return error?.message || t('exports.failed.generic');
}

function failed(error) {
	if (gone(error)) return projectGone(project.id);
	toast(exportErrorText(error), error?.status === 409 || error?.status === 429 ? 'warning' : 'error');
}

function reset(projectId) {
	if (exportState.projectId === projectId) return;
	stopPolling();
	Object.assign(exportState, { projectId, job: null, jobs: [], loaded: false, starting: false, busy: null });
}

async function saved() {
	const ok = await flushSave();
	if (!ok || !project.id) {
		toast(t('exports.toast.saveFirst'), 'error');
		return false;
	}
	return true;
}

export async function exportExchange(format) {
	if (exportState.busy) return;
	exportState.busy = format;
	try {
		if (!(await saved())) return;
		const result = await getClient().download(exchangePath(project.id, format), exchangeFile(doc.name, format));
		if (!result.ok) return failed(result.error);
		toast(t('modals.export.downloaded', { file: result.data.filename }), 'success');
	} finally {
		exportState.busy = null;
	}
}

const fileOf = (job) => job.file?.name || videoFile(doc.name, job.resolution, job.format ?? 'web', job.stems);

function settle(job) {
	const before = exportState.job;
	if (before && before.id === job.id) exportState.job = job;
	exportState.jobs = mergeJob(exportState.jobs, job);
	if (finishedNow(before, job) && (!shown() || !canShowLibrary())) {
		toast(t('exports.toast.done', { file: fileOf(job) }), 'success', { label: t('exports.download'), run: () => downloadJob(job) });
	}
	schedule();
}

export async function listJobs() {
	const projectId = project.id;
	if (!projectId || !getClient()) return;
	reset(projectId);
	const result = await getClient().listExports(projectId);
	if (projectId !== project.id) return;
	exportState.loaded = true;
	if (!result.ok) {
		if (gone(result.error)) projectGone(projectId);
		return;
	}
	exportState.jobs = sortJobs(result.data);
	const active = currentJob(exportState.jobs);
	const mine = exportState.job ? exportState.jobs.find((j) => j.id === exportState.job.id) : null;
	exportState.job = active ?? mine ?? null;
	schedule();
}

export async function startVideoExport({ format, resolution, stems = false, ratio = null }) {
	if (exportState.starting || isJobActive(exportState.job)) return;
	exportState.starting = true;
	try {
		if (!(await saved())) return;
		const projectId = project.id;
		const result = await getClient().exportVideo(projectId, { format, resolution, stems, ...(ratio ? { ratio } : {}) });
		if (projectId !== project.id) return;
		if (!result.ok) {
			if (result.error.code === 'export_running') await listJobs();
			return failed(result.error);
		}
		exportState.job = result.data;
		exportState.jobs = mergeJob(exportState.jobs, result.data);
		schedule();
	} finally {
		exportState.starting = false;
	}
}

const shown = () => watching && ui.modal?.type === 'export';
const followed = () => live && Boolean(getClient()) && isJobActive(exportState.job) && exportState.projectId === project.id;

export async function pollJob() {
	const job = exportState.job;
	if (polling || !followed()) return schedule();
	polling = true;
	const projectId = project.id;
	const result = await getClient().exportJob(job.id);
	polling = false;
	if (!live || projectId !== project.id || exportState.job?.id !== job.id) return schedule();
	if (!result.ok) {
		if (result.error.status === 404) await listJobs();
		return schedule();
	}
	settle(result.data);
}

function schedule() {
	const every = pollDelay({ followed: followed(), shown: shown() });
	if (every === pollEvery) return;
	stopPolling();
	if (!every) return;
	pollTimer = setInterval(pollJob, every);
	pollEvery = every;
}

export function stopPolling() {
	clearInterval(pollTimer);
	pollTimer = null;
	pollEvery = 0;
}

export function watchExports() {
	watching = true;
	live = true;
	schedule();
	listJobs();
	return () => {
		watching = false;
		schedule();
	};
}

export function resumeExports() {
	live = true;
	return listJobs();
}

export async function cancelJob(job) {
	const result = await getClient().cancelExport(job.id);
	if (!result.ok && result.error.status !== 404 && result.error.status !== 409) return failed(result.error);
	if (result.ok && result.data) settle(result.data);
	else await listJobs();
}

export async function deleteJob(job) {
	const ok = await confirm({
		title: t('exports.delete.title'),
		message: t('exports.delete.message', { file: fileOf(job) }),
		variant: 'danger',
		confirmLabel: t('exports.delete.confirm'),
		cancelLabel: t('exports.delete.cancel')
	});
	if (!ok) return;
	const result = await getClient().cancelExport(job.id);
	if (!result.ok && result.error.status !== 404) return failed(result.error);
	exportState.jobs = exportState.jobs.filter((j) => j.id !== job.id);
	if (exportState.job?.id === job.id) exportState.job = null;
	toast(t('exports.toast.deleted'));
}

export async function downloadJob(job) {
	const result = await getClient().download(jobFilePath(job.id), fileOf(job));
	if (!result.ok) return failed(result.error);
	toast(t('modals.export.downloaded', { file: result.data.filename }), 'success');
}

export function showInLibrary() {
	ui.modal = null;
	openLibrary(t('exports.libraryTitle'));
}

export function disposeExports() {
	watching = false;
	live = false;
	stopPolling();
}

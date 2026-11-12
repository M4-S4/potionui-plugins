import { t } from '../i18n/index.svelte.js';
import { doc, ui, act, toast } from './state.svelte.js';
import { getClient, project } from './project.svelte.js';
import { FINISH_POLL_MS, FINISH_READ_TRIES, MAX_FINISH_RUNS, cleanFinishing, effectByKey, finishFailure, finishRequest, finishable, finishedName, finishingOf, settingOf, toolsById } from './finishing.js';

export const finishState = $state({ tools: null, loading: false, toolsFailed: false, runs: [] });

const planned = new Map();
const controls = new Map();

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const finishTiming = { wait: delay };

export const finishTools = () => toolsById(finishState.tools ?? []);

export function finishShown() {
	for (let i = finishState.runs.length - 1; i >= 0; i--) if (finishState.runs[i].projectId === project.id) return finishState.runs[i];
	return null;
}

export async function loadFinishing() {
	const client = getClient();
	if (!client || finishState.loading) return;
	finishState.loading = true;
	const result = await client.mediaTools('video');
	finishState.loading = false;
	if (result.ok) Object.assign(finishState, { tools: result.data, toolsFailed: false });
	else finishState.toolsFailed = true;
}

export function setFinish(key, patch) {
	const effect = effectByKey(key);
	if (!effect) return;
	act(() => {
		const all = { ...finishingOf(doc) };
		all[key] = { ...settingOf(all, effect, finishTools().get(effect.tool)), ...patch };
		const clean = cleanFinishing(all);
		if (clean) doc.master.finishing = clean;
		else delete doc.master.finishing;
	});
}

export function planFinish(jobId, steps, fileName) {
	if (!jobId || !steps?.length) return;
	planned.set(jobId, { steps, fileName, projectId: project.id });
}

export const finishPlanned = (jobId) => planned.has(jobId);

export function dropFinish(jobId) {
	const plan = planned.get(jobId) ?? null;
	planned.delete(jobId);
	return plan;
}

export function keepFinish(jobId, plan) {
	if (jobId && plan) planned.set(jobId, plan);
}

function record(fields) {
	const runs = [...finishState.runs.filter((run) => run.key !== fields.key), fields];
	for (let i = 0; runs.length > MAX_FINISH_RUNS && i < runs.length - 1; ) {
		if (runs[i].status === 'running') i += 1;
		else runs.splice(i, 1);
	}
	finishState.runs = runs;
	return finishState.runs[finishState.runs.length - 1];
}

function close(run, control, status, extra = {}) {
	if (control.stopped) return null;
	Object.assign(run, { status, cancelling: false, ...extra });
	controls.delete(run.key);
	if (ui.modal?.type !== 'export' || run.projectId !== project.id) tell(run);
	return status === 'done' ? run.item : null;
}

function tell(run) {
	if (run.status === 'done') toast(t('exports.finish.toastDone', { file: finishedName(run.fileName) }), 'success', { label: t('exports.finish.download'), run: () => downloadFinished(run) }, 6000);
	else if (run.status === 'failed') toast(`${finishFailureText(run)} ${t('exports.finish.rawKept')}`, run.failure === 'lost' ? 'warning' : 'error', undefined, 8000);
	else if (run.status === 'cancelled') toast(`${t('exports.finish.cancelled')} ${t('exports.finish.rawKept')}`, 'info');
}

function apply(run, control, data) {
	run.progress = data.progress;
	if (data.status === 'failed') return close(run, control, 'failed', { failure: finishFailure(data.error), message: data.error?.message ?? '' });
	if (data.status === 'cancelled') return close(run, control, 'cancelled');
	if (data.status !== 'completed') return undefined;
	const item = data.items.find((x) => x.mediaType === 'video') ?? null;
	return item ? close(run, control, 'done', { progress: 1, item }) : close(run, control, 'failed', { failure: 'failed' });
}

export async function finishJob(job, { wait = finishTiming.wait } = {}) {
	const plan = planned.get(job?.id);
	if (!plan || plan.projectId !== project.id) return null;
	planned.delete(job.id);
	const client = getClient();
	const fileName = !job.stems && job.file?.name ? job.file.name : plan.fileName;
	const control = { stopped: false };
	const run = record({ key: job.id, jobId: job.id, projectId: plan.projectId, runId: null, status: 'running', cancelling: false, progress: 0, item: null, failure: null, message: '', fileName });
	controls.set(run.key, control);
	if (!finishable(job) || !client) return close(run, control, 'failed', { failure: 'noLibrary' });
	const started = await client.startMediaRun(finishRequest(job.media.itemId, plan.steps));
	if (control.stopped) return null;
	if (!started.ok) return close(run, control, 'failed', { failure: finishFailure(started.error), message: started.error?.message ?? '' });
	run.runId = started.data.id;
	if (run.cancelling) await askCancel(run);
	let misses = 0;
	while (run.status === 'running') {
		await wait(FINISH_POLL_MS * 2 ** misses);
		if (control.stopped || run.status !== 'running') break;
		const read = await client.mediaRun(run.runId);
		if (control.stopped || run.status !== 'running') break;
		if (!read.ok) {
			misses += 1;
			if (read.error?.status === 404 || misses >= FINISH_READ_TRIES) return close(run, control, 'failed', { failure: 'lost', message: '' });
			continue;
		}
		misses = 0;
		const ended = apply(run, control, read.data);
		if (ended !== undefined) return ended;
	}
	return run.status === 'done' ? run.item : null;
}

async function askCancel(run) {
	const control = controls.get(run.key);
	if (!control) return;
	const result = await getClient()?.cancelMediaRun(run.runId);
	if (control.stopped || run.status !== 'running') return;
	if (!result?.ok) {
		run.cancelling = false;
		if (result?.error?.status === 404) return close(run, control, 'failed', { failure: 'lost', message: '' });
		return toast(t('exports.finish.cancelFailed'), 'error');
	}
	apply(run, control, result.data);
}

export async function cancelFinish() {
	const run = finishShown();
	if (!run || run.status !== 'running' || run.cancelling) return;
	run.cancelling = true;
	if (run.runId) await askCancel(run);
}

export async function downloadFinished(run = finishShown()) {
	if (run?.status !== 'done' || !run.item) return;
	const result = await getClient().downloadCore(run.item.url, finishedName(run.fileName));
	if (!result.ok) return toast(t('exports.finish.downloadFailed'), 'error');
	toast(t('modals.export.downloaded', { file: result.data.filename }), 'success');
}

export function finishFailureText(run) {
	if (run?.failure === 'busy') return t('exports.finish.failure.busy');
	if (run?.failure === 'gone') return t('exports.finish.failure.gone');
	if (run?.failure === 'lost') return t('exports.finish.failure.lost');
	if (run?.failure === 'noLibrary') return t('exports.finish.failure.noLibrary');
	return run?.message ? t('exports.finish.failure.failedWith', { message: run.message }) : t('exports.finish.failure.failed');
}

export function disposeFinishing() {
	for (const control of controls.values()) control.stopped = true;
	controls.clear();
	planned.clear();
	for (const run of finishState.runs) if (run.status === 'running') Object.assign(run, { status: 'failed', failure: 'lost', message: '', cancelling: false });
}

export function resetFinishing() {
	disposeFinishing();
	Object.assign(finishState, { tools: null, loading: false, toolsFailed: false, runs: [] });
}

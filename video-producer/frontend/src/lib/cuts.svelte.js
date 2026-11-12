import { t } from '../i18n/index.svelte.js';
import { ui, doc, asset, insertShots, select, toast, undo } from './state.svelte.js';
import { getClient, project } from './project.svelte.js';
import { insertIndex } from './band.js';
import { ulid } from './ulid.js';
import { MAX_CUT_SHOTS, POLL_MS, buildCuts, cutFailure, cutName, cutRequest } from './cuts.js';

export const cuts = $state({ status: 'idle', progress: 0, runId: null, failure: null, message: '' });

let ticket = 0;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function reset() {
	Object.assign(cuts, { status: 'idle', progress: 0, runId: null, failure: null, message: '' });
}

function failed(error) {
	Object.assign(cuts, { status: 'failed', progress: 0, runId: null, failure: cutFailure(error) ?? 'failed', message: error?.message ?? '' });
	return null;
}

export function cutFailureText(kind, message = '') {
	if (kind === 'none') return t('project.cuts.failure.none');
	if (kind === 'tooMany') return t('project.cuts.failure.tooMany', { max: MAX_CUT_SHOTS });
	if (kind === 'busy') return t('project.cuts.failure.busy');
	return message ? t('project.cuts.failure.failedWith', { message }) : t('project.cuts.failure.failed');
}

export function clearCuts() {
	if (cuts.status !== 'running') reset();
}

export async function findCuts({ assetId, sensitivity, shortest, mode = 'source', at = 'end' }, { wait = delay } = {}) {
	const source = asset(assetId);
	const client = getClient();
	const body = cutRequest(source?.origin, { sensitivity, shortest });
	if (!client || !body || cuts.status === 'running') return null;
	const mine = ++ticket;
	const projectId = project.id;
	Object.assign(cuts, { status: 'running', progress: 0, runId: null, failure: null, message: '' });
	const started = await client.startMediaRun(body);
	if (mine !== ticket) {
		if (started.ok) await client.cancelMediaRun(started.data.id);
		return null;
	}
	if (!started.ok) return failed(started.error);
	cuts.runId = started.data.id;
	let run = null;
	while (true) {
		await wait(POLL_MS);
		if (mine !== ticket) return null;
		const read = await client.mediaRun(started.data.id);
		if (mine !== ticket) return null;
		if (!read.ok) return failed(read.error);
		run = read.data;
		cuts.progress = run.progress;
		if (run.status === 'completed') break;
		if (run.status === 'failed') return failed(run.error);
		if (run.status === 'cancelled') {
			reset();
			return null;
		}
	}
	reset();
	const name = cutName(source?.name, t('project.cuts.untitled'));
	if (project.id !== projectId) {
		toast(t('project.cuts.elsewhere', { count: run.items.length }), 'info', undefined, 6000);
		return null;
	}
	return placeCuts(run.items, { mode, at, name });
}

export async function cancelCuts() {
	const runId = cuts.runId;
	ticket += 1;
	reset();
	if (runId) await getClient()?.cancelMediaRun(runId);
}

export function placeCuts(items, { mode, at, name }) {
	const built = buildCuts(items, { mode, label: (n) => t('project.cuts.shotLabel', { name, n }), makeId: ulid });
	if (!built.clips.length) {
		toast(t('project.cuts.empty'), 'warning');
		return null;
	}
	const index = insertIndex(doc.clips, at, ui.selection?.kind === 'clip' ? ui.selection.id : null);
	insertShots(index, built.clips, () => {
		doc.assets.push(...built.assets);
		if (built.references.length) doc.references.push(...built.references);
	});
	ui.workspace = 'storyboard';
	select('clip', built.clips[0].id);
	const count = built.clips.length;
	const message = mode === 'motion' ? t('project.cuts.addedMotion', { count, name }) : t('project.cuts.addedSource', { count, name });
	toast(message, 'success', { label: t('shell.toast.undo'), run: undo }, 6000);
	return built;
}

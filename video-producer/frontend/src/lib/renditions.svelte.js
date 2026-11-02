import { t } from '../i18n/index.svelte.js';
import { toast } from './state.svelte.js';
import { project, getClient, projectGone } from './project.svelte.js';
import { noteText } from './production.svelte.js';
import { isActiveRendition } from './cadence.js';

const POLL_EVERY = 5000;

export const renditionStore = $state({ projectId: null, list: [], loaded: false, sending: false });
export const conformEstimate = $state({ key: null, seconds: null, loading: false });

let timer = null;

const gone = (error) => error?.code === 'project_not_found';

function follow() {
	const active = renditionStore.list.some(isActiveRendition);
	if (active && !timer) timer = setInterval(() => loadRenditions(), POLL_EVERY);
	if (!active && timer) {
		clearInterval(timer);
		timer = null;
	}
}

export async function loadRenditions(projectId = project.id) {
	if (!projectId || !getClient()) return;
	if (renditionStore.projectId !== projectId) Object.assign(renditionStore, { projectId, list: [], loaded: false });
	const result = await getClient().listRenditions(projectId);
	if (projectId !== project.id || renditionStore.projectId !== projectId) return;
	if (!result.ok) {
		if (gone(result.error)) projectGone(projectId);
		return;
	}
	renditionStore.list = result.data ?? [];
	renditionStore.loaded = true;
	follow();
}

export function stopRenditions() {
	clearInterval(timer);
	timer = null;
	Object.assign(renditionStore, { projectId: null, list: [], loaded: false, sending: false });
}

export async function conformTakes(takeIds) {
	if (renditionStore.sending || !takeIds.length || !project.id) return false;
	renditionStore.sending = true;
	try {
		const projectId = project.id;
		const result = await getClient().orderRenditions(projectId, takeIds);
		if (projectId !== project.id) return false;
		if (!result.ok) {
			if (gone(result.error)) projectGone(projectId);
			else toast(t('generation.cadence.failed'), 'error');
			return false;
		}
		await loadRenditions(projectId);
		const { renditions, refused } = result.data;
		if (renditions.length) toast(t('generation.cadence.started', { count: renditions.length }), 'success');
		if (refused.length) toast(noteText(refused[0]), 'warning');
		return renditions.length > 0;
	} finally {
		renditionStore.sending = false;
	}
}

export async function cancelRendition(rendition) {
	const result = await getClient().cancelRendition(rendition.id);
	if (!result.ok && result.error.status !== 404) toast(t('generation.toast.actionFailed'), 'error');
	await loadRenditions();
}

export async function estimateConform(takeIds) {
	const projectId = project.id;
	if (!projectId || !takeIds.length || !getClient()) {
		Object.assign(conformEstimate, { key: null, seconds: null, loading: false });
		return;
	}
	const key = JSON.stringify([projectId, takeIds]);
	if (key === conformEstimate.key) return;
	Object.assign(conformEstimate, { key, seconds: null, loading: true });
	const result = await getClient().renditionsEstimate(projectId, takeIds);
	if (conformEstimate.key !== key) return;
	Object.assign(conformEstimate, { seconds: result.ok ? result.data.seconds : null, loading: false });
}

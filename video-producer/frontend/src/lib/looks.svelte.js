import { untrack } from 'svelte';
import { t } from '../i18n/index.svelte.js';
import { toast } from './state.svelte.js';
import { project, getClient, projectGone } from './project.svelte.js';
import { onTake } from './takes.svelte.js';

const SETTLE = 1500;
const POLL = 8000;

export const lookState = $state({ projectId: null, data: null, asking: false });

let alive = false;
let timer = null;
let poller = null;

export const currentLooks = () => (lookState.projectId && lookState.projectId === project.id ? lookState.data : null);

function schedulePoll() {
	clearTimeout(poller);
	poller = alive && lookState.data?.queued ? setTimeout(refreshLooks, POLL) : null;
}

export async function refreshLooks() {
	const projectId = project.id;
	const client = getClient();
	if (!projectId || !client) return;
	const result = await client.looks(projectId);
	if (projectId !== project.id) return;
	if (!result.ok) {
		if (result.error.code === 'project_not_found') projectGone(projectId);
		return;
	}
	Object.assign(lookState, { projectId, data: result.data });
	schedulePoll();
}

function schedule(delay = SETTLE) {
	clearTimeout(timer);
	timer = setTimeout(refreshLooks, delay);
}

export async function measureLooks() {
	const projectId = project.id;
	const client = getClient();
	if (!projectId || !client || lookState.asking) return;
	lookState.asking = true;
	try {
		const result = await client.measureLooks(projectId);
		if (projectId !== project.id) return;
		if (!result.ok) {
			if (result.error.code === 'project_not_found') return projectGone(projectId);
			return toast(t('lib.looks.failed'), 'error');
		}
		Object.assign(lookState, { projectId, data: result.data });
		if (!result.data.embedder.available) toast(t('lib.looks.unavailable'), 'warning');
		else toast(result.data.queued ? t('lib.looks.asked', { count: result.data.queued }) : t('lib.looks.none'), result.data.queued ? 'info' : 'success');
		schedulePoll();
	} finally {
		lookState.asking = false;
	}
}

export function startLooks() {
	alive = true;
	const offTake = onTake((take, live) => live && take.status === 'done' && schedule());
	const stopWatch = $effect.root(() => {
		$effect(() => {
			const id = project.id;
			project.version;
			if (id) untrack(() => schedule(id === lookState.projectId ? SETTLE : 0));
		});
	});
	return () => {
		alive = false;
		offTake();
		stopWatch();
		clearTimeout(timer);
		clearTimeout(poller);
	};
}

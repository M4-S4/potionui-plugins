import { t } from '../i18n/index.svelte.js';
import { doc, ui, act, toast, asset, clipLabel } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { confirm } from './host.js';
import { assetIdOf, choiceOf, inFlight, keyframeAsset, keyframeOptions, ordered, requestKey, storedChoice } from './keyframes.js';

const POLL_EVERY = 4000;
const ESTIMATE_DELAY = 500;

export const keyframeState = $state({ shotId: null, list: [], loaded: false, estimate: null, estimating: false, starting: false, error: null });

let estimateKey = null;
let estimateTimer = null;
let pollTimer = null;
let controller = null;

const gone = (error) => error?.code === 'project_not_found';
const current = (projectId, shotId) => projectId === project.id && shotId === keyframeState.shotId;

export const keyframeChoices = () => keyframeOptions(ui.me?.keyframePresets);
export const keyframeChoice = () => storedChoice(doc.engine);

export function chooseKeyframeOption(key) {
	const option = keyframeChoices().find((o) => o.key === key);
	if (option) act(() => (doc.engine.keyframes = choiceOf(option)));
}

function schedulePoll() {
	clearTimeout(pollTimer);
	pollTimer = keyframeState.list.some(inFlight) ? setTimeout(refreshKeyframes, POLL_EVERY) : null;
}

function merge(takes) {
	const byId = new Map(keyframeState.list.map((take) => [take.id, take]));
	for (const take of takes) byId.set(take.id, take);
	keyframeState.list = ordered([...byId.values()]);
	schedulePoll();
}

function replace(take) {
	if (take) merge([take]);
}

export async function refreshKeyframes() {
	const { shotId } = keyframeState;
	const projectId = project.id;
	if (!shotId || !projectId || !getClient()) return;
	const result = await getClient().keyframes(projectId, shotId);
	if (!current(projectId, shotId)) return;
	if (!result.ok) {
		if (gone(result.error)) projectGone(projectId);
		return schedulePoll();
	}
	keyframeState.list = ordered(result.data);
	keyframeState.loaded = true;
	schedulePoll();
}

export function closeKeyframes() {
	clearTimeout(pollTimer);
	clearTimeout(estimateTimer);
	pollTimer = estimateTimer = null;
	controller?.abort();
	controller = null;
	estimateKey = null;
	keyframeState.shotId = null;
}

export function openKeyframes(shotId) {
	closeKeyframes();
	Object.assign(keyframeState, { shotId, list: [], loaded: false, estimate: null, estimating: false, starting: false, error: null });
	refreshKeyframes();
	return closeKeyframes;
}

async function fireEstimate(body, key) {
	const { shotId } = keyframeState;
	if (!(await flushSave()) || !project.id || key !== estimateKey) return;
	const projectId = project.id;
	controller?.abort();
	controller = new AbortController();
	keyframeState.estimating = true;
	const result = await getClient().estimateKeyframes(projectId, shotId, body, controller.signal);
	if (!current(projectId, shotId) || key !== estimateKey) return;
	keyframeState.estimating = false;
	if (result.ok) return Object.assign(keyframeState, { estimate: result.data, error: null });
	if (result.error.code === 'aborted') return;
	if (gone(result.error)) return projectGone(projectId);
	Object.assign(keyframeState, { estimate: null, error: result.error });
}

export function scheduleKeyframeEstimate(body, force = false) {
	const key = requestKey(body);
	if (key === estimateKey && !force) return;
	estimateKey = key;
	clearTimeout(estimateTimer);
	estimateTimer = setTimeout(() => fireEstimate(body, key), ESTIMATE_DELAY);
}

export async function startCandidates(body) {
	if (keyframeState.starting || !keyframeState.shotId) return;
	keyframeState.starting = true;
	try {
		const { shotId } = keyframeState;
		if (!(await flushSave()) || !project.id) return toast(t('keyframes.toast.saveFirst'), 'error');
		const projectId = project.id;
		const result = await getClient().generateKeyframes(projectId, shotId, body);
		if (!current(projectId, shotId)) return;
		if (!result.ok) {
			if (gone(result.error)) return projectGone(projectId);
			scheduleKeyframeEstimate(body, true);
			return toast(result.error.code === 'blocked' ? t('keyframes.toast.blocked') : t('keyframes.toast.notStarted'), result.error.status === 409 ? 'warning' : 'error');
		}
		merge(result.data);
		toast(t('keyframes.toast.started', { count: result.data.length }), 'success');
	} finally {
		keyframeState.starting = false;
	}
}

async function sendLabel(take, label) {
	const projectId = project.id;
	const result = await getClient().labelTake(projectId, take.id, label);
	if (result.ok) replace(result.data);
	else if (gone(result.error)) projectGone(projectId);
	else toast(t('keyframes.toast.labelFailed'), 'error');
}

export function acceptCandidate(take, role, onaccept) {
	const clip = doc.clips.find((c) => c.id === take.shotId);
	const id = assetIdOf(take);
	if (!asset(id)) act(() => doc.assets.push(keyframeAsset(take, t('keyframes.assetName', { shot: clipLabel(clip), variant: take.variant }))));
	onaccept(role, id);
	if (take.label !== 'candidate') sendLabel(take, 'candidate');
	toast(role === 'last' ? t('keyframes.toast.acceptedLast', { variant: take.variant }) : t('keyframes.toast.acceptedFirst', { variant: take.variant }), 'success');
}

export function toggleRejected(take) {
	return sendLabel(take, take.label === 'rejected' ? 'draft' : 'rejected');
}

export async function retryCandidate(take) {
	const result = await getClient().retryTake(take.id);
	if (result.ok) return replace(result.data);
	toast(result.error.status === 409 ? t('keyframes.toast.blocked') : t('keyframes.toast.notStarted'), 'error');
}

export async function cancelCandidate(take) {
	const result = await getClient().cancelTake(take.id);
	if (result.ok) replace(result.data);
	else toast(t('keyframes.toast.cancelFailed'), 'error');
}

export async function deleteCandidate(take) {
	const ok = await confirm({ title: t('keyframes.delete.title', { variant: take.variant }), message: t('keyframes.delete.message'), variant: 'danger', confirmLabel: t('keyframes.delete.confirm') });
	if (!ok) return;
	const projectId = project.id;
	const result = await getClient().deleteTake(projectId, take.id);
	if (!result.ok && result.error.status !== 404) return toast(t('keyframes.toast.deleteFailed'), 'error');
	keyframeState.list = keyframeState.list.filter((x) => x.id !== take.id);
	schedulePoll();
}

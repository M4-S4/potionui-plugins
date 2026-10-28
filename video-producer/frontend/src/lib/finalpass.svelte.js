import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, toast, clipLabel } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { takeStore } from './takes.svelte.js';
import { cancelTake, followTakes, noteText, presetById } from './production.svelte.js';
import { UPSCALE_TARGETS, aspectOf, finalResolution } from './generation.js';
import { AUTO_TARGET, DEFAULT_RTX_SOURCE, GUIDED_PRESET, passBody, passChoice, passFlying } from './finalpass.js';

const ESTIMATE_DELAY = 400;

export const passState = $state({ key: null, data: null, loading: false, error: null, sending: false, cancelling: false });

let timer = null;
let controller = null;

const gone = (error) => error?.code === 'project_not_found';

export function openFinalPass() {
	ui.menuOpen = null;
	ui.paletteOpen = false;
	ui.modal = { type: 'final-pass' };
}

export function passTargets() {
	return [AUTO_TARGET, ...(ui.me?.upscaleTargets?.length ? ui.me.upscaleTargets : UPSCALE_TARGETS)];
}

export const guidedReady = () => ui.me?.features?.guided === true;

export function guidedResolution() {
	return (finalResolution(presetById(GUIDED_PRESET), aspectOf(doc.aspect, doc.resolution)) ?? '1280x720').replace('x', '×');
}

export function savedChoice() {
	return passChoice(doc.finalPass, passTargets(), guidedReady());
}

function remember(choice) {
	const next = { method: choice.method, target: choice.target, upscaler: choice.upscaler, rtxSource: choice.rtxSource ?? DEFAULT_RTX_SOURCE };
	const before = doc.finalPass ?? {};
	if (before.method === next.method && before.target === next.target && before.upscaler === next.upscaler && before.rtxSource === next.rtxSource) return;
	act(() => (doc.finalPass = next));
}

export function rememberRtxSource(rtxSource) {
	if ((doc.finalPass ?? {}).rtxSource === rtxSource) return;
	act(() => (doc.finalPass = { ...(doc.finalPass ?? {}), rtxSource }));
}

function shotsText(note) {
	const ids = Array.isArray(note?.data?.shot_ids) ? note.data.shot_ids : note?.data?.shot_id ? [note.data.shot_id] : [];
	return ids.map((id) => clipLabel(doc.clips.find((c) => c.id === id))).join(', ');
}

function ownText(note) {
	const data = note?.data ?? {};
	if (note?.code === 'guided_unavailable') return t('generation.finalPass.block.guidedUnavailable');
	if (note?.code === 'guide_lora_missing') return t('generation.finalPass.block.loraMissing', { file: data.file ?? '—' });
	if (note?.code === 'final_running') return t('generation.finalPass.block.running');
	if (note?.code === 'take_not_done') return t('generation.finalPass.block.notDone');
	if (note?.code === 'shot_not_found') return t('generation.finalPass.block.shotGone');
	if (note?.code === 'guided_frame_failed') return t('generation.finalPass.block.frame');
	return '';
}

export function passNoteText(note) {
	const own = ownText(note);
	if (!own) return noteText(note);
	const shots = shotsText(note);
	return shots ? t('generation.block.forShots', { shots, text: own }) : own;
}

function clearEstimate() {
	clearTimeout(timer);
	timer = null;
	controller?.abort();
	controller = null;
}

export function schedulePassEstimate(sources, choice) {
	if (!project.id || !sources.length) {
		clearEstimate();
		Object.assign(passState, { key: null, data: null, loading: false, error: null });
		return;
	}
	const projectId = project.id;
	const body = passBody(sources, choice);
	const key = JSON.stringify([projectId, project.version, body]);
	if (key === passState.key) return;
	clearEstimate();
	Object.assign(passState, { key, loading: true, error: null });
	timer = setTimeout(async () => {
		timer = null;
		const own = new AbortController();
		controller = own;
		const result = await getClient().finalPassEstimate(projectId, body, own.signal);
		if (controller !== own) return;
		controller = null;
		if (!result.ok) {
			if (result.error.code === 'aborted') return;
			if (gone(result.error)) return projectGone(projectId);
			Object.assign(passState, { data: null, loading: false, error: result.error });
			return;
		}
		Object.assign(passState, { data: result.data, loading: false, error: null });
	}, ESTIMATE_DELAY);
}

export function stopPassEstimate() {
	clearEstimate();
	Object.assign(passState, { key: null, data: null, loading: false, error: null });
}

function failed(error) {
	if (gone(error)) return projectGone(project.id);
	const blocks = Array.isArray(error?.data?.blocks) ? error.data.blocks : [];
	if (blocks.length) toast(passNoteText(blocks[0]), 'warning');
	else toast(t('generation.finalPass.failed'), 'error');
}

export async function startFinalPass(sources, choice) {
	if (passState.sending || !sources.length) return false;
	passState.sending = true;
	try {
		remember(choice);
		const saved = await flushSave();
		if (!saved || !project.id) {
			toast(t('generation.toast.saveFirst'), 'error');
			return false;
		}
		const projectId = project.id;
		const result = await getClient().finalPass(projectId, passBody(sources, choice));
		if (projectId !== project.id) return false;
		if (!result.ok) {
			failed(result.error);
			return false;
		}
		followTakes(result.data);
		toast(t('generation.finalPass.started', { count: result.data.length }), 'success');
		return true;
	} finally {
		passState.sending = false;
	}
}

export async function cancelFinalPass() {
	const flying = passFlying(takeStore.list);
	if (!flying.length || passState.cancelling) return;
	passState.cancelling = true;
	try {
		await Promise.all(flying.map((take) => cancelTake(take)));
	} finally {
		passState.cancelling = false;
	}
	toast(t('generation.finalPass.cancelled', { count: flying.length }));
}

import { t, tFor } from '../i18n/index.svelte.js';
import { doc, ui, replaceDoc, toast, adopt } from './state.svelte.js';
import { DEFAULT_PROMPT_LANGUAGE, emptyDoc, migrate, starterDoc } from './starter.js';
import { mergeDocs, same } from './merge.js';
import { pause } from './playback.svelte.js';
import { confirm } from './host.js';

export const project = $state({ id: null, version: 0, status: 'idle', savedAt: null, error: null, fatal: null });

const SAVE_DELAY = 800;

let client = null;
let lastSavedJson = null;
let timer = null;
let inFlight = null;
let pulling = null;
let wanted = 0;
let asks = 0;
let answered = 0;
const loadListeners = new Set();

export function onLoaded(listener) {
	loadListeners.add(listener);
	return () => loadListeners.delete(listener);
}

export function bindClient(next) {
	client = next;
}

export function getClient() {
	return client;
}

export const currentJson = () => JSON.stringify($state.snapshot(doc));

function loaded(p) {
	if (ui.playing) pause();
	clearTimeout(timer);
	timer = null;
	replaceDoc({ ...emptyDoc(t), ...p.doc });
	Object.assign(project, { id: p.id, version: p.version, status: 'saved', savedAt: p.updatedAt, error: null });
	lastSavedJson = currentJson();
	ui.dirty = false;
	for (const listener of loadListeners) listener(p);
}

function remember(id) {
	if (ui.me) ui.me.lastProjectId = id;
	client?.saveLastProject(id);
}

function saveErrorText(error) {
	if (error?.code === 'invalid_doc') return t('project.toast.invalidDoc');
	if (error?.code === 'doc_too_large') return t('project.toast.tooLarge');
	return t('project.toast.saveFailed');
}

export function noteChange(json) {
	if (!project.id || lastSavedJson === null) return;
	ui.dirty = json !== lastSavedJson;
	if (ui.dirty) scheduleSave();
}

export function savedSnapshot() {
	return lastSavedJson === null ? null : JSON.parse(lastSavedJson);
}

export function markSaved(version, saved) {
	lastSavedJson = JSON.stringify(saved);
	Object.assign(project, { version, savedAt: new Date().toISOString() });
	ui.dirty = currentJson() !== lastSavedJson;
	if (ui.dirty) scheduleSave();
}

export function scheduleSave() {
	clearTimeout(timer);
	timer = setTimeout(() => {
		timer = null;
		flushSave();
	}, SAVE_DELAY);
}

const DELETED = 'deleted';
const gone = (error) => error?.code === 'project_not_found';

function forget(id) {
	clearTimeout(timer);
	timer = null;
	lastSavedJson = null;
	Object.assign(project, { id: null, version: 0, status: 'idle', error: null });
	if (ui.me?.lastProjectId === id) ui.me.lastProjectId = null;
	toast(t('project.toast.deletedElsewhere'), 'error');
	return DELETED;
}

async function reopenAfterDeletion() {
	const result = await openLatestOrStarter();
	if (!result.ok) project.fatal = result.error;
}

export async function projectGone(id) {
	if (!id || id !== project.id) return;
	forget(id);
	await reopenAfterDeletion();
}

function serverDoc(p) {
	const next = migrate({ ...emptyDoc(t), ...p.doc, assets: Array.isArray(p.doc?.assets) ? p.doc.assets : [] });
	delete next.results;
	return next;
}

export function mergeServer(p) {
	const base = savedSnapshot();
	if (!base || !p?.doc) return null;
	const theirs = serverDoc(p);
	const mine = $state.snapshot(doc);
	const { value, conflicts, dropped } = mergeDocs(base, mine, theirs);
	const changed = !same(value, mine);
	if (changed) adopt(JSON.parse(JSON.stringify(value)));
	Object.assign(project, { version: p.version, savedAt: p.updatedAt ?? new Date().toISOString(), status: 'saved', error: null });
	const now = $state.snapshot(doc);
	lastSavedJson = JSON.stringify(same(now, theirs) ? now : theirs);
	ui.dirty = currentJson() !== lastSavedJson;
	if (ui.dirty) scheduleSave();
	return { changed, conflicts, dropped };
}

export function mergedToast(outcome, texts) {
	if (outcome.dropped) return toast(texts.dropped(outcome.dropped), 'warning', texts.action);
	if (outcome.conflicts) return toast(texts.kept(outcome.conflicts), 'warning', texts.action);
	toast(texts.merged(), texts.level ?? 'success', texts.action);
}

async function reloadAfterConflict(id) {
	const result = await client.getProject(id);
	if (id !== project.id) return false;
	if (gone(result.error)) return forget(id);
	if (!result.ok) {
		Object.assign(project, { status: 'error', error: result.error });
		toast(t('project.toast.saveFailed'), 'error', { label: t('project.retry'), run: () => flushSave() });
		return false;
	}
	const merged = mergeServer(result.data);
	if (!merged) {
		loaded(result.data);
		toast(t('project.toast.reloaded'), 'warning');
	} else
		mergedToast(merged, {
			merged: () => t('project.toast.merged'),
			kept: (count) => t('project.toast.mergedKept', { count }),
			dropped: (count) => t('project.toast.mergedDropped', { count }),
			level: 'warning'
		});
	return false;
}

const UNCHANGED = { changed: false, conflicts: 0, dropped: 0 };

async function pullOnce(id) {
	if (inFlight) await inFlight;
	if (id !== project.id) return null;
	const result = await client.getProject(id);
	if (id !== project.id) return null;
	if (gone(result.error)) {
		await projectGone(id);
		return null;
	}
	if (!result.ok) return null;
	if (inFlight) await inFlight;
	if (id !== project.id || result.data.version <= project.version) return UNCHANGED;
	return mergeServer(result.data) ?? UNCHANGED;
}

async function pullRounds() {
	const outcome = { changed: false, conflicts: 0, dropped: 0 };
	try {
		await null;
		let late = 0;
		while (project.id && client) {
			const asked = answered !== asks;
			if (!asked && (wanted <= project.version || late >= 2)) break;
			if (!asked) late += 1;
			answered = asks;
			const step = await pullOnce(project.id);
			if (!step) break;
			outcome.changed ||= step.changed;
			outcome.conflicts += step.conflicts;
			outcome.dropped += step.dropped;
		}
		return outcome;
	} finally {
		pulling = null;
		wanted = 0;
	}
}

export function pullProject(version = 0) {
	wanted = Math.max(wanted, version);
	asks += 1;
	pulling ??= pullRounds();
	return pulling;
}

export async function flushSave() {
	clearTimeout(timer);
	timer = null;
	if (inFlight) {
		await inFlight;
		return flushSave();
	}
	if (!project.id || !client) return true;
	const json = currentJson();
	if (json === lastSavedJson) {
		ui.dirty = false;
		if (project.status === 'error') project.status = 'saved';
		return true;
	}
	const id = project.id;
	const wasError = project.status === 'error';
	project.status = 'saving';
	inFlight = (async () => {
		const result = await client.saveProject(id, JSON.parse(json), project.version);
		if (id !== project.id) return false;
		if (result.ok) {
			lastSavedJson = json;
			Object.assign(project, { version: result.data.version, savedAt: result.data.updatedAt ?? new Date().toISOString(), status: 'saved', error: null });
			ui.dirty = currentJson() !== lastSavedJson;
			return true;
		}
		if (result.error.code === 'version_conflict') return reloadAfterConflict(id);
		if (gone(result.error)) return forget(id);
		Object.assign(project, { status: 'error', error: result.error });
		if (!wasError) toast(saveErrorText(result.error), 'error', { label: t('project.retry'), run: () => flushSave() });
		return false;
	})();
	let outcome;
	try {
		outcome = await inFlight;
	} finally {
		inFlight = null;
		if (project.status === 'saved' && ui.dirty) scheduleSave();
	}
	if (outcome !== DELETED) return outcome;
	await reopenAfterDeletion();
	return false;
}

const CANCELLED = { ok: false, error: { status: 0, code: 'cancelled', message: '', data: null } };

async function readyToLeave() {
	if ((await flushSave()) || !ui.dirty || !project.id) return true;
	return confirm({ title: t('project.discard.title'), message: t('project.discard.message', { name: doc.name }), variant: 'warning', confirmLabel: t('project.discard.confirm') });
}

export async function openProject(id) {
	if (id !== project.id && !(await readyToLeave())) return CANCELLED;
	const result = await client.getProject(id);
	if (!result.ok) return result;
	if (!result.data.doc) return { ok: false, error: { status: 0, code: 'invalid_response', message: '', data: null } };
	loaded(result.data);
	remember(id);
	return result;
}

async function openCreated(source) {
	const result = await client.createProject(source);
	if (!result.ok) return result;
	loaded({ ...result.data, doc: result.data.doc ?? source });
	remember(result.data.id);
	return result;
}

export async function openLatestOrStarter() {
	const lastId = ui.me?.lastProjectId;
	if (lastId) {
		const result = await openProject(lastId);
		if (result.ok || !['project_not_found', 'not_found'].includes(result.error.code)) return result;
	}
	const listed = await client.listProjects();
	if (!listed.ok) return listed;
	if (listed.data.length) return openProject(listed.data[0].id);
	return openCreated(starterDoc(t, tFor(DEFAULT_PROMPT_LANGUAGE), DEFAULT_PROMPT_LANGUAGE));
}

export async function createProject(source = emptyDoc(t)) {
	const result = await openCreated(source);
	if (result.ok) {
		ui.playhead = 0;
		toast(t('lib.toast.newProject'), 'success');
	} else toast(t('project.toast.createFailed'), 'error');
	return result;
}

export async function deleteProject(id) {
	const result = await client.deleteProject(id);
	if (result.ok && ui.me?.lastProjectId === id) ui.me.lastProjectId = null;
	return result;
}

export async function listProjects() {
	return client.listProjects();
}

export async function listVersions() {
	return client.listVersions(project.id);
}

export async function restoreVersion(version) {
	if (!(await readyToLeave())) return CANCELLED;
	const result = await client.restoreVersion(project.id, version);
	if (!result.ok) return result;
	loaded(result.data);
	return result;
}

export function disposeProject() {
	clearTimeout(timer);
	timer = null;
}

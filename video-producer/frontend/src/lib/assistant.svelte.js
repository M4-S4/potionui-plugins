import { getLocale, t } from '../i18n/index.svelte.js';
import { doc, ui, act, toast, round, secs, clipLabel, allIssues, ruleText, openDirector, undo } from './state.svelte.js';
import { project, savedSnapshot, markSaved, flushSave, getClient, pullProject } from './project.svelte.js';
import { promptLanguageOf } from './starter.js';
import { bibleContext } from './bible.js';
import { seams } from './continuity.svelte.js';
import { chat } from './host.js';
import { ulid } from './ulid.js';
import { flyingTakes, realTakesOf } from './takes.svelte.js';
import { engineLabel, followTakes } from './production.svelte.js';
import { listJobs } from './exports.svelte.js';
import { LIVE_TOOLS, PAGE_TOOLS, applyPrompts, changePlan, issuesContext, productionContext, promptChanges, promptPlan, proposalFrom, reviewCount, reviewFrom, seamsContext, shotsContext, startedTakes } from './assistant.js';

export const review = $state({ current: null });

const MIN_SHOT_S = 2;
const MAX_SHOT_S = 15;
const clipOf = (id) => (id ? (doc.clips.find((c) => c.id === id) ?? null) : null);
const nameOf = (id, fallback) => (clipOf(id) ? clipLabel(clipOf(id)) : fallback);

export function seamNames(seam) {
	return { from: nameOf(seam.fromShotId, seam.fromLabel), to: nameOf(seam.toShotId, seam.toLabel) };
}

function issueNames(seam, issue) {
	const { from, to } = seamNames(seam);
	const shot = issue.shotId ? nameOf(issue.shotId, issue.shotId === seam.fromShotId ? from : to) : to;
	return { from, to, shot };
}

const durationOf = (issue) => (clipOf(issue.shotId) ? secs(clipOf(issue.shotId).dur) : '');

const seamTexts = {
	no_instruction: (n) => n.shot && t('assistant.seam.no_instruction', { shot: n.shot }),
	conflict: (n, i) => n.shot && ruleText(i.rule) && t('assistant.seam.conflict', { shot: n.shot, rule: ruleText(i.rule) }),
	duration: (n, i) => n.shot && durationOf(i) && t('assistant.seam.duration', { shot: n.shot, duration: durationOf(i), min: MIN_SHOT_S, max: MAX_SHOT_S }),
	fl2va_no_frame: (n) => n.shot && t('assistant.seam.fl2va_no_frame', { shot: n.shot }),
	camera_change: (n) => n.from && n.to && t('assistant.seam.camera_change', { from: n.from, to: n.to }),
	lum: (n) => n.from && n.to && t('assistant.seam.lum', { from: n.from, to: n.to }),
	warm: (n) => n.from && n.to && t('assistant.seam.warm', { from: n.from, to: n.to }),
	identity: (n) => n.from && n.to && t('assistant.seam.identity', { from: n.from, to: n.to }),
	cast_unnamed: (n, i) => n.shot && i.labels.length && t('assistant.seam.cast_unnamed', { shot: n.shot, labels: i.labels.join(', ') })
};

const fixTexts = {
	no_instruction: () => t('assistant.fix.no_instruction'),
	conflict: () => t('assistant.fix.conflict'),
	duration: () => t('assistant.fix.duration', { min: MIN_SHOT_S, max: MAX_SHOT_S }),
	fl2va_no_frame: () => t('assistant.fix.fl2va_no_frame'),
	camera_change: (n) => n.to && t('assistant.fix.camera_change', { to: n.to }),
	lum: () => t('assistant.fix.lum'),
	warm: () => t('assistant.fix.warm'),
	identity: () => t('assistant.fix.identity'),
	cast_unnamed: () => t('assistant.fix.cast_unnamed')
};

export function reviewText(seam, issue) {
	return seamTexts[issue.kind]?.(issueNames(seam, issue), issue) || issue.text;
}

export function reviewFix(seam, issue) {
	return fixTexts[issue.kind]?.(issueNames(seam, issue), issue) || issue.fix;
}

export function contextSnapshot() {
	if (ui.dirty && project.id) flushSave();
	return {
		projectId: project.id,
		projectVersion: project.version,
		locale: getLocale(),
		name: doc.name,
		promptLanguage: promptLanguageOf(doc.promptLanguage),
		workspace: ui.workspace,
		selection: ui.selection ? { ...ui.selection } : null,
		playhead: round(ui.playhead, 0.04),
		range: ui.range ? { in: ui.range.in, out: ui.range.out } : null,
		synopsis: doc.synopsis,
		direction: $state.snapshot(doc.direction),
		bible: bibleContext(doc),
		production: productionContext(ui.production, flyingTakes().length, engineLabel()),
		shots: shotsContext(doc, clipLabel, realTakesOf),
		issues: issuesContext(allIssues()),
		seams: seamsContext(seams())
	};
}

export function suggest(text) {
	chat.prefill(text);
	chat.open();
}

export function showReview() {
	openDirector();
	ui.sidebarOpen = true;
}

function appliedToast(tool, changes) {
	if (tool === 'vp_fix_conflicts') return toast(t('assistant.toast.fixed', { count: changes.length }), 'success');
	toast(t('assistant.toast.prompt', { shot: clipLabel(doc.clips.find((c) => c.id === changes[0].shotId)) }), 'success');
}

export function applyPromptResult(tool, result) {
	if (result?.status === 'pending_approval') return { status: 'noop' };
	const changes = promptChanges(tool, result);
	const saved = savedSnapshot();
	const plan = promptPlan({ result, changes, projectId: project.id, version: project.version, saved, current: doc });
	if (plan === 'stale') return { status: 'stale', message: t('assistant.stale.write') };
	if (plan === 'noop') return { status: 'noop' };
	if (plan === 'reload') {
		pull(result.version);
		return { status: 'applied' };
	}
	act(() => applyPrompts(doc, changes));
	markSaved(result.version, applyPrompts(saved, changes));
	appliedToast(tool, changes);
	return { status: 'applied' };
}

export function applyProposal(result) {
	if (result?.status === 'pending_approval') return { status: 'noop' };
	if (!project.id || result?.project_id !== project.id) return { status: 'stale', message: t('assistant.stale.read') };
	const proposal = proposalFrom(result, ulid);
	if (!proposal.length) return { status: 'noop' };
	ui.storyProposal = proposal;
	ui.workspace = 'storyboard';
	if (ui.storyView === 'band') {
		ui.storyOpen = true;
		ui.storyTab = 'cut';
	} else ui.sidebarOpen = true;
	toast(t('assistant.toast.proposal', { count: proposal.length }), 'success');
	return { status: 'applied' };
}

export function applyReview(result) {
	if (result?.status === 'pending_approval') return { status: 'noop' };
	if (!project.id || result?.project_id !== project.id) return { status: 'stale', message: t('assistant.stale.read') };
	const next = reviewFrom(result);
	if (!next) return { status: 'noop' };
	review.current = next;
	const count = reviewCount(review.current);
	const visible = ui.workspace === 'director' && ui.sidebarOpen;
	const message = count ? t('assistant.toast.review', { count }) : t('assistant.toast.reviewClear');
	toast(message, count ? 'warning' : 'success', visible ? undefined : { label: t('assistant.toast.show'), run: showReview });
	return { status: 'applied' };
}

function changedToast(outcome) {
	if (!outcome?.changed) return;
	const message = outcome.conflicts ? t('assistant.toast.changedKept', { count: outcome.conflicts }) : t('assistant.toast.changed');
	toast(message, outcome.conflicts ? 'warning' : 'success', { label: t('shell.toast.undo'), run: undo });
}

function pull(version = 0) {
	return pullProject(version).then(changedToast, () => toast(t('assistant.toast.reloadFailed'), 'error'));
}

async function reloadTakes(projectId) {
	const result = await getClient()?.listTakes(projectId);
	if (result?.ok && projectId === project.id) followTakes(result.data);
}

function exportStarted() {
	listJobs();
	toast(t('assistant.toast.export'), 'success', { label: t('assistant.toast.show'), run: () => (ui.modal = { type: 'export' }) });
}

export function applyChangeResult(tool, result) {
	const plan = changePlan({ tool, result, projectId: project.id, version: project.version });
	if (plan.status === 'stale') return { status: 'stale', message: t('assistant.stale.write') };
	if (plan.status === 'noop') return { status: 'noop' };
	if (plan.pull) pull(plan.pull);
	if (plan.takes) reloadTakes(project.id);
	const started = startedTakes(tool, result);
	if (started) toast(t('assistant.toast.takes', { count: started }), 'success', { label: t('assistant.toast.show'), run: () => openDirector('review') });
	if (plan.exported) exportStarted();
	return { status: 'applied' };
}

function onToolEnd(event) {
	const detail = event?.detail;
	if (detail?.success === false || detail?.pending || !LIVE_TOOLS.includes(detail?.tool_name) || !project.id) return;
	pull();
}

export function startAssistant() {
	const offs = [
		chat.provideContext('video_producer', contextSnapshot),
		chat.onToolApplied('vp_write_shot_prompt', (result) => applyPromptResult('vp_write_shot_prompt', result)),
		chat.onToolApplied('vp_fix_conflicts', (result) => applyPromptResult('vp_fix_conflicts', result)),
		chat.onToolApplied('vp_split_synopsis', applyProposal),
		chat.onToolApplied('vp_check_continuity', applyReview),
		...PAGE_TOOLS.map((tool) => chat.onToolApplied(tool, (result) => applyChangeResult(tool, result)))
	];
	if (typeof window !== 'undefined') window.addEventListener('potionui:tool-end', onToolEnd);
	return () => {
		for (const off of offs) off();
		if (typeof window !== 'undefined') window.removeEventListener('potionui:tool-end', onToolEnd);
		review.current = null;
	};
}

import { touch } from './shots.js';
import { castLabels } from './bible.js';

export const PROMPT_LIMIT = 300;
export const LABEL_LIMIT = 34;
export const MAX_PROPOSAL = 24;
const FIRST_ROLES = ['first', 'début', 'debut'];
const LAST_ROLES = ['last', 'fin'];
const MEASURED_KINDS = ['lum', 'warm'];
const SIMULATED_KINDS = ['identity'];

export function clipped(value, limit = PROMPT_LIMIT) {
	const text = String(value ?? '');
	return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

const seconds = (value) => Math.round((Number(value) || 0) * 100) / 100;
const roleOf = (frame) => String(frame?.role ?? '').trim().toLowerCase();
const hasFrame = (doc, shotId, roles) => (doc.frames ?? []).some((f) => f.shotId === shotId && f.assetId && roles.includes(roleOf(f)));
const isText = (value) => typeof value === 'string';

export function promptFor(doc, shotId) {
	return (doc?.prompts ?? []).find((p) => p.shotId === shotId) ?? null;
}

export function shotsContext(doc, labelOf) {
	return (doc.clips ?? []).map((c) => {
		const p = promptFor(doc, c.id);
		return {
			id: c.id,
			label: labelOf(c),
			start: seconds(c.start),
			dur: seconds(c.dur),
			stage: c.stage,
			promptId: p?.id ?? null,
			prompt: clipped(p?.text),
			hasFirstFrame: hasFrame(doc, c.id, FIRST_ROLES),
			hasLastFrame: hasFrame(doc, c.id, LAST_ROLES),
			take: c.take ?? null,
			cast: castLabels(doc, c)
		};
	});
}

export function productionContext(production, queued) {
	return { target: production.target, mode: production.mode, quality: production.quality, state: production.state, progress: Math.round(production.progress), queue: queued };
}

export function issuesContext(issues) {
	return issues.map((i) => ({ shotId: i.prompt?.shotId ?? null, level: i.level, text: i.text }));
}

export function seamsContext(seams) {
	return seams.map((s) => ({
		fromShotId: s.from.id,
		toShotId: s.to.id,
		issues: s.issues.map((i) => ({ kind: i.kind, text: i.text })),
		measured: Boolean(s.measured)
	}));
}

export function promptChanges(tool, result) {
	const raw =
		tool === 'vp_write_shot_prompt'
			? [{ shotId: result?.shot_id, promptId: result?.prompt_id, text: result?.text }]
			: (Array.isArray(result?.changes) ? result.changes : []).map((c) => ({ shotId: c?.shot_id, promptId: c?.prompt_id, text: c?.after }));
	return raw.filter((c) => isText(c.shotId) && isText(c.promptId) && isText(c.text));
}

export function editedPrompts(saved, current, changes) {
	return changes.filter((c) => (promptFor(saved, c.shotId)?.text ?? null) !== (promptFor(current, c.shotId)?.text ?? null)).map((c) => c.shotId);
}

export function promptPlan({ result, changes, projectId, version, saved, current }) {
	if (!projectId || result?.project_id !== projectId) return 'stale';
	const next = result.version;
	if (!Number.isInteger(next) || !changes.length) return 'noop';
	if (next < version) return 'noop';
	if (next > version + 1 || !saved) return 'reload';
	if (changes.some((c) => !current.clips.some((x) => x.id === c.shotId))) return 'reload';
	if (editedPrompts(saved, current, changes).length) return 'reload';
	return 'apply';
}

export function applyPrompts(target, changes) {
	for (const c of changes) {
		const clip = target.clips.find((x) => x.id === c.shotId);
		if (!clip) continue;
		const prompt = target.prompts.find((p) => p.id === c.promptId) ?? promptFor(target, c.shotId);
		if ((prompt ? prompt.text : '') !== c.text) touch(clip);
		if (prompt) prompt.text = c.text;
		else target.prompts.push({ id: c.promptId, shotId: clip.id, start: clip.start, dur: clip.dur, strength: 75, text: c.text });
	}
	return target;
}

export function proposalFrom(result, makeId) {
	return (Array.isArray(result?.proposal) ? result.proposal : [])
		.filter((x) => isText(x?.prompt) && x.prompt.trim() && Number.isFinite(Number(x.duration_s)))
		.slice(0, MAX_PROPOSAL)
		.map((x, i) => ({
			id: makeId(),
			keep: true,
			n: i + 1,
			label: clipped(String(x.label ?? '').trim(), LABEL_LIMIT),
			prompt: x.prompt.trim(),
			dur: Math.min(15, Math.max(2, Math.round(Number(x.duration_s) * 10) / 10))
		}));
}

export function reviewFrom(result, now = Date.now()) {
	if (!Array.isArray(result?.seams)) return null;
	const seams = result.seams
		.map((s) => ({
			fromShotId: s?.from_shot_id ?? null,
			toShotId: s?.to_shot_id ?? null,
			fromLabel: isText(s?.from_label) ? s.from_label : '',
			toLabel: isText(s?.to_label) ? s.to_label : '',
			issues: (Array.isArray(s?.issues) ? s.issues : [])
				.filter((i) => isText(i?.text) && i.text.trim())
				.map((i) => ({
					kind: String(i.kind ?? ''),
					text: i.text.trim(),
					fix: isText(i.fix) ? i.fix.trim() : '',
					shotId: isText(i.shot_id) ? i.shot_id : null,
					rule: isText(i.rule) ? i.rule : null,
					labels: Array.isArray(i.labels) ? i.labels.filter((x) => isText(x) && x.trim()) : [],
					measured: !SIMULATED_KINDS.includes(i.kind) && (i.measured === true || MEASURED_KINDS.includes(i.kind)),
					simulated: SIMULATED_KINDS.includes(i.kind)
				}))
		}))
		.filter((s) => s.issues.length);
	const checked = new Date(result?.checked_at ?? now);
	return { projectId: result?.project_id ?? null, checkedAt: Number.isNaN(checked.getTime()) ? new Date(now).toISOString() : checked.toISOString(), seams };
}

export function reviewCount(review) {
	return (review?.seams ?? []).reduce((sum, s) => sum + s.issues.length, 0);
}

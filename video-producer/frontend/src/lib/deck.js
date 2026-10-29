import { labelOf } from './labels.js';

export const DECK_TONES = { ready: 'muted', blocked: 'warning', running: 'signal', done: 'success', failed: 'danger' };

export const DECK_HEIGHT = 92;
export const DECK_COMPACT_CENTRE = 420;

export function deckCompact({ narrow = false, centre = Infinity, deck = DECK_HEIGHT } = {}) {
	if (narrow) return true;
	return centre + deck - DECK_HEIGHT < DECK_COMPACT_CENTRE;
}

export function deckState({ state, missing }) {
	if (state === 'running') return 'running';
	if (missing?.length) return 'blocked';
	if (state === 'failed') return 'failed';
	if (state === 'done') return 'done';
	return 'ready';
}

export const deckTone = (state) => DECK_TONES[state] ?? DECK_TONES.ready;

export function remainingSeconds(elapsed, progress) {
	if (!(elapsed > 0) || !(progress >= 5) || progress >= 100) return null;
	return (elapsed * (100 - progress)) / progress;
}

export function deckEyebrow({ target, clips, shots, label, rangeText, durationText }, t) {
	if (target === 'picked') return [clips === 1 ? t('production.scope.shot', { number: shots.list }) : shots.more ? t('production.scope.shotsMore', shots) : t('production.scope.shots', shots), t('production.deck.total', { duration: durationText })].join(' · ');
	if (target === 'sequence') return [t('production.target.sequence'), t('production.count.shots', { count: clips }), durationText].join(' · ');
	if (target === 'range') return [t('production.target.range'), rangeText, t('production.count.shots', { count: clips })].join(' · ');
	if (!clips) return [t('production.target.clip'), t('production.scope.none')].join(' · ');
	return [t('production.scope.shot', { number: shots.list }), label, rangeText].filter(Boolean).join(' · ');
}

export function deckTitle({ state, clips, current, percent, lastCount, failed, failedVariant }, t) {
	if (state === 'blocked') return t('production.deck.blocked');
	if (state === 'running') return current ? t('production.deck.running', { variant: current.variant, shot: current.shot, percent }) : t('production.deck.generating', { percent });
	if (state === 'done') return t('production.ready', { count: lastCount });
	if (state === 'failed') return failedVariant ? t('production.deck.failed', { variant: failedVariant }) : t('production.deck.failedCount', { count: failed });
	return t('production.deck.ready', { count: clips });
}

export const DECK_UNBLOCK = {
	noShot: 'review',
	noDirection: 'direction',
	emptyPrompts: 'shot',
	noEngine: 'engine',
	unavailable: 'engine',
	no_preset: 'engine',
	no_model: 'engine',
	missing_models: 'engine',
	profile_unsupported: 'engine'
};

export function deckUnblock(reason) {
	if (!reason) return null;
	const action = DECK_UNBLOCK[reason.code] ?? (reason.shotId ? 'shot' : null);
	if (!action) return null;
	return { action, shotId: action === 'shot' ? (reason.shotId ?? null) : null };
}

export function deckUnblockLabel(action, t) {
	if (action === 'shot') return t('production.deck.unblock.shot');
	if (action === 'direction') return t('production.deck.unblock.direction');
	if (action === 'review') return t('production.deck.unblock.review');
	return t('production.deck.unblock.engine');
}

export function deckDetail({ state, counts, missing, warnings, conflicts, step, queued, unblock = false, failure = '', retry = false, details = false, compare = false, finalPass = false }, t) {
	if (state === 'blocked') return { text: missing[0] ?? '', warn: true, whole: true, actions: unblock ? ['unblock'] : [] };
	if (state === 'running') return { text: [step, queued > 0 ? t('production.deck.queued', { count: queued }) : null].filter(Boolean).join(' · '), warn: false, whole: false, actions: ['enqueue'] };
	if (state === 'done') return { text: '', warn: false, whole: false, actions: ['results', ...(compare ? ['compare'] : []), ...(finalPass ? ['finalPass'] : [])] };
	if (state === 'failed') return { text: retry ? failure : '', warn: false, whole: true, actions: retry ? ['retry', ...(details ? ['details'] : [])] : ['results'] };
	return { text: warnings[0] ?? counts, warn: warnings.length > 0, whole: false, actions: conflicts > 0 ? ['conflicts'] : [] };
}

export function deckActions(actions, compact) {
	return compact ? actions.slice(0, 1) : actions;
}

export function deckCell({ state, timeText, vramText, cloud, over, oom = false, elapsed, remaining, lastSeconds, noEngine }, t, fmt) {
	if (state === 'running') return { label: t('production.deck.elapsed'), value: fmt(elapsed ?? 0), sub: remaining != null ? t('production.deck.remaining', { duration: fmt(remaining) }) : '', warn: false, vramWarn: false };
	if (state === 'done' && lastSeconds != null) return { label: t('production.deck.last'), value: fmt(lastSeconds), sub: '', warn: false, vramWarn: false };
	if (state === 'blocked' || noEngine) return { label: t('production.deck.estimated'), value: '—', sub: '', warn: false, vramWarn: false };
	return { label: t('production.deck.estimated'), value: timeText, sub: cloud ? '' : vramText, warn: Boolean(over), vramWarn: !cloud && state === 'failed' && Boolean(oom) };
}

export function latestDone(takes, count = 2) {
	return takes
		.filter((take) => take.status === 'done')
		.sort((a, b) => String(b.createdAt ?? '').localeCompare(String(a.createdAt ?? '')))
		.slice(0, count);
}

export function selectedEverywhere(clips, takes) {
	return clips.length > 0 && clips.every((clip) => takes.some((take) => take.shotId === clip.id && take.status === 'done' && labelOf(take) === 'final'));
}

export function deckChip({ engine, profile, size, drafts }, t) {
	return [engine, profile, size, drafts === null ? t('production.deck.draftsMixed') : t('production.deck.drafts', { count: drafts })].filter(Boolean);
}

export function deckChipFolded({ engine, short = engine, prefixes = [], profile, size, drafts }, fit, t) {
	const name = fit.engine === 'full' ? engine : fit.engine === 'cut' && fit.cut >= 0 ? `${prefixes[fit.cut]}…` : short;
	if (fit.tier === 'engine') return [name];
	if (fit.tier === 'profile') return [name, profile].filter(Boolean);
	return deckChip({ engine: name, profile, size, drafts }, t);
}

export function deckLine({ compact, eyebrow, detail }) {
	if (!compact || detail.warn || detail.whole || !eyebrow) return detail.text;
	return [eyebrow, detail.text].filter(Boolean).join(' · ');
}

export const DECK_STATES = ['ready', 'blocked', 'running', 'done', 'failed'];

export const DECK_TONES = { ready: 'muted', blocked: 'warning', running: 'signal', done: 'success', failed: 'danger' };

export const DECK_HEIGHT = 92;
export const DECK_COMPACT_HEIGHT = 56;
export const DECK_COMPACT_CENTRE = 440;

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

export function deckDetail({ state, counts, missing, warnings, conflicts, step, queued }, t) {
	if (state === 'blocked') return { text: missing[0] ?? '', warn: true, actions: [] };
	if (state === 'running') return { text: [step, queued > 0 ? t('production.deck.queued', { count: queued }) : null].filter(Boolean).join(' · '), warn: false, actions: ['enqueue'] };
	if (state === 'done' || state === 'failed') return { text: '', warn: false, actions: ['results'] };
	return { text: warnings[0] ?? counts, warn: warnings.length > 0, actions: conflicts > 0 ? ['conflicts'] : [] };
}

export function deckCell({ state, timeText, vramText, cloud, over, elapsed, remaining, lastSeconds, noEngine }, t, fmt) {
	if (state === 'running') return { label: t('production.deck.elapsed'), value: fmt(elapsed ?? 0), sub: remaining != null ? t('production.deck.remaining', { duration: fmt(remaining) }) : '', warn: false };
	if (state === 'done' && lastSeconds != null) return { label: t('production.deck.last'), value: fmt(lastSeconds), sub: '', warn: false };
	if (state === 'blocked' || noEngine) return { label: t('production.deck.estimated'), value: '—', sub: '', warn: false };
	return { label: t('production.deck.estimated'), value: timeText, sub: cloud ? '' : vramText, warn: Boolean(over) };
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
	if (!compact || detail.warn || !eyebrow) return detail.text;
	return [eyebrow, detail.text].filter(Boolean).join(' · ');
}

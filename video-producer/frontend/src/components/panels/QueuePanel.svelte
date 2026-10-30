<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, select, clipLabel, shotNumber } from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { cancelTake, prioritizeTake, presetById, queueState } from '../../lib/production.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { canPrioritize, handedOver, queueOrder } from '../../lib/queue.js';
	import { waitText } from '../../lib/chain.svelte.js';
	import { presetLabel } from '../../lib/generation.js';
	import { labelOf } from '../../lib/labels.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	const ordered = $derived(queueOrder(takeStore.list));
	const slots = $derived(queueState.slots);
	const elsewhere = $derived(queueState.elsewhere);
	const others = $derived((elsewhere?.waiting ?? 0) + (elsewhere?.inFlight ?? 0));
	const labelTone = { final: 'border-signal text-signal', candidate: 'border-success/60 text-success', rejected: 'border-danger/60 text-danger', draft: 'border-line-strong text-fg-muted' };

	const clipOf = (take) => doc.clips.find((c) => c.id === take.shotId) ?? null;
	const progress = (take) => (take.status === 'running' ? Math.round(Math.min(100, Math.max(0, take.progress ?? 0))) : 0);

	function shotText(take) {
		const clip = clipOf(take);
		return clip ? `${shotNumber(clip)} · ${clipLabel(clip)}` : t('panels.queue.shotGone');
	}

	function stateText(take) {
		if (take.status === 'running') return take.step || t('generation.state.running');
		if (handedOver(take)) return t('panels.queue.handed');
		const wait = waitText(take);
		if (wait) return wait;
		const place = queueState.positions[take.id];
		return place ? t('panels.queue.place', { place }) : t('lib.status.queued');
	}

	function engineText(take) {
		const preset = presetById(take.presetId);
		return preset ? presetLabel(preset) : '';
	}

	function goTo(take) {
		const clip = clipOf(take);
		if (!clip) return;
		select('clip', clip.id);
		seek(clip.start);
	}
</script>

<div class="flex flex-col gap-3 p-3">
	<div class="flex flex-wrap items-center justify-between gap-2 text-xs text-fg-muted">
		<span>{t('panels.queue.count', { count: ordered.length })}</span>
		{#if slots && slots.max != null}
			<HostUi name="Tooltip" props={{ text: t('panels.queue.slotsTip'), wrapperClass: 'inline-flex' }}>
				<span class="vp-tc flex items-center gap-1"><Icon name="layers" class="h-3.5 w-3.5" />{t('panels.queue.slots', { used: slots.inFlight, max: slots.max })}</span>
			</HostUi>
		{/if}
	</div>
	{#if others}
		<p class="text-xs text-fg-subtle">{t('panels.queue.elsewhere', { count: others })}</p>
	{/if}

	{#if !ordered.length}
		<HostUi name="EmptyState" props={{ compact: true, icon: hostIconName('list'), title: t('panels.queue.empty'), description: t('panels.queue.emptyHint') }} />
	{:else}
		<ol class="space-y-1.5" aria-label={t('panels.queue.title')}>
			{#each ordered as take (take.id)}
				{@const label = labelOf(take)}
				{@const running = take.status === 'running'}
				<li class="rounded-lg border p-2 {running ? 'border-signal/60' : 'border-line-strong'}" data-take={take.id}>
					<div class="flex items-center gap-2">
						<button type="button" class="min-w-0 flex-1 truncate text-left text-sm font-medium hover:underline" onclick={() => goTo(take)}>{shotText(take)}</button>
						<span class="vp-tc shrink-0 text-xs text-fg-muted">{take.variant}</span>
					</div>
					<div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-muted">
						<span>{take.quality === 'final' ? t('lib.stage.final') : t('lib.stage.draft')}</span>
						<span class="rounded-sm border px-1 text-2xs {labelTone[label]}">{t(`generation.label.${label}`)}</span>
						{#if engineText(take)}<span class="min-w-0 truncate text-fg-subtle">{engineText(take)}</span>{/if}
					</div>
					<div class="mt-1.5 flex items-center gap-2">
						<span class="min-w-0 flex-1 truncate text-xs {running ? 'text-signal' : 'text-fg-subtle'}">{stateText(take)}</span>
						{#if running}<span class="vp-tc text-xs text-fg-muted">{t('exports.percent', { value: progress(take) })}</span>{/if}
						<HostUi
							name="IconButton"
							props={{ icon: hostIconName('arrow-up'), label: t('panels.queue.prioritize', { variant: take.variant }), tooltip: canPrioritize(take, ordered) ? t('panels.queue.prioritizeTip') : t('panels.queue.prioritizeNo'), size: 'xs', disabled: !canPrioritize(take, ordered), onclick: () => prioritizeTake(take) }}
						/>
						<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('panels.queue.cancel', { variant: take.variant }), tooltip: t('panels.queue.cancelTip'), size: 'xs', onclick: () => cancelTake(take) }} />
					</div>
					{#if running}
						<div class="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('production.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress(take)}>
							<div class="h-full rounded-full bg-signal transition-[width] duration-150" style:width="{progress(take)}%"></div>
						</div>
					{/if}
				</li>
			{/each}
		</ol>
	{/if}
</div>

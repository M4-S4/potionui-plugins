<script>
	import { t } from '../../i18n/index.svelte.js';
	import { doc, shotNumber } from '../../lib/state.svelte.js';
	import { takesOf } from '../../lib/production.svelte.js';
	import { isInFlight } from '../../lib/generation.js';
	import { labelOf } from '../../lib/labels.js';
	import { waitText } from '../../lib/chain.svelte.js';
	import { chooseTake } from '../../lib/band.svelte.js';
	import { commandById } from '../../lib/commands.js';
	import ComposedPrompt from '../shots/ComposedPrompt.svelte';
	import ShotSummary from './ShotSummary.svelte';

	let { clip } = $props();

	const takes = $derived([...takesOf(clip)].sort((a, b) => String(a.variant).localeCompare(String(b.variant))));
	const choosable = (take) => (take.status === 'done' && Boolean(take.url)) || take.status === 'failed';
	const percent = (take) => Math.round(Math.min(100, Math.max(0, take.progress ?? 0)));

	function stateOf(take) {
		if (take.status === 'running') return `${t('generation.state.running')} · ${t('exports.percent', { value: percent(take) })}`;
		if (take.status === 'queued') return waitText(take) || t('lib.status.queued');
		if (take.status === 'failed') return t('lib.status.failed');
		if (take.status === 'cancelled') return t('lib.status.cancelled');
		return t(`generation.label.${labelOf(take)}`);
	}
</script>

<section class="space-y-1.5" data-shot-takes={clip.id}>
	<div class="vp-section-title">{t('inspector.tab.takes')}</div>
	{#each takes as take (take.id)}
		<button
			type="button"
			class="flex min-h-7 w-full items-center gap-2 rounded px-1.5 text-left text-xs transition-colors {choosable(take) ? 'hover:bg-surface-2' : 'cursor-default'}"
			disabled={!choosable(take)}
			onclick={() => chooseTake(take)}
		>
			<span class="w-14 shrink-0 text-fg-subtle">{t('panels.director.pick.takeLine', { variant: take.variant })}</span>
			<span class="min-w-0 flex-1 truncate {take.status === 'failed' ? 'text-danger' : isInFlight(take) ? 'text-signal' : 'text-fg'}">{stateOf(take)}</span>
		</button>
		{#if take.status === 'running'}
			<div class="mx-1.5 h-1 overflow-hidden rounded-full bg-surface-3" aria-hidden="true"><div class="h-full rounded-full bg-signal" style:width="{percent(take)}%"></div></div>
		{/if}
	{:else}
		<p class="text-xs text-fg-subtle">{t('panels.director.review.noTakes', { key: commandById('generate')?.key ?? '' })}</p>
	{/each}
	{#if takes.length}<p class="text-xs text-fg-subtle">{t('panels.director.pick.takesHint', { shot: shotNumber(clip) })}</p>{/if}
</section>

<ComposedPrompt source={doc} shotId={clip.id} />

<ShotSummary {clip} />

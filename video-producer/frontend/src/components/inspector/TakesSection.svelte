<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc } from '../../lib/state.svelte.js';
	import { takesOf, startGeneration, shotActivity, currentEngine, engineLabel } from '../../lib/production.svelte.js';
	import { aspectOf, draftResolution, finalResolution } from '../../lib/generation.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import TakeCard from '../takes/TakeCard.svelte';

	let { clip } = $props();
	const takes = $derived(takesOf(clip));
	const groups = $derived(
		[
			['final', t('inspector.takes.final'), takes.filter((r) => r.quality === 'final')],
			['draft', t('inspector.takes.drafts'), takes.filter((r) => r.quality === 'draft')]
		].filter(([, , list]) => list.length)
	);
	const engine = $derived(currentEngine());
	const running = $derived(shotActivity(clip.id).state === 'running');
	const aspect = $derived(aspectOf(doc.aspect, doc.resolution));
	const draftRes = $derived(draftResolution(engine?.info, ui.me?.settings?.draftResolution, aspect));
	const finalRes = $derived(finalResolution(engine?.info, aspect));
</script>

{#if !takes.length && takeStore.loaded}
	<HostUi name="EmptyState" props={{ compact: true, icon: 'layers', title: t('inspector.takes.empty'), description: t('inspector.takes.emptyHint') }} />
{/if}

{#each groups as [key, title, list] (key)}
	<section class="space-y-1.5">
		<div class="vp-section-title">{title} · {list.length}</div>
		<ul class="space-y-2">
			{#each list as take (take.id)}
				<TakeCard {take} {clip} />
			{/each}
		</ul>
	</section>
{/each}

<div class="space-y-1.5 rounded-lg bg-surface-2/60 p-2.5">
	<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'sparkles', class: 'w-full', disabled: running || !engine, onclick: () => startGeneration({ clips: [clip], quality: 'draft' }) }}>
		<span class="flex-1 truncate text-left">{t('inspector.takes.more', { count: doc.engine.variants ?? 1 })}</span>
		<span class="max-w-28 truncate text-fg-muted">{engineLabel()}</span>
	</HostUi>
	{#if draftRes && finalRes}<p class="text-xs text-fg-muted">{t('inspector.takes.note', { res: draftRes.replace('x', '×'), final: finalRes.replace('x', '×') })}</p>{/if}
</div>

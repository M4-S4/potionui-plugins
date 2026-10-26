<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc } from '../../lib/state.svelte.js';
	import { takesOf, currentEngine } from '../../lib/production.svelte.js';
	import { aspectOf, draftResolution, finalResolution } from '../../lib/generation.js';
	import { labelGroups, rejectedCount } from '../../lib/labels.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import TakeCard from '../takes/TakeCard.svelte';
	import DraftsField from '../shots/DraftsField.svelte';

	let { clip } = $props();
	const takes = $derived(takesOf(clip));
	const groups = $derived(labelGroups(takes, ui.hideRejected));
	const rejected = $derived(rejectedCount(takes));
	const engine = $derived(currentEngine());
	const aspect = $derived(aspectOf(doc.aspect, doc.resolution));
	const draftRes = $derived(draftResolution(engine?.info, ui.me?.settings?.draftResolution, aspect));
	const finalRes = $derived(finalResolution(engine?.info, aspect));
</script>

{#if !takes.length && takeStore.loaded}
	<HostUi name="EmptyState" props={{ compact: true, icon: 'layers', title: t('inspector.takes.empty'), description: t('inspector.takes.emptyHint') }} />
{/if}

{#if rejected}
	<div class="flex min-h-6 items-center justify-between gap-2 text-xs text-fg-muted">
		<label for="vp-hide-rejected-{clip.id}">{t('generation.labels.hideRejected', { count: rejected })}</label>
		<HostUi name="Switch" props={{ id: `vp-hide-rejected-${clip.id}`, checked: ui.hideRejected, size: 'lg', label: t('generation.labels.hideRejected', { count: rejected }), onchange: (v) => (ui.hideRejected = v) }} />
	</div>
{/if}

{#each groups as [key, list] (key)}
	<section class="space-y-1.5">
		<div class="vp-section-title">{t(`generation.labels.group.${key}`)} · {list.length}</div>
		<ul class="space-y-2">
			{#each list as take (take.id)}
				<TakeCard {take} {clip} />
			{/each}
		</ul>
	</section>
{/each}

<div class="space-y-1.5 rounded-lg bg-surface-2/60 p-2.5">
	<div class="flex items-center gap-2">
		<span class="min-w-0 flex-1 text-xs text-fg-muted">{t('inspector.takes.drafts')}</span>
		<DraftsField clips={[clip]} label={false} />
	</div>
	{#if draftRes && finalRes}<p class="text-xs text-fg-muted">{t('inspector.takes.note', { res: draftRes.replace('x', '×'), final: finalRes.replace('x', '×') })}</p>{/if}
</div>

<script>
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipLabel } from '../../lib/state.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { VIEWS, nextToReview, reviewCounts } from '../../lib/director.js';
	import { labelOf } from '../../lib/labels.js';
	import { takeThumb } from '../../lib/media.js';
	import { chooseTake } from '../../lib/band.svelte.js';
	import { commandById } from '../../lib/commands.js';

	const counts = $derived(reviewCounts(doc.clips, takeStore.list));
	const next = $derived(nextToReview(doc.clips, takeStore.list));
	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const views = $derived.by(() => {
		const keys = VIEWS.map((id) => commandById(`view-${id}`)?.key).filter(Boolean);
		return keys.length ? `${keys[0]}…${keys.at(-1).slice(-1)}` : '';
	});
	const shortcuts = $derived([
		[t('panels.director.pick.keyViews'), views],
		[t('inspector.empty.keyGenerate'), commandById('generate')?.key],
		[t('inspector.empty.keyCommands'), commandById('palette')?.key]
	]);

	function goNext() {
		chooseTake(next.take);
		ui.reveal = next.clip.id;
	}
</script>

<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs" data-review-counts>
	<dt class="text-fg-subtle">{t('panels.director.review.filter.review')}</dt>
	<dd class="text-fg-muted">{t('panels.director.pick.shots', { count: counts.review })}</dd>
	<dt class="text-fg-subtle">{t('panels.director.review.filter.running')}</dt>
	<dd class="text-fg-muted">{t('panels.director.pick.shots', { count: counts.running })}</dd>
	<dt class="text-fg-subtle">{t('panels.director.review.filter.final')}</dt>
	<dd class="text-fg-muted">{t('panels.director.pick.of', { count: counts.final, total: doc.clips.length })}</dd>
</dl>

{#if next}
	<section class="space-y-1.5">
		<div class="vp-section-title">{t('panels.director.pick.next')}</div>
		<button type="button" class="flex w-full items-center gap-2.5 rounded-lg border border-line-strong p-1.5 text-left transition-colors hover:border-line-hover hover:bg-surface-2" data-review-next={next.take.id} onclick={goNext}>
			<span class="block aspect-video w-20 shrink-0 overflow-hidden rounded bg-surface-3">{#if takeThumb(next.take)}<img src={takeThumb(next.take)} alt="" class="h-full w-full object-cover" />{/if}</span>
			<span class="min-w-0 flex-1">
				<span class="block truncate text-xs font-medium text-fg">{num(next.clip)} · {clipLabel(next.clip)}</span>
				<span class="block truncate text-xs text-fg-subtle">{t('panels.director.pick.nextTake', { variant: next.take.variant, label: t(`generation.label.${labelOf(next.take)}`) })}</span>
			</span>
		</button>
	</section>
{/if}

<div class="space-y-2 rounded-xl border border-dashed border-line-hover p-3 text-xs text-fg-muted">
	<p class="text-sm text-fg">{t('panels.director.pick.emptyTitle')}</p>
	<p>{t('panels.director.pick.emptyText')}</p>
	<ul class="space-y-1 pt-1">
		{#each shortcuts as [label, keys] (label)}
			<li class="flex justify-between gap-2"><span>{label}</span><kbd class="vp-kbd">{keys}</kbd></li>
		{/each}
	</ul>
</div>

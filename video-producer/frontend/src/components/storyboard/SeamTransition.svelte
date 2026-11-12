<script>
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { doc, act, relayout } from '../../lib/state.svelte.js';
	import { DISSOLVE_CHOICES, asked, dissolveBefore, limitOf, lostSeconds, setDissolve } from '../../lib/dissolve.js';
	import { shotChained } from '../../lib/chain.js';
	import { seamImage } from '../../lib/seam.js';

	let { clip } = $props();

	const id = $props.id();
	const index = $derived(doc.clips.findIndex((c) => c.id === clip?.id));
	const wanted = $derived(asked(clip));
	const applied = $derived(index > 0 ? dissolveBefore(doc.clips, index) : 0);
	const limit = $derived(index > 0 ? limitOf(doc.clips[index - 1], clip) : { seconds: 0, by: null });
	const choices = $derived(wanted && !DISSOLVE_CHOICES.includes(wanted) ? [...DISSOLVE_CHOICES, wanted].sort((a, b) => a - b) : DISSOLVE_CHOICES);
	const total = $derived(lostSeconds(doc.clips));
	const chained = $derived(Boolean(clip) && ((shotChained(doc, clip) && clip.stage !== 'source') || Boolean(seamImage(doc, clip.id, 'first')?.frameOf)));
	const value = (v) => formatNumber(v, { maximumFractionDigits: 2 });
	const sec = (v) => `${formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 2 })} s`;

	function choose(v) {
		act(() => {
			if (setDissolve(doc.clips, index, v)) relayout();
		});
	}
</script>

{#if index > 0}
	<div class="flex w-full flex-col gap-1.5" data-seam-transition={clip.id}>
		<div class="flex items-center gap-2">
			<label for={id} class="w-24 shrink-0 text-xs text-fg-muted">{t('timeline.dissolve.label')}</label>
			<select {id} class="input vp-dense min-w-0 flex-1" value={String(wanted)} onchange={(e) => choose(+e.currentTarget.value)}>
				<option value="0">{t('timeline.dissolve.cut')}</option>
				{#each choices as v (v)}<option value={String(v)}>{t('timeline.dissolve.value', { value: value(v) })}</option>{/each}
			</select>
		</div>
		{#if applied > 0}
			<p class="text-xs text-warning" data-dissolve-loss>{t('timeline.dissolve.shorter', { dur: sec(applied) })}</p>
			{#if limit.by === 'half'}<p class="text-xs text-fg-subtle" data-dissolve-capped>{t('timeline.dissolve.capped', { dur: sec(limit.seconds) })}</p>{/if}
			{#if limit.by === 'grid'}<p class="text-xs text-fg-subtle" data-dissolve-rounded>{t('timeline.dissolve.rounded', { dur: sec(limit.seconds) })}</p>{/if}
			{#if Math.abs(applied - limit.seconds) > 1e-6}<p class="text-xs text-fg-subtle" data-dissolve-overlap>{t('timeline.dissolve.overlap', { dur: sec(applied), asked: sec(limit.seconds) })}</p>{/if}
			{#if chained}<p class="text-xs text-fg-subtle" data-dissolve-chained>{t('timeline.dissolve.chained')}</p>{/if}
			{#if total > applied}<p class="text-xs text-fg-subtle" data-dissolve-total>{t('timeline.dissolve.total', { dur: sec(total) })}</p>{/if}
		{:else if wanted > 0 && limit.by === 'brief'}
			<p class="text-xs text-fg-subtle" data-dissolve-brief>{t('timeline.dissolve.tooBrief')}</p>
		{:else if wanted > 0}
			<p class="text-xs text-fg-subtle" data-dissolve-capped>{t('timeline.dissolve.tooShort')}</p>
		{:else}
			<p class="text-xs text-fg-subtle">{t('timeline.dissolve.hint')}</p>
		{/if}
	</div>
{/if}

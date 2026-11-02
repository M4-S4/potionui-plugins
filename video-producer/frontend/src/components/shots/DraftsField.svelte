<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, act } from '../../lib/state.svelte.js';
	import { MAX_DRAFTS, MIN_DRAFTS, setDrafts, sharedDrafts } from '../../lib/shots.js';

	let { clips = [], value = undefined, onchange = null, label = true, disabled = false, id = undefined } = $props();

	const options = Array.from({ length: MAX_DRAFTS - MIN_DRAFTS + 1 }, (_, i) => MIN_DRAFTS + i);
	const current = $derived(value !== undefined ? value : sharedDrafts(clips, doc.engine));
	const tip = $derived(clips.length > 1 && current === null ? t('generation.drafts.mixedTip') : t('generation.drafts.tip'));

	function change(e) {
		const n = Number(e.currentTarget.value);
		if (onchange) return onchange(n);
		act(() => setDrafts(clips, n));
	}
</script>

<HostUi name="Tooltip" props={{ text: tip, wrapperClass: 'inline-flex shrink-0 items-center' }}>
	<span class="inline-flex items-center gap-1.5">
		{#if label}<span class="text-xs text-fg-muted">{t('generation.drafts.label')}</span>{/if}
		<select {id} class="vp-popup vp-tc" style:padding-left={label ? null : '0.5rem'} style:padding-right={label ? null : '1.375rem'} style:background-position={label ? null : 'calc(100% - 10px) 52%, calc(100% - 6px) 52%'} value={current ?? ''} {disabled} aria-label={t('generation.drafts.aria')} onchange={change} onclick={(e) => e.stopPropagation()}>
			{#if current === null}<option value="" disabled>{t('generation.drafts.mixed')}</option>{/if}
			{#each options as n (n)}<option value={n}>{t('generation.drafts.option', { count: n })}</option>{/each}
		</select>
	</span>
</HostUi>

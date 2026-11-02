<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { scrollShade } from '../../lib/scrollshade.js';

	let { items, value, onselect, label, class: className = '', children } = $props();
</script>

<div class="vp-pills no-scrollbar flex min-w-0 items-center gap-1 overflow-x-auto p-1 {className}" role="tablist" aria-label={label} use:scrollShade>
	{#each items as item (item.id)}
		{#if item.tip}
			<HostUi name="Tooltip" props={{ text: item.tip }}>{@render pill(item)}</HostUi>
		{:else}
			{@render pill(item)}
		{/if}
	{/each}
	{@render children?.()}
</div>

{#snippet pill(item)}
	<button type="button" role="tab" class="vp-pill shrink-0" aria-selected={value === item.id} onclick={() => onselect(item.id)}>{item.label}{#if item.count != null}<span class="vp-tc text-2xs text-fg-subtle">{item.count}</span>{/if}</button>
{/snippet}

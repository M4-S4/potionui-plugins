<script>
	import Icon from '../Icon.svelte';

	let { icon = null, title, subtitle = '', lead, children } = $props();
</script>

<div class="vp-zone-head">
	{@render lead?.()}
	{#if icon}<Icon name={icon} class="h-4 w-4 shrink-0 text-fg-muted" />{/if}
	<h2 class="shrink-0 whitespace-nowrap text-sm font-semibold">{title}</h2>
	{#if subtitle}<span class="vp-tc shrink-0 whitespace-nowrap text-xs text-fg-subtle">{subtitle}</span>{/if}
	{@render children?.()}
</div>

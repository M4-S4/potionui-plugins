<script>
	import Icon from '../Icon.svelte';

	let { icon = null, title, subtitle = '', border = true, children } = $props();
</script>

<div class="vp-panel-head" class:border-b={border} class:border-line={border}>
	{#if icon}<Icon name={icon} class="h-4 w-4 shrink-0 text-fg-muted" />{/if}
	<h2 class="shrink-0 text-sm font-semibold">{title}</h2>
	{#if subtitle}<span class="min-w-0 truncate text-xs text-fg-subtle">{subtitle}</span>{/if}
	<div class="flex-1"></div>
	{@render children?.()}
</div>

<script>
	let { items, value, onselect, label, class: className = '', children } = $props();
</script>

<div class="vp-tabs {className}" role="tablist" aria-label={label}>
	{#each items as tab (tab.id)}
		<button type="button" role="tab" aria-selected={value === tab.id} onclick={() => onselect(tab.id)}>
			{tab.label}
			{#if tab.badge}<span class="vp-tabs-badge">{tab.badge}</span>{/if}
			{#if tab.dot}<span class="h-1.5 w-1.5 rounded-full bg-warning"></span>{/if}
		</button>
	{/each}
	{#if children}<div class="flex-1"></div>{@render children()}{/if}
</div>

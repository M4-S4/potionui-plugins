<script>
	import { paths } from '../lib/icons.js';

	let { name, class: className = 'h-4 w-4', strokeWidth = 1.75 } = $props();

	const d = $derived(paths[name] ?? null);
</script>

{#if d}
	<svg class={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
		{#each d as path}
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width={strokeWidth} d={path} />
		{/each}
	</svg>
{:else}
	<span class="{className} inline-flex items-center justify-center text-xs" aria-hidden="true">{name?.[0] ?? ''}</span>
{/if}

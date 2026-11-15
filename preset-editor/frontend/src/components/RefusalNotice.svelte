<script>
	import Icon from './Icon.svelte';

	let { refusal, onClose } = $props();
</script>

<div class="space-y-1 rounded border border-danger/40 bg-danger/10 px-2 py-1 text-xs text-danger" role="alert">
	<div class="flex items-center gap-2">
		<p class="flex-1 font-semibold">{refusal.title}</p>
		<button type="button" class="rounded p-0.5 text-fg-subtle hover:text-danger" title="Close" onclick={onClose}>
			<Icon name="close" class="h-3.5 w-3.5" />
		</button>
	</div>
	{#if refusal.lines.length}
		<ul class="space-y-0.5 break-all font-mono">
			{#each refusal.lines as line, position (position)}
				<li>{line}</li>
			{/each}
		</ul>
		<p>{refusal.ending}</p>
	{/if}
</div>

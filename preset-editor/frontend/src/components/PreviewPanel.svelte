<script>
	import HostUi from '../../../../../sdk/HostUi.svelte';

	let { presetId, modes = [], publishedAt = null } = $props();

	let mode = $state(modes[0] ?? '');
	let open = $state(false);

	$effect(() => {
		if (!modes.includes(mode)) mode = modes[0] ?? '';
	});
</script>

<section class="rounded-lg border border-line bg-surface-1">
	<header class="flex flex-wrap items-center gap-2 px-4 py-2.5">
		<h3 class="text-sm font-semibold text-fg">Form preview</h3>
		<span class="text-xs text-fg-subtle">of the published version{publishedAt ? '' : ' (publish first)'}</span>
		<span class="flex-1"></span>
		{#if publishedAt && modes.length}
			<select class="input text-xs" bind:value={mode} aria-label="Mode to preview">
				{#each modes as item (item)}
					<option value={item}>{item}</option>
				{/each}
			</select>
			<button type="button" class="rounded px-2 py-0.5 text-xs text-fg-muted hover:bg-surface-3/60 hover:text-fg" onclick={() => (open = !open)}>{open ? 'Hide' : 'Show'}</button>
		{/if}
	</header>
	{#if open && publishedAt && mode}
		<div class="border-t border-line px-4 py-3">
			{#key `${presetId}:${mode}:${publishedAt}`}
				<HostUi name="DynamicForm" props={{ presetId, mode, audience: 'advanced', initialData: {}, onFormDataChange: () => {} }} />
			{/key}
		</div>
	{/if}
</section>

<script>
	import ActionButton from './ActionButton.svelte';
	import { downloadPreset } from '../lib/client.js';
	import { clickOutside, onEscape, toast } from '../lib/dom.js';

	let { api, entries = [], phase = 'ready', error = '', pageRoute = '/plugins/preset-editor' } = $props();

	let open = $state(false);

	$effect(() => {
		if (!open) return;
		return onEscape(() => (open = false));
	});

	async function download(entry) {
		open = false;
		const result = await downloadPreset(api, entry.id);
		if (!result.ok) toast('error', result.error.message);
	}
</script>

<div class="relative" use:clickOutside={() => (open = false)}>
	<ActionButton icon="edit" ariaHaspopup="menu" ariaExpanded={open} title="Edit a local preset in the Preset Editor" onclick={() => (open = !open)}>
		Edit…
	</ActionButton>
	{#if open}
		<div class="absolute right-0 z-20 mt-1 w-64 overflow-hidden rounded-md border border-line bg-surface-2 shadow-lg" role="menu">
			{#if phase === 'loading'}
				<p class="px-3 py-2 text-xs text-fg-subtle">Loading…</p>
			{:else if phase === 'error'}
				<p class="px-3 py-2 text-xs text-danger">{error}</p>
			{:else if entries.length === 0}
				<p class="px-3 py-2 text-xs text-fg-subtle">No local preset yet. Duplicate one with New Preset.</p>
			{:else}
				<ul class="max-h-72 overflow-y-auto py-1">
					{#each entries as entry (entry.id)}
						<li class="flex items-stretch">
							<a
								href="{pageRoute}?preset={encodeURIComponent(entry.id)}"
								class="block min-w-0 flex-1 px-3 py-1.5 text-xs text-fg hover:bg-surface-3"
								role="menuitem"
								onclick={() => (open = false)}
							>
								<span class="block truncate font-medium">{entry.name}</span>
								<span class="block truncate font-mono text-2xs text-fg-subtle">{entry.path}</span>
							</a>
							<button type="button" class="flex items-center px-2 text-2xs text-fg-subtle hover:bg-surface-3 hover:text-fg" role="menuitem" title="Download {entry.name} as a zip archive" onclick={() => download(entry)}>zip</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</div>

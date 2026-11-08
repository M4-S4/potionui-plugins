<script>
	import HostUi from '../../../../../sdk/HostUi.svelte';
	import { downloadPreset } from '../lib/client.js';
	import { clickOutside, onEscape, toast } from '../lib/dom.js';

	let { api, entries = [], phase = 'ready', error = '', pageRoute = '/plugins/preset-editor' } = $props();

	let open = $state(false);
	let downloading = $state('');

	$effect(() => {
		if (!open) return;
		return onEscape(() => (open = false));
	});

	async function download(entry) {
		if (downloading) return;
		downloading = entry.id;
		const result = await downloadPreset(api, entry.id);
		downloading = '';
		open = false;
		if (!result.ok) toast('error', result.error.message);
	}
</script>

<div class="relative" use:clickOutside={() => (open = false)}>
	<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'edit', loading: !!downloading, ariaHaspopup: 'menu', ariaExpanded: open, onclick: () => (open = !open), attrs: { title: downloading ? 'Downloading the zip archive…' : 'Edit a local preset in the Preset Editor' } }}>Edit…</HostUi>
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
							<button type="button" class="flex items-center gap-1 px-2 text-2xs text-fg-subtle hover:bg-surface-3 hover:text-fg disabled:cursor-not-allowed disabled:opacity-50" role="menuitem" title="Download {entry.name} as a zip archive" disabled={!!downloading} aria-busy={downloading === entry.id ? 'true' : undefined} onclick={() => download(entry)}>
								{#if downloading === entry.id}
									<span class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-current" aria-hidden="true"></span>
									Downloading…
								{:else}
									zip
								{/if}
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}
</div>

<script>
	import { onMount } from 'svelte';
	import ActionButton from './ActionButton.svelte';
	import Pill from './Pill.svelte';
	import { listHistory, restoreVersion } from '../lib/client.js';
	import { formatStamp, formatTimestamp } from '../lib/drafts.js';
	import { toast } from '../lib/dom.js';

	let { api, preset, onBack, onRestored } = $props();

	let phase = $state('loading');
	let entries = $state.raw([]);
	let error = $state('');
	let restoring = $state('');

	onMount(load);

	async function load() {
		phase = 'loading';
		const result = await listHistory(api, preset.id);
		if (!result.ok) {
			error = result.error.message;
			phase = 'error';
			return;
		}
		entries = Array.isArray(result.data) ? result.data : [];
		phase = 'ready';
	}

	async function restore(entry) {
		restoring = entry.stamp;
		const result = await restoreVersion(api, preset.id, entry.stamp);
		restoring = '';
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		toast('success', 'Version restored as a draft');
		onRestored?.(result.data);
	}
</script>

<div class="space-y-4">
	<div class="flex flex-wrap items-center gap-2">
		<ActionButton variant="ghost" icon="arrow-left" onclick={onBack}>All presets</ActionButton>
		<h2 class="min-w-0 flex-1 truncate text-base font-semibold text-fg">History of {preset.name}</h2>
		<span class="font-mono text-xs text-fg-subtle">{preset.id}</span>
	</div>

	<section class="rounded-lg border border-line bg-surface-1">
		{#if phase === 'loading'}
			<p class="px-4 py-6 text-center text-sm text-fg-subtle">Loading…</p>
		{:else if phase === 'error'}
			<p class="px-4 py-6 text-center text-sm text-danger">{error}</p>
		{:else if entries.length === 0}
			<p class="px-4 py-6 text-center text-sm text-fg-subtle">No previous version: a version is kept each time the preset is published over or deleted.</p>
		{:else}
			<ul class="divide-y divide-line">
				{#each entries as entry (entry.stamp)}
					<li class="flex flex-wrap items-center gap-3 px-4 py-2.5">
						<div class="min-w-0 flex-1">
							<p class="text-sm text-fg">
								{entry.name ?? preset.name}{#if entry.version}<span class="text-fg-subtle"> · v{entry.version}</span>{/if}
							</p>
							<p class="text-xs text-fg-subtle">
								{formatStamp(entry.stamp)}{#if entry.archived_at} ({formatTimestamp(entry.archived_at)}){/if}
								{#if entry.target_dir}· <span class="font-mono">{entry.target_dir}</span>{/if}
							</p>
						</div>
						<Pill tone={entry.reason === 'delete' ? 'danger' : 'neutral'}>{entry.reason === 'delete' ? 'deleted' : 'replaced'}</Pill>
						<ActionButton icon="restore" loading={restoring === entry.stamp} disabled={!!restoring} title="Open this version as a draft" onclick={() => restore(entry)}>Restore</ActionButton>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</div>

<script>
	import ActionButton from './ActionButton.svelte';
	import Icon from './Icon.svelte';
	import Pill from './Pill.svelte';
	import { KIND_LABELS, countByKind, coverUrl, filterPresets, sortPresets } from '../lib/catalog.js';
	import { describeSource, formatTimestamp } from '../lib/drafts.js';

	let {
		entries = [],
		drafts = [],
		busyId = null,
		onDuplicate,
		onEdit,
		onDelete,
		onHistory,
		onOpenDraft,
		onDiscardDraft,
		onRefresh
	} = $props();

	let query = $state('');
	let kind = $state('all');
	let installed = $state('all');

	const counts = $derived(countByKind(entries));
	const shown = $derived(sortPresets(filterPresets(entries, { query, kind, installed })));
	const KIND_FILTERS = ['all', 'local', 'marketplace', 'plugin'];
	const KIND_TONES = { local: 'accent', marketplace: 'neutral', plugin: 'info' };
</script>

{#if drafts.length}
	<section class="mb-6 rounded-lg border border-line bg-surface-1">
		<header class="flex items-center gap-2 border-b border-line px-4 py-2.5">
			<Icon name="edit" class="h-4 w-4 text-fg-subtle" />
			<h2 class="text-sm font-semibold text-fg">Drafts</h2>
			<Pill tone="neutral">{drafts.length}</Pill>
		</header>
		<ul class="divide-y divide-line">
			{#each drafts as draft (draft.draft_id)}
				<li class="flex flex-wrap items-center gap-3 px-4 py-2.5">
					<div class="min-w-0 flex-1">
						<p class="truncate text-sm font-medium text-fg">{draft.name}</p>
						<p class="truncate text-xs text-fg-subtle">
							{describeSource(draft.source)} · <span class="font-mono">{draft.target_dir}</span> · updated {formatTimestamp(draft.updated_at)}
							{#if draft.published_at}· published{/if}
						</p>
					</div>
					{#if draft.last_lint}
						<Pill tone={draft.last_lint.errors?.length ? 'danger' : 'success'}>
							{draft.last_lint.errors?.length ? `${draft.last_lint.errors.length} lint error${draft.last_lint.errors.length > 1 ? 's' : ''}` : 'lint ok'}
						</Pill>
					{/if}
					<ActionButton variant="primary" icon="edit" onclick={() => onOpenDraft?.(draft)}>Open</ActionButton>
					<ActionButton variant="ghost" icon="trash" title="Discard this draft" onclick={() => onDiscardDraft?.(draft)}>Discard</ActionButton>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<section class="rounded-lg border border-line bg-surface-1">
	<header class="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
		<h2 class="text-sm font-semibold text-fg">Presets</h2>
		<Pill tone="neutral">{shown.length} / {entries.length}</Pill>
		<div class="ml-auto flex flex-wrap items-center gap-2">
			<label class="relative">
				<span class="sr-only">Search presets</span>
				<Icon name="search" class="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-subtle" />
				<input type="search" class="input w-48 pl-7 text-xs" placeholder="Search by name, id or folder" bind:value={query} />
			</label>
			<select class="input text-xs" bind:value={installed} aria-label="Installation state">
				<option value="all">Installed or not</option>
				<option value="installed">Installed</option>
				<option value="available">Not installed</option>
			</select>
			{#if onRefresh}
				<ActionButton variant="ghost" icon="refresh" title="Reload the catalogue" onclick={onRefresh}>Refresh</ActionButton>
			{/if}
		</div>
	</header>
	<div class="flex flex-wrap gap-1.5 border-b border-line px-4 py-2" role="group" aria-label="Preset origin">
		{#each KIND_FILTERS as filter (filter)}
			<button
				type="button"
				class="rounded px-2 py-0.5 text-xs transition-colors {kind === filter ? 'bg-accent/10 text-accent' : 'text-fg-muted hover:bg-surface-3/60 hover:text-fg'}"
				aria-pressed={kind === filter}
				onclick={() => (kind = filter)}
			>
				{filter === 'all' ? 'All' : KIND_LABELS[filter]} <span class="text-fg-subtle">{counts[filter]}</span>
			</button>
		{/each}
	</div>
	{#if shown.length === 0}
		<p class="px-4 py-8 text-center text-sm text-fg-subtle">No preset matches.</p>
	{:else}
		<ul class="divide-y divide-line">
			{#each shown as entry (entry.id)}
				<li class="flex flex-wrap items-center gap-3 px-4 py-2.5">
					{#if coverUrl(entry)}
						<img src={coverUrl(entry)} alt="" class="h-10 w-10 flex-shrink-0 rounded bg-surface-3 object-cover" loading="lazy" />
					{:else}
						<span class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded bg-surface-3 text-fg-subtle" aria-hidden="true">
							<Icon name="document" class="h-4 w-4" />
						</span>
					{/if}
					<div class="min-w-0 flex-1">
						<p class="flex min-w-0 flex-wrap items-center gap-1.5">
							<span class="truncate text-sm font-medium text-fg" title={entry.name}>{entry.name}</span>
							<Pill tone={KIND_TONES[entry.kind] ?? 'neutral'}>{entry.kind === 'plugin' && entry.pluginId ? entry.pluginId : KIND_LABELS[entry.kind]}</Pill>
							{#if entry.installed}<Pill tone="success">installed</Pill>{/if}
						</p>
						<p class="truncate text-xs text-fg-subtle">
							<span class="font-mono">{entry.id}</span>
							{#if entry.path}· <span class="font-mono">{entry.path}</span>{/if}
							{#if entry.engine}· {entry.engine}{/if}
							{#if entry.modes.length}· {entry.modes.join(', ')}{/if}
						</p>
					</div>
					<div class="flex flex-wrap items-center gap-1.5">
						<ActionButton icon="copy" title="Create a local copy of this preset" loading={busyId === entry.id} onclick={() => onDuplicate?.(entry)}>Duplicate</ActionButton>
						{#if entry.editable}
							<ActionButton variant="primary" icon="edit" title="Open a draft of this preset" loading={busyId === entry.id} onclick={() => onEdit?.(entry)}>Edit</ActionButton>
							<ActionButton variant="ghost" icon="history" title="Previous versions" onclick={() => onHistory?.(entry)}>History</ActionButton>
							<ActionButton variant="ghost" icon="trash" title="Delete this local preset" onclick={() => onDelete?.(entry)}>Delete</ActionButton>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</section>

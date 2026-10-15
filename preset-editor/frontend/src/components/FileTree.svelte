<script>
	import Icon from './Icon.svelte';
	import { buildTree, flattenTree } from '../lib/files.js';

	let { files = [], selected = '', onSelect } = $props();

	const rows = $derived(flattenTree(buildTree(files)));
	const ICONS = { manifest: 'document', description: 'document', pipeline: 'publish', form: 'edit', tab: 'edit', media: 'folder', options: 'document' };
</script>

<ul class="space-y-0.5 text-xs" role="tree">
	{#each rows as row (row.path)}
		<li role="treeitem" aria-selected={row.path === selected}>
			{#if row.kind === 'dir'}
				<span class="flex items-center gap-1 py-0.5 text-fg-subtle" style="padding-left: {row.depth * 12}px">
					<Icon name="folder" class="h-3.5 w-3.5" />{row.name}
				</span>
			{:else}
				<button
					type="button"
					class="flex w-full items-center gap-1 rounded py-0.5 pr-1 text-left transition-colors {row.path === selected ? 'bg-accent/15 text-accent' : row.editable || row.media ? 'text-fg hover:bg-surface-3/60' : 'text-fg-subtle'}"
					style="padding-left: {row.depth * 12}px"
					disabled={!row.editable && !row.media}
					title={row.editable ? row.path : row.media ? `${row.path} (${row.size} B, opens the media editor)` : `${row.path} (${row.size} B, not editable as text)`}
					onclick={() => onSelect?.(row.path)}
				>
					<Icon name={ICONS[row.fileKind] ?? 'document'} class="h-3.5 w-3.5 flex-shrink-0" />
					<span class="truncate">{row.name}</span>
				</button>
			{/if}
		</li>
	{/each}
</ul>

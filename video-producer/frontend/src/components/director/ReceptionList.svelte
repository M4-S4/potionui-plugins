<script>
	import { t } from '../../i18n/index.svelte.js';
	import { doc, shotNumber } from '../../lib/state.svelte.js';
	import Icon from '../Icon.svelte';

	let { rows, label } = $props();

	const shotsText = (clips) => (clips.length > 3 ? t('panels.director.refs.shots', { count: clips.length }) : t('panels.director.refs.listed', { count: clips.length, list: clips.map(shotNumber).join(', ') }));
</script>

<ul class="space-y-2" aria-label={label} data-reception>
	{#each rows as row (row.key)}
		<li class="min-w-0" data-reception-row={row.status}>
			<div class="flex items-baseline gap-2">
				<span class="min-w-0 flex-1 truncate text-sm" title={row.title}>{row.title}</span>
				<span class="flex shrink-0 items-center gap-1 text-xs {row.tone}">{#if row.ok}<Icon name="check" class="h-3 w-3" />{/if}{row.text}</span>
			</div>
			<div class="text-xs text-fg-subtle">{shotsText(row.shots)}</div>
		</li>
	{/each}
</ul>

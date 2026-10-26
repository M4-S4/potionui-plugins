<script>
	import { doc } from '../../lib/state.svelte.js';
	import { TAG_CLASS, referenceTags } from '../../lib/reftags.js';
	import { refTagLabel, refTagTip } from '../../lib/references.js';
	import Icon from '../Icon.svelte';

	let { reference, class: extra = '' } = $props();

	const tags = $derived(referenceTags(doc, reference));
</script>

<span class="flex min-w-0 flex-wrap items-center gap-1 {extra}" data-ref-tags>
	{#each tags as tag, i (i)}
		<span class={TAG_CLASS} title={refTagTip(tag)} data-ref-tag={tag.kind}>
			{#if tag.icon}<Icon name={tag.icon} class="h-3 w-3 shrink-0" />{/if}
			<span class="truncate">{refTagLabel(tag)}</span>
		</span>
	{/each}
</span>

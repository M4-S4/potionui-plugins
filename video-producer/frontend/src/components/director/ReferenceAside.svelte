<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, deleteSelection } from '../../lib/state.svelte.js';
	import { panelSelection } from '../../lib/director.js';
	import { typeIcon } from '../../lib/reftags.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import ReferenceChosen from './ReferenceChosen.svelte';
	import ReferenceShot from './ReferenceShot.svelte';
	import ReferenceProject from './ReferenceProject.svelte';
	import ElsewhereNote from '../inspector/ElsewhereNote.svelte';
	import Icon from '../Icon.svelte';

	const filtered = $derived(panelSelection('references', ui.selection));
	const reference = $derived(filtered.shown?.kind === 'reference' ? (doc.references.find((r) => r.id === filtered.shown.id) ?? null) : null);
	const clip = $derived(filtered.shown?.kind === 'clip' ? (doc.clips.find((c) => c.id === filtered.shown.id) ?? null) : null);
	const head = $derived.by(() => {
		if (reference) return { icon: typeIcon(reference), title: t('panels.director.refs.reference'), sub: '' };
		if (clip) return { icon: 'bookmark', title: t('panels.director.refs.ofShot'), sub: String(doc.clips.indexOf(clip) + 1).padStart(2, '0') };
		return { icon: 'bookmark', title: commandById('view-references')?.label ?? '', sub: '' };
	});
</script>

<aside class="flex min-h-0 flex-col overflow-hidden border-l border-line bg-surface-1" aria-label={head.title} class:invisible={!ui.inspectorOpen} data-reference-aside={reference ? 'reference' : clip ? 'shot' : 'none'}>
	<div class="vp-panel-head border-b border-line">
		<Icon name={head.icon} class="h-4 w-4 text-fg-muted" />
		<span class="truncate text-sm font-semibold">{head.title}</span>
		{#if head.sub}<span class="vp-tc shrink-0 text-xs text-fg-subtle">{head.sub}</span>{/if}
		<div class="flex-1"></div>
		<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('inspector.close'), tooltip: t('inspector.closeTip'), kbd: commandById('inspector')?.key, size: 'sm', class: 'vp-h7', onclick: () => (ui.inspectorOpen = false) }} />
	</div>
	<div class="min-h-0 flex-1 overflow-auto">
		{#key reference?.id ?? clip?.id ?? 'none'}
			{#if reference}
				<ReferenceChosen {reference} />
			{:else if clip}
				<ReferenceShot {clip} />
			{:else}
				<ReferenceProject />
			{/if}
		{/key}
	</div>
	{#if filtered.elsewhere}<ElsewhereNote kind={filtered.elsewhere.kind} />{/if}
	{#if reference}
		<div class="flex shrink-0 items-center justify-end border-t border-line px-3 py-2">
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'trash', onclick: deleteSelection }}>{t('inspector.reference.remove')}</HostUi>
		</div>
	{/if}
</aside>

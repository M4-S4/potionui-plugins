<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipLabel } from '../../lib/state.svelte.js';
	import { instructionOf } from '../../lib/bible.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import ComposedPrompt from '../shots/ComposedPrompt.svelte';
	import Icon from '../Icon.svelte';

	const picked = $derived(ui.selection?.kind === 'clip' ? doc.clips.find((c) => c.id === ui.selection.id) : null);
	const witness = $derived(doc.clips.find((c) => c.id === ui.witness) ?? picked ?? doc.clips.find((c) => instructionOf(doc, c)) ?? doc.clips[0] ?? null);
	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
</script>

<aside class="flex min-h-0 flex-col overflow-hidden border-l border-line bg-surface-1" aria-label={t('panels.director.aside.prompt')} class:invisible={!ui.inspectorOpen}>
	<div class="vp-panel-head border-b border-line">
		<Icon name="type" class="h-4 w-4 text-fg-muted" />
		<span class="truncate text-sm font-semibold">{t('panels.director.aside.prompt')}</span>
		<div class="flex-1"></div>
		<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('inspector.close'), tooltip: t('inspector.closeTip'), kbd: commandById('inspector')?.key, size: 'sm', class: 'vp-h7', onclick: () => (ui.inspectorOpen = false) }} />
	</div>
	<div class="min-h-0 flex-1 space-y-3 overflow-auto p-3">
		{#if witness}
			<label class="block space-y-1">
				<span class="vp-label">{t('panels.director.aside.witness')}</span>
				<select class="vp-popup w-full" value={witness.id} onchange={(e) => (ui.witness = e.currentTarget.value)}>
					{#each doc.clips as c (c.id)}<option value={c.id}>{num(c)} · {clipLabel(c)}</option>{/each}
				</select>
			</label>
			<p class="text-xs text-fg-subtle">{t('panels.director.aside.hint')}</p>
			<ComposedPrompt source={doc} shotId={witness.id} />
		{:else}
			<p class="text-xs text-fg-subtle">{t('panels.director.aside.none')}</p>
		{/if}
	</div>
</aside>

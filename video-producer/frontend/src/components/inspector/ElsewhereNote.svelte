<script>
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, selected, shotNumber } from '../../lib/state.svelte.js';
	import { spaceLabel } from '../../lib/commands.js';
	import { promptShot } from '../../lib/director.js';
	import { laneTitle } from '../../lib/tracks.js';
	import Icon from '../Icon.svelte';

	let { kind } = $props();

	const item = $derived(selected());

	function nameOf(it) {
		if (kind === 'audio' || kind === 'frame') return asset(it.assetId)?.name ?? '';
		if (kind === 'lane') return laneTitle(doc.lanes, it);
		if (kind === 'prompt') {
			const text = String(it.text ?? '').trim();
			const shot = promptShot(doc, it);
			return text.length > 40 ? `${text.slice(0, 39).trim()}…` : text || (shot ? shotNumber(shot) : '');
		}
		return it.name ?? it.text ?? it.label ?? '';
	}

	function textOf(it) {
		const params = { name: nameOf(it), space: spaceLabel(ui.selectedIn) ?? t('inspector.elsewhere.space') };
		if (kind === 'audio') return t('inspector.elsewhere.audio', params);
		if (kind === 'title') return t('inspector.elsewhere.title', params);
		if (kind === 'prompt') return t('inspector.elsewhere.prompt', params);
		if (kind === 'frame') return t('inspector.elsewhere.frame', params);
		if (kind === 'marker') return t('inspector.elsewhere.marker', params);
		if (kind === 'reference') return t('inspector.elsewhere.reference', params);
		return t('inspector.elsewhere.lane', params);
	}
</script>

{#if item}
	<p class="flex shrink-0 items-start gap-1.5 border-t border-dashed border-line-strong px-3 py-2 text-xs text-fg-subtle" data-elsewhere={kind}>
		<Icon name="info" class="mt-px h-3.5 w-3.5 shrink-0" />
		<span class="min-w-0">{textOf(item)}</span>
	</p>
{/if}

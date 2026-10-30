<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui } from '../../lib/state.svelte.js';
	import { AUTO_TARGET } from '../../lib/finalpass.js';
	import { targetLabel } from '../../lib/finalpass.svelte.js';

	let { upscaler = $bindable(), rtxSource = $bindable(), target = $bindable(), targets, ready, engine = false, rtxShown = false } = $props();

	const upscalers = $derived([
		{ id: 'auto', label: t('generation.finalPass.upscaler.auto') },
		{ id: 'rtx', label: t('generation.finalPass.upscaler.rtx'), disabled: ui.me?.features?.upscalers?.rtx !== true },
		{ id: 'seedvr2', label: t('generation.finalPass.upscaler.seedvr2'), disabled: ui.me?.features?.upscalers?.seedvr2 !== true },
		...(engine ? [{ id: 'engine', label: t('generation.finalPass.upscaler.engine') }] : [])
	]);
	const rtxSources = $derived([
		{ id: 'compressed', label: t('generation.finalPass.rtxSource.compressed') },
		{ id: 'clean', label: t('generation.finalPass.rtxSource.clean') }
	]);
</script>

<div class="flex items-center gap-3">
	<span class="shrink-0 text-xs text-fg-muted">{t('generation.finalPass.upscaler.label')}</span>
	<HostUi name="SegmentedControl" props={{ variant: 'toggle', ariaLabel: t('generation.finalPass.upscaler.label'), items: upscalers, selected: upscaler, onSelect: (id) => (upscaler = id) }} />
</div>
{#if rtxShown}
	<div class="flex items-center gap-3">
		<span class="shrink-0 text-xs text-fg-muted">{t('generation.finalPass.rtxSource.label')}</span>
		<HostUi name="SegmentedControl" props={{ variant: 'toggle', ariaLabel: t('generation.finalPass.rtxSource.label'), items: rtxSources, selected: rtxSource, onSelect: (id) => (rtxSource = id) }} />
	</div>
	<p class="text-xs text-fg-subtle">{rtxSource === 'clean' ? t('generation.finalPass.rtxSource.cleanHint') : t('generation.finalPass.rtxSource.compressedHint')}</p>
{/if}
<HostUi name="SegmentedControl" props={{ variant: 'toggle', fullWidth: true, ariaLabel: t('generation.final.target'), items: targets.map((id) => ({ id, label: targetLabel(id), disabled: !ready })), selected: target, onSelect: (id) => (target = id) }} />
{#if target === AUTO_TARGET}<p class="text-xs text-fg-subtle">{t('generation.finalPass.targetAuto')}</p>{/if}

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { doc, act, toast } from '../../lib/state.svelte.js';
	import { colorPresets, colorPresetLabel, clipFilter } from '../../lib/look.js';
	import { shotFrame } from '../../lib/media.js';
	import { showShot } from '../../lib/monitor.svelte.js';
	import SliderField from './SliderField.svelte';

	let { clip, compact = false, all = true } = $props();
	const picture = $derived(shotFrame(clip));

	function set(k, v) {
		clip[k] = v;
		showShot(clip);
	}
	function apply(name) {
		act(() => Object.assign(clip, colorPresets[name], { preset: name }));
		showShot(clip);
	}
	function applyAll() {
		const p = { exposure: clip.exposure, contrast: clip.contrast, saturation: clip.saturation, temperature: clip.temperature, preset: clip.preset };
		act(() => doc.clips.forEach((c) => Object.assign(c, p)));
		showShot(clip);
		toast(t('inspector.color.appliedAll'));
	}

	const exposure = (v) => t('inspector.color.exposureValue', { value: formatNumber(v, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero' }) });
	const temperature = (v) =>
		v === 0 ? t('inspector.color.neutral') : v > 0 ? t('inspector.color.warm', { value: formatNumber(v, { signDisplay: 'always' }) }) : t('inspector.color.cool', { value: formatNumber(v) });
</script>

<section class="space-y-1.5">
	{#if compact}
		<label class="flex items-center gap-2">
			<span class="shrink-0 text-xs text-fg-muted">{t('inspector.color.preset')}</span>
			<select class="vp-popup min-w-0 flex-1" value={clip.preset} onchange={(e) => apply(e.currentTarget.value)}>
				{#if !(clip.preset in colorPresets)}<option value={clip.preset} disabled>{colorPresetLabel(clip.preset)}</option>{/if}
				{#each Object.keys(colorPresets) as name (name)}<option value={name}>{colorPresetLabel(name)}</option>{/each}
			</select>
		</label>
	{:else}
		<div class="vp-section-title">{t('inspector.color.presets')}</div>
		<div class="grid grid-cols-3 gap-1.5">
			{#each Object.keys(colorPresets) as name (name)}
				<button
					type="button"
					class="overflow-hidden rounded-md border text-left transition-colors {clip.preset === name ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}"
					aria-pressed={clip.preset === name}
					onclick={() => apply(name)}
				>
					{#if picture}
						<img src={picture} alt="" class="aspect-video w-full object-cover" style:filter={clipFilter({ ...clip, ...colorPresets[name] })} />
					{:else}
						<span class="block aspect-video w-full bg-surface-3"></span>
					{/if}
					<span class="block truncate px-1 py-0.5 text-2xs text-fg-muted">{colorPresetLabel(name)}</span>
				</button>
			{/each}
		</div>
	{/if}
</section>

<section class="space-y-2">
	{#if !compact}<div class="vp-section-title">{t('inspector.color.fine')}</div>{/if}
	<SliderField label={t('inspector.color.exposure')} value={clip.exposure} min={-2} max={2} step={0.05} format={exposure} onchange={(v) => set('exposure', v)} />
	<SliderField label={t('inspector.color.contrast')} value={clip.contrast} min={50} max={150} unit=" %" onchange={(v) => set('contrast', v)} />
	<SliderField label={t('inspector.color.saturation')} value={clip.saturation} min={0} max={200} unit=" %" onchange={(v) => set('saturation', v)} />
	<SliderField label={t('inspector.color.temperature')} value={clip.temperature} min={-100} max={100} format={temperature} onchange={(v) => set('temperature', v)} />
	<div class="flex gap-1.5 pt-1">
		<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', class: 'flex-1 justify-center', onclick: () => apply('Original') }}>{t('inspector.color.reset')}</HostUi>
		{#if all}<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', class: 'flex-1 justify-center', onclick: applyAll }}>{t('inspector.color.applyAll')}</HostUi>{/if}
	</div>
</section>

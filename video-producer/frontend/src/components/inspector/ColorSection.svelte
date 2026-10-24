<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { doc, asset, act, toast } from '../../lib/state.svelte.js';
	import { colorPresets, colorPresetLabel, clipFilter } from '../../lib/look.js';
	import { drawGraded, lookSteps, lumaHistogram } from '../../lib/grade.js';
	import { shotFrame } from '../../lib/media.js';
	import { matchToPrevious, seam } from '../../lib/continuity.svelte.js';
	import SliderField from './SliderField.svelte';
	import Icon from '../Icon.svelte';

	let { clip } = $props();
	const a = $derived(asset(clip.assetId));
	const picture = $derived(shotFrame(clip));
	const visual = $derived(Boolean(a && a.kind !== 'audio' && (a.src || picture)));
	const idx = $derived(doc.clips.indexOf(clip));
	const sm = $derived(idx > 0 ? seam(idx) : null);
	const colorIssue = $derived(sm?.issues.some((x) => x.fix));
	const set = (k, v) => (clip[k] = v);

	function apply(name) {
		act(() => Object.assign(clip, colorPresets[name], { preset: name }));
	}
	function applyAll() {
		const p = { exposure: clip.exposure, contrast: clip.contrast, saturation: clip.saturation, temperature: clip.temperature, preset: clip.preset };
		act(() => doc.clips.forEach((c) => Object.assign(c, p)));
		toast(t('inspector.color.appliedAll'));
	}

	const exposure = (v) => t('inspector.color.exposureValue', { value: formatNumber(v, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero' }) });
	const temperature = (v) =>
		v === 0 ? t('inspector.color.neutral') : v > 0 ? t('inspector.color.warm', { value: formatNumber(v, { signDisplay: 'always' }) }) : t('inspector.color.cool', { value: formatNumber(v) });

	let bins = $state([]);
	$effect(() => {
		if (!picture) {
			bins = [];
			return;
		}
		const steps = lookSteps(clip);
		let alive = true;
		const img = new Image();
		img.onload = () => {
			if (!alive) return;
			const c = document.createElement('canvas');
			c.width = 160;
			c.height = 90;
			const g = c.getContext('2d', { willReadFrequently: true });
			if (!g) return;
			try {
				bins = lumaHistogram(drawGraded(g, img, 160, 90, steps));
			} catch {
				bins = [];
			}
		};
		img.src = picture;
		return () => {
			alive = false;
			img.onload = null;
		};
	});
</script>

{#if !visual}
	<p class="rounded-lg border border-dashed border-line-hover p-3 text-xs text-fg-muted">{t('inspector.color.pending')}</p>
{:else}
	<section class="space-y-1.5">
		<div class="vp-section-title">{t('inspector.color.scope')}</div>
		<div class="h-20 rounded-lg border border-line-strong bg-canvas p-1.5">
			<svg viewBox="0 0 64 1" preserveAspectRatio="none" class="h-full w-full" role="img" aria-label={t('inspector.color.histogram')}>
				{#each bins as v, i}<rect x={i} y={1 - v} width="0.8" height={v} fill="rgb(var(--fg-muted))" />{/each}
			</svg>
		</div>
	</section>

	{#if idx > 0}
		<button
			type="button"
			class="flex min-h-8 w-full items-center gap-2 rounded-lg border p-2 text-left text-xs transition-colors {colorIssue ? 'border-warning/40 text-fg hover:bg-surface-2' : 'border-line-strong text-fg-muted hover:bg-surface-2'}"
			onclick={() => matchToPrevious(clip)}
		>
			<Icon name={colorIssue ? 'alert' : 'link'} class="h-3.5 w-3.5 shrink-0 {colorIssue ? 'text-warning' : ''}" />
			<span class="flex-1">{colorIssue ? t('inspector.color.gap') : t('inspector.color.matchPrevious')}</span>
			<span class="text-signal">{t('inspector.color.match')}</span>
		</button>
	{/if}

	<section class="space-y-1.5">
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
	</section>

	<section class="space-y-2">
		<div class="vp-section-title">{t('inspector.color.fine')}</div>
		<SliderField label={t('inspector.color.exposure')} value={clip.exposure} min={-2} max={2} step={0.05} format={exposure} onchange={(v) => set('exposure', v)} />
		<SliderField label={t('inspector.color.contrast')} value={clip.contrast} min={50} max={150} unit=" %" onchange={(v) => set('contrast', v)} />
		<SliderField label={t('inspector.color.saturation')} value={clip.saturation} min={0} max={200} unit=" %" onchange={(v) => set('saturation', v)} />
		<SliderField label={t('inspector.color.temperature')} value={clip.temperature} min={-100} max={100} format={temperature} onchange={(v) => set('temperature', v)} />
		<div class="flex gap-1.5 pt-1">
			<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', class: 'flex-1 justify-center', onclick: () => apply('Original') }}>{t('inspector.color.reset')}</HostUi>
			<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', class: 'flex-1 justify-center', onclick: applyAll }}>{t('inspector.color.applyAll')}</HostUi>
		</div>
	</section>
{/if}

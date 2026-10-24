<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { drawGraded } from '../../lib/grade.js';
	import { lutOf, matchStale } from '../../lib/match.js';
	import { anchorKey, anchorThumb, anchorsOf, autoMatch, clearMatch, defaultAnchor, matchGaps, matchState, setDeflicker, storedAnchor } from '../../lib/match.svelte.js';
	import { shotFrame } from '../../lib/media.js';
	import SliderField from './SliderField.svelte';
	import Icon from '../Icon.svelte';

	let { clip } = $props();
	let picked = $state('');
	let after = $state();

	const anchors = $derived(anchorsOf(clip));
	const stored = $derived(storedAnchor(clip, anchors));
	const chosen = $derived(clip.match ? stored : (anchors.find((a) => anchorKey(a) === picked) ?? defaultAnchor(anchors)));
	const stale = $derived(matchStale(clip));
	const gaps = $derived(clip.match && !stale ? matchGaps(clip.match) : null);
	const lut = $derived(lutOf(clip));
	const busy = $derived(matchState.busy === clip.id);
	const measuring = $derived(Boolean(matchState.busy));
	const picture = $derived(shotFrame(clip));
	const anchorPicture = $derived(anchorThumb(chosen));
	const id = $props.id();

	const delta = (v) => formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
	const strength = (v) => t('inspector.match.strengthValue', { value: Math.round(v) });

	function gapText(gap) {
		const parts = [];
		if (Math.abs(gap.light) >= 2) parts.push(gap.light > 0 ? t('inspector.match.lighter') : t('inspector.match.darker'));
		if (Math.abs(gap.warm) >= 2) parts.push(gap.warm > 0 ? t('inspector.match.warmer') : t('inspector.match.cooler'));
		if (Math.abs(gap.tint) >= 2) parts.push(gap.tint > 0 ? t('inspector.match.magenta') : t('inspector.match.green'));
		return parts.join(' · ');
	}

	function pick(key) {
		const anchor = anchors.find((a) => anchorKey(a) === key);
		picked = key;
		if (clip.match && anchor) autoMatch(clip, anchor);
	}

	$effect(() => {
		const canvas = after;
		const src = picture;
		const current = lut;
		if (!canvas || !src || !current) return;
		let alive = true;
		const img = new Image();
		img.onload = () => {
			if (!alive) return;
			const g = canvas.getContext('2d', { willReadFrequently: true });
			if (!g) return;
			canvas.width = 160;
			canvas.height = Math.max(1, Math.round((160 * img.naturalHeight) / img.naturalWidth));
			try {
				const data = drawGraded(g, img, canvas.width, canvas.height, [], current);
				g.putImageData(new ImageData(data, canvas.width, canvas.height), 0, 0);
			} catch {
				g.clearRect(0, 0, canvas.width, canvas.height);
			}
		};
		img.src = src;
		return () => {
			alive = false;
			img.onload = null;
		};
	});
</script>

<section class="space-y-2" aria-labelledby="{id}-title">
	<div class="flex items-center justify-between gap-2">
		<div id="{id}-title" class="vp-section-title">{t('inspector.match.title')}</div>
		{#if clip.match}
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => clearMatch(clip) }}>{t('inspector.match.remove')}</HostUi>
		{/if}
	</div>

	{#if !anchors.length}
		<p class="rounded-lg border border-dashed border-line-hover p-2.5 text-xs text-fg-muted">{t('inspector.match.noAnchor')}</p>
	{:else}
		<label class="block space-y-1">
			<span class="text-xs text-fg-muted">{t('inspector.match.anchor')}</span>
			<select class="input vp-dense w-full" value={anchorKey(chosen)} disabled={measuring} onchange={(e) => pick(e.currentTarget.value)}>
				{#if clip.match && !stored}<option value="" disabled>{t('inspector.match.anchorGone')}</option>{/if}
				{#each anchors as anchor (anchorKey(anchor))}<option value={anchorKey(anchor)}>{anchor.label}</option>{/each}
			</select>
		</label>
		{#if chosen?.kind === 'previous' || chosen?.carried}
			<p class="flex gap-1.5 text-2xs text-fg-subtle"><Icon name="alert" class="h-3 w-3 shrink-0 text-warning" />{t('inspector.match.driftHint')}</p>
		{/if}

		<div class="grid {lut ? 'grid-cols-3' : 'grid-cols-2'} gap-1.5 text-2xs text-fg-muted">
			<figure class="space-y-0.5">
				{#if anchorPicture}<img src={anchorPicture} alt="" class="aspect-video w-full rounded-md border border-line-strong object-cover" />{:else}<span class="block aspect-video w-full rounded-md bg-surface-3"></span>{/if}
				<figcaption class="truncate">{t('inspector.match.anchorTile')}</figcaption>
			</figure>
			<figure class="space-y-0.5">
				{#if picture}<img src={picture} alt="" class="aspect-video w-full rounded-md border border-line-strong object-cover" />{:else}<span class="block aspect-video w-full rounded-md bg-surface-3"></span>{/if}
				<figcaption class="truncate">{t('inspector.match.takeTile')}</figcaption>
			</figure>
			{#if lut}
				<figure class="space-y-0.5">
					<canvas bind:this={after} class="aspect-video w-full rounded-md border border-line-strong bg-surface-3 object-cover" aria-label={t('inspector.match.matchedTile')}></canvas>
					<figcaption class="truncate">{t('inspector.match.matchedTile')}</figcaption>
				</figure>
			{/if}
		</div>

		{#if stale}
			<p class="flex gap-1.5 rounded-lg border border-warning/40 p-2 text-xs text-fg"><Icon name="alert" class="h-3.5 w-3.5 shrink-0 text-warning" />{t('inspector.match.stale')}</p>
		{:else if gaps}
			<p class="text-xs text-fg-muted" role="status">
				{t('inspector.match.gap', { before: delta(gaps.before.delta), after: delta(gaps.after.delta) })}{#if gapText(gaps.before)}<span class="text-fg-subtle"> · {gapText(gaps.before)}</span>{/if}
			</p>
		{/if}

		{#if clip.match && !stale}
			<SliderField label={t('inspector.match.strength')} value={clip.match.strength} min={0} max={100} format={strength} onchange={(v) => (clip.match.strength = v)} />
		{/if}

		<HostUi name="Button" props={{ variant: clip.match && !stale ? 'secondary' : 'primary', size: 'xs', class: 'w-full justify-center', icon: 'sparkles', disabled: measuring || !chosen, onclick: () => autoMatch(clip, chosen) }}>
			{busy ? t('inspector.match.measuring') : clip.match ? t('inspector.match.remeasure') : t('inspector.match.run')}
		</HostUi>
	{/if}

	<div class="flex min-h-7 items-center gap-2 text-xs">
		<HostUi name="Switch" props={{ id: `vp-deflicker-${clip.id}`, checked: clip.deflicker === true, size: 'lg', label: t('inspector.match.deflicker'), onchange: (v) => setDeflicker(clip, v) }} />
		<label for="vp-deflicker-{clip.id}" class="flex-1">{t('inspector.match.deflicker')}</label>
	</div>
	<p class="text-2xs text-fg-subtle">{t('inspector.match.exportNote')}</p>
</section>

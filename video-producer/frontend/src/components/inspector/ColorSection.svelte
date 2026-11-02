<script>
	import { t } from '../../i18n/index.svelte.js';
	import { doc, asset } from '../../lib/state.svelte.js';
	import { drawGraded, lookSteps, lumaHistogram } from '../../lib/grade.js';
	import { lutOf } from '../../lib/match.js';
	import { shotFrame } from '../../lib/media.js';
	import { matchToPrevious, seam } from '../../lib/continuity.svelte.js';
	import ColorControls from './ColorControls.svelte';
	import MatchSection from './MatchSection.svelte';
	import Icon from '../Icon.svelte';

	let { clip } = $props();
	const a = $derived(asset(clip.assetId));
	const picture = $derived(shotFrame(clip));
	const visual = $derived(Boolean(a && a.kind !== 'audio' && (a.src || picture)));
	const idx = $derived(doc.clips.indexOf(clip));
	const sm = $derived(idx > 0 ? seam(idx) : null);
	const colorIssue = $derived(sm?.issues.some((x) => x.fix));

	let bins = $state([]);
	$effect(() => {
		if (!picture) {
			bins = [];
			return;
		}
		const steps = lookSteps(clip);
		const lut = lutOf(clip);
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
				bins = lumaHistogram(drawGraded(g, img, 160, 90, steps, lut));
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

	{#key clip.id}<MatchSection {clip} />{/key}

	<ColorControls {clip} />
{/if}

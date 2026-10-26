<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipLabel } from '../../lib/state.svelte.js';
	import { takesOf } from '../../lib/production.svelte.js';
	import { labelOf } from '../../lib/labels.js';
	import { seam, matchToPrevious } from '../../lib/continuity.svelte.js';
	import { seamPick } from '../../lib/continuity.js';
	import { seamImage } from '../../lib/seam.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { clipThumb } from '../../lib/media.js';
	import { previewable, seamStatus } from '../../lib/band.js';
	import { compareSeam, labelPreviewed, pickShot, previewed, selectedShot } from '../../lib/band.svelte.js';
	import { clipFilter } from '../../lib/look.js';
	import { lutOf } from '../../lib/match.js';
	import Viewer from '../viewer/Viewer.svelte';
	import MatchCanvas from '../viewer/MatchCanvas.svelte';
	import SeamAction from '../takes/SeamAction.svelte';
	import Icon from '../Icon.svelte';

	const RATIOS = { '16:9': 16 / 9, '2.39:1': 2.39, '9:16': 9 / 16, '1:1': 1, '4:5': 0.8 };
	let w = $state(0);
	let h = $state(0);
	let stills = $state([]);

	const clip = $derived(selectedShot());
	const index = $derived(clip ? doc.clips.indexOf(clip) : -1);
	const prev = $derived(index > 0 ? doc.clips[index - 1] : null);
	const next = $derived(index >= 0 ? (doc.clips[index + 1] ?? null) : null);
	const take = $derived(previewed());
	const takes = $derived(clip ? previewable(takesOf(clip), ui.hideRejected) : []);
	const comparing = $derived(clip && index > 0 && ui.seamCompare === clip.id ? seam(index) : null);
	const ratio = $derived(RATIOS[doc.aspect] ?? 16 / 9);
	const margin = $derived((w - Math.min(w, Math.max(0, h - 60) * ratio)) / 2);
	const sides = $derived(Boolean(clip) && margin >= 170);
	const pick = $derived(comparing ? seamPick(doc, index, takeStore.list) : null);
	const endSrc = (c) => (c ? (seamImage(doc, c.id, 'last')?.src ?? clipThumb(c)) : null);
	const startSrc = (c) => (c ? (seamImage(doc, c.id, 'first')?.src ?? clipThumb(c)) : null);
	const lastSrc = $derived(comparing ? (pick?.last?.src ?? endSrc(prev)) : null);
	const firstSrc = $derived(comparing ? (clipThumb(clip) ?? pick?.first?.src ?? startSrc(clip)) : null);
	const labels = ['rejected', 'candidate', 'final'];
	const num = (i) => String(i + 1).padStart(2, '0');
</script>

<section class="relative grid min-h-0 min-w-0" bind:clientWidth={w} bind:clientHeight={h} aria-label={t('storyboard.band.monitor')}>
	{#if comparing}
		<div class="flex min-h-0 flex-col items-center justify-center gap-2 overflow-auto bg-canvas p-3">
			<div class="flex w-full max-w-[640px] items-center gap-2 text-xs">
				<span class="flex h-[18px] w-[18px] items-center justify-center rounded-full {comparing.issues.length ? 'bg-warning-solid text-black' : 'bg-surface-3 text-success'}"><Icon name={comparing.issues.length ? 'alert' : 'link'} class="h-3 w-3" /></span>
				<span class="font-semibold text-fg">{t('storyboard.band.seamTitle', { n: num(index - 1), m: num(index) })}</span>
				<span class="min-w-0 flex-1 truncate text-fg-subtle">{clipLabel(prev)} → {clipLabel(clip)}</span>
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => (ui.seamCompare = null) }}>{t('storyboard.band.close')}</HostUi>
			</div>
			<div class="flex gap-1">
				{#each [[lastSrc, t('storyboard.band.endOf', { n: num(index - 1) }), prev], [firstSrc, t('storyboard.band.startOf', { n: num(index) }), clip]] as [src, caption, shot], k (caption)}
					{@const look = lutOf(shot)}
					<div class="relative h-[168px] w-[300px] overflow-hidden rounded {src ? 'bg-black' : 'bg-surface-3 bg-[repeating-linear-gradient(135deg,rgb(var(--line-strong))_0_1px,transparent_1px_10px)]'}">
						{#if src}<img bind:this={stills[k]} {src} alt="" class="h-full w-full object-cover" style:filter={clipFilter(shot)} />{/if}
						{#if src && look && stills[k]}<MatchCanvas source={stills[k]} lut={look} filter={clipFilter(shot)} cover />{/if}
						<span class="absolute bottom-1.5 left-1.5 rounded bg-black/65 px-1.5 text-2xs text-white">{caption}</span>
					</div>
				{/each}
			</div>
			<ul class="flex w-full max-w-[604px] flex-col gap-1.5 text-xs">
				{#each comparing.issues as issue, n (n)}
					<li class="flex items-start gap-2">
						<Icon name="alert" class="mt-px h-3.5 w-3.5 shrink-0 text-warning" />
						<span class="min-w-0 flex-1 text-fg-muted">{issue.text}</span>
						{#if issue.fix}<button type="button" class="vp-link-hit shrink-0 text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => matchToPrevious(clip)}>{t('panels.story.matchColor')}</button>{/if}
						{#if issue.kind.startsWith('chain_')}<span class="shrink-0"><SeamAction {clip} /></span>{/if}
					</li>
				{:else}
					<li class="flex items-center gap-2 text-fg-muted"><Icon name="check" class="h-3.5 w-3.5 text-success" />{comparing.measured ? t('panels.story.continuityOk') : t('panels.story.continuityNone')}</li>
				{/each}
			</ul>
		</div>
	{:else}
		<Viewer />
		{#if sides}
			<div class="pointer-events-none absolute inset-x-0 bottom-11 top-0 flex items-center justify-between px-4">
				{@render side(prev, index, true)}
				{@render side(next, index + 1, false)}
			</div>
		{/if}
		{#if take}
			{@const label = labelOf(take)}
			<div class="absolute bottom-14 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-full border border-line-strong bg-surface-3/95 py-1 pl-3 pr-1 text-xs text-fg shadow-floating backdrop-blur-xl">
				<span>{t('storyboard.band.previewing', { variant: take.variant ?? '', n: takes.indexOf(take) + 1, count: takes.length })}</span>
				<div class="vp-seg" role="group" aria-label={t('storyboard.band.labelGroup')}>
					{#each labels as key (key)}
						<button type="button" aria-pressed={label === key} onclick={() => labelPreviewed(key)}>{t(`generation.label.${key}`)}</button>
					{/each}
				</div>
				<span class="text-2xs text-fg-subtle">{t('storyboard.band.takeKeys')}</span>
			</div>
		{/if}
	{/if}
</section>

{#snippet side(shot, seamIndex, before)}
	{#if shot}
		{@const src = before ? endSrc(shot) : startSrc(shot)}
		{@const status = seamIndex > 0 && seamIndex < doc.clips.length ? seamStatus(seam(seamIndex)) : null}
		<div class="flex items-center gap-2.5 {before ? '' : 'flex-row-reverse'}">
			<button type="button" class="pointer-events-auto flex w-[140px] flex-col gap-1 text-left text-2xs text-fg-subtle" onclick={() => pickShot(shot)} title={clipLabel(shot)}>
				<span class="truncate">{before ? t('storyboard.band.endOf', { n: num(doc.clips.indexOf(shot)) }) : t('storyboard.band.startOf', { n: num(doc.clips.indexOf(shot)) })} · {clipLabel(shot)}</span>
				<span class="block h-[79px] w-full overflow-hidden rounded border border-line-strong opacity-85 {src ? 'bg-black' : 'bg-surface-3'}">{#if src}<img {src} alt="" class="h-full w-full object-cover" style:filter={clipFilter(shot)} />{/if}</span>
			</button>
			{#if status}
				<HostUi name="Tooltip" props={{ text: status === 'issue' ? t('storyboard.band.seamCompare') : t('storyboard.band.seamOkTip'), wrapperClass: 'pointer-events-auto inline-flex' }}>
					<button
						type="button"
						class="flex h-[22px] w-[22px] items-center justify-center rounded-full {status === 'issue' ? 'bg-warning-solid text-black' : 'border border-line-strong bg-surface-3 text-success'}"
						aria-label={t('storyboard.band.seamCompare')}
						onclick={() => compareSeam(before ? clip : shot)}
					><Icon name={status === 'issue' ? 'alert' : 'link'} class="h-3 w-3" /></button>
				</HostUi>
			{/if}
		</div>
	{:else}
		<span></span>
	{/if}
{/snippet}

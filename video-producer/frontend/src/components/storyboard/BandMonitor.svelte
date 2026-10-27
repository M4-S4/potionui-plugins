<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipLabel } from '../../lib/state.svelte.js';
	import { takesOf } from '../../lib/production.svelte.js';
	import { labelOf } from '../../lib/labels.js';
	import { seam } from '../../lib/continuity.svelte.js';
	import { seamPick } from '../../lib/continuity.js';
	import { seamImage } from '../../lib/seam.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { clipThumb } from '../../lib/media.js';
	import { previewable, seamStatus } from '../../lib/band.js';
	import { compareSeam, labelPreviewed, pickShot, previewed, selectedShot } from '../../lib/band.svelte.js';
	import { clipFilter, colorPresetLabel } from '../../lib/look.js';
	import { lutOf } from '../../lib/match.js';
	import { aspectOf } from '../../lib/generation.js';
	import Viewer from '../viewer/Viewer.svelte';
	import MatchCanvas from '../viewer/MatchCanvas.svelte';
	import SeamPanel from './SeamPanel.svelte';
	import ColorControls from '../inspector/ColorControls.svelte';
	import Icon from '../Icon.svelte';

	let w = $state(0);
	let h = $state(0);
	let stills = $state([]);
	let grading = $state([false, false]);
	const id = $props.id();

	const clip = $derived(selectedShot());
	const index = $derived(clip ? doc.clips.indexOf(clip) : -1);
	const prev = $derived(index > 0 ? doc.clips[index - 1] : null);
	const next = $derived(index >= 0 ? (doc.clips[index + 1] ?? null) : null);
	const take = $derived(previewed());
	const takes = $derived(clip ? previewable(takesOf(clip), ui.hideRejected) : []);
	const comparing = $derived(clip && index > 0 && ui.seamCompare === clip.id ? seam(index) : null);
	const ratio = $derived(aspectOf(doc.aspect, doc.resolution));
	const margin = $derived((w - Math.min(w, Math.max(0, h - 60) * ratio)) / 2);
	const sides = $derived(Boolean(clip) && margin >= 170);
	const pick = $derived(comparing ? seamPick(doc, index, takeStore.list) : null);
	const endSrc = (c) => (c ? (seamImage(doc, c.id, 'last')?.src ?? clipThumb(c)) : null);
	const startSrc = (c) => (c ? (seamImage(doc, c.id, 'first')?.src ?? clipThumb(c)) : null);
	const lastSrc = $derived(comparing ? (pick?.last?.src ?? endSrc(prev)) : null);
	const firstSrc = $derived(comparing ? (clipThumb(clip) ?? pick?.first?.src ?? startSrc(clip)) : null);
	const roomy = $derived(w >= 1150);
	const beside = $derived(roomy || grading.some(Boolean));
	const gradeColumn = $derived(roomy ? '240px' : 'minmax(180px, 200px)');
	const labels = ['rejected', 'candidate', 'final'];
	const num = (i) => String(i + 1).padStart(2, '0');
</script>

<section class="relative grid min-h-0 min-w-0" bind:clientWidth={w} bind:clientHeight={h} aria-label={t('storyboard.band.monitor')}>
	{#if comparing}
		<div class="flex min-h-0 flex-col overflow-auto bg-canvas p-3">
			<div class="m-auto flex w-full flex-col items-center gap-2">
				<div class="flex w-full max-w-[640px] items-center gap-2 text-xs">
					<span class="flex h-[18px] w-[18px] items-center justify-center rounded-full {comparing.issues.length ? 'bg-warning-solid text-black' : 'bg-surface-3 text-success'}"><Icon name={comparing.issues.length ? 'alert' : 'link'} class="h-3 w-3" /></span>
					<span class="font-semibold text-fg">{t('storyboard.band.seamTitle', { n: num(index - 1), m: num(index) })}</span>
					<span class="min-w-0 flex-1 truncate text-fg-subtle">{clipLabel(prev)} → {clipLabel(clip)}</span>
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => (ui.seamCompare = null) }}>{t('storyboard.band.close')}</HostUi>
				</div>
				<div
					class="grid w-full items-start justify-center gap-x-1 gap-y-2"
					style:grid-template-columns={beside ? `${gradeColumn} minmax(0, 300px) minmax(0, 300px) ${gradeColumn}` : 'repeat(2, minmax(0, 300px))'}
					style:grid-template-areas={beside ? '"grade0 still0 still1 grade1" "grade0 seam seam grade1"' : '"still0 still1" "grade0 grade1" "seam seam"'}
				>
					{#each [[lastSrc, t('storyboard.band.endOf', { n: num(index - 1) }), prev, index - 1], [firstSrc, t('storyboard.band.startOf', { n: num(index) }), clip, index]] as [src, caption, shot, at], k (caption)}
						{@const look = lutOf(shot)}
						<div class="relative aspect-video w-full overflow-hidden rounded {src ? 'bg-black' : 'bg-surface-3 bg-[repeating-linear-gradient(135deg,rgb(var(--line-strong))_0_1px,transparent_1px_10px)]'}" style:grid-area="still{k}">
							{#if src}<img bind:this={stills[k]} {src} alt="" class="h-full w-full object-cover" style:filter={clipFilter(shot)} />{/if}
							{#if src && look && stills[k]}<MatchCanvas source={stills[k]} lut={look} filter={clipFilter(shot)} cover />{/if}
							<span class="absolute bottom-1.5 left-1.5 rounded bg-black/65 px-1.5 text-2xs text-white">{caption}</span>
						</div>
						<div class="min-w-0 {beside ? 'overflow-y-auto' : ''}" style:grid-area="grade{k}" style:max-height={beside ? `${Math.max(160, h - 64)}px` : null} data-seam-grade={shot.id}>
							<button
								type="button"
								class="flex h-7 w-full items-center gap-1.5 rounded px-1.5 text-left text-xs text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg"
								aria-expanded={grading[k]}
								aria-controls="{id}-grade-{k}"
								onclick={() => (grading[k] = !grading[k])}
							>
								<Icon name={grading[k] ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5 shrink-0" />
								<Icon name="palette" class="h-3.5 w-3.5 shrink-0" />
								<span class="min-w-0 flex-1 truncate">{t('storyboard.band.grade', { n: num(at) })}</span>
								<span class="shrink-0 truncate text-fg" style:max-width="50%">{colorPresetLabel(shot.preset)}</span>
							</button>
							{#if grading[k]}
								<div id="{id}-grade-{k}" class="mt-1 space-y-3 rounded-lg border border-line-strong bg-surface-1 p-2.5">
									<ColorControls clip={shot} compact all={false} />
								</div>
							{/if}
						</div>
					{/each}
					<div class="flex min-w-0" style:grid-area="seam"><SeamPanel {clip} title={false} compare={false} /></div>
				</div>
			</div>
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

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, clipLabel } from '../../lib/state.svelte.js';
	import { identityTakes } from '../../lib/continuity.svelte.js';
	import { seamPick } from '../../lib/continuity.js';
	import { seamImage } from '../../lib/seam.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { clipThumb } from '../../lib/media.js';
	import { clipFilter } from '../../lib/look.js';
	import { compareSeamHere, openSeam } from '../../lib/band.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import SeamPanel from '../storyboard/SeamPanel.svelte';
	import ColorControls from '../inspector/ColorControls.svelte';
	import Icon from '../Icon.svelte';

	let { clip, previous } = $props();

	let grading = $state(false);
	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const index = $derived(doc.clips.indexOf(clip));
	const pick = $derived(seamPick(doc, index, takeStore.list));
	const lastSrc = $derived(pick?.last?.src ?? seamImage(doc, previous.id, 'last')?.src ?? clipThumb(previous));
	const firstSrc = $derived(clipThumb(clip) ?? pick?.first?.src ?? seamImage(doc, clip.id, 'first')?.src ?? null);
	const pair = $derived(identityTakes(clip));
	const sides = $derived([
		{ src: lastSrc, shot: previous, caption: `${t('storyboard.band.endOf', { n: num(previous) })} · ${clipLabel(previous)}` },
		{ src: firstSrc, shot: clip, caption: `${t('storyboard.band.startOf', { n: num(clip) })} · ${clipLabel(clip)}` }
	]);
</script>

<section class="space-y-2" data-seam-pair={clip.id}>
	<div class="grid grid-cols-2 gap-1.5">
		{#each sides as side (side.shot.id)}
			<figure class="min-w-0 space-y-1">
				<span class="block aspect-video w-full overflow-hidden rounded bg-surface-3">{#if side.src}<img src={side.src} alt="" class="h-full w-full object-cover" style:filter={clipFilter(side.shot)} />{/if}</span>
				<figcaption class="line-clamp-2 text-2xs text-fg-subtle">{side.caption}</figcaption>
			</figure>
		{/each}
	</div>
	<div class="flex flex-wrap gap-1.5">
		{#if pair}
			<HostUi name="Tooltip" props={{ text: t('panels.director.pick.compareSeamTip'), wrapperClass: 'inline-flex' }}>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('compare'), onclick: () => compareSeamHere(clip) }}>{t('panels.director.pick.compareSeam')}</HostUi>
			</HostUi>
		{/if}
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('grid'), onclick: () => openSeam(clip) }}>{t('panels.director.review.seamCompare')}</HostUi>
	</div>
</section>

<section class="space-y-2">
	<div class="vp-section-title">{t('panels.director.pick.gaps')}</div>
	<SeamPanel {clip} title={false} compare={false} />
</section>

<section class="space-y-2">
	<button type="button" class="flex h-7 w-full items-center gap-1.5 rounded px-1.5 text-left text-xs text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg" aria-expanded={grading} onclick={() => (grading = !grading)}>
		<Icon name={grading ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5 shrink-0" />
		<span class="min-w-0 flex-1 truncate">{t('panels.director.pick.colorOf', { shot: num(clip) })}</span>
	</button>
	{#if grading}<ColorControls {clip} compact all={false} />{/if}
</section>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatRelative, t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs, clipLabel, reviewPick } from '../../lib/state.svelte.js';
	import { panelSelection } from '../../lib/director.js';
	import { showDetails } from '../../lib/production.svelte.js';
	import { labelOf } from '../../lib/labels.js';
	import { stages } from '../../lib/catalog.js';
	import { clipThumb, takeThumb } from '../../lib/media.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import ReviewTake from './ReviewTake.svelte';
	import ReviewFailure from './ReviewFailure.svelte';
	import ReviewShot from './ReviewShot.svelte';
	import ReviewSeam from './ReviewSeam.svelte';
	import ReviewEmpty from './ReviewEmpty.svelte';
	import ElsewhereNote from '../inspector/ElsewhereNote.svelte';
	import Icon from '../Icon.svelte';

	const pick = $derived(reviewPick());
	const elsewhere = $derived(panelSelection('review', ui.selection).elsewhere);
	const take = $derived(pick?.take ?? null);
	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const labelTone = { final: 'border-signal text-signal', candidate: 'border-success/60 text-success', rejected: 'border-danger/60 text-danger', draft: 'border-line-strong text-fg-muted' };

	const head = $derived.by(() => {
		if (take) return { icon: 'layers', title: t('panels.director.pick.take'), sub: `${num(pick.clip)} · ${take.variant}` };
		if (pick?.kind === 'seam') return { icon: 'link', title: t('panels.director.pick.seam'), sub: `${num(pick.previous)} → ${num(pick.clip)}` };
		if (pick) return { icon: 'film', title: t('panels.director.pick.shot'), sub: num(pick.clip) };
		return { icon: 'layers', title: commandById('view-review')?.label ?? '', sub: '' };
	});
	const thumb = $derived(take ? takeThumb(take) : pick ? clipThumb(pick.clip) : null);
	const when = $derived(take ? formatRelative(take.finishedAt ?? take.createdAt) : '');
	const key = $derived(pick ? `${pick.kind}:${take?.id ?? pick.clip.id}` : 'none');
</script>

<aside class="flex min-h-0 flex-col overflow-hidden border-l border-line bg-surface-1" aria-label={head.title} class:invisible={!ui.inspectorOpen} data-review-aside={pick?.kind ?? 'none'}>
	<div class="vp-panel-head border-b border-line">
		<Icon name={head.icon} class="h-4 w-4 text-fg-muted" />
		<span class="truncate text-sm font-semibold">{head.title}</span>
		{#if head.sub}<span class="vp-tc shrink-0 text-xs text-fg-subtle">{head.sub}</span>{/if}
		<div class="flex-1"></div>
		<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('inspector.close'), tooltip: t('inspector.closeTip'), kbd: commandById('inspector')?.key, size: 'sm', class: 'vp-h7', onclick: () => (ui.inspectorOpen = false) }} />
	</div>
	{#if pick && pick.kind !== 'seam'}
		<div class="flex shrink-0 items-center gap-2.5 border-b border-line px-3 py-2.5">
			{#if thumb}
				<img src={thumb} alt="" class="h-10 w-16 shrink-0 rounded-md object-cover" />
			{:else}
				<span class="flex h-10 w-16 shrink-0 items-center justify-center rounded-md bg-surface-3 bg-[repeating-linear-gradient(135deg,rgb(var(--line-strong))_0_1px,transparent_1px_8px)] {pick.kind === 'failed' ? 'text-danger' : 'text-fg-muted'}"><Icon name={pick.kind === 'failed' ? 'alert' : 'sparkles'} class="h-4 w-4" /></span>
			{/if}
			<div class="min-w-0 flex-1">
				<div class="truncate text-sm font-medium">{num(pick.clip)} · {clipLabel(pick.clip)}{take ? ` · ${take.variant}` : ''}</div>
				<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-subtle">
					{#if pick.kind === 'take'}
						<span class="shrink-0 rounded-sm border px-1 text-2xs font-medium {labelTone[labelOf(take)]}">{t(`generation.label.${labelOf(take)}`)}</span>
						<span class="whitespace-nowrap">{pick.clip.take === take.id ? t('panels.director.pick.placed') : t('panels.director.pick.notPlaced')}</span>
					{:else if pick.kind === 'failed'}
						<span class="shrink-0 text-danger">{t('lib.status.failed')}</span>
					{:else}
						<span class="flex shrink-0 items-center gap-1 {stages[pick.clip.stage].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[pick.clip.stage].dot}"></span>{stages[pick.clip.stage].label}</span>
						<span class="vp-tc shrink-0">{secs(pick.clip.dur)}</span>
					{/if}
					{#if when}<span class="whitespace-nowrap">{when}</span>{/if}
				</div>
			</div>
		</div>
	{/if}
	<div class="min-h-0 flex-1 space-y-4 overflow-auto p-3">
		{#key key}
			{#if pick?.kind === 'take'}
				<ReviewTake clip={pick.clip} {take} />
			{:else if pick?.kind === 'failed'}
				<ReviewFailure clip={pick.clip} {take} />
			{:else if pick?.kind === 'seam'}
				<ReviewSeam clip={pick.clip} previous={pick.previous} />
			{:else if pick}
				<ReviewShot clip={pick.clip} />
			{:else}
				<ReviewEmpty />
			{/if}
		{/key}
	</div>
	{#if elsewhere}<ElsewhereNote kind={elsewhere.kind} />{/if}
	{#if !pick || pick.kind === 'take' || pick.kind === 'shot' || take?.generationId}
		<div class="flex shrink-0 items-center gap-2 border-t border-line px-3 py-2">
			{#if take?.generationId}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'info', onclick: () => showDetails(take) }}>{t('generation.card.detailsTip')}</HostUi>
			{:else if pick?.kind === 'shot'}
				<span class="text-xs text-fg-subtle">{t('panels.director.pick.generate', { key: commandById('generate')?.key ?? '' })}</span>
			{:else if !pick}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', class: 'w-full', onclick: () => (ui.modal = { type: 'project' }) }}>{t('inspector.projectProps')}</HostUi>
			{/if}
			{#if pick?.kind === 'take'}<span class="ml-auto shrink-0 text-xs text-fg-subtle">{t('panels.director.pick.labelsOnCard')}</span>{/if}
		</div>
	{/if}
</aside>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, select, secs, clipLabel } from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { takesOf, assembleChosen } from '../../lib/production.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { stages } from '../../lib/catalog.js';
	import { seam, matchToPrevious } from '../../lib/continuity.svelte.js';
	import { labelOf, rejectedCount, visibleTakes } from '../../lib/labels.js';
	import { shotStale } from '../../lib/shots.js';
	import { sections } from '../../lib/band.js';
	import { REVIEW_FILTERS, VIEW_ICONS, reviewCounts, reviewShots, reviewState } from '../../lib/director.js';
	import { commandById } from '../../lib/commands.js';
	import { mountHostSlot } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import Viewer from '../viewer/Viewer.svelte';
	import TakeCard from '../takes/TakeCard.svelte';
	import SeamAction from '../takes/SeamAction.svelte';
	import DirectorViews from './DirectorViews.svelte';
	import FilterPills from '../shell/FilterPills.svelte';
	import ZoneHeader from '../shell/ZoneHeader.svelte';
	import FinalPassButton from '../production/FinalPassButton.svelte';
	import Icon from '../Icon.svelte';

	const counts = $derived(reviewCounts(doc.clips, takeStore.list));
	const filter = $derived(ui.reviewFilter ?? (counts.review ? 'review' : 'all'));
	const shown = $derived(reviewShots(doc.clips, takeStore.list, filter));
	const rejected = $derived(rejectedCount(takeStore.list));
	const chosen = $derived(takeStore.list.filter((r) => labelOf(r) === 'final' && r.status === 'done').length);
	const withFinal = $derived(counts.final);
	const end = $derived(doc.clips.reduce((m, c) => Math.max(m, c.start + c.dur), 0));
	const parts = $derived(sections(doc.markers, end));
	const watching = $derived(ui.compare?.length === 2 || ui.preview?.kind === 'result');
	const isSel = (c) => ui.selection?.kind === 'clip' && ui.selection.id === c.id;
	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const partOf = (c) => parts.find((p) => c.start >= p.start && c.start < p.end)?.label ?? '';
	const pills = $derived(REVIEW_FILTERS.map((f) => ({ id: f, label: filterLabel(f), count: counts[f] })));

	function filterLabel(f) {
		if (f === 'review') return t('panels.director.review.filter.review');
		if (f === 'running') return t('panels.director.review.filter.running');
		if (f === 'final') return t('panels.director.review.filter.final');
		return t('panels.director.review.filter.all');
	}

	function pick(c) {
		select('clip', c.id);
		seek(c.start);
	}

	function openSeam(c) {
		ui.workspace = 'storyboard';
		ui.storyView = 'band';
		pick(c);
		ui.seamCompare = c.id;
	}

	const noShots = $derived({
		compact: true,
		icon: 'film',
		title: t('panels.director.review.noShots'),
		description: t('panels.director.review.noShotsHint'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'sm', icon: 'grid', onclick: () => (ui.workspace = 'storyboard'), children: t('panels.director.review.toStoryboard') }) }
	});
	const noneHere = $derived({
		compact: true,
		icon: 'layers',
		title: t('panels.director.review.emptyFilter'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'sm', onclick: () => (ui.reviewFilter = 'all'), children: t('panels.director.review.showAll') }) }
	});
</script>

<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas" aria-label={commandById('view-review')?.label}>
	<ZoneHeader icon={ui.sidebarOpen ? VIEW_ICONS.review : null} title={commandById('view-review')?.label} subtitle={t('panels.director.review.count', { count: takeStore.list.length })}>
		{#snippet lead()}<DirectorViews />{/snippet}
		<FilterPills class="ml-1 flex-1" label={t('panels.director.review.filters')} items={pills} value={filter} onselect={(f) => (ui.reviewFilter = f)}>
			{#if rejected}
				<span class="vp-divider"></span>
				<button type="button" class="vp-pill shrink-0" aria-pressed={ui.hideRejected} onclick={() => (ui.hideRejected = !ui.hideRejected)}>{t('generation.labels.hideRejected', { count: rejected })}</button>
			{/if}
		</FilterPills>
	</ZoneHeader>

	{#if watching}
		<div class="grid min-h-0 shrink-0 border-b border-line" style:height="46%">
			<Viewer />
		</div>
	{/if}

	<div class="min-h-0 flex-1 overflow-auto">
		{#if !doc.clips.length}
			<div class="m-auto w-full max-w-lg p-6"><HostUi name="EmptyState" props={noShots} /></div>
		{:else if !shown.length}
			<div class="m-auto w-full max-w-lg p-6"><HostUi name="EmptyState" props={noneHere} /></div>
		{:else}
			{#each shown as c (c.id)}
				{@const i = doc.clips.indexOf(c)}
				{@const join = filter === 'all' && i > 0 ? seam(i) : null}
				{@const own = takesOf(c)}
				{@const list = visibleTakes(own, ui.hideRejected)}
				{@const state = reviewState(own)}
				{@const stale = shotStale(c, own)}
				{#if join?.issues.length}
					<div class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-1.5 text-xs text-warning" style:background-color="rgb(var(--warning) / 0.06)">
						<Icon name="link" class="h-3.5 w-3.5 shrink-0" />
						<span class="min-w-0">{t('panels.director.review.seam', { from: num(doc.clips[i - 1]), to: num(c) })} · {join.issues.map((x) => x.text).join(' · ')}</span>
						{#if join.issues.some((x) => x.fix)}<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => matchToPrevious(c)}>{t('panels.dock.match')}</button>{/if}
						<SeamAction clip={c} />
						<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => openSeam(c)}>{t('panels.director.review.seamCompare')}</button>
					</div>
				{/if}
				<section class="border-b border-line px-4 py-3 {isSel(c) ? 'bg-surface-1' : ''}" aria-label={clipLabel(c)}>
					<button type="button" class="mb-2 flex min-h-7 w-full items-center gap-2 text-left" onclick={() => pick(c)}>
						<span class="vp-tc text-xs text-fg-subtle">{num(c)}</span>
						<span class="min-w-0 truncate text-sm font-medium">{clipLabel(c)}</span>
						<span class="flex shrink-0 items-center gap-1 text-xs {stages[c.stage].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[c.stage].dot}"></span>{stages[c.stage].label}</span>
						<span class="vp-tc shrink-0 text-xs text-fg-subtle">{secs(c.start)} → {secs(c.start + c.dur)}</span>
						{#if partOf(c)}<span class="shrink-0 truncate text-xs text-fg-subtle">{partOf(c)}</span>{/if}
						<span class="flex-1"></span>
						{#if state.failed}<span class="flex shrink-0 items-center gap-1 text-xs text-danger"><Icon name="alert" class="h-3 w-3" />{t('panels.director.review.failed')}</span>{/if}
						{#if stale}<span class="flex shrink-0 items-center gap-1 text-xs text-warning"><Icon name="pencil" class="h-3 w-3" />{t('storyboard.stale')}</span>{/if}
					</button>
					{#if list.length}
						<ul class="grid gap-2" style:grid-template-columns="repeat(auto-fill, minmax(300px, 1fr))">
							{#each list as take (take.id)}
								<TakeCard {take} clip={c} />
							{/each}
						</ul>
					{:else}
						<p class="text-xs text-fg-subtle">{t('panels.director.review.noTakes', { key: commandById('generate')?.key ?? '' })}</p>
					{/if}
				</section>
			{/each}
		{/if}
	</div>

	{#if takeStore.list.length}
		<div class="flex h-10 shrink-0 items-center gap-2 border-t border-line px-4">
			<span class="text-xs text-fg-muted">{t('panels.director.review.finals', { count: withFinal, total: doc.clips.length })}</span>
			<div class="flex-1"></div>
			<FinalPassButton />
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('layers'), disabled: !chosen, onclick: assembleChosen }}>{t('panels.dock.results.assemble', { count: chosen })}</HostUi>
		</div>
	{/if}
</section>

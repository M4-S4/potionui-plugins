<script>
	import { tick } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs, clipLabel, reviewPick, shotNumber } from '../../lib/state.svelte.js';
	import { takesOf, assembleChosen } from '../../lib/production.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { stages } from '../../lib/catalog.js';
	import { seam, matchToPrevious } from '../../lib/continuity.svelte.js';
	import { takeLabelOf, rejectedCount, visibleTakes } from '../../lib/labels.js';
	import { shotStale } from '../../lib/shots.js';
	import { sections } from '../../lib/band.js';
	import { chooseSeam, chooseShot, chooseTake, openSeam } from '../../lib/band.svelte.js';
	import { REVIEW_FILTERS, VIEW_ICONS, reviewCounts, reviewFilterOf, reviewShots, reviewState } from '../../lib/director.js';
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
	const filter = $derived(reviewFilterOf(ui.reviewFilter, counts));
	const shown = $derived(reviewShots(doc.clips, takeStore.list, filter));
	const rejected = $derived(rejectedCount(takeStore.list));
	const chosen = $derived(takeStore.list.filter((r) => takeLabelOf(r) === 'final' && r.status === 'done').length);
	const withFinal = $derived(counts.final);
	const end = $derived(doc.clips.reduce((m, c) => Math.max(m, c.start + c.dur), 0));
	const parts = $derived(sections(doc.markers, end));
	const taking = $derived(ui.compare?.length === 2 || ui.preview?.kind === 'result');
	const watching = $derived(ui.reviewMonitor || taking);
	const isSel = (c) => ui.selection?.kind === 'clip' && ui.selection.id === c.id;
	const picked = $derived(reviewPick());
	const seamOn = (c) => picked?.kind === 'seam' && picked.clip.id === c.id;
	const partOf = (c) => parts.find((p) => c.start >= p.start && c.start < p.end)?.label ?? '';
	const pills = $derived(REVIEW_FILTERS.map((f) => ({ id: f, label: filterLabel(f), count: counts[f] })));

	function filterLabel(f) {
		if (f === 'review') return t('panels.director.review.filter.review');
		if (f === 'running') return t('panels.director.review.filter.running');
		if (f === 'final') return t('panels.director.review.filter.final');
		return t('panels.director.review.filter.all');
	}

	$effect(() => {
		if (taking) ui.reviewMonitor = true;
	});
	$effect(() => () => (ui.reviewMonitor = false));

	let rows = $state(null);
	$effect(() => {
		const id = ui.reveal;
		if (!id || !rows) return;
		if (ui.selection?.kind !== 'clip' || ui.selection.id !== id) return void (ui.reveal = null);
		if (!shown.some((c) => c.id === id)) return void (ui.reviewFilter = 'all');
		tick().then(() => {
			rows?.querySelector(`[data-review-shot="${id}"]`)?.scrollIntoView({ block: 'start' });
			ui.reveal = null;
		});
	});

	$effect(() => {
		const id = picked?.take?.id;
		if (!id || !rows || !watching) return;
		tick().then(() => rows?.querySelector(`[data-take-card="${id}"]`)?.scrollIntoView({ block: 'nearest' }));
	});

	function choose(e, c) {
		if (e.target.closest?.('button, a, input, select, textarea, label')) return;
		chooseShot(c);
	}

	function chooseAt(e, c) {
		if (e.target.closest?.('button, a, input, select, textarea, label')) return;
		chooseSeam(c);
	}

	function closeMonitor() {
		ui.preview = null;
		ui.compare = null;
		ui.reviewMonitor = false;
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
		<div class="relative grid min-h-0 shrink-0 border-b border-line" style:height="46%">
			<Viewer />
			<div class="absolute right-2 top-2 z-20">
				<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('panels.director.review.closeMonitor'), tooltip: t('panels.director.review.closeMonitor'), kbd: t('commands.kbd.escape'), size: 'sm', class: 'vp-h7', onclick: closeMonitor }} />
			</div>
		</div>
	{/if}

	<div class="min-h-0 flex-1 overflow-auto" bind:this={rows}>
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
					<div
						role="presentation"
						class="relative flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-1.5 text-xs text-warning"
						style:background-color="rgb(var(--warning) / {seamOn(c) ? 0.16 : 0.06})"
						data-review-seam={c.id}
						aria-current={seamOn(c) ? 'true' : undefined}
						onclick={(e) => chooseAt(e, c)}
					>
						{#if seamOn(c)}<span class="absolute inset-y-0 left-0 w-0.5 bg-signal" aria-hidden="true"></span>{/if}
						<Icon name="link" class="h-3.5 w-3.5 shrink-0" />
						<button type="button" class="min-w-0 text-left hover:text-fg" title={t('panels.director.review.seamTip')} onclick={() => chooseSeam(c)}>{t('panels.director.review.seam', { from: shotNumber(doc.clips[i - 1]), to: shotNumber(c) })} · {join.issues.map((x) => x.text).join(' · ')}</button>
						{#if join.issues.some((x) => x.fix)}<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => matchToPrevious(c)}>{t('panels.dock.match')}</button>{/if}
						<SeamAction clip={c} />
						<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => openSeam(c)}>{t('panels.director.review.seamCompare')}</button>
					</div>
				{/if}
				<section class="relative border-b border-line {isSel(c) ? 'bg-surface-1' : ''}" data-review-shot={c.id} aria-label={clipLabel(c)} aria-current={isSel(c) ? 'true' : undefined}>
					{#if isSel(c)}<span class="absolute inset-y-0 left-0 w-0.5 bg-signal" aria-hidden="true"></span>{/if}
					<div role="presentation" class="px-4 py-3" onclick={(e) => choose(e, c)}>
						<button type="button" class="mb-2 flex min-h-7 cursor-pointer items-center gap-2 rounded px-1.5 text-left transition-colors hover:bg-surface-2" style:margin-inline="-0.375rem" style:width="calc(100% + 0.75rem)" onclick={() => chooseShot(c)}>
							<span class="vp-tc text-xs text-fg-subtle">{shotNumber(c)}</span>
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
									<TakeCard {take} clip={c} onchoose={chooseTake} chosen={picked?.take?.id === take.id} />
								{/each}
							</ul>
						{:else}
							<p class="text-xs text-fg-subtle">{t('panels.director.review.noTakes', { key: commandById('generate')?.key ?? '' })}</p>
						{/if}
					</div>
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

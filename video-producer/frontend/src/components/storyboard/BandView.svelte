<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs, addShot } from '../../lib/state.svelte.js';
	import { shotActivity, takesOf } from '../../lib/production.svelte.js';
	import { stages } from '../../lib/catalog.js';
	import { hostIconName } from '../../lib/icons.js';
	import { commandById } from '../../lib/commands.js';
	import { lastFailure } from '../../lib/band.js';
	import { bandChecks, selectedShot } from '../../lib/band.svelte.js';
	import BandLanes from './BandLanes.svelte';
	import BandMonitor from './BandMonitor.svelte';
	import ShotQuickEdit from './ShotQuickEdit.svelte';
	import StoryWindow from './StoryWindow.svelte';
	import ViewSwitch from './ViewSwitch.svelte';
	import Icon from '../Icon.svelte';

	let lanes = $state();
	const sel = $derived(selectedShot());
	const counts = $derived(Object.keys(stages).map((k) => [k, doc.clips.filter((c) => c.stage === k).length]));
	const running = $derived(doc.clips.filter((c) => shotActivity(c.id).state === 'running').length);
	const failed = $derived(doc.clips.filter((c) => lastFailure(takesOf(c))).length);
	const checks = $derived(doc.clips.length ? bandChecks().length : 0);
	const key = (id) => commandById(id)?.key || undefined;
	const total = $derived(doc.clips.reduce((sum, c) => sum + c.dur, 0));
</script>

<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas" aria-label={t('storyboard.title')}>
	<div class="flex h-10 shrink-0 items-center gap-3 border-b border-line px-4">
		<span class="shrink-0 text-sm font-semibold">{t('storyboard.title')}</span>
		<span class="vp-tc shrink-0 whitespace-nowrap text-xs text-fg-subtle">{t('storyboard.summary', { count: doc.clips.length, duration: secs(total) })}</span>
		<div class="flex min-w-0 flex-1 items-center gap-3 overflow-hidden whitespace-nowrap">
			{#each counts as [k, n] (k)}
				<span class="flex shrink-0 items-center gap-1.5 text-xs {n ? 'text-fg-muted' : 'text-fg-subtle'}" title={t('storyboard.stageCount', { stage: stages[k].label, n })}>
					<span class="h-1.5 w-1.5 rounded-full {stages[k].dot} {n ? '' : 'opacity-40'}"></span>{stages[k].label}<span class="vp-tc text-fg">{n}</span>
				</span>
			{/each}
			{#if running}<span class="flex shrink-0 items-center gap-1 text-xs text-signal"><Icon name="sparkles" class="h-3 w-3" />{t('storyboard.band.running', { count: running })}</span>{/if}
			{#if failed}<span class="flex shrink-0 items-center gap-1 text-xs text-danger"><Icon name="alert" class="h-3 w-3" />{t('storyboard.band.failedCount', { count: failed })}</span>{/if}
		</div>
		<HostUi name="Tooltip" props={{ text: t('storyboard.story.tip'), kbd: key('story-window'), wrapperClass: 'inline-flex shrink-0' }}>
			<button type="button" class="flex h-7 items-center gap-1.5 rounded border px-2.5 text-xs font-medium {ui.storyOpen ? 'border-signal bg-surface-3 text-fg shadow-[inset_0_0_0_1px_rgb(var(--signal))]' : 'border-line-strong bg-surface-2 text-fg hover:border-line-hover'}" aria-pressed={ui.storyOpen} onclick={() => (ui.storyOpen = !ui.storyOpen)}>
				<Icon name="book" class="h-3.5 w-3.5" />{t('storyboard.story.title')}
				{#if checks}<span class="vp-tc min-w-4 rounded-full bg-warning-solid px-1 text-center text-2xs font-semibold leading-4 text-black" title={t('storyboard.story.checksTip', { count: checks })}>{checks}</span>{/if}
			</button>
		</HostUi>
		<ViewSwitch />
		<div class="flex shrink-0 items-center gap-1" role="group" aria-label={t('timeline.zoom')}>
			<HostUi name="IconButton" props={{ icon: 'minus', label: t('timeline.zoomOut'), size: 'xs', kbd: key('zoom-out'), onclick: () => (ui.pxPerSec = Math.max(8, ui.pxPerSec / 1.25)) }} />
			<input class="vp-slider w-20" type="range" min="8" max="220" bind:value={ui.pxPerSec} aria-label={t('timeline.zoom')} />
			<HostUi name="IconButton" props={{ icon: 'plus', label: t('timeline.zoomIn'), size: 'xs', kbd: key('zoom-in'), onclick: () => (ui.pxPerSec = Math.min(220, ui.pxPerSec * 1.25)) }} />
			<HostUi name="Tooltip" props={{ text: t('timeline.fitTip') }}>
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => lanes?.fit() }}>{t('timeline.fit')}</HostUi>
			</HostUi>
		</div>
		<HostUi name="IconButton" props={{ icon: hostIconName('magnet'), label: t('timeline.snapping'), size: 'sm', class: 'vp-h7 vp-toggle', ariaPressed: ui.snapping, kbd: key('snap'), onclick: () => (ui.snapping = !ui.snapping) }} />
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => addShot(t('lib.default.shot'), '', 4, sel?.id ?? null) }}>{t('storyboard.addShot')}</HostUi>
	</div>

	<BandLanes bind:this={lanes} />

	<div class="grid min-h-0 flex-1 {ui.storyOpen ? '' : 'grid-cols-[minmax(0,1fr)_440px]'}">
		{#if ui.storyOpen}
			<StoryWindow />
		{:else if !doc.clips.length}
			<div class="col-span-2 flex items-center justify-center p-6">
				<div class="max-w-md text-center">
					<Icon name="film" class="mx-auto h-6 w-6 text-fg-subtle" />
					<h2 class="mt-3 text-md font-semibold text-fg">{t('storyboard.band.emptyTitle')}</h2>
					<p class="mt-1.5 text-sm text-fg-muted">{t('storyboard.band.emptyText')}</p>
					<div class="mt-4 flex justify-center gap-2">
						<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('wand'), onclick: () => ((ui.storyOpen = true), (ui.storyTab = 'cut')) }}>{t('storyboard.story.title')}</HostUi>
						<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'plus', onclick: () => addShot() }}>{t('storyboard.newShot')}</HostUi>
					</div>
				</div>
			</div>
		{:else}
			<BandMonitor />
			<aside class="min-h-0 overflow-auto border-l border-line bg-surface-1 p-3" aria-label={t('storyboard.quick.title')}>
				{#if sel}
					{#key sel.id}<ShotQuickEdit clip={sel} />{/key}
				{:else}
					<p class="flex h-full items-center justify-center text-center text-xs text-fg-subtle">{t('storyboard.quick.none')}</p>
				{/if}
			</aside>
		{/if}
	</div>
</section>

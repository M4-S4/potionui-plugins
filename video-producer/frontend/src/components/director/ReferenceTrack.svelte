<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, asset, secs, clipLabel } from '../../lib/state.svelte.js';
	import { engineTitle, shotReceptionFor } from '../../lib/references.js';
	import { trackItemsOf } from '../../lib/vrefs.js';
	import { trackFrames, trackGroups, vrefLabel } from '../../lib/vreftracks.js';
	import { roleLabel, sentSeconds, trackVerdict } from '../../lib/vreftracks.svelte.js';
	import { matchState, matchToSuite } from '../../lib/match.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { showInReview } from '../../lib/band.svelte.js';
	import { TAG_CLASS } from '../../lib/reftags.js';
	import { hostIconName } from '../../lib/icons.js';
	import ReceptionList from './ReceptionList.svelte';
	import Icon from '../Icon.svelte';

	let { track } = $props();

	const label = $derived(vrefLabel(track.slot));
	const items = $derived(trackItemsOf(doc, track.id));
	const thumb = $derived(assetThumb(items.length ? asset(items[0].assetId) : null));
	const shots = $derived(doc.clips.map(shotReceptionFor));
	const groups = $derived(trackGroups(shots, track.id));
	const going = $derived(groups.filter((g) => g.status === 'sent').flatMap((g) => g.clips));
	const suites = $derived(track.role === 'continuation' ? going.filter((c) => c.assetId) : []);

	function title(group) {
		if (group.status === 'excluded') return t('panels.director.refs.excludedBy');
		if (group.status === 'off') return t('panels.director.track.offBy');
		return engineTitle(group.engine);
	}

	const rows = $derived(groups.map((g) => ({ key: g.key, status: g.status, title: title(g), shots: g.clips, ...trackVerdict(g.entry) })));
	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const shotName = (c) => `${num(c)} · ${clipLabel(c)}`;
</script>

<div class="space-y-4 p-3" data-reference-track={track.id}>
	<div class="flex items-center gap-2.5">
		{#if thumb}
			<img src={thumb} alt="" class="h-10 w-16 shrink-0 rounded-md object-cover" />
		{:else}
			<span class="flex h-10 w-16 shrink-0 items-center justify-center rounded-md bg-surface-3 text-fg-muted"><Icon name="film" class="h-4 w-4" /></span>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="flex min-w-0 items-center gap-1.5">
				<span class="{TAG_CLASS} vp-tc shrink-0">{label}</span>
				<span class="truncate text-sm font-medium">{track.name || t('inspector.kind.vtrack')}</span>
			</div>
			<div class="truncate text-xs text-fg-subtle">{[roleLabel(track.role), sentSeconds(trackFrames(track)), t('panels.director.track.pieces', { count: items.length })].join(' · ')}</div>
		</div>
	</div>

	<p class="text-xs text-fg-subtle">{track.role === 'continuation' ? t('inspector.vref.continuationHint') : t('inspector.vref.motionHint')}</p>

	<section class="space-y-2" data-reference-reception>
		<div class="vp-section-title">{t('panels.director.refs.received')}</div>
		{#if rows.length}
			<ReceptionList {rows} label={t('panels.director.refs.received')} />
		{:else}
			<p class="text-xs text-fg-subtle">{items.length ? t('panels.director.track.under') : t('panels.director.track.empty')}</p>
		{/if}
		<p class="text-xs text-fg-subtle">{t('inspector.vref.engineHint')}</p>
	</section>

	<section class="space-y-2">
		<div class="vp-section-title">{going.length ? t('panels.director.refs.going', { count: going.length }) : t('panels.director.refs.goingNone')}</div>
		{#if going.length}
			<div class="flex flex-wrap gap-1" data-reference-going>
				{#each going as c (c.id)}
					<button type="button" class="vp-tc rounded border border-line-strong px-1.5 py-0.5 text-xs text-fg-muted transition-colors hover:border-signal hover:text-fg" title={t('panels.director.refs.goingTip', { shot: shotName(c) })} onclick={() => showInReview(c)}>{num(c)}</button>
				{/each}
			</div>
		{/if}
	</section>

	{#if suites.length}
		<section class="space-y-2" data-track-suite>
			<div class="vp-section-title">{t('panels.director.track.seam')}</div>
			<p class="text-xs text-fg-subtle">{t('panels.director.track.seamText', { label })}</p>
			<div class="flex flex-wrap gap-1.5">
				{#each suites as c (c.id)}
					<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('palette'), disabled: Boolean(matchState.busy), onclick: () => matchToSuite(c, track.id) }}>{t('panels.director.track.match', { shot: num(c) })}</HostUi>
				{/each}
			</div>
		</section>
	{/if}

	{#if items.length}<p class="text-xs text-fg-subtle">{t('panels.director.track.span', { start: secs(Math.min(...items.map((i) => i.start))), end: secs(Math.max(...items.map((i) => i.start + i.dur))) })}</p>{/if}
</div>

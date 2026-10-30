<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, select, secs, clipLabel, shotNumber } from '../../lib/state.svelte.js';
	import { families, addReference, refMediaKind, referenceTagText, engineOf, engineTitle, shotReceptionFor } from '../../lib/references.js';
	import { typeIcon } from '../../lib/reftags.js';
	import { mountHostSlot } from '../../lib/host.js';
	import { assetThumb } from '../../lib/media.js';
	import { activateOnKey } from '../../lib/keyboard.js';
	import { presetProfiles } from '../../lib/generation.js';
	import { takesReferences } from '../../lib/reception.js';
	import { excludedOf, isGlobal, sentReferences, shotReferences } from '../../lib/shots.js';
	import { spaceLabel } from '../../lib/commands.js';
	import { VIEW_ICONS, panelSelection } from '../../lib/director.js';
	import DirectorViews from '../director/DirectorViews.svelte';
	import FilterPills from '../shell/FilterPills.svelte';
	import ZoneHeader from '../shell/ZoneHeader.svelte';
	import Icon from '../Icon.svelte';
	import RefTags from './RefTags.svelte';
	import { trackItemsOf, videoTracksOf } from '../../lib/vrefs.js';
	import { receivingCount, vrefLabel } from '../../lib/vreftracks.js';
	import { roleLabel } from '../../lib/vreftracks.svelte.js';
	import { TAG_CLASS } from '../../lib/reftags.js';

	let q = $state('');
	const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
	const project = $derived(engineOf({}));
	const sent = $derived(!project.info || (presetProfiles(project.info).includes(project.profile) && takesReferences(project.profile)));
	const chosen = $derived(panelSelection('references', ui.selection).shown);
	const shot = $derived(chosen?.kind === 'clip' ? (doc.clips.find((c) => c.id === chosen.id) ?? null) : null);
	const going = $derived(shot ? new Set(sentReferences(doc, shot).map((r) => r.id)) : null);
	const left = $derived(shot ? new Set(excludedOf(shot)) : null);
	const aside = $derived(shot ? new Set(shotReferences(doc, shot).inherited.filter((x) => x.notCast && !x.excluded).map((x) => x.reference.id)) : null);
	const shotNum = $derived(shot ? shotNumber(shot) : '');
	const list = $derived(
		doc.references.filter((r) => (ui.refSpace === 'all' || r.space === ui.refSpace) && (!q || norm(`${r.name} ${referenceTagText(r)}`).includes(norm(q))))
	);
	const groups = $derived([
		{ id: 'global', title: t('references.group.global'), hint: t('references.group.globalHint'), refs: list.filter(isGlobal) },
		{ id: 'shot', title: t('references.group.shot'), hint: t('references.group.shotHint'), refs: list.filter((r) => !isGlobal(r)) }
	]);
	const tracks = $derived(
		ui.refSpace === 'all' || ui.refSpace === 'mouvement' ? videoTracksOf(doc).filter((track) => !q || norm(`${vrefLabel(track.slot)} ${track.name ?? ''} ${roleLabel(track.role)}`).includes(norm(q))) : []
	);
	const receptions = $derived(tracks.length ? doc.clips.map(shotReceptionFor) : []);
	const trackThumb = (track) => {
		const first = trackItemsOf(doc, track.id)[0];
		return first ? assetThumb(asset(first.assetId)) : null;
	};
	const isTrack = (track) => ui.selection?.kind === 'vtrack' && ui.selection.id === track.id;
	const fam = (id) => families.find((f) => f.id === id);
	const isSel = (r) => ui.selection?.kind === 'reference' && ui.selection.id === r.id;
	const family = $derived(ui.refSpace === 'all' ? null : (fam(ui.refSpace) ?? null));
	const inFamily = $derived(doc.references.filter((r) => !family || r.space === family.id).length);
	const pills = $derived([{ id: 'all', label: t('references.all'), count: doc.references.length }, ...families.map((f) => ({ id: f.id, label: f.short, tip: f.hint, count: doc.references.filter((r) => r.space === f.id).length }))]);
	const emptyProps = $derived({
		icon: family?.icon ?? 'bookmark',
		title: family ? t('references.empty.family', { family: family.label }) : t('references.empty.all'),
		description: family ? family.hint : t('references.empty.allHint'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'sm', icon: 'plus', onclick: () => addReference(), children: t('references.add') }) }
	});

	function emptyText(group) {
		const family = ui.refSpace !== 'all' ? fam(ui.refSpace)?.label : null;
		if (group === 'global') return family ? t('references.empty.globalIn', { family }) : t('references.empty.global');
		return family ? t('references.empty.shotIn', { family }) : t('references.empty.shot');
	}
</script>

<section class="isolate flex min-w-0 flex-col bg-canvas" aria-label={t('references.title')}>
	<ZoneHeader icon={ui.sidebarOpen ? VIEW_ICONS.references : null} title={t('references.title')} subtitle={t('references.total', { count: doc.references.length })}>
		{#snippet lead()}<DirectorViews />{/snippet}
		{#if !sent && doc.references.length}
			<HostUi name="Tooltip" props={{ text: t('generation.refs.why', { engine: engineTitle(project) }), wrapperClass: 'inline-flex shrink-0' }}>
				<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('generation.refs.notSent')}</HostUi>
			</HostUi>
		{/if}
		<FilterPills class="ml-1" label={t('references.families')} items={pills} value={ui.refSpace} onselect={(id) => (ui.refSpace = id)} />
		<div class="flex-1"></div>
		<div class="relative w-52 min-w-28">
			<Icon name="search" class="pointer-events-none absolute left-2 top-1.5 h-4 w-4 text-fg-subtle" />
			<input class="input vp-dense !pl-7" placeholder={t('references.search')} bind:value={q} aria-label={t('references.searchLabel')} />
		</div>
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'shrink-0', onclick: () => addReference() }}>{t('references.add')}</HostUi>
	</ZoneHeader>

	{#if shot}
		<p class="flex shrink-0 items-center gap-1.5 border-b border-line px-5 py-2 text-xs text-fg-muted" data-reference-highlight={shot.id}>
			<Icon name="info" class="h-3.5 w-3.5 shrink-0" />
			<span class="min-w-0">{t('references.highlight', { count: going.size, shot: `${shotNum} · ${clipLabel(shot)}`, space: spaceLabel(ui.selectedIn) ?? t('inspector.elsewhere.space') })}</span>
		</p>
	{/if}
	<div class="flex min-h-0 flex-1 flex-col gap-6 overflow-auto p-5">
		{#if !inFamily && !tracks.length}
			<div class="m-auto w-full max-w-lg">
				<HostUi name="EmptyState" props={emptyProps} />
			</div>
		{/if}
		{#each inFamily ? groups : [] as g (g.id)}
			<section>
				<div class="mb-3 flex items-baseline gap-2">
					<h3 class="text-sm font-semibold">{g.title}</h3>
					<span class="text-xs text-fg-subtle">{t('references.groupHint', { hint: g.hint, count: g.refs.length })}</span>
				</div>
				{#if g.refs.length}
					<ul class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
						{#each g.refs as r (r.id)}
							{@const a = r.assetId ? asset(r.assetId) : null}
							{@const thumb = assetThumb(a)}
							{@const kind = refMediaKind(r.space, r.type)}
							{@const f = fam(r.space)}
							{@const playable = a?.kind === 'audio' && a.src}
							<li class="rounded-xl border bg-surface-1 p-2 transition-[border-color,box-shadow,opacity] duration-150 {isSel(r) ? 'border-signal shadow-[0_0_0_1px_rgb(var(--signal))]' : going?.has(r.id) ? 'border-signal' : 'border-line-strong hover:border-line-hover'} {left?.has(r.id) || aside?.has(r.id) ? 'opacity-50' : ''}" data-reference-card={r.id} data-going={going ? going.has(r.id) : null}>
								<div
									role="button"
									tabindex="0"
									class="group w-full text-left"
									draggable={!!a?.src}
									ondragstart={(e) => a?.src && e.dataTransfer.setData('text/x-asset', a.id)}
									onclick={() => select('reference', r.id)}
									onkeydown={(e) => activateOnKey(e, () => select('reference', r.id))}
									title={a?.src ? t('references.dragHint') : f?.hint}
								>
									<div class="relative aspect-video overflow-hidden rounded-lg bg-surface-3">
										{#if thumb}
											<img src={thumb} alt="" class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03] motion-reduce:transition-none motion-reduce:group-hover:scale-100" draggable="false" />
										{:else}
											<div class="flex h-full items-center justify-center bg-[radial-gradient(circle_at_30%_20%,rgb(var(--viz-8)/0.25),transparent_60%)]">
												<Icon name={typeIcon(r)} class="h-7 w-7 text-fg-muted" />
											</div>
										{/if}
									</div>
									<div class="space-y-1 px-1 pb-0.5 pt-2">
										<div class="truncate text-sm font-medium">{r.name}</div>
										<RefTags reference={r} />
										{#if left?.has(r.id)}<div class="text-xs text-warning">{t('references.excludedFrom', { shot: shotNum })}</div>{/if}
										{#if aside?.has(r.id)}<div class="text-xs text-fg-subtle" data-not-cast>{t('references.notCastIn', { shot: shotNum })}</div>{/if}
										{#if r.file || a?.kind === 'audio'}<div class="truncate text-xs text-fg-subtle">{[r.file ? t('references.file', { file: r.file }) : '', a?.kind === 'audio' ? (a.srcDur ? secs(a.srcDur) : a.name) : ''].filter(Boolean).join(' · ')}</div>{/if}
										{#if kind === 'audio' && !playable}
											<div class="mt-1 text-xs text-warning">{t('references.noSound')}</div>
										{:else if !a}
											<div class="mt-1 text-xs text-warning">{kind === 'video' ? t('references.noVideo') : t('references.noImage')}</div>
										{/if}
									</div>
								</div>
								{#if playable}
									<div class="px-1 pb-0.5">
										<!-- svelte-ignore a11y_media_has_caption -->
										<audio class="mt-1 h-8 w-full" controls preload="metadata" src={a.src} aria-label={t('references.listen', { name: r.name })}></audio>
									</div>
								{/if}
							</li>
						{/each}
					</ul>
				{:else}
					<HostUi name="EmptyState" props={{ compact: true, icon: 'bookmark', title: emptyText(g.id) }} />
				{/if}
			</section>
		{/each}
		{#if tracks.length}
			<section data-reference-tracks>
				<div class="mb-3 flex items-baseline gap-2">
					<h3 class="text-sm font-semibold">{t('references.group.tracks')}</h3>
					<span class="text-xs text-fg-subtle">{t('references.groupHint', { hint: t('references.group.tracksHint'), count: tracks.length })}</span>
				</div>
				<ul class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
					{#each tracks as track (track.id)}
						{@const thumb = trackThumb(track)}
						{@const count = receivingCount(receptions, track.id)}
						<li class="rounded-xl border bg-surface-1 p-2 transition-[border-color,box-shadow,opacity] duration-150 {isTrack(track) ? 'border-signal shadow-[0_0_0_1px_rgb(var(--signal))]' : 'border-line-strong hover:border-line-hover'} {track.off ? 'opacity-50' : ''}" data-reference-track-card={track.id}>
							<div role="button" tabindex="0" class="group w-full text-left" onclick={() => select('vtrack', track.id)} onkeydown={(e) => activateOnKey(e, () => select('vtrack', track.id))}>
								<div class="relative aspect-video overflow-hidden rounded-lg bg-surface-3">
									{#if thumb}
										<img src={thumb} alt="" class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03] motion-reduce:transition-none motion-reduce:group-hover:scale-100" draggable="false" />
									{:else}
										<div class="flex h-full items-center justify-center bg-[radial-gradient(circle_at_30%_20%,rgb(var(--viz-8)/0.25),transparent_60%)]"><Icon name="film" class="h-7 w-7 text-fg-muted" /></div>
									{/if}
								</div>
								<div class="space-y-1 px-1 pb-0.5 pt-2">
									<div class="flex min-w-0 items-center gap-1.5">
										<span class="{TAG_CLASS} vp-tc shrink-0">{vrefLabel(track.slot)}</span>
										<span class="truncate text-sm font-medium">{track.name || t('inspector.kind.vtrack')}</span>
									</div>
									<div class="truncate text-xs text-fg-subtle">{roleLabel(track.role)}</div>
									{#if track.off}
										<div class="text-xs text-fg-subtle">{t('lib.vref.verdict.off')}</div>
									{:else if count}
										<div class="text-xs text-success">{t('references.trackReceived', { count })}</div>
									{:else}
										<div class="text-xs text-fg-subtle">{t('timeline.vref.nobody')}</div>
									{/if}
								</div>
							</div>
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	</div>
</section>

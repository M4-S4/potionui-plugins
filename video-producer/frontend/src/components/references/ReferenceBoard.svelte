<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, select, secs } from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { families, addReference, refMediaKind, refTypeLabel, refRoleLabel } from '../../lib/references.js';
	import { mountHostSlot } from '../../lib/host.js';
	import { assetThumb } from '../../lib/media.js';
	import { activateOnKey } from '../../lib/keyboard.js';
	import { engineLabel, supportedProfiles } from '../../lib/production.svelte.js';
	import DirectorViews from '../director/DirectorViews.svelte';
	import Icon from '../Icon.svelte';

	let q = $state('');
	const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
	const sent = $derived(supportedProfiles().includes('Ref2VA'));
	const shotOf = (r) => (r.scope.type === 'shot' ? doc.clips.find((c) => c.id === r.scope.shotId) ?? null : null);
	const list = $derived(
		doc.references.filter((r) => (ui.refSpace === 'all' || r.space === ui.refSpace) && (!q || norm(`${r.name} ${refTypeLabel(r.type)} ${refRoleLabel(r.role)}`).includes(norm(q))))
	);
	const groups = $derived([
		{ id: 'global', title: t('references.group.global'), hint: t('references.group.globalHint'), refs: list.filter((r) => r.scope.type === 'global') },
		{ id: 'shot', title: t('references.group.shot'), hint: t('references.group.shotHint'), refs: list.filter((r) => r.scope.type === 'shot') }
	]);
	const fam = (id) => families.find((f) => f.id === id);
	const isSel = (r) => ui.selection?.kind === 'reference' && ui.selection.id === r.id;
	const family = $derived(ui.refSpace === 'all' ? null : (fam(ui.refSpace) ?? null));
	const inFamily = $derived(doc.references.filter((r) => !family || r.space === family.id).length);
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

	function openAt(r) {
		const shot = shotOf(r);
		if (shot) seek(shot.start);
	}
</script>

<section class="isolate flex min-w-0 flex-col bg-canvas" aria-label={t('references.title')}>
	<div class="flex h-10 shrink-0 items-center gap-3 border-b border-line px-4">
		<DirectorViews />
		<span class="shrink-0 whitespace-nowrap text-sm font-semibold">{t('references.title')}</span>
		<span class="shrink-0 whitespace-nowrap text-xs text-fg-subtle">{t('references.total', { count: doc.references.length })}</span>
		{#if !sent && doc.references.length}
			<HostUi name="Tooltip" props={{ text: t('generation.refs.why', { engine: engineLabel() }), wrapperClass: 'inline-flex shrink-0' }}>
				<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('generation.refs.notSent')}</HostUi>
			</HostUi>
		{/if}
		<div class="no-scrollbar ml-1 flex min-w-0 items-center gap-1 overflow-x-auto p-1" role="tablist" aria-label={t('references.families')}>
			<button type="button" role="tab" class="vp-pill shrink-0" aria-selected={ui.refSpace === 'all'} onclick={() => (ui.refSpace = 'all')}>{t('references.all')}</button>
			{#each families as f (f.id)}
				<HostUi name="Tooltip" props={{ text: f.hint }}>
					<button type="button" role="tab" class="vp-pill shrink-0" aria-selected={ui.refSpace === f.id} onclick={() => (ui.refSpace = f.id)}>{f.short}</button>
				</HostUi>
			{/each}
		</div>
		<div class="flex-1"></div>
		<div class="relative w-52 min-w-28">
			<Icon name="search" class="pointer-events-none absolute left-2 top-1.5 h-4 w-4 text-fg-subtle" />
			<input class="input vp-dense !pl-7" placeholder={t('references.search')} bind:value={q} aria-label={t('references.searchLabel')} />
		</div>
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'shrink-0', onclick: () => addReference() }}>{t('references.add')}</HostUi>
	</div>

	<div class="flex min-h-0 flex-1 flex-col gap-6 overflow-auto p-5">
		{#if !inFamily}
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
							{@const shot = shotOf(r)}
							{@const playable = a?.kind === 'audio' && a.src}
							<li class="rounded-xl border bg-surface-1 p-2 transition-[border-color,box-shadow] duration-150 {isSel(r) ? 'border-signal shadow-[0_0_0_1px_rgb(var(--signal))]' : 'border-line-strong hover:border-line-hover'}">
								<div
									role="button"
									tabindex="0"
									class="group w-full text-left"
									draggable={!!a?.src}
									ondragstart={(e) => a?.src && e.dataTransfer.setData('text/x-asset', a.id)}
									onclick={() => select('reference', r.id)}
									onkeydown={(e) => activateOnKey(e, () => select('reference', r.id))}
									ondblclick={() => openAt(r)}
									title={a?.src ? t('references.dragHint') : f?.hint}
								>
									<div class="relative aspect-video overflow-hidden rounded-lg bg-surface-3">
										{#if thumb}
											<img src={thumb} alt="" class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03] motion-reduce:transition-none motion-reduce:group-hover:scale-100" draggable="false" />
										{:else}
											<div class="flex h-full items-center justify-center bg-[radial-gradient(circle_at_30%_20%,rgb(var(--viz-8)/0.25),transparent_60%)]">
												<Icon name={f?.icon ?? 'bookmark'} class="h-7 w-7 text-fg-muted" />
											</div>
										{/if}
										<span class="absolute left-2 top-2 flex items-center gap-1 rounded-md bg-black/60 px-1.5 py-0.5 text-xs text-white backdrop-blur-sm"><Icon name={f?.icon ?? 'bookmark'} class="h-3 w-3" />{refTypeLabel(r.type)}</span>
										<span class="absolute bottom-2 right-2 rounded-md bg-black/60 px-1.5 py-0.5 text-xs text-white backdrop-blur-sm">
											{#if r.scope.type === 'global'}{t('references.globalBadge')}{:else if shot}<span class="vp-tc">{t('references.range', { start: secs(shot.start), end: secs(shot.start + shot.dur) })}</span>{/if}
										</span>
									</div>
									<div class="px-1 pb-0.5 pt-2">
										<div class="truncate text-sm font-medium">{r.name}</div>
										<div class="truncate text-xs text-fg-subtle">{r.file ? t('references.roleFile', { role: refRoleLabel(r.role), file: r.file }) : refRoleLabel(r.role)}{a?.kind === 'audio' ? ` · ${a.srcDur ? secs(a.srcDur) : a.name}` : ''}</div>
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
	</div>
</section>

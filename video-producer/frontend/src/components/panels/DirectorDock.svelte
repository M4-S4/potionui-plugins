<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { ui, doc, select, secs, globalPrompt, allIssues, itemsIn, productionRange, act, clipLabel } from '../../lib/state.svelte.js';
	import { takesOf, assembleChosen, generateQueue, supportedProfiles, engineLabel } from '../../lib/production.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { seams, matchToPrevious } from '../../lib/continuity.svelte.js';
	import { directionFields, stages } from '../../lib/catalog.js';
	import { families, addReference, attachToRange } from '../../lib/references.js';
	import { hostIconName } from '../../lib/icons.js';
	import PanelHeader from './PanelHeader.svelte';
	import Tabs from '../shell/Tabs.svelte';
	import TakeCard from '../takes/TakeCard.svelte';
	import Icon from '../Icon.svelte';

	const modes = ['FL2VA', 'Ref2VA', 'Hybrid AV'];
	let open = $state({ univers: true, personnages: false, photographie: false, palette: true, rythme: false });

	const chars = $derived(globalPrompt().length);
	const issues = $derived(allIssues().filter((i) => i.level !== 'missing'));
	const range = $derived(productionRange());
	const scope = $derived(itemsIn(range));
	const local = $derived(scope.prompts[0]);
	const seamIssues = $derived(seams().flatMap((s) => s.issues.map((x) => ({ ...x, clip: s.to }))));
	const chosen = $derived(takeStore.list.filter((r) => r.chosen && r.status === 'done').length);
	const takeCount = $derived(takeStore.list.length + (doc.results?.length ?? 0));
	const supported = $derived(supportedProfiles());
	const unsupported = $derived(modes.filter((m) => !supported.includes(m)));
	const tabs = $derived([
		{ id: 'direction', label: t('panels.dock.tab.direction'), dot: issues.length > 0 || seamIssues.length > 0 },
		{ id: 'references', label: t('panels.dock.tab.references') },
		{ id: 'results', label: t('panels.dock.tab.results'), badge: takeCount || null }
	]);
	const allFamilies = $derived([{ id: 'all', label: t('panels.dock.refs.all'), icon: 'bookmark', hint: '' }, ...families]);
	const refFamily = $derived(families.find((f) => f.id === ui.refSpace) ?? null);
	const refCount = $derived(refFamily ? doc.references.filter((r) => r.space === refFamily.id).length : doc.references.length);

	function modeHint(m) {
		if (m === 'FL2VA') return t('panels.dock.mode.fl2va');
		if (m === 'Ref2VA') return t('panels.dock.mode.ref2va');
		return t('panels.dock.mode.hybrid');
	}

	function openPrompt(p) {
		select('prompt', p.id);
		seek(p.start);
		ui.modal = { type: 'prompt', id: p.id };
	}
</script>

<PanelHeader icon="sparkles" title={t('panels.dock.title')} border={false}>
	<HostUi
		name="IconButton"
		props={{ icon: 'settings', label: t('panels.dock.settings'), size: 'sm', class: 'vp-h7', tooltip: t('panels.dock.settingsTip'), onclick: () => (ui.modal = { type: 'advanced', step: 1 }) }}
	/>
</PanelHeader>

<Tabs label={t('panels.dock.tabs')} value={ui.dockTab} onselect={(id) => (ui.dockTab = id)} items={tabs} />

<div class="min-h-0 flex-1 overflow-auto">
	{#if ui.dockTab === 'direction'}
		<div class="m-3 rounded-lg border border-line-strong bg-canvas/50 p-2.5">
			<div class="mb-2 flex items-baseline justify-between">
				<span class="vp-section-title">{t('panels.dock.guide.title')}</span>
				<span class="vp-tc text-xs text-fg-subtle">{t('panels.dock.range', { start: secs(range[0]), end: secs(range[1]) })}</span>
			</div>
			<ol class="space-y-1.5 text-xs">
				<li class="flex gap-2">
					<span class="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-sm bg-surface-3 text-2xs font-semibold">1</span>
					<div class="min-w-0">
						<div class="font-medium text-fg">{t('panels.dock.guide.global')}</div>
						<div class="text-fg-subtle">{t('panels.dock.guide.globalHint', { chars })}</div>
					</div>
				</li>
				<li class="flex gap-2">
					<span class="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-sm bg-surface-3 text-2xs font-semibold">2</span>
					<div class="min-w-0">
						<div class="font-medium text-fg">{t('panels.dock.guide.local')}</div>
						{#if local}
							<button type="button" class="block min-h-6 max-w-full truncate text-left text-fg-muted hover:text-fg" onclick={() => (ui.modal = { type: 'prompt', id: local.id })}>
								{t('panels.dock.guide.quote', { text: local.text || t('panels.dock.guide.emptyPrompt') })}
							</button>
						{:else}
							<div class="text-fg-subtle">{t('panels.dock.guide.noPrompt')}</div>
						{/if}
					</div>
				</li>
				<li class="flex gap-2">
					<span class="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-sm bg-surface-3 text-2xs font-semibold">3</span>
					<div class="min-w-0">
						<div class="font-medium text-fg">{t('panels.dock.guide.refs')}</div>
						<div class="text-fg-subtle">
							{t('panels.dock.count.refs', { count: scope.references.length })} · {t('panels.dock.count.frames', { count: scope.frames.length })} · {t('panels.dock.count.controls', { count: scope.controls.length })}
						</div>
					</div>
				</li>
			</ol>
			<div class="mt-2">
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('list'), class: 'w-full', onclick: () => (ui.modal = { type: 'recap' }) }}>{t('panels.dock.guide.recap')}</HostUi>
			</div>
		</div>

		{#if issues.length || seamIssues.length}
			<div class="mx-3 mb-3">
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: hostIconName('alert'), title: t('panels.dock.issues', { count: issues.length + seamIssues.length }), live: 'off' }}>
					<ul class="mt-1.5 space-y-2">
						{#each issues as i, n (n)}
							<li class="flex gap-1.5 text-xs text-fg-muted">
								<Icon name={i.level === 'control' ? 'route' : 'sparkles'} class="mt-px h-3.5 w-3.5 shrink-0 text-fg-subtle" />
								<span>
									{i.text}
									<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => openPrompt(i.prompt)}>{t('panels.dock.issuePrompt', { time: secs(i.prompt.start) })}</button>
								</span>
							</li>
						{/each}
						{#each seamIssues as i, n (n)}
							<li class="flex gap-1.5 text-xs text-fg-muted">
								<Icon name={i.kind === 'identity' ? 'user' : 'palette'} class="mt-px h-3.5 w-3.5 shrink-0 text-fg-subtle" />
								<span>
									{i.text}
									{#if i.fix}
										<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => matchToPrevious(i.clip)}>{t('panels.dock.match')}</button>
									{:else}
										<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => (select('clip', i.clip.id), (ui.inspectorTab = 'takes'))}>{t('panels.dock.seeTakes')}</button>
									{/if}
								</span>
							</li>
						{/each}
					</ul>
				</HostUi>
			</div>
		{/if}

		<div class="space-y-1 px-3">
			<div class="vp-label mb-1">{t('panels.dock.profile')}</div>
			<HostUi
				name="SegmentedControl"
				props={{
					variant: 'toggle',
					fullWidth: true,
					ariaLabel: t('panels.dock.profileGroup'),
					items: modes.map((m) => ({ id: m, label: m, disabled: !supported.includes(m) })),
					selected: doc.direction.mode,
					onSelect: (m) => act(() => (doc.direction.mode = m))
				}}
			/>
			<p class="pt-1 text-xs text-fg-subtle">{modeHint(doc.direction.mode)}</p>
			{#if unsupported.length}
				<HostUi name="Tooltip" props={{ text: t('generation.profile.why', { profiles: unsupported.join(', '), engine: engineLabel() }), wrapperClass: 'inline-flex' }}>
					<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('generation.profile.badge', { profiles: unsupported.join(' · ') })}</span>
				</HostUi>
			{/if}
		</div>

		<div class="mt-3 border-t border-line">
			<div class="flex items-center justify-between px-3 pb-1 pt-3">
				<span class="vp-section-title">{t('panels.dock.global')}</span>
				<span class="vp-tc text-xs {chars > 4000 ? 'text-danger' : 'text-fg-subtle'}">{t('panels.dock.globalCount', { chars, max: 4000 })}</span>
			</div>
			{#each directionFields as f (f.key)}
				<div class="border-b border-line/70 px-3">
					<button type="button" class="flex h-8 w-full items-center gap-1.5 text-left text-sm" aria-expanded={open[f.key]} onclick={() => (open[f.key] = !open[f.key])}>
						<Icon name={open[f.key] ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5 text-fg-subtle" />
						<span class="flex-1 text-fg">{f.label}</span>
						{#if doc.direction[f.key]?.trim()}<Icon name="check" class="h-3.5 w-3.5 text-success" />{:else}<span class="text-xs text-fg-subtle">{t('panels.dock.fieldEmpty')}</span>{/if}
					</button>
					{#if open[f.key]}
						<div class="pb-2.5">
							<textarea class="input text-sm" rows="3" bind:value={doc.direction[f.key]} placeholder={f.hint} aria-label={f.label} oninput={() => (ui.dirty = true)}></textarea>
							<button type="button" class="mt-1 flex min-h-6 items-center gap-1 text-xs text-fg-muted hover:text-fg" onclick={() => (ui.modal = { type: 'library', target: { kind: 'direction', key: f.key } })}>
								<Icon name="wand" class="h-3.5 w-3.5" />{t('panels.dock.library')}
							</button>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{:else if ui.dockTab === 'references'}
		<div class="flex flex-col gap-4 p-3">
			<p class="text-xs text-fg-subtle">{t('panels.dock.refs.intro')}</p>
			{#if !supported.includes('Ref2VA')}
				<HostUi name="Tooltip" props={{ text: t('generation.refs.why', { engine: engineLabel() }), wrapperClass: 'inline-flex' }}>
					<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('generation.refs.badge')}</span>
				</HostUi>
			{/if}
			<ul class="space-y-0.5" role="tablist" aria-label={t('panels.dock.refs.families')}>
				{#each allFamilies as f (f.id)}
					{@const n = f.id === 'all' ? doc.references.length : doc.references.filter((r) => r.space === f.id).length}
					<li>
						<button
							type="button"
							role="tab"
							aria-selected={ui.refSpace === f.id}
							class="flex w-full items-center gap-2.5 rounded-lg border px-2 py-1.5 text-left transition-colors {ui.refSpace === f.id ? 'border-signal bg-surface-2 text-fg' : 'border-transparent text-fg-muted hover:bg-surface-2'}"
							onclick={() => (ui.refSpace = f.id)}
						>
							<Icon name={f.icon} class="h-4 w-4 shrink-0" />
							<span class="min-w-0 flex-1">
								<span class="block text-sm">{f.label}</span>
								{#if f.hint}<span class="block truncate text-xs text-fg-muted">{f.hint}</span>{/if}
							</span>
							<span class="vp-tc text-xs text-fg-muted">{n}</span>
						</button>
					</li>
				{/each}
			</ul>
			{#if !refCount}
				<HostUi
					name="EmptyState"
					props={{ compact: true, icon: refFamily?.icon ?? 'bookmark', title: refFamily ? t('references.empty.family', { family: refFamily.label }) : t('references.empty.all'), description: refFamily ? refFamily.hint : t('references.empty.allHint') }}
				/>
			{/if}
			<div class="grid grid-cols-2 gap-2 text-xs">
				<div class="rounded-lg border border-line-strong p-2">
					<div class="text-fg-subtle">{t('panels.dock.refs.global')}</div>
					<div class="vp-tc mt-0.5 text-sm text-fg">{doc.references.filter((r) => r.scope.type === 'global').length}</div>
				</div>
				<div class="rounded-lg border border-line-strong p-2">
					<div class="text-fg-subtle">{t('panels.dock.refs.inRange')}</div>
					<div class="vp-tc mt-0.5 text-sm text-fg">{scope.references.filter((r) => r.scope.type === 'shot').length}</div>
				</div>
			</div>
			{#if ui.selection?.kind === 'reference'}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('target'), class: 'w-full', onclick: attachToRange }}>
					{t('panels.dock.refs.attach', { start: secs(range[0]), end: secs(range[1]) })}
				</HostUi>
			{/if}
			<div class="flex flex-col gap-0.5">
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'w-full !justify-start', onclick: () => addReference() }}>{t('panels.dock.refs.add')}</HostUi>
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'w-full !justify-start', onclick: () => (ui.modal = { type: 'splat' }) }}>{t('panels.dock.refs.splat')}</HostUi>
			</div>
			<p class="text-xs text-fg-subtle">{t('panels.dock.refs.dragHint')}</p>
		</div>
	{:else}
		<div class="flex flex-col gap-4 p-3">
			{#if ui.production.queue.length}
				<div class="rounded-lg border border-line-strong p-2.5">
					<div class="mb-1.5 flex items-center justify-between">
						<span class="vp-section-title">{t('panels.dock.queue.title', { count: ui.production.queue.length })}</span>
						<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => (ui.production.queue = []) }}>{t('panels.dock.queue.clear')}</HostUi>
					</div>
					<ul class="space-y-1 text-xs text-fg-muted">
						{#each ui.production.queue as w, i (w.id)}
							<li class="flex items-center gap-2">
								<span class="vp-tc">{i + 1}.</span>{w.label}<span class="ml-auto text-fg-subtle">{w.quality === 'final' ? t('panels.dock.final') : t('panels.dock.draft')}</span>
							</li>
						{/each}
					</ul>
					<div class="mt-2">
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'sparkles', class: 'w-full', onclick: generateQueue }}>{t('panels.dock.queue.generate')}</HostUi>
					</div>
				</div>
			{/if}

			{#if !takeCount && takeStore.loaded}
				<HostUi name="EmptyState" props={{ compact: true, icon: 'sparkles', title: t('panels.dock.results.empty'), description: t('panels.dock.results.emptyHint') }} />
			{/if}

			{#each doc.clips.filter((c) => takesOf(c).length) as c (c.id)}
				{@const list = takesOf(c)}
				<section>
					<button type="button" class="mb-1 flex min-h-7 w-full items-center gap-2 text-left" onclick={() => (select('clip', c.id), seek(c.start))}>
						<span class="vp-tc text-xs text-fg-subtle">{String(doc.clips.indexOf(c) + 1).padStart(2, '0')}</span>
						<span class="min-w-0 flex-1 truncate text-sm font-medium">{clipLabel(c)}</span>
						<span class="flex items-center gap-1 text-xs {stages[c.stage].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[c.stage].dot}"></span>{stages[c.stage].label}</span>
					</button>
					<ul class="space-y-2">
						{#each list as r (r.id)}
							<TakeCard take={r} clip={c} />
						{/each}
					</ul>
				</section>
			{/each}
		</div>
	{/if}
</div>

{#if ui.dockTab === 'results' && takeCount}
	<div class="shrink-0 border-t border-line p-3">
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'layers', class: 'w-full', disabled: !chosen, onclick: assembleChosen }}>{t('panels.dock.results.assemble', { count: chosen })}</HostUi>
	</div>
{/if}

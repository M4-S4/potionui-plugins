<script>
	import { untrack } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, act, secs, allIssues, fmtDuration } from '../../lib/state.svelte.js';
	import {
		readiness,
		startGeneration,
		cancelGeneration,
		openQueue,
		openEngineSettings,
		openResults,
		jobClips,
		currentEngine,
		engineGroups,
		engineLabel,
		selectEngine,
		setProjectQuality,
		supportedProfiles,
		soundGuides,
		backendName,
		estimateRequest,
		scheduleEstimate,
		estimateState
	} from '../../lib/production.svelte.js';
	import { PRODUCTION_MODES, modeLabel } from '../../lib/catalog.js';
	import { aspectOf, draftResolution, finalResolution } from '../../lib/generation.js';
	import { commandById } from '../../lib/commands.js';
	import { hasOwnEngine } from '../../lib/engine.js';
	import { fitInline } from '../../lib/barfit.js';
	import { optionCount } from '../../lib/options.js';
	import { MAX_MARGIN, referenceMargin, setReferenceMargin } from '../../lib/sound.js';
	import { announcer } from '../../lib/announce.js';
	import { hostIconName } from '../../lib/icons.js';
	import { overlayLayer } from '../../lib/host.js';
	import Icon from '../Icon.svelte';
	import InfoTip from '../shell/InfoTip.svelte';
	import SeamAction from '../takes/SeamAction.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import { takeCount } from '../../lib/shots.js';
	import { flyingTakes } from '../../lib/takes.svelte.js';

	const p = $derived(ui.production);
	const ready = $derived(readiness());
	const it = $derived(ready.items);
	const est = $derived(ready.est);
	const clips = $derived(jobClips(ready.range));
	const engine = $derived(currentEngine());
	const groups = $derived(engineGroups());
	const cloud = $derived(engine?.kind === 'cloud');
	const aspect = $derived(aspectOf(doc.aspect, doc.resolution));
	const draftRes = $derived(draftResolution(engine?.info, ui.me?.settings?.draftResolution, aspect)?.replace('x', '×') ?? '—');
	const finalRes = $derived(finalResolution(engine?.info, aspect)?.replace('x', '×') ?? '—');
	const conflicts = $derived(allIssues().filter((i) => i.level !== 'missing' && it.prompts.includes(i.prompt)));
	const status = $derived(p.state === 'running' ? 'running' : p.state === 'done' ? 'done' : ready.missing.length ? 'missing' : 'ready');
	const busy = $derived(status === 'running');
	const blocked = $derived(ready.missing.length > 0);
	const notes = $derived(blocked ? [...ready.missing, ...ready.warnings] : ready.warnings);
	const gapClip = $derived(blocked ? null : (ready.gaps.map((id) => doc.clips.find((c) => c.id === id)).find((c) => c && doc.clips.indexOf(c) > 0) ?? null));
	const primary = $derived(p.mode === 'render3d' ? t('production.prepareRender') : t('production.generate'));
	const targets = $derived([
		{ id: 'clip', label: t('production.target.clip') },
		{ id: 'range', label: t('production.target.range') },
		{ id: 'sequence', label: t('production.target.sequence') }
	]);
	const qualities = $derived([
		{ id: 'draft', label: t('lib.stage.draft') },
		{ id: 'final', label: t('lib.stage.final') }
	]);
	const one = (v) => formatNumber(v ?? 0, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
	const minutes = (v) => formatNumber(v ?? 0, { maximumFractionDigits: 1 });
	const money = (v) => formatNumber(Number(v), { style: 'currency', currency: 'USD' });
	const scope = $derived(
		[
			t('production.count.shots', { count: clips.length }),
			t('production.count.prompts', { count: it.prompts.length }),
			t('production.count.frames', { count: it.frames.length }),
			t('production.count.references', { count: it.references.length }),
			it.controls.length ? t('production.count.controls', { count: it.controls.length }) : ''
		]
			.filter(Boolean)
			.join(' · ')
	);
	const resolutions = $derived([...new Set((est?.shots ?? []).map((s) => s.resolution?.replace('x', '×')).filter(Boolean))].join(', ') || '—');
	const quota = $derived(est?.quota ?? null);
	const showQuota = $derived(Boolean(quota?.applies && !quota.exempt && quota.limit !== null));
	const showCost = $derived(Boolean(ui.isAdmin && est?.cost?.known && est.cost.totalUsd !== null));
	const vram = $derived(est?.vram ?? null);
	const timeText = $derived(est?.time.seconds != null ? `≈ ${fmtDuration(est.time.seconds)}` : '—');
	const vramText = $derived(vram && !vram.unknown && vram.estimateGb != null ? t('production.estimate.vramShort', { value: one(vram.estimateGb) }) : '—');
	const estLines = $derived.by(() => {
		if (!est) return [estimateState.loading ? t('generation.estimate.loading') : t('generation.estimate.pending')];
		const lines = [t('generation.estimate.scope', { shots: t('production.count.shots', { count: clips.length }), variants: t('production.count.takes', { count: takeCount(clips, doc.engine) }), res: resolutions })];
		lines.push(est.time.seconds != null ? t('generation.estimate.time', { duration: fmtDuration(est.time.seconds), engine: engineLabel(), count: est.time.samples }) : t('generation.estimate.timeUnknown', { engine: engineLabel() }));
		if (!cloud) {
			if (!vram || vram.unknown || vram.estimateGb == null) lines.push(t('generation.estimate.vramUnknown'));
			else if (vram.freeGb != null) lines.push(t('generation.estimate.vram', { need: one(vram.estimateGb), free: one(vram.freeGb), backend: backendName(vram.backendId ?? engine?.backend) }));
			else lines.push(t('generation.estimate.vramNeed', { need: one(vram.estimateGb) }));
			if (vram?.streams) lines.push(t('generation.warn.vramStream'));
		}
		if (quota?.exempt) lines.push(t('generation.estimate.quotaExempt'));
		else if (showQuota) lines.push(t('generation.estimate.quota', { need: minutes(quota.neededMinutes), remaining: minutes(quota.remaining), limit: minutes(quota.limit) }));
		else if (quota && !quota.applies) lines.push(t('generation.estimate.noQuota'));
		if (ui.isAdmin && est.cost) lines.push(est.cost.known && est.cost.totalUsd !== null ? t('generation.estimate.cost', { cost: money(est.cost.totalUsd) }) : t('generation.estimate.costUnknown'));
		return [...lines, ...ready.notes];
	});
	const over = $derived(Boolean(vram?.streams || quota?.blocks));
	const queued = $derived(flyingTakes().length);
	const queueTip = $derived(queued ? `${t('production.queue')} · ${t('production.queued', { count: queued })}` : t('production.queue'));
	const engineTip = $derived.by(() => {
		if (!engine) return groups.length ? engineLabel() : t('generation.engine.empty');
		const backend = (ui.me?.engines ?? []).find((e) => e.id === engine.backend);
		const parts = [engine.label, engine.group];
		if (backend && backend.kind !== 'cloud' && backend.vramFree != null && backend.vramTotal != null) parts.push(t('generation.engine.vram', { free: one(backend.vramFree), total: one(backend.vramTotal) }));
		return parts.join(' · ');
	});

	const profileItems = $derived(supportedProfiles().map((m) => ({ id: m, label: m })));
	const showProfile = $derived(profileItems.length > 1 || !profileItems.some((m) => m.id === doc.direction.mode));
	const guided = $derived(soundGuides());
	const own = $derived(doc.clips.filter(hasOwnEngine).length);
	const setCount = $derived(optionCount(doc.engine, engine?.preset));
	const editTip = $derived(engine ? t('production.editEngineTip', { engine: engine.label }) : t('production.editEngine'));
	const MORE = 'engine-more';
	let room = $state(0);
	let widths = $state({ engine: 184, profile: 220, margin: 128, own: 64, label: 88 });
	const fit = $derived(
		fitInline(room, [
			{ id: 'engine', width: widths.engine, rank: 1 },
			{ id: 'profile', width: widths.profile, rank: 2, show: showProfile },
			{ id: 'margin', width: widths.margin, rank: 3, show: guided },
			{ id: 'own', width: widths.own, rank: 4, show: own > 0 },
			{ id: 'edit', width: 28, rank: 0, pinned: true },
			{ id: 'label', width: widths.label, rank: 5, folds: false }
		])
	);
	const moreOpen = $derived(ui.menuOpen === MORE && fit.overflow.length > 0);

	function profileHint(m) {
		if (m === 'FL2VA') return t('production.profile.fl2va');
		if (m === 'Ref2VA') return t('production.profile.ref2va');
		return t('production.profile.hybrid');
	}

	function setProfile(m) {
		if (m !== doc.direction.mode) act(() => (doc.direction.mode = m));
	}

	function setMargin(value) {
		act(() => setReferenceMargin(doc.engine, value));
	}

	const voice = announcer();
	let spoken = $state('');

	$effect(() => {
		const request = estimateRequest();
		untrack(() => scheduleEstimate(request));
	});

	$effect(() => {
		if (!busy) {
			voice.reset();
			spoken = '';
			return;
		}
		const said = voice.next(p.step, p.progress);
		if (said) spoken = `${said.label} · ${t('exports.percent', { value: said.value })}`;
	});

	function pick(id) {
		p.target = id;
		if (id === 'range' && !ui.range) ui.range = { in: ready.range[0], out: ready.range[1] };
	}

	function directionIssues() {
		ui.workspace = 'director';
		ui.dockTab = 'direction';
	}
</script>

<div class="flex h-11 items-center gap-2 border-b border-line bg-surface-1 px-3" role="region" aria-label={t('production.region')}>
	<HostUi name="SegmentedControl" props={{ items: targets, selected: p.target, variant: 'toggle', ariaLabel: t('production.target.label'), onSelect: pick }} />
	<HostUi name="Tooltip" props={{ text: scope, wrapperClass: 'flex shrink-0' }}>
		<div class="flex flex-col pl-1 leading-tight">
			<span class="vp-tc whitespace-nowrap text-sm text-fg">{secs(ready.range[0])} → {secs(ready.range[1])}</span>
			<span class="flex items-center gap-1 whitespace-nowrap text-xs text-fg-subtle">
				{t('production.count.shots', { count: clips.length })} · {t('production.count.prompts', { count: it.prompts.length })}
				{#if conflicts.length}
					<HostUi name="Tooltip" props={{ text: conflicts.map((c) => c.text).join(' · ') }}>
						<button type="button" class="ml-0.5 flex min-h-6 items-center gap-0.5 text-warning hover:underline" aria-label={t('production.conflicts', { count: conflicts.length })} onclick={directionIssues}>
							<Icon name="alert" class="h-3 w-3" />{conflicts.length}
						</button>
					</HostUi>
				{/if}
			</span>
		</div>
	</HostUi>

	<div class="vp-divider"></div>

	<HostUi name="Tooltip" props={{ text: p.quality === 'draft' ? t('production.quality.draftTip', { resolution: draftRes }) : t('production.quality.finalTip', { resolution: finalRes }) }}>
		<HostUi name="SegmentedControl" props={{ items: qualities, selected: p.quality, variant: 'toggle', ariaLabel: t('production.quality.label'), onSelect: setProjectQuality }} />
	</HostUi>
	{#if p.mode !== 'render3d'}<DraftsField {clips} label={false} disabled={busy || !clips.length} />{/if}
	<select class="vp-popup" bind:value={ui.production.mode} disabled={busy} aria-label={t('production.mode.label')}>
		{#each PRODUCTION_MODES as m (m)}<option value={m}>{modeLabel(m)}</option>{/each}
	</select>

	<div class="vp-divider"></div>

	<div class="flex min-w-0 flex-1 items-center gap-2" role="group" aria-label={t('production.engine.group')} bind:clientWidth={room} data-vp-engine>
		{#if fit.inline.has('engine')}<span class="inline-flex shrink-0" bind:offsetWidth={widths.engine}>{@render engineSelect(false)}</span>{/if}
		{#if fit.inline.has('profile')}<span class="inline-flex shrink-0" bind:offsetWidth={widths.profile}>{@render profilePicker()}</span>{/if}
		{#if fit.inline.has('margin')}<span class="inline-flex shrink-0" bind:offsetWidth={widths.margin}>{@render marginField()}</span>{/if}
		{#if fit.inline.has('own')}<span class="inline-flex shrink-0" bind:offsetWidth={widths.own}>{@render ownShots()}</span>{/if}
		<HostUi name="Tooltip" props={{ text: editTip, kbd: commandById('engine')?.key, wrapperClass: 'inline-flex shrink-0' }}>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: hostIconName('sliders'), class: 'h-7 px-2', ariaLabel: t('production.editEngine'), onclick: () => openEngineSettings(engine?.preset) }}>
				{#if fit.inline.has('label')}<span bind:offsetWidth={widths.label} class="inline-flex items-center gap-1.5 whitespace-nowrap">{t('production.editEngine')}{#if setCount}<span class="vp-tc rounded-sm bg-surface-3 px-1 text-2xs text-fg-muted">{setCount}</span>{/if}</span>{/if}
			</HostUi>
		</HostUi>
		{#if fit.overflow.length}
			<div class="relative shrink-0" data-vp-menu>
				<HostUi name="IconButton" props={{ icon: hostIconName('dots'), label: t('production.more'), tooltip: t('production.more'), size: 'sm', class: 'vp-h7', ariaExpanded: moreOpen, onclick: () => (ui.menuOpen = moreOpen ? null : MORE) }} />
				{#if moreOpen}
					<div class="vp-menu left-0 top-8 w-72" role="dialog" aria-label={t('production.more')} use:overlayLayer in:fly={{ y: -4, duration: ms(120) }}>
						<div class="space-y-3 p-2">
							{#if fit.overflow.includes('engine')}<div class="space-y-1"><span class="vp-label block">{t('production.engine.label')}</span>{@render engineSelect(true)}</div>{/if}
							{#if fit.overflow.includes('profile')}<div class="space-y-1"><span class="vp-label block">{t('production.profile.label')}</span>{@render profilePicker()}</div>{/if}
							{#if fit.overflow.includes('margin')}<div class="space-y-1"><span class="vp-label block">{t('production.margin.label')}</span>{@render marginField()}</div>{/if}
							{#if fit.overflow.includes('own')}{@render ownShots()}{/if}
						</div>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<HostUi name="IconButton" props={{ icon: hostIconName('list'), label: t('production.queueLabel'), tooltip: queueTip, kbd: commandById('queue')?.key, size: 'sm', class: 'vp-h7', onclick: openQueue }} />

	<div class="sr-only" aria-live="polite">{spoken}</div>
	<div class="flex min-w-0 items-center gap-2">
		{#if busy}
			<div class="w-44" in:fade={{ duration: ms(120) }}>
				<div class="flex justify-between gap-2 text-xs">
					<span class="truncate text-signal">{p.step}</span>
					<span class="vp-tc text-fg-muted">{t('exports.percent', { value: Math.round(p.progress) })}</span>
				</div>
				<div class="mt-1 h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('production.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={p.running ? Math.round(p.progress) : undefined}>
					<div class="h-full rounded-full bg-signal transition-[width] duration-150" style:width="{p.progress}%"></div>
				</div>
			</div>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: cancelGeneration }}>{t('production.cancel')}</HostUi>
		{:else}
			{#if status === 'done'}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: openResults }}>
					<Icon name="check" class="h-3.5 w-3.5 text-success" />{t('production.ready', { count: p.lastCount })}
				</HostUi>
			{/if}
			{#if notes.length}
				<InfoTip lines={notes} wrapperClass="flex min-w-3.5">
					<span class="vp-notice text-xs text-warning"><Icon name="alert" class="h-3.5 w-3.5 shrink-0" /><span class="vp-notice-text">{notes[0]}</span></span>
				</InfoTip>
			{/if}
			{#if gapClip}<SeamAction clip={gapClip} variant="icon" />{/if}
			{#if ready.noEngine && ui.isAdmin}
				<a class="vp-link-hit shrink-0 whitespace-nowrap text-xs text-fg underline decoration-signal underline-offset-2 hover:decoration-2" href="/admin?tab=plugins">{t('generation.engine.settings')}</a>
			{/if}
			{#if !ready.noEngine && p.mode !== 'render3d'}
				<InfoTip lines={estLines} wrapperClass="inline-flex shrink-0 items-center">
					<span class="flex items-center gap-1.5 whitespace-nowrap text-xs transition-opacity {over ? 'text-warning' : 'text-fg-muted'} {estimateState.loading ? 'opacity-60' : ''}">
						<Icon name={over ? 'alert' : 'history'} class="h-3.5 w-3.5" />
						<span class="vp-tc">{timeText}</span>
						{#if !cloud}
							<span class="text-fg-subtle">·</span>
							<span class="vp-tc">{vramText}</span>
						{/if}
						{#if showCost || showQuota}
							<span class="vp-cost text-fg-subtle">·</span>
							<span class="vp-tc vp-cost">{showCost ? money(est.cost.totalUsd) : t('production.estimate.quotaShort', { value: minutes(quota.neededMinutes) })}</span>
						{/if}
					</span>
				</InfoTip>
			{/if}
			<HostUi name="Tooltip" props={{ text: primary, kbd: commandById('generate')?.key }}>
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'sparkles', class: 'h-8 px-3.5', disabled: blocked, onclick: () => startGeneration() }}>{primary}</HostUi>
			</HostUi>
		{/if}
	</div>
</div>

{#snippet engineSelect(wide)}
	<HostUi name="Tooltip" props={{ text: engineTip, wrapperClass: wide ? 'flex w-full' : 'inline-flex min-w-0 items-center' }}>
		<select class="vp-popup {wide ? 'w-full' : 'max-w-48'}" value={engine?.key ?? ''} disabled={!groups.length} aria-label={t('production.engine.label')} onchange={(e) => selectEngine(e.currentTarget.value)}>
			{#if !engine}<option value="" disabled>{groups.length ? engineLabel() : t('generation.engine.none')}</option>{/if}
			{#each groups as g (g.label)}
				<optgroup label={g.label}>
					{#each g.options as o (o.key)}<option value={o.key}>{o.label}</option>{/each}
				</optgroup>
			{/each}
		</select>
	</HostUi>
{/snippet}

{#snippet profilePicker()}
	<HostUi name="Tooltip" props={{ text: profileHint(doc.direction.mode), wrapperClass: 'inline-flex' }}>
		<HostUi name="SegmentedControl" props={{ items: profileItems, selected: doc.direction.mode, variant: 'toggle', ariaLabel: t('production.profile.label'), onSelect: setProfile }} />
	</HostUi>
{/snippet}

{#snippet marginField()}
	<HostUi name="Tooltip" props={{ text: t('production.margin.tip'), wrapperClass: 'inline-flex' }}>
		<label class="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-fg-muted">
			<span>{t('production.margin.short')}</span>
			<input class="input vp-dense vp-tc w-14" type="number" min="0" max={MAX_MARGIN} step="0.5" value={referenceMargin(doc.engine)} aria-label={t('production.margin.label')} onchange={(e) => setMargin(e.currentTarget.value)} />
			<span>{t('production.margin.unit')}</span>
		</label>
	</HostUi>
{/snippet}

{#snippet ownShots()}
	<HostUi name="Tooltip" props={{ text: t('production.own.tip'), wrapperClass: 'inline-flex' }}>
		<span class="inline-flex min-h-6 items-center gap-1 whitespace-nowrap text-xs text-fg-muted"><Icon name="sliders" class="h-3 w-3" />{t('production.own', { count: own })}</span>
	</HostUi>
{/snippet}

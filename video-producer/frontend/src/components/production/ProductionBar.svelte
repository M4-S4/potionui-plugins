<script>
	import { untrack } from 'svelte';
	import { fade, fly } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, act, secs, allIssues, fmtDuration, openDirector, pickedClips, clearPicked } from '../../lib/state.svelte.js';
	import {
		readiness,
		startGeneration,
		cancelGeneration,
		QUEUE_MENU,
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
	import { aspectOf, draftResolution, finalResolution } from '../../lib/generation.js';
	import { chosenSize } from '../../lib/formats.js';
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
	import SizePicker from './SizePicker.svelte';
	import { setEngineSize } from '../../lib/framing.svelte.js';
	import QueuePanel from '../panels/QueuePanel.svelte';
	import { takeCount } from '../../lib/shots.js';
	import { shotNumbers } from '../../lib/director.js';
	import { flyingTakes } from '../../lib/takes.svelte.js';
	import { withSendings } from '../../lib/vreftracks.svelte.js';

	const p = $derived(ui.production);
	const ready = $derived(readiness());
	const it = $derived(ready.items);
	const est = $derived(ready.est);
	const clips = $derived(jobClips(ready.range));
	const engine = $derived(currentEngine());
	const groups = $derived(engineGroups());
	const cloud = $derived(engine?.kind === 'cloud');
	const aspect = $derived(aspectOf(doc.aspect, doc.resolution));
	const draftRes = $derived(draftResolution(engine?.info, ui.me?.settings?.draftResolution, aspect, chosenSize(doc, engine?.preset, 'draft'))?.replace('x', '×') ?? '—');
	const finalRes = $derived(finalResolution(engine?.info, aspect, chosenSize(doc, engine?.preset, 'final'))?.replace('x', '×') ?? '—');
	const conflicts = $derived(allIssues().filter((i) => i.level !== 'missing' && it.prompts.includes(i.prompt)));
	const status = $derived(p.state === 'running' ? 'running' : p.state === 'done' ? 'done' : ready.missing.length ? 'missing' : 'ready');
	const busy = $derived(status === 'running');
	const blocked = $derived(ready.missing.length > 0);
	const notes = $derived(blocked ? [...ready.missing, ...ready.warnings] : ready.warnings);
	const gapClip = $derived(blocked ? null : (ready.gaps.map((id) => doc.clips.find((c) => c.id === id)).find((c) => c && doc.clips.indexOf(c) > 0) ?? null));
	const picked = $derived(pickedClips().length);
	const byShots = $derived(ui.workspace === 'director' && (picked > 0 || p.target === 'clip'));
	const span = $derived.by(() => {
		if (!byShots) return `${secs(ready.range[0])} → ${secs(ready.range[1])}`;
		const numbers = shotNumbers(doc, clips);
		if (!clips.length) return t('production.scope.none');
		if (clips.length === 1) return t('production.scope.shot', { number: numbers.list });
		return numbers.more ? t('production.scope.shotsMore', numbers) : t('production.scope.shots', numbers);
	});
	const primary = $derived(busy ? t('production.enqueue') : t('production.generate'));
	const primaryTip = $derived(busy ? t('production.enqueueTip') : t('production.generate'));
	const targets = $derived([
		{ id: 'clip', label: t('production.target.clip') },
		{ id: 'range', label: t('production.target.range') },
		{ id: 'sequence', label: t('production.target.sequence') },
		...(picked ? [{ id: 'picked', label: t('production.target.picked', { count: picked }) }] : [])
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
			t('production.count.references', { count: it.references.length })
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
	const supported = $derived(profileItems.some((m) => m.id === doc.direction.mode));
	const showProfile = $derived(profileItems.length > 1 || !supported);
	const guided = $derived(soundGuides());
	const own = $derived(doc.clips.filter(hasOwnEngine).length);
	const setCount = $derived(optionCount(doc.engine, engine?.preset));
	const editTip = $derived(engine ? t('production.editEngineTip', { engine: engine.label }) : t('production.editEngine'));
	const MORE = 'engine-more';
	const ENGINE_MIN = 112;
	const ENGINE_WIDE = 192;
	const GIVES = ['go', 'scope', 'notice'];
	let widths = $state({ profile: 220, compact: 96, margin: 128, own: 64, label: 88, go: 128, scope: 104, notice: 160 });
	let space = $state({ room: 0, go: 0, scope: 0, notice: 0 });
	const watched = new Map();
	let observer = null;

	function measure() {
		const size = (key, read) => (watched.get(key)?.isConnected ? read(watched.get(key)) : 0);
		space = { room: size('room', (el) => el.clientWidth), ...Object.fromEntries(GIVES.map((key) => [key, size(key, (el) => el.offsetWidth)])) };
	}

	function watch(node, key) {
		observer ??= new ResizeObserver(measure);
		watched.set(key, node);
		observer.observe(node);
		return {
			destroy() {
				observer.unobserve(node);
				if (watched.get(key) === node) watched.delete(key);
			}
		};
	}

	const fit = $derived(
		fitInline(space.room + space.go + space.scope + space.notice, [
			{ id: 'engine', width: ENGINE_WIDE, min: ENGINE_MIN, rank: 3, keep: true },
			{ id: 'profile', width: widths.profile, min: widths.compact, rank: 4, keep: true, show: showProfile },
			{ id: 'margin', width: widths.margin, rank: 6, show: guided },
			{ id: 'own', width: widths.own, rank: 7, show: own > 0 },
			{ id: 'edit', width: 28, rank: 0, pinned: true },
			{ id: 'label', width: widths.label, rank: 8, folds: false },
			{ id: 'go', width: widths.go, rank: 1, outside: true },
			{ id: 'scope', width: widths.scope, rank: 2, outside: true },
			{ id: 'notice', width: widths.notice, rank: 5, outside: true, show: notes.length > 0 }
		])
	);
	const moreOpen = $derived(ui.menuOpen === MORE && fit.overflow.length > 0);
	const queueOpen = $derived(ui.menuOpen === QUEUE_MENU);

	$effect(() => {
		for (const key of GIVES) if (space[key] > 0) widths[key] = space[key];
	});

	$effect(() => () => observer?.disconnect());

	function profileHint(m) {
		if (m === 'FL2VA') return t('production.profile.fl2va');
		if (m === 'Ref2VA') return t('production.profile.ref2va');
		return t('production.profile.hybrid');
	}

	function setProfile(m) {
		if (m !== doc.direction.mode) withSendings(() => act(() => (doc.direction.mode = m)));
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
		if (id === 'picked') return;
		clearPicked();
		p.target = id;
		if (id === 'range' && !ui.range) ui.range = { in: ready.range[0], out: ready.range[1] };
	}

	function directionIssues() {
		openDirector('direction');
	}
</script>

<div class="flex h-11 items-center gap-2 border-b border-line bg-surface-1 px-3" role="region" aria-label={t('production.region')}>
	<HostUi name="SegmentedControl" props={{ items: targets, selected: picked ? 'picked' : p.target, variant: 'toggle', ariaLabel: t('production.target.label'), onSelect: pick }} />
	<span class="flex shrink-0" use:watch={'scope'}>
		{#if fit.inline.has('scope')}
			<HostUi name="Tooltip" props={{ text: scope, wrapperClass: 'flex shrink-0' }}>
				<div class="flex flex-col pl-1 leading-tight">
					<span class="{byShots ? '' : 'vp-tc '}whitespace-nowrap text-sm text-fg">{span}</span>
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
		{/if}
	</span>

	<div class="vp-divider"></div>

	<HostUi name="Tooltip" props={{ text: p.quality === 'draft' ? t('production.quality.draftTip', { resolution: draftRes }) : t('production.quality.finalTip', { resolution: finalRes }) }}>
		<HostUi name="SegmentedControl" props={{ items: qualities, selected: p.quality, variant: 'toggle', ariaLabel: t('production.quality.label'), onSelect: setProjectQuality }} />
	</HostUi>
	{#if engine && !cloud && engine.info?.resolutions?.length}
		<SizePicker preset={engine.info} quality={p.quality} backend={engine.backend} value={chosenSize(doc, engine.preset, p.quality)} onselect={(v) => setEngineSize(engine.preset, p.quality, v)} variant="popup" />
	{/if}
	<DraftsField {clips} label={false} disabled={!clips.length} />

	<div class="vp-divider"></div>

	<div class="flex min-w-0 flex-1 items-center gap-2" role="group" aria-label={t('production.engine.group')} use:watch={'room'} data-vp-engine>
		<span class="inline-flex min-w-28 max-w-48 shrink">{@render engineSelect()}</span>
		{#if fit.wide.has('profile')}
			<span class="inline-flex shrink-0" bind:offsetWidth={widths.profile}>{@render profilePicker()}</span>
		{:else if fit.inline.has('profile')}
			<span class="inline-flex shrink-0" bind:offsetWidth={widths.compact}>{@render profileSelect()}</span>
		{/if}
		{#if fit.inline.has('margin')}<span class="inline-flex shrink-0" bind:offsetWidth={widths.margin}>{@render marginField()}</span>{/if}
		{#if fit.inline.has('own')}<span class="inline-flex shrink-0" bind:offsetWidth={widths.own}>{@render ownShots()}</span>{/if}
		<HostUi name="Tooltip" props={{ text: editTip, kbd: commandById('engine')?.key, wrapperClass: 'inline-flex shrink-0' }}>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: hostIconName('sliders'), class: 'h-7 px-2', ariaLabel: t('production.editEngine'), onclick: () => openEngineSettings(engine?.preset) }}>
				{#if fit.inline.has('label')}<span bind:offsetWidth={widths.label} class="inline-flex items-center gap-1.5 whitespace-nowrap">{t('production.editEngine')}{#if setCount}<span class="vp-tc rounded-sm bg-surface-3 px-1 text-2xs text-fg-muted">{setCount}</span>{/if}</span>{/if}
			</HostUi>
		</HostUi>
		{#if fit.overflow.length}
			<div class="relative shrink-0" data-vp-menu>
				<HostUi name="IconButton" props={{ icon: 'more', label: t('production.more'), tooltip: t('production.more'), size: 'sm', class: 'vp-h7', ariaExpanded: moreOpen, onclick: () => (ui.menuOpen = moreOpen ? null : MORE) }} />
				{#if moreOpen}
					<div class="vp-menu left-0 top-8 w-72" role="dialog" aria-label={t('production.more')} use:overlayLayer in:fly={{ y: -4, duration: ms(120) }}>
						<div class="space-y-3 p-2">
							{#if fit.overflow.includes('margin')}<div class="space-y-1"><span class="vp-label block">{t('production.margin.label')}</span>{@render marginField()}</div>{/if}
							{#if fit.overflow.includes('own')}{@render ownShots()}{/if}
						</div>
					</div>
				{/if}
			</div>
		{/if}
	</div>

	<div class="relative shrink-0" data-vp-menu>
		<HostUi name="IconButton" props={{ icon: hostIconName('list'), label: t('production.queueLabel'), tooltip: queueTip, kbd: commandById('queue')?.key, size: 'sm', class: 'vp-h7', ariaExpanded: queueOpen, onclick: () => (ui.menuOpen = queueOpen ? null : QUEUE_MENU) }} />
		{#if queueOpen}
			<div class="vp-menu overflow-auto" style:right="0" style:bottom="2.25rem" style:width="22rem" style:max-height="60vh" role="dialog" aria-label={t('panels.queue.title')} use:overlayLayer in:fly={{ y: 4, duration: ms(120) }}>
				<QueuePanel />
			</div>
		{/if}
	</div>

	<div class="sr-only" aria-live="polite">{spoken}</div>
	<div class="flex shrink-0 items-center gap-2">
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
		{:else if status === 'done'}
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: openResults }}>
				<Icon name="check" class="h-3.5 w-3.5 text-success" />{t('production.ready', { count: p.lastCount })}
			</HostUi>
		{/if}
		{#if notes.length}
			<InfoTip lines={notes} wrapperClass="flex shrink-0">
				<span class="vp-notice text-xs text-warning"><Icon name="alert" class="h-3.5 w-3.5 shrink-0" /><span class="vp-notice-text" use:watch={'notice'}>{#if fit.inline.has('notice')}{notes[0]}{/if}</span></span>
			</InfoTip>
		{/if}
		{#if !busy}
			{#if gapClip}<SeamAction clip={gapClip} variant="icon" />{/if}
			{#if ready.noEngine && ui.isAdmin}
				<a class="vp-link-hit shrink-0 whitespace-nowrap text-xs text-fg underline decoration-signal underline-offset-2 hover:decoration-2" href="/admin?tab=plugins">{t('generation.engine.settings')}</a>
			{/if}
			{#if !ready.noEngine}
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
		{/if}
		<HostUi name="Tooltip" props={{ text: primaryTip, kbd: commandById('generate')?.key }}>
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'sparkles', class: 'h-8 px-3.5', ariaLabel: primary, disabled: blocked, onclick: () => startGeneration() }}>
				<span class="-ml-1.5 whitespace-nowrap" class:pl-1.5={fit.inline.has('go')} use:watch={'go'} data-generate={busy ? 'enqueue' : 'start'}>{#if fit.inline.has('go')}{primary}{/if}</span>
			</HostUi>
		</HostUi>
	</div>
</div>

{#snippet engineSelect()}
	<HostUi name="Tooltip" props={{ text: engineTip, wrapperClass: 'flex w-full min-w-0 items-center' }}>
		<select class="vp-popup w-full min-w-0" value={engine?.key ?? ''} disabled={!groups.length} aria-label={t('production.engine.label')} onchange={(e) => selectEngine(e.currentTarget.value)}>
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

{#snippet profileSelect()}
	<HostUi name="Tooltip" props={{ text: profileHint(doc.direction.mode), wrapperClass: 'inline-flex' }}>
		<select class="vp-popup" value={doc.direction.mode} aria-label={t('production.profile.label')} onchange={(e) => setProfile(e.currentTarget.value)}>
			{#if !supported}<option value={doc.direction.mode} disabled>{doc.direction.mode}</option>{/if}
			{#each profileItems as m (m.id)}<option value={m.id}>{m.label}</option>{/each}
		</select>
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

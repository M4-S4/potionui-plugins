<script>
	import { untrack } from 'svelte';
	import { fly } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, act, secs, allIssues, fmtDuration, openDirector, pickedClips, clearPicked, clipLabel } from '../../lib/state.svelte.js';
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
	import { optionCount } from '../../lib/options.js';
	import { MAX_MARGIN, referenceMargin, setReferenceMargin } from '../../lib/sound.js';
	import { announcer } from '../../lib/announce.js';
	import { overlayLayer } from '../../lib/host.js';
	import { clipThumb, takeThumb } from '../../lib/media.js';
	import { deckCell, deckChip, deckDetail, deckEyebrow, deckState, deckTitle, deckTone, remainingSeconds } from '../../lib/deck.js';
	import Icon from '../Icon.svelte';
	import InfoTip from '../shell/InfoTip.svelte';
	import SeamAction from '../takes/SeamAction.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import SizePicker from './SizePicker.svelte';
	import { setEngineSize } from '../../lib/framing.svelte.js';
	import QueuePanel from '../panels/QueuePanel.svelte';
	import { sharedDrafts, takeCount } from '../../lib/shots.js';
	import { shotNumbers } from '../../lib/director.js';
	import { flyingTakes, takeStore } from '../../lib/takes.svelte.js';
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
	const state = $derived(deckState({ state: p.state, missing: ready.missing }));
	const tone = $derived(deckTone(state));
	const busy = $derived(state === 'running');
	const blocked = $derived(ready.missing.length > 0);
	const notes = $derived(blocked ? [...ready.missing, ...ready.warnings] : ready.warnings);
	const gapClip = $derived(blocked ? null : (ready.gaps.map((id) => doc.clips.find((c) => c.id === id)).find((c) => c && doc.clips.indexOf(c) > 0) ?? null));
	const picked = $derived(pickedClips().length);
	const target = $derived(picked ? 'picked' : p.target);
	const numbers = $derived(shotNumbers(doc, clips));
	const rangeText = $derived(`${secs(ready.range[0])} → ${secs(ready.range[1])}`);
	const durationText = $derived(secs(clips.reduce((sum, c) => sum + c.dur, 0)));
	const eyebrow = $derived(deckEyebrow({ target, clips: clips.length, shots: numbers, label: clips.length === 1 ? clipLabel(clips[0]) : '', rangeText, durationText }, t));
	const flying = $derived(flyingTakes());
	const runningTake = $derived(flying.find((x) => x.status === 'running') ?? null);
	const shotNumber = (take) => {
		const index = doc.clips.findIndex((c) => c.id === take.shotId);
		return index < 0 ? '' : String(index + 1).padStart(2, '0');
	};
	const current = $derived(runningTake ? { variant: runningTake.variant, shot: shotNumber(runningTake) } : null);
	const percent = $derived(Math.round(p.progress));
	const title = $derived(deckTitle({ state, clips: clips.length, current, percent, lastCount: p.lastCount, failed: p.failed, failedVariant: p.failedVariant }, t));
	const counts = $derived(
		[
			t('production.count.prompts', { count: it.prompts.length }),
			t('production.count.frames', { count: it.frames.length }),
			t('production.count.references', { count: it.references.length }),
			t('production.count.takes', { count: takeCount(clips, doc.engine) })
		]
			.filter(Boolean)
			.join(' · ')
	);
	const detail = $derived(deckDetail({ state, counts, missing: ready.missing, warnings: ready.warnings, conflicts: conflicts.length, step: p.step, queued: flying.length - p.running }, t));
	const lastTake = $derived([...takeStore.list].filter((x) => x.status === 'done').sort((a, b) => String(b.createdAt ?? '').localeCompare(String(a.createdAt ?? '')))[0] ?? null);
	const thumb = $derived.by(() => {
		const clip = clips[0];
		const own = clip ? clipThumb(clip) : null;
		if (own) return { src: own, corner: secs(clip.dur) };
		const last = lastTake ? takeThumb(lastTake) : null;
		if (last) return { src: last, corner: lastTake.variant };
		return null;
	});
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
		if (showCost || showQuota) lines.push(showCost ? money(est.cost.totalUsd) : t('production.estimate.quotaShort', { value: minutes(quota.neededMinutes) }));
		return [...lines, ...ready.notes, ...notes];
	});
	const over = $derived(Boolean(vram?.streams || quota?.blocks));
	let now = $state(Date.now());
	const elapsed = $derived(busy && p.startedAt ? Math.max(0, (now - p.startedAt) / 1000) : null);
	const cell = $derived(deckCell({ state, timeText, vramText, cloud, over, elapsed, remaining: remainingSeconds(elapsed, p.progress), lastSeconds: p.lastSeconds, noEngine: ready.noEngine }, t, fmtDuration));
	const cellLines = $derived(busy ? [p.step || t('generation.state.running')] : estLines);
	const queued = $derived(flying.length);
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
	const sizes = $derived(Boolean(engine && !cloud && engine.info?.resolutions?.length));
	const chip = $derived(deckChip({ engine: engine ? engine.label : groups.length ? engineLabel() : t('generation.engine.none'), profile: showProfile ? doc.direction.mode : '', size: sizes ? (p.quality === 'draft' ? draftRes : finalRes) : '', drafts: clips.length ? sharedDrafts(clips, doc.engine) : 1 }, t));
	const chipTip = $derived([engineTip, showProfile ? profileHint(doc.direction.mode) : '', t('production.deck.chipTip')].filter(Boolean).join(' · '));
	const MORE = 'engine-more';
	let held = $state(false);
	let nested = false;
	const moreOpen = $derived(held && (ui.menuOpen === MORE || String(ui.menuOpen ?? '').startsWith('picker:')));
	const queueOpen = $derived(ui.menuOpen === QUEUE_MENU);
	const primaryTip = $derived(busy ? t('production.deck.cancel') : t('production.generate'));

	$effect(() => {
		const open = ui.menuOpen;
		untrack(() => {
			if (open === MORE) held = true;
			else if (open === null && held && nested) ui.menuOpen = MORE;
			else if (!String(open ?? '').startsWith('picker:')) held = false;
			nested = held && String(open ?? '').startsWith('picker:');
		});
	});

	$effect(() => {
		if (!busy) return;
		now = Date.now();
		const timer = setInterval(() => (now = Date.now()), 1000);
		return () => clearInterval(timer);
	});

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

	function toggleMore() {
		ui.menuOpen = moreOpen ? null : MORE;
	}
</script>

<div class="vp-deck" role="region" aria-label={t('production.region')} data-state={state}>
	{#if busy}
		<div class="vp-deck-progress-track" role="progressbar" aria-label={t('production.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={p.running ? percent : undefined}>
			<div class="vp-deck-progress-fill" class:is-indeterminate={!p.running} style:width="{p.running ? p.progress : 0}%"></div>
		</div>
	{/if}
	<div class="vp-deck-grid">
		<section class="vp-deck-status">
			<div class="vp-deck-thumb">
				{#if thumb}
					<img src={thumb.src} alt="" />
					<span class="vp-deck-clock">{thumb.corner}</span>
				{:else}
					<Icon name="film" class="h-[18px] w-[18px]" />
				{/if}
			</div>
			<div class="vp-deck-copy">
				<span class="vp-deck-eyebrow">{eyebrow}</span>
				<div class="vp-deck-title-line">
					<span class="vp-deck-dot is-{tone}"></span>
					<span class="vp-deck-title" aria-live="polite">{title}</span>
				</div>
				<div class="vp-deck-detail">
					{#if detail.text}
						<InfoTip lines={notes.length ? notes : [detail.text]} wrapperClass="flex min-w-0">
							<span class="vp-deck-detail-text" class:text-warning={detail.warn}>{detail.text}</span>
						</InfoTip>
					{/if}
					{#if detail.actions.includes('conflicts')}
						<HostUi name="Tooltip" props={{ text: conflicts.map((c) => c.text).join(' · ') }}>
							<button type="button" class="vp-deck-inline-action text-warning" onclick={directionIssues}>
								<Icon name="alert" class="h-3 w-3" />{t('production.conflicts', { count: conflicts.length })}
							</button>
						</HostUi>
					{/if}
					{#if detail.actions.includes('enqueue')}
						<HostUi name="Tooltip" props={{ text: t('production.enqueueTip'), kbd: commandById('generate')?.key }}>
							<button type="button" class="vp-deck-inline-action" disabled={blocked} onclick={() => startGeneration()}>
								{t('production.enqueue')}<kbd class="vp-kbd vp-tc text-2xs text-fg-muted">{commandById('generate')?.key ?? ''}</kbd>
							</button>
						</HostUi>
					{/if}
					{#if detail.actions.includes('results')}
						<button type="button" class="vp-deck-inline-action" onclick={openResults}>{t('production.deck.results')}</button>
					{/if}
					{#if !busy && gapClip}<SeamAction clip={gapClip} variant="icon" />{/if}
					{#if !busy && ready.noEngine && ui.isAdmin}
						<a class="vp-link-hit shrink-0 whitespace-nowrap text-xs text-fg underline decoration-signal underline-offset-2 hover:decoration-2" href="/admin?tab=plugins">{t('generation.engine.settings')}</a>
					{/if}
				</div>
			</div>
		</section>

		<section class="vp-deck-run">
			<HostUi name="SegmentedControl" props={{ items: targets, selected: target, variant: 'toggle', ariaLabel: t('production.target.label'), onSelect: pick }} />
			<HostUi name="Tooltip" props={{ text: primaryTip, kbd: busy ? undefined : commandById('generate')?.key, wrapperClass: 'inline-flex' }}>
				<button type="button" class="vp-deck-generate" class:is-cancel={busy} disabled={blocked && !busy} aria-label={primaryTip} data-generate={busy ? 'cancel' : 'start'} onclick={() => (busy ? cancelGeneration() : startGeneration())}>
					<svg class="vp-deck-mark" viewBox="0 0 48 48" fill="none" aria-hidden="true">
						{#if busy}
							<path fill="currentColor" fill-rule="evenodd" d="M24 15.5a8.5 8.5 0 100 17 8.5 8.5 0 000-17zM24 26.21 20.51 29.70 18.30 27.49 21.79 24 18.30 20.51 20.51 18.30 24 21.79 27.49 18.30 29.70 20.51 26.21 24 29.70 27.49 27.49 29.70z" />
						{:else}
							<path fill="currentColor" fill-rule="evenodd" d="M24 15.5a8.5 8.5 0 100 17 8.5 8.5 0 000-17zm-3.4 3.1 9.4 5.4-9.4 5.4z" />
						{/if}
						<g class="vp-deck-mark-orbit">
							<g fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
								<path d="M27.51 9.93 A14.5 14.5 0 0 1 37.94 28.0" />
								<path d="M34.43 34.07 A14.5 14.5 0 0 1 13.57 34.07" />
								<path d="M10.06 28.0 A14.5 14.5 0 0 1 20.49 9.93" />
							</g>
							<g fill="currentColor">
								<circle cx="24" cy="6" r="1.7" />
								<circle cx="39.6" cy="33" r="1.7" />
								<circle cx="8.4" cy="33" r="1.7" />
							</g>
						</g>
					</svg>
				</button>
			</HostUi>
			<HostUi name="Tooltip" props={{ text: p.quality === 'draft' ? t('production.quality.draftTip', { resolution: draftRes }) : t('production.quality.finalTip', { resolution: finalRes }) }}>
				<HostUi name="SegmentedControl" props={{ items: qualities, selected: p.quality, variant: 'toggle', ariaLabel: t('production.quality.label'), onSelect: setProjectQuality }} />
			</HostUi>
		</section>

		<section class="vp-deck-utility">
			<div class="sr-only" aria-live="polite">{spoken}</div>
			<InfoTip lines={cellLines} wrapperClass="vp-deck-timing">
				<span class="vp-deck-cell-label">{cell.label}</span>
				<span class="vp-deck-cell-value {cell.warn ? 'text-warning' : ''} {estimateState.loading && !busy ? 'opacity-60' : ''}">
					{cell.value}{#if cell.sub}<span class="vp-deck-cell-sub" class:text-warning={cell.warn}> · {cell.sub}</span>{/if}
				</span>
			</InfoTip>
			<div class="relative flex min-w-0 items-center gap-1" data-vp-menu>
				<HostUi name="Tooltip" props={{ text: chipTip, wrapperClass: 'flex min-w-0' }}>
					<button type="button" class="vp-deck-chip" aria-expanded={moreOpen} aria-haspopup="dialog" onclick={toggleMore}>
						<Icon name="sliders" class="h-4 w-4 shrink-0" />
						<span class="vp-deck-chip-text">{#each chip as part, i (i)}{#if i}<span class="vp-deck-chip-dot"> · </span>{/if}<span class={i === 0 ? 'vp-deck-chip-engine' : ''}>{part}</span>{/each}</span>
						{#if setCount}<span class="vp-deck-badge vp-tc">{setCount}</span>{/if}
					</button>
				</HostUi>
				<div class="relative shrink-0" data-vp-menu>
					<HostUi name="Tooltip" props={{ text: queueTip, kbd: commandById('queue')?.key, wrapperClass: 'inline-flex' }}>
						<button type="button" class="vp-deck-icon-button" aria-label={t('production.queueLabel')} aria-expanded={queueOpen} aria-haspopup="dialog" onclick={() => (ui.menuOpen = queueOpen ? null : QUEUE_MENU)}>
							<Icon name="list" class="h-[18px] w-[18px]" />
							{#if queued}<span class="vp-deck-queue-count">{queued}</span>{/if}
						</button>
					</HostUi>
					{#if queueOpen}
						<div class="vp-menu overflow-auto" style:right="0" style:bottom="2.75rem" style:width="22rem" style:max-height="60vh" role="dialog" aria-label={t('panels.queue.title')} use:overlayLayer in:fly={{ y: 4, duration: ms(120) }}>
							<QueuePanel />
						</div>
					{/if}
				</div>
				<HostUi name="Tooltip" props={{ text: t('production.more'), wrapperClass: 'inline-flex' }}>
					<button type="button" class="vp-deck-icon-button" aria-label={t('production.more')} aria-expanded={moreOpen} aria-haspopup="dialog" onclick={toggleMore}>
						<Icon name="more" class="h-[18px] w-[18px]" />
					</button>
				</HostUi>
				{#if moreOpen}
					<div class="vp-menu" style:right="0" style:bottom="2.75rem" style:width="22rem" role="dialog" aria-label={t('production.more')} use:overlayLayer in:fly={{ y: 4, duration: ms(120) }}>
						<div class="space-y-3 p-2">
							<div class="space-y-1"><span class="vp-label block">{t('production.engine.label')}</span>{@render engineSelect()}</div>
							{#if showProfile}<div class="space-y-1"><span class="vp-label block">{t('production.profile.label')}</span>{@render profilePicker()}</div>{/if}
							{#if sizes}
								<div class="space-y-1">
									<span class="vp-label block">{p.quality === 'draft' ? t('production.size.draftLabel', { engine: engine.label }) : t('production.size.finalLabel', { engine: engine.label })}</span>
									<SizePicker preset={engine.info} quality={p.quality} backend={engine.backend} value={chosenSize(doc, engine.preset, p.quality)} onselect={(v) => setEngineSize(engine.preset, p.quality, v)} variant="popup" />
								</div>
							{/if}
							<div class="space-y-1"><span class="vp-label block">{t('generation.drafts.label')}</span><DraftsField {clips} label={false} disabled={!clips.length} /></div>
							{#if guided}<div class="space-y-1"><span class="vp-label block">{t('production.margin.label')}</span>{@render marginField()}</div>{/if}
							{#if own > 0}{@render ownShots()}{/if}
							<div class="vp-menu-sep"></div>
							<HostUi name="Tooltip" props={{ text: editTip, kbd: commandById('engine')?.key, wrapperClass: 'flex' }}>
								<button type="button" role="menuitem" onclick={() => openEngineSettings(engine?.preset)}>
									<Icon name="sliders" class="h-3.5 w-3.5" />{t('production.editEngine')}{#if setCount}<span class="vp-deck-badge vp-tc">{setCount}</span>{/if}
								</button>
							</HostUi>
							<button type="button" role="menuitem" onclick={openResults}><Icon name="layers" class="h-3.5 w-3.5" />{t('production.deck.results')}</button>
						</div>
					</div>
				{/if}
			</div>
		</section>
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

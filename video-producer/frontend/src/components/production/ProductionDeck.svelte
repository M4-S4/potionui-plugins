<script>
	import { untrack } from 'svelte';
	import { fly } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, secs, allIssues, fmtDuration, openDirector, pickedClips, clearPicked, clipLabel } from '../../lib/state.svelte.js';
	import {
		readiness,
		startGeneration,
		cancelGeneration,
		QUEUE_MENU,
		openQueue,
		openResults,
		jobClips,
		currentEngine,
		engineGroups,
		engineLabel,
		setProjectQuality,
		supportedProfiles,
		backendName,
		estimateRequest,
		scheduleEstimate,
		estimateState,
		retryTake,
		showDetails,
		toggleCompare,
		tryAgain
	} from '../../lib/production.svelte.js';
	import { aspectOf, draftResolution, failureText, finalResolution, presetLabel } from '../../lib/generation.js';
	import { chosenSize } from '../../lib/formats.js';
	import { commandById } from '../../lib/commands.js';
	import { optionCount } from '../../lib/options.js';
	import { announcer } from '../../lib/announce.js';
	import { overlayLayer } from '../../lib/host.js';
	import { setReturnFocus } from '../../lib/focus.js';
	import { clipThumb, takeThumb } from '../../lib/media.js';
	import { DECK_MENU, deckActions, deckCell, deckChip, deckChipFolded, deckCompact, deckDetail, deckEyebrow, deckLine, deckState, deckTitle, deckTone, deckUnblock, deckUnblockLabel, latestDone, remainingSeconds, selectedEverywhere } from '../../lib/deck.js';
	import { anchoredPopover } from '../../lib/popover.js';
	import { drawerFocus } from '../../lib/drawer.js';
	import { fitChip, shortPresetName } from '../../lib/barfit.js';
	import { viewport } from '../../lib/viewport.svelte.js';
	import { profileControl, profileHint } from '../../lib/deck-drawer.js';
	import { openFinalPass } from '../../lib/finalpass.svelte.js';
	import Icon from '../Icon.svelte';
	import InfoTip from '../shell/InfoTip.svelte';
	import SeamAction from '../takes/SeamAction.svelte';
	import ProductionDrawer from './ProductionDrawer.svelte';
	import QueuePanel from '../panels/QueuePanel.svelte';
	import { sharedDrafts, takeCount, shotNumberAt } from '../../lib/shots.js';
	import { shotNumbers } from '../../lib/director.js';
	import { flyingTakes, takeById, takeStore } from '../../lib/takes.svelte.js';

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
	const lines = $derived(ready.missing.length ? ready.missing : ready.refused ? [ready.refused.text] : []);
	const state = $derived(deckState({ state: p.state, missing: lines }));
	const tone = $derived(deckTone(state));
	const busy = $derived(state === 'running');
	const blocked = $derived(ready.missing.length > 0);
	const notes = $derived(lines.length ? [...lines, ...ready.warnings] : ready.warnings);
	const noticeLabel = $derived(notes.length > 1 ? t('production.notices', { count: notes.length, text: notes[0] }) : (notes[0] ?? ''));
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
		return index < 0 ? '' : shotNumberAt(index);
	};
	const current = $derived(runningTake ? { variant: runningTake.variant, shot: shotNumber(runningTake) } : null);
	const percent = $derived(Math.round(runningTake ? Math.min(100, Math.max(0, runningTake.progress ?? 0)) : p.progress));
	const title = $derived(deckTitle({ state, clips: clips.length, current, percent, lastCount: p.lastCount, failed: p.failed, failedVariant: p.failedVariant }, t));
	const counts = $derived(
		[
			t('production.count.prompts', { count: it.prompts.length }),
			it.frames.length ? t('production.count.frames', { count: it.frames.length }) : '',
			it.references.length ? t('production.count.references', { count: it.references.length }) : '',
			t('production.count.takes', { count: takeCount(clips, doc.engine) })
		]
			.filter(Boolean)
			.join(' · ')
	);
	const failedTake = $derived(state === 'failed' ? takeById(p.failedTake) : null);
	const failure = $derived(failedTake ? failureText(failedTake, t) : '');
	const oom = $derived(failedTake?.errorCode === 'cuda_oom');
	const recent = $derived(latestDone(takeStore.list));
	const lastTake = $derived(recent[0] ?? null);
	const finalReady = $derived(selectedEverywhere(doc.clips, takeStore.list));
	const unblock = $derived(state === 'blocked' ? deckUnblock(ready.reasons[0] ?? ready.refused?.reason) : null);
	const detail = $derived(
		deckDetail(
			{
				state,
				counts,
				missing: lines,
				warnings: ready.warnings,
				conflicts: conflicts.length,
				step: p.step,
				queued: flying.length - p.running,
				unblock: Boolean(unblock),
				failure,
				retry: Boolean(failedTake),
				details: Boolean(failedTake?.generationId),
				compare: recent.length >= 2,
				finalPass: finalReady
			},
			t
		)
	);
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
		return lines;
	});
	const estNotes = $derived([...ready.notes, ...notes]);
	const over = $derived(Boolean(vram?.streams || quota?.blocks));
	let now = $state(Date.now());
	const elapsed = $derived(busy && p.startedAt ? Math.max(0, (now - p.startedAt) / 1000) : null);
	const cell = $derived(deckCell({ state, timeText, vramText, cloud, over, oom, elapsed, remaining: remainingSeconds(elapsed, p.progress), lastSeconds: p.lastSeconds, noEngine: ready.noEngine }, t, fmtDuration));
	const cellLines = $derived(busy ? [p.step || t('generation.state.running'), ...estLines] : estLines);
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
	const showProfile = $derived(profileItems.length > 1 || profileControl({ items: profileItems, current: doc.direction.mode }) === 'popup');
	const setCount = $derived(optionCount(doc.engine, engine?.preset));
	const sizes = $derived(Boolean(engine && !cloud && engine.info?.resolutions?.length));
	const engineName = $derived(engine ? (cloud ? engine.label : presetLabel(engine.info)) : groups.length ? engineLabel() : t('generation.engine.none'));
	const engineShort = $derived(shortPresetName(engineName));
	const engineWords = $derived(engineShort.split(' ').filter(Boolean));
	const enginePrefixes = $derived(engineWords.slice(0, -1).map((_, i) => engineWords.slice(0, i + 1).join(' ')));
	const chipParts = $derived({ engine: engineName, short: engineShort, prefixes: enginePrefixes, profile: showProfile ? doc.direction.mode : '', size: sizes ? (p.quality === 'draft' ? draftRes : finalRes) : '', drafts: clips.length ? sharedDrafts(clips, doc.engine) : 1 });
	const chipFull = $derived(deckChip(chipParts, t));
	const draftsLabel = $derived(chipFull[chipFull.length - 1]);
	let fit = $state({ cell: true, engine: 'full', tier: 'full', cut: null });
	let compact = $state(false);
	const chip = $derived(deckChipFolded(chipParts, fit, t));
	const folded = $derived(chip.join(' · ') !== chipFull.join(' · '));
	const showCell = $derived(!compact && fit.cell);
	const cellText = $derived(showCell ? '' : `${cell.label} ${cell.value}${cell.sub ? ` · ${cell.sub}` : ''}`);
	const chipTip = $derived([engineTip, showProfile ? profileHint(doc.direction.mode, t) : '', cellText, t('production.deck.chipTip')].filter(Boolean).join(' · '));
	const line = $derived(deckLine({ compact, eyebrow, detail }));
	const actions = $derived(deckActions(detail.actions, compact));
	const CELL_PAD = 16;
	const CELL_GAP = 6;
	const MORE = DECK_MENU.more;
	const ESTIMATE = DECK_MENU.estimate;
	const moreOpen = $derived(ui.menuOpen === MORE);
	const estimateOpen = $derived(ui.menuOpen === ESTIMATE);
	const queueOpen = $derived(ui.menuOpen === QUEUE_MENU);
	const primaryTip = $derived(busy ? t('production.deck.cancel') : t('production.generate'));
	let deckEl = $state();
	let cellEl = $state();
	let chipEl = $state();
	let chipTextEl = $state();
	let groupEl = $state();
	let utilityEl = $state();
	let rulerEl = $state();

	$effect(() => {
		const narrow = viewport.compact;
		if (!deckEl) return;
		const centre = deckEl.closest('.vp-root')?.querySelector('main') ?? null;
		const read = () => {
			compact = deckCompact({ narrow, centre: centre ? centre.getBoundingClientRect().height : Infinity, deck: deckEl.getBoundingClientRect().height });
		};
		read();
		if (!centre) return;
		const resized = new ResizeObserver(read);
		resized.observe(centre);
		return () => resized.disconnect();
	});

	function measure() {
		if (!utilityEl || !rulerEl || !chipEl || !chipTextEl || !groupEl) return;
		const width = (rule) => rulerEl.querySelector(`[data-rule="${rule}"]`)?.getBoundingClientRect().width ?? 0;
		const chrome = chipEl.getBoundingClientRect().width - chipTextEl.getBoundingClientRect().width;
		const others = groupEl.getBoundingClientRect().width - chipEl.getBoundingClientRect().width;
		const cellWidth = compact ? 0 : Math.max(width('cell-label'), width('cell-value')) + CELL_PAD;
		fit = fitChip({
			room: utilityEl.getBoundingClientRect().width - others - chrome,
			engine: width('engine'),
			short: width('short'),
			prefixes: [...rulerEl.querySelectorAll('[data-rule="prefix"]')].map((el) => el.getBoundingClientRect().width),
			ellipsis: width('ellipsis'),
			sep: width('sep'),
			profile: width('profile'),
			size: width('size'),
			drafts: width('drafts'),
			cell: cellWidth,
			cellGap: CELL_GAP
		});
	}

	$effect(() => {
		if (!utilityEl || !rulerEl || !groupEl) return;
		compact;
		measure();
		const resized = new ResizeObserver(measure);
		const changed = new MutationObserver(measure);
		resized.observe(utilityEl);
		resized.observe(groupEl);
		resized.observe(rulerEl);
		changed.observe(rulerEl, { childList: true, subtree: true, characterData: true });
		return () => {
			resized.disconnect();
			changed.disconnect();
		};
	});

	$effect(() => {
		if (!busy) return;
		now = Date.now();
		const timer = setInterval(() => (now = Date.now()), 1000);
		return () => clearInterval(timer);
	});

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

	function toggleEstimate() {
		ui.menuOpen = estimateOpen ? null : ESTIMATE;
	}

	$effect(() => {
		if (!showCell && estimateOpen) ui.menuOpen = null;
	});

	function unblockNow() {
		if (!unblock) return;
		if (unblock.action === 'direction') return openDirector('direction');
		if (unblock.action === 'review') return openDirector('review');
		if (unblock.action === 'engine') return toggleDrawer();
		if (unblock.action === 'retry') return tryAgain();
		const id = unblock.shotId ?? clips[0]?.id ?? null;
		if (id) ui.modal = { type: 'shot', id };
	}

	function compareLast() {
		const [newer, older] = recent;
		if (!newer || !older) return;
		ui.compare = [older.id];
		toggleCompare(newer.id);
		openResults();
	}

	function toggleDrawer() {
		if (ui.deckDrawer) {
			ui.deckDrawer = false;
			return;
		}
		setReturnFocus(chipEl);
		ui.menuOpen = null;
		ui.deckDrawer = true;
	}

	function fromMore(run) {
		ui.menuOpen = null;
		run();
	}
</script>

<div bind:this={deckEl} class="vp-deck" class:is-compact={compact} role="region" aria-label={t('production.region')} data-state={state}>
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
				<span class="vp-deck-eyebrow" aria-hidden={compact}>{eyebrow}</span>
				<div class="vp-deck-title-line">
					<span class="vp-deck-dot is-{tone}"></span>
					<span class="vp-deck-title" aria-live="polite">{title}</span>
				</div>
				<div class="vp-deck-detail">
					{#if line}
						<InfoTip lines={notes.length ? notes : [line]} label={notes.length ? noticeLabel : ''} wrapperClass="flex min-w-0 items-center gap-1.5">
							{#if detail.warn}<Icon name="alert" class="h-3 w-3 shrink-0 text-warning" />{/if}<span class="vp-deck-detail-text" class:text-warning={detail.warn} class:is-whole={detail.warn || detail.whole}>{line}</span>
						</InfoTip>
					{/if}
					{#if actions.includes('conflicts')}
						<HostUi name="Tooltip" props={{ text: conflicts.map((c) => c.text).join(' · ') }}>
							<button type="button" class="vp-deck-inline-action text-warning" onclick={directionIssues}>
								<Icon name="alert" class="h-3 w-3" />{t('production.conflicts', { count: conflicts.length })}
							</button>
						</HostUi>
					{/if}
					{#if actions.includes('enqueue')}
						<HostUi name="Tooltip" props={{ text: t('production.enqueueTip'), kbd: commandById('generate')?.key }}>
							<button type="button" class="vp-deck-inline-action" disabled={blocked} onclick={() => startGeneration()}>
								{t('production.enqueue')}<kbd class="vp-kbd vp-tc text-2xs text-fg-muted">{commandById('generate')?.key ?? ''}</kbd>
							</button>
						</HostUi>
					{/if}
					{#if actions.includes('unblock') && unblock}
						<button type="button" class="vp-deck-inline-action" onclick={unblockNow}>{deckUnblockLabel(unblock.action, t)}</button>
					{/if}
					{#if actions.includes('results')}
						<button type="button" class="vp-deck-inline-action" onclick={openResults}>{t('production.deck.results')}</button>
					{/if}
					{#if actions.includes('compare')}
						<HostUi name="Tooltip" props={{ text: t('production.deck.compareTip') }}>
							<button type="button" class="vp-deck-inline-action" onclick={compareLast}><Icon name="compare" class="h-3 w-3" />{t('production.deck.compare')}</button>
						</HostUi>
					{/if}
					{#if actions.includes('finalPass')}
						<HostUi name="Tooltip" props={{ text: t('production.deck.finalTip'), kbd: commandById('final-pass')?.key }}>
							<button type="button" class="vp-deck-inline-action" onclick={openFinalPass}><Icon name="arrow-up" class="h-3 w-3" />{t('generation.finalPass.title')}</button>
						</HostUi>
					{/if}
					{#if actions.includes('retry') && failedTake}
						<HostUi name="Tooltip" props={{ text: t('production.deck.retryTip', { variant: failedTake.variant }) }}>
							<button type="button" class="vp-deck-inline-action" onclick={() => retryTake(failedTake)}><Icon name="refresh" class="h-3 w-3" />{t('generation.card.retry')}</button>
						</HostUi>
					{/if}
					{#if actions.includes('details') && failedTake}
						<HostUi name="Tooltip" props={{ text: t('generation.card.detailsTip') }}>
							<button type="button" class="vp-deck-inline-action" onclick={() => showDetails(failedTake)}>{t('production.deck.details')}</button>
						</HostUi>
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

		<section bind:this={utilityEl} class="vp-deck-utility">
			<div class="sr-only" aria-live="polite">{spoken}</div>
			<span bind:this={rulerEl} class="vp-deck-chip-ruler" aria-hidden="true">
				<span class="vp-deck-chip-engine" data-rule="engine">{engineName}</span>
				<span class="vp-deck-chip-engine" data-rule="short">{engineShort}</span>
				{#each enginePrefixes as prefix, i (i)}<span class="vp-deck-chip-engine" data-rule="prefix">{prefix}</span>{/each}
				<span class="vp-deck-chip-engine" data-rule="ellipsis">…</span>
				<span class="vp-deck-chip-dot" data-rule="sep">{' · '}</span>
				<span data-rule="profile">{chipParts.profile}</span>
				<span data-rule="size">{chipParts.size}</span>
				<span data-rule="drafts">{draftsLabel}</span>
				<span class="vp-deck-cell-label" data-rule="cell-label">{cell.label}</span>
				<span class="vp-deck-cell-value" data-rule="cell-value">{cell.value}{#if cell.sub}<span class="vp-deck-cell-sub">{` · ${cell.sub}`}</span>{/if}</span>
			</span>
			{#if showCell}
				<div class="flex shrink-0" data-vp-menu>
					<HostUi name="Tooltip" props={{ text: estimateOpen ? '' : t('production.deck.cellTip'), wrapperClass: 'inline-flex' }}>
						<button bind:this={cellEl} type="button" class="vp-deck-timing" aria-haspopup="dialog" aria-expanded={estimateOpen} onclick={toggleEstimate}>
							<span class="vp-deck-cell-label">{cell.label}</span>
							<span class="vp-deck-cell-value {cell.warn ? 'text-warning' : ''} {estimateState.loading && !busy ? 'opacity-60' : ''}">
								{cell.value}{#if cell.sub}<span class="vp-deck-cell-sub" class:text-warning={cell.warn || cell.vramWarn}>{` · ${cell.sub}`}</span>{/if}
							</span>
						</button>
					</HostUi>
					<div class="vp-menu vp-deck-popover" role="dialog" aria-label={t('production.deck.estimateTitle')} tabindex="-1" hidden={!estimateOpen} use:overlayLayer use:anchoredPopover={() => cellEl?.getBoundingClientRect() ?? null} use:drawerFocus={estimateOpen}>
						<div class="vp-deck-popover-title">{t('production.deck.estimateTitle')}</div>
						<ul class="vp-deck-popover-lines">
							{#each cellLines as text, i (i)}<li>{text}</li>{/each}
						</ul>
						{#if estNotes.length}
							<ul class="vp-deck-popover-notes">
								{#each estNotes as note, i (i)}<li><Icon name="alert" class="h-3 w-3 shrink-0" /><span>{note}</span></li>{/each}
							</ul>
						{/if}
					</div>
				</div>
			{/if}
			<div bind:this={groupEl} class="relative flex min-w-0 items-center gap-1" data-vp-menu>
				<HostUi name="Tooltip" props={{ text: chipTip, wrapperClass: 'flex min-w-0' }}>
					<button bind:this={chipEl} type="button" class="vp-deck-chip" aria-label={folded ? chipFull.join(' · ') : undefined} aria-expanded={ui.deckDrawer} aria-haspopup="dialog" onclick={toggleDrawer}>
						<Icon name="sliders" class="h-4 w-4 shrink-0" />
						<span bind:this={chipTextEl} class="vp-deck-chip-text">{#each chip as part, i (i)}{#if i}<span class="vp-deck-chip-dot">{' · '}</span>{/if}<span class={i === 0 ? 'vp-deck-chip-engine' : ''}>{part}</span>{/each}</span>
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
					<button type="button" class="vp-deck-icon-button" aria-label={t('production.more')} aria-expanded={moreOpen} aria-haspopup="menu" onclick={toggleMore}>
						<Icon name="more" class="h-[18px] w-[18px]" />
					</button>
				</HostUi>
				{#if moreOpen}
					<div class="vp-menu" style:right="0" style:bottom="2.75rem" role="menu" aria-label={t('production.more')} use:overlayLayer in:fly={{ y: 4, duration: ms(120) }}>
						<button type="button" role="menuitem" onclick={() => fromMore(openResults)}>
							<Icon name="layers" class="h-3.5 w-3.5 shrink-0" /><span class="flex-1">{t('production.deck.results')}</span>{#if commandById('results')?.key}<span class="vp-menu-key">{commandById('results').key}</span>{/if}
						</button>
						<button type="button" role="menuitem" onclick={() => fromMore(() => setTimeout(openQueue))}>
							<Icon name="list" class="h-3.5 w-3.5 shrink-0" /><span class="flex-1">{t('production.queue')}</span>{#if queued}<span class="vp-deck-badge vp-tc">{queued}</span>{/if}{#if commandById('queue')?.key}<span class="vp-menu-key">{commandById('queue').key}</span>{/if}
						</button>
						<div class="vp-menu-sep" role="separator"></div>
						<button type="button" role="menuitem" onclick={() => fromMore(openFinalPass)}>
							<Icon name="arrow-up" class="h-3.5 w-3.5 shrink-0" /><span class="flex-1">{t('generation.finalPass.title')}</span>{#if commandById('final-pass')?.key}<span class="vp-menu-key">{commandById('final-pass').key}</span>{/if}
						</button>
					</div>
				{/if}
			</div>
		</section>
	</div>
	{#if ui.deckDrawer}
		<ProductionDrawer anchor={deckEl} {clips} {engineTip} onclose={() => (ui.deckDrawer = false)} />
	{/if}
</div>

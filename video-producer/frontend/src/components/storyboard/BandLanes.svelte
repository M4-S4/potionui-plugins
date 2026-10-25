<script>
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, clamp, round, relayout, secs, clipLabel, promptOf, sourceLength } from '../../lib/state.svelte.js';
	import { takesOf, shotActivity, shotEngineText, shotDurationLimit, fitShot, soundOf } from '../../lib/production.svelte.js';
	import { activityStep } from '../../lib/generation.js';
	import { labelOf } from '../../lib/labels.js';
	import { overrunsTake, shotStale } from '../../lib/shots.js';
	import { castLabels } from '../../lib/bible.js';
	import { seamImage } from '../../lib/seam.js';
	import { seam } from '../../lib/continuity.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { drag, cancelDrag, snap, rulerStep, waveform, peakWaveform } from '../../lib/timeline.js';
	import { wheelZoomFactor } from '../../lib/timebase.js';
	import { audioPeaks } from '../../lib/sources.svelte.js';
	import { clipThumb } from '../../lib/media.js';
	import { clipFilter } from '../../lib/look.js';
	import { stages } from '../../lib/catalog.js';
	import { laneCode } from '../../lib/tracks.js';
	import { CONDITION, MUX } from '../../lib/sound.js';
	import { overlayLayer } from '../../lib/host.js';
	import { MUSIC_ROLE, displayStart, lastFailure, musicEnd, sections, seamStatus, stackOrder } from '../../lib/band.js';
	import { compareSeam, pickShot, previewTake, proposalLayout, selectedShot } from '../../lib/band.svelte.js';
	import Icon from '../Icon.svelte';
	import SoundNote from '../shots/SoundNote.svelte';

	const HEAD = 120;
	const SONG = 48;
	const SHOTS = 138;
	const TAKES = 62;
	const MUSIC = 40;
	const REFS = 30;
	const TOTAL_H = SONG + SHOTS + TAKES + MUSIC + REFS;

	let scroller = $state();
	let viewW = $state(800);
	let scrollX = $state(0);
	let reorder = $state(null);

	const pps = $derived(ui.pxPerSec);
	const x = (time) => time * pps;
	const layout = $derived(proposalLayout());
	const starts = $derived(doc.clips.map((c, i) => displayStart(c, i, layout)));
	const cut = $derived(doc.clips.reduce((sum, c) => sum + c.dur, 0) + (layout?.shift ?? 0));
	const song = $derived(musicEnd(doc));
	const total = $derived(Math.max(cut, song, 1));
	const laneW = $derived(Math.max(0, viewW));
	const contentW = $derived(Math.max(laneW, (total + 6) * pps));
	const parts = $derived(sections(doc.markers, Math.max(song, cut)));
	const step = $derived(rulerStep(pps));
	const ticks = $derived(Array.from({ length: Math.ceil(contentW / pps / step) + 1 }, (_, i) => i * step));
	const musicLanes = $derived(doc.lanes.filter((l) => l.role === MUSIC_ROLE));
	const musicItems = $derived(doc.audio.filter((a) => musicLanes.some((l) => l.id === a.lane)));
	const sel = $derived(selectedShot());
	const overview = $derived(Math.max(total, 1));
	const tickLabel = (v) => (step < 1 ? formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : `${Math.floor(v / 60)}:${String(Math.floor(v % 60)).padStart(2, '0')}`);
	const tone = { [CONDITION]: 'border-success/60 bg-success/15 text-success', [MUX]: 'border-line-hover bg-fg-subtle/15 text-fg-muted' };

	const timeAt = (clientX) => {
		const r = scroller.getBoundingClientRect();
		return Math.max(0, (clientX - r.left + scroller.scrollLeft) / pps);
	};

	function setDragText(text, limit = false) {
		if (!ui.drag) return;
		ui.drag.text = text;
		ui.drag.limit = limit;
	}

	function rulerDown(e) {
		seek(timeAt(e.clientX));
		drag(e, { undoable: false, onMove: (dx, dy, ev) => seek(snap(timeAt(ev.clientX), null).t) });
	}

	function shotDown(e, c) {
		drag(e, {
			onMove: (dx, dy, ev) => {
				const at = timeAt(ev.clientX);
				const others = doc.clips.filter((o) => o.id !== c.id);
				const index = others.filter((o) => starts[doc.clips.indexOf(o)] + o.dur / 2 < at).length;
				const next = others[index];
				reorder = { id: c.id, dx, index, at: next ? starts[doc.clips.indexOf(next)] : cut };
				setDragText(t('timeline.drag.position', { n: index + 1 }));
			},
			onCancel: () => (reorder = null),
			onClick: () => pickShot(c),
			onEnd: () => {
				if (!reorder) return;
				const from = doc.clips.indexOf(c);
				const [moved] = doc.clips.splice(from, 1);
				doc.clips.splice(reorder.index, 0, moved);
				relayout();
				reorder = null;
				pickShot(moved, false);
			}
		});
	}

	function trimDown(e, c) {
		pickShot(c, false);
		const range = shotDurationLimit(c);
		const max = sourceLength(c);
		const d0 = c.dur;
		drag(e, {
			onMove: (dx) => {
				const end = ui.snapping ? snap(c.start + d0 + dx / pps, c.id) : { t: c.start + d0 + dx / pps, at: null };
				const nd = clamp(end.t - c.start, 0.4, range.max);
				const limit = nd >= range.max - 0.001;
				c.dur = round(nd, 0.04);
				relayout();
				if (ui.drag) ui.drag.at = end.at;
				if (limit) setDragText(range.by === 'engine' ? t('timeline.drag.engineLimitAt', { dur: secs(range.max) }) : t('timeline.drag.sourceLimitAt', { dur: secs(range.by === 'source' ? max : range.max) }), true);
				else setDragText(overrunsTake(range.take, d0, c.dur) ? t('timeline.drag.beyondTake', { dur: secs(c.dur) }) : t('timeline.drag.rippled', { dur: secs(c.dur) }));
			},
			onEnd: () => {
				if (fitShot(c, d0)) relayout();
			}
		});
	}

	function wheel(e) {
		if (e.ctrlKey || e.metaKey) {
			e.preventDefault();
			const at = timeAt(e.clientX);
			const before = e.clientX - scroller.getBoundingClientRect().left;
			ui.pxPerSec = clamp(ui.pxPerSec * wheelZoomFactor(e), 8, 220);
			requestAnimationFrame(() => scroller && (scroller.scrollLeft = at * ui.pxPerSec - before));
		} else if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && !e.shiftKey) {
			e.preventDefault();
			scroller.scrollLeft += e.deltaY;
		}
	}

	function overviewDown(e) {
		const bar = e.currentTarget;
		const go = (clientX) => {
			const r = bar.getBoundingClientRect();
			scroller.scrollLeft = ((clientX - r.left) / r.width) * overview * pps - laneW / 2;
		};
		go(e.clientX);
		drag(e, { undoable: false, onMove: (dx, dy, ev) => go(ev.clientX) });
	}

	function reveal(id) {
		const i = doc.clips.findIndex((c) => c.id === id);
		if (i < 0 || !scroller) return;
		const a = x(starts[i]);
		const b = a + x(doc.clips[i].dur);
		if (a < scroller.scrollLeft) scroller.scrollLeft = a - 40;
		else if (b > scroller.scrollLeft + laneW) scroller.scrollLeft = b - laneW + 60;
	}

	$effect(() => {
		const id = sel?.id;
		if (id && !ui.playing) queueMicrotask(() => reveal(id));
	});

	$effect(() => {
		if (!ui.playing || !scroller) return;
		const px = x(ui.playhead);
		if (px > scroller.scrollLeft + laneW - 40 || px < scroller.scrollLeft) scroller.scrollLeft = px - 40;
	});

	$effect(() => cancelDrag);

	export function fit() {
		ui.pxPerSec = clamp((laneW - 24) / total, 8, 220);
		if (scroller) scroller.scrollLeft = 0;
	}

	function focusPrompt() {
		document.getElementById('vp-quick-prompt')?.focus();
	}
</script>

<div class="shrink-0 border-b border-line">
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="relative mx-3.5 mb-1.5 mt-2 h-6 cursor-pointer overflow-hidden rounded border border-line bg-surface-2 vp-touch-none" style:margin-left="{HEAD + 1}px" title={t('storyboard.band.overviewTip')} onpointerdown={overviewDown}>
		{#each doc.clips as c, i (c.id)}
			{@const failed = lastFailure(takesOf(c))}
			{@const running = shotActivity(c.id).state === 'running'}
			<div
				class="absolute bottom-[5px] top-[5px] rounded-sm {failed ? 'bg-danger/75' : running ? 'bg-signal/60' : stages[c.stage].dot} {sel?.id === c.id ? 'ring-[1.5px] ring-fg' : ''}"
				style:left="{(starts[i] / overview) * 100}%"
				style:width="calc({(c.dur / overview) * 100}% - 2px)"
				style:opacity={failed || running ? null : 0.6}
			></div>
			{#if i > 0 && seamStatus(seam(i)) === 'issue'}<div class="absolute inset-y-0.5 -ml-px w-[3px] rounded-sm bg-warning-solid" style:left="{(starts[i] / overview) * 100}%"></div>{/if}
		{/each}
		{#each layout?.ghosts ?? [] as g (g.id)}
			<div class="absolute bottom-[5px] top-[5px] rounded-sm border border-dashed border-signal" style:left="{(g.start / overview) * 100}%" style:width="calc({(g.dur / overview) * 100}% - 2px)"></div>
		{/each}
		<div class="pointer-events-none absolute inset-y-0 rounded border-[1.5px] border-fg/70 bg-fg/5" style:left="{Math.min(100, (scrollX / pps / overview) * 100)}%" style:width="{Math.max(1, Math.min(100, (laneW / pps / overview) * 100))}%"></div>
		<div class="pointer-events-none absolute inset-y-0 w-[1.5px] bg-danger" style:left="{(ui.playhead / overview) * 100}%"></div>
	</div>

	<div class="flex" style:height="{TOTAL_H + 10}px">
		<div class="ml-3.5 shrink-0 border-r border-line" style:width="{HEAD - 14}px">
			<div class="flex items-center gap-2 border-b border-line border-l-[3px] border-l-success px-2 text-xs text-fg-muted" style:height="{SONG}px"><Icon name="music" class="h-3.5 w-3.5 shrink-0 text-fg-subtle" /><span class="truncate">{t('storyboard.band.song')}</span></div>
			<div class="flex items-center gap-2 border-b border-line border-l-[3px] border-l-viz-1 px-2 text-xs text-fg-muted" style:height="{SHOTS}px"><Icon name="film" class="h-3.5 w-3.5 shrink-0 text-fg-subtle" /><span class="truncate">{t('storyboard.band.shots')}</span></div>
			<div class="flex items-center gap-2 border-b border-line border-l-[3px] border-l-viz-1 px-2 text-xs text-fg-muted" style:height="{TAKES}px" title={t('storyboard.band.takesTip')}><Icon name="layers" class="h-3.5 w-3.5 shrink-0 text-fg-subtle" /><span class="truncate">{t('storyboard.band.takes')}</span></div>
			<div class="flex items-center gap-2 border-b border-line border-l-[3px] border-l-success px-2 text-xs text-fg-muted" style:height="{MUSIC}px" title={musicLanes.map((l) => `${laneCode(doc.lanes, l.id)} · ${l.name}`).join(', ')}><Icon name="music" class="h-3.5 w-3.5 shrink-0 text-fg-subtle" /><span class="truncate">{musicLanes.length ? musicLanes.map((l) => laneCode(doc.lanes, l.id)).join(', ') + ' · ' + t('storyboard.band.music') : t('storyboard.band.music')}</span></div>
			<div class="flex items-center gap-2 border-l-[3px] border-l-viz-2 px-2 text-xs text-fg-muted" style:height="{REFS}px" title={t('storyboard.band.soundTip')}><Icon name="wave" class="h-3.5 w-3.5 shrink-0 text-fg-subtle" /><span class="truncate">{t('storyboard.band.sound')}</span></div>
		</div>

		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="relative mr-3.5 min-w-0 flex-1 overflow-x-auto overflow-y-hidden" bind:this={scroller} bind:clientWidth={viewW} onscroll={() => (scrollX = scroller.scrollLeft)} onwheel={wheel} style:overscroll-behavior-x="contain">
			<div class="relative" style:width="{contentW}px" style:height="{TOTAL_H}px">
				{#each [SONG, SONG + SHOTS, SONG + SHOTS + TAKES, SONG + SHOTS + TAKES + MUSIC] as edge (edge)}
					<div class="pointer-events-none absolute inset-x-0 h-px bg-line" style:top="{edge - 1}px"></div>
				{/each}

				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div class="absolute inset-x-0 top-0 h-[22px] cursor-text vp-touch-none" onpointerdown={rulerDown}>
					{#each ticks as tick (tick)}
						<div class="absolute bottom-0 h-2 w-px bg-viz-axis" style:left="{x(tick)}px"></div>
						<span class="vp-tc absolute top-1 pl-1 text-2xs text-fg-subtle" style:left="{x(tick)}px">{tickLabel(tick)}</span>
					{/each}
				</div>
				<div class="absolute inset-x-0 top-[25px] h-[18px]">
					{#each parts as p (p.id ?? p.start)}
						<div class="absolute top-0 h-[18px] truncate rounded-sm border-l-2 border-success bg-success/15 px-1.5 text-2xs leading-[18px] text-fg-muted" style:left="{x(p.start)}px" style:width="{Math.max(4, x(p.end - p.start) - 2)}px" title={t('storyboard.band.partTip', { label: p.label, start: secs(p.start), end: secs(p.end) })}>
							<span class="font-semibold text-fg">{p.label}</span>
						</div>
					{/each}
					{#if !parts.length}<span class="absolute left-2 top-0 text-2xs leading-[18px] text-fg-subtle">{t('storyboard.band.partsHint')}</span>{/if}
				</div>

				<div class="absolute inset-x-0" style:top="{SONG + 2}px" style:height="{SHOTS - 4}px">
					{#each doc.clips as c, i (c.id)}
						{@render shot(c, i)}
					{/each}
					{#each layout?.ghosts ?? [] as g (g.id)}
						{@render ghost(g)}
					{/each}
					{#if reorder}<div class="absolute -top-1 bottom-[-4px] z-20 -ml-px w-[3px] rounded bg-signal" style:left="{x(reorder.at)}px"></div>{/if}
					{#if !doc.clips.length && !layout}<span class="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-fg-subtle">{t('storyboard.band.noShots')}</span>{/if}
				</div>

				<div class="absolute inset-x-0" style:top="{SONG + SHOTS}px" style:height="{TAKES}px">
					{#each doc.clips as c, i (c.id)}
						{@render stack(c, i)}
					{/each}
				</div>

				<div class="absolute inset-x-0" style:top="{SONG + SHOTS + TAKES}px" style:height="{MUSIC}px">
					{#each musicItems as a (a.id)}
						{@const src = asset(a.assetId)}
						{@const w = x(a.dur)}
						{@const peaks = audioPeaks(src)}
						<div class="absolute bottom-1 top-1 overflow-hidden rounded-sm bg-success/10" style:left="{x(a.start)}px" style:width="{w}px" title={src?.name ?? ''}>
							<svg class="absolute inset-0" width={w} height={MUSIC - 8} aria-hidden="true">
								<polygon points={src?.src ? (peaks ? peakWaveform(peaks, w, MUSIC - 8, a.srcIn, pps) : '') : waveform(a.assetId, w, MUSIC - 8, a.srcIn, pps, src?.synth)} fill="rgb(var(--success))" opacity="0.6" />
							</svg>
						</div>
					{/each}
					{#if !musicItems.length}<span class="absolute left-2 top-1/2 -translate-y-1/2 text-2xs text-fg-subtle">{t('storyboard.band.noMusic')}</span>{/if}
				</div>

				<div class="absolute inset-x-0" style:top="{SONG + SHOTS + TAKES + MUSIC}px" style:height="{REFS}px">
					{#each doc.clips as c, i (c.id)}
						{@const sound = soundOf(c)}
						{#if sound?.sends}
							{@const names = [...sound.lanes.map((id) => laneCode(doc.lanes, id)), ...sound.references.map((r) => r.name)]}
							<div class="absolute top-1 flex h-[21px] items-center gap-1 overflow-hidden whitespace-nowrap rounded-sm border px-1.5 text-2xs {tone[sound.behavior] ?? 'border-warning/50 bg-warning/10 text-warning'}" style:left="{x(starts[i])}px" style:width="{Math.max(6, x(c.dur) - 3)}px" title={names.join(', ')}>
								<Icon name="wave" class="h-3 w-3 shrink-0" /><span class="truncate">{names.join(' · ')}</span>
							</div>
						{/if}
					{/each}
				</div>

				{#if ui.drag?.at != null}<div class="pointer-events-none absolute inset-y-0 w-px bg-warning" style:left="{x(ui.drag.at)}px"></div>{/if}
				<div class="pointer-events-none absolute inset-y-0 z-30 w-px bg-danger" style:left="{x(ui.playhead)}px"></div>
			</div>
		</div>
	</div>
</div>

{#if ui.drag?.text}
	<div class="pointer-events-none fixed rounded border bg-surface-3 px-2 py-1 text-xs shadow-floating {ui.drag.limit ? 'border-danger text-danger' : 'border-line-strong text-fg'}" style:left="{ui.drag.x + 14}px" style:top="{ui.drag.y - 30}px" use:overlayLayer={'tooltip'}>
		{ui.drag.text}
	</div>
{/if}

{#snippet shot(c, i)}
	{@const w = Math.max(8, x(c.dur) - 3)}
	{@const thumb = clipThumb(c)}
	{@const takes = takesOf(c)}
	{@const activity = shotActivity(c.id)}
	{@const failed = lastFailure(takes)}
	{@const first = thumb ? null : seamImage(doc, c.id, 'first')}
	{@const last = thumb ? null : seamImage(doc, c.id, 'last')}
	{@const narrow = w < 92}
	{@const isSel = sel?.id === c.id}
	{@const engine = shotEngineText(c)}
	{@const sound = soundOf(c)}
	{@const cast = castLabels(doc, c)}
	{@const stale = shotStale(c, takes)}
	{@const silent = !c.assetId && !promptOf(c)?.text?.trim()}
	{@const sm = i > 0 ? seam(i) : null}
	{@const status = seamStatus(sm)}
	<div
		class="group absolute bottom-0 top-0 overflow-hidden rounded-md border bg-surface-1 vp-touch-none {isSel ? 'z-10 border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'} {reorder?.id === c.id ? 'z-20 opacity-80 shadow-floating' : ''}"
		style:left="{x(starts[i])}px"
		style:width="{w}px"
		style:transform={reorder?.id === c.id ? `translateX(${reorder.dx}px)` : null}
		role="button"
		tabindex={isSel ? 0 : -1}
		aria-label={t('storyboard.band.shotLabel', { n: i + 1, name: clipLabel(c), dur: secs(c.dur), stage: stages[c.stage].label })}
		title={`${String(i + 1).padStart(2, '0')} · ${clipLabel(c)} · ${secs(c.dur)}`}
		data-band-shot={c.id}
		onpointerdown={(e) => shotDown(e, c)}
		ondblclick={() => (ui.modal = { type: 'shot', id: c.id })}
		onkeydown={(e) => e.key === 'Enter' && (e.preventDefault(), focusPrompt())}
	>
		<div class="absolute inset-x-0 top-0 flex h-[88px] gap-px bg-canvas">
			{#if thumb}
				<div class="h-full flex-1 bg-repeat-x" style:background-image="url({thumb})" style:background-size="auto 100%" style:filter={clipFilter(c)}></div>
			{:else}
				{#if first?.src && !narrow}<div class="relative h-full w-[42%] max-w-[120px] bg-cover bg-center" style:background-image="url({first.src})"><span class="absolute bottom-0 left-0 rounded-tr bg-black/60 px-1 text-2xs text-white">{t('storyboard.band.first')}</span></div>{/if}
				<div class="flex h-full flex-1 flex-col items-center justify-center gap-1 bg-surface-3 bg-[repeating-linear-gradient(135deg,rgb(var(--line-strong))_0_1px,transparent_1px_10px)] text-2xs text-fg-muted">
					{#if w > 40}<Icon name="sparkles" class="h-3.5 w-3.5" />{/if}
					{#if w > 150 && !first?.src}<span>{t('storyboard.placeholder')}</span>{/if}
				</div>
				{#if last?.src && w > 200}<div class="relative h-full w-[42%] max-w-[120px] bg-cover bg-center" style:background-image="url({last.src})"><span class="absolute bottom-0 left-0 rounded-tr bg-black/60 px-1 text-2xs text-white">{t('storyboard.band.last')}</span></div>{/if}
			{/if}
		</div>
		<span class="vp-tc absolute left-1.5 top-1.5 rounded bg-black/60 px-1 text-2xs font-medium leading-4 text-white">{String(i + 1).padStart(2, '0')}</span>
		<div class="absolute right-1.5 top-1.5 flex gap-1">
			{#if activity.state === 'running'}
				<span class="flex h-[18px] items-center gap-1 rounded bg-black/60 px-1.5 text-2xs text-white" title={activityStep(activity) || (activity.running ? t('generation.state.running') : t('lib.status.queued'))}>
					<Icon name={activity.running ? 'sparkles' : 'history'} class="h-3 w-3" />{#if !narrow}{activity.running ? `${Math.round(activity.progress)} %` : t('lib.status.queued')}{/if}
				</span>
			{:else if failed}
				<span class="flex h-[18px] items-center gap-1 rounded bg-danger-solid px-1.5 text-2xs text-white" title={t('storyboard.band.failedTip', { variant: failed.variant ?? '' })}><Icon name="alert" class="h-3 w-3" />{#if !narrow}{t('storyboard.band.failed')}{/if}</span>
			{/if}
		</div>
		{#if stale || silent}
			<span class="absolute left-3.5 top-[64px] flex h-[18px] max-w-[calc(100%-1.25rem)] items-center gap-1 rounded bg-warning-solid px-1.5 text-2xs font-medium text-black" title={stale ? t('storyboard.staleTip') : t('storyboard.band.silentTip')}>
				<Icon name="pencil" class="h-3 w-3 shrink-0" />{#if !narrow}<span class="truncate">{stale ? t('storyboard.stale') : t('storyboard.noPrompt')}</span>{/if}
			</span>
		{/if}
		{#if activity.state === 'running'}
			<div class="absolute inset-x-0 top-[85px] h-[3px] bg-signal/25"><div class="h-full bg-signal transition-[width] duration-150" style:width="{activity.progress}%"></div></div>
		{/if}
		<div class="absolute inset-x-0 bottom-[3px] top-[88px] flex flex-col gap-0.5 px-1.5 pt-1">
			{#if !narrow}<span class="truncate text-xs font-medium text-fg">{clipLabel(c)}</span>{/if}
			<div class="flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-2xs text-fg-subtle">
				<span class="vp-tc">{secs(c.dur)}</span>
				{#if engine && w > 46}<span class="flex shrink-0 text-signal" role="img" aria-label={engine} title={engine}><Icon name="sliders" class="h-3 w-3" /></span>{/if}
				{#if sound?.behavior && w > 46}<span class="inline-flex shrink-0"><SoundNote behavior={sound.behavior} compact /></span>{/if}
				{#if cast.length && !narrow}<span class="flex min-w-0 items-center gap-0.5 truncate"><Icon name="user" class="h-3 w-3 shrink-0" /><span class="truncate">{cast.join(', ')}</span></span>{/if}
			</div>
		</div>
		<div class="absolute inset-x-0 bottom-0 h-[3px] {stages[c.stage].dot}"></div>
		<button type="button" tabindex="-1" class="vp-hit absolute inset-y-0 right-0 z-20 w-2 cursor-ew-resize hover:bg-warning {isSel ? 'bg-warning/60' : ''}" aria-label={t('timeline.trim.end')} title={t('storyboard.band.trimTip')} onpointerdown={(e) => trimDown(e, c)}></button>
	</div>
	{#if status}
		<button
			type="button"
			class="absolute z-30 -ml-[11px] flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 border-canvas {status === 'issue' ? 'bg-warning-solid text-black shadow-[0_0_0_3px_rgb(var(--warning-solid)/0.3)]' : 'bg-surface-3 text-success'} {ui.seamCompare === c.id ? 'ring-2 ring-signal' : ''}"
			style:left="{x(starts[i]) - 1.5}px"
			style:top="77px"
			aria-label={status === 'issue' ? t('storyboard.band.seamIssue', { n: i, m: i + 1 }) : t('storyboard.band.seamOk', { n: i, m: i + 1 })}
			title={status === 'issue' ? sm.issues.map((x) => x.text).join('\n') : t('storyboard.band.seamOkTip')}
			onpointerdown={(e) => e.stopPropagation()}
			onclick={() => compareSeam(c)}
		><Icon name={status === 'issue' ? 'alert' : 'link'} class="h-3 w-3" /></button>
	{/if}
{/snippet}

{#snippet ghost(g)}
	<div class="absolute bottom-0 top-0 overflow-hidden rounded-md border-[1.5px] border-dashed border-signal bg-signal/5 bg-[repeating-linear-gradient(135deg,rgb(var(--signal)/0.12)_0_6px,transparent_6px_12px)]" style:left="{x(g.start)}px" style:width="{Math.max(6, x(g.dur) - 3)}px" title={t('storyboard.band.ghostTip', { name: g.label, dur: secs(g.dur) })}>
		<span class="vp-tc absolute left-1.5 top-1.5 text-2xs font-semibold text-signal">+{String(g.n).padStart(2, '0')}</span>
		<div class="absolute inset-x-1.5 bottom-2 flex flex-col text-2xs text-fg-muted">
			<span class="truncate text-xs font-medium text-fg">{g.label}</span>
			<span class="vp-tc">{secs(g.dur)}</span>
		</div>
	</div>
{/snippet}

{#snippet stack(c, i)}
	{@const order = stackOrder(takesOf(c), ui.hideRejected)}
	{@const w = Math.max(6, x(c.dur) - 3)}
	{@const isSel = sel?.id === c.id}
	{#each order.slice(0, 4) as take, r (take.id)}
		{@const label = labelOf(take)}
		{@const shown = ui.preview?.kind === 'result' && ui.preview.id === take.id}
		<button
			type="button"
			tabindex="-1"
			class="absolute h-3 overflow-hidden whitespace-nowrap vp-tc rounded-sm border px-1 text-left text-[9px] font-semibold leading-[10px] {take.status === 'done' ? (label === 'final' ? 'border-transparent bg-success/55 text-fg' : label === 'candidate' ? 'border-transparent bg-signal/50 text-fg' : label === 'rejected' ? 'border-transparent bg-[repeating-linear-gradient(135deg,rgb(var(--danger)/0.35)_0_2px,transparent_2px_5px)] text-danger' : 'border-transparent bg-fg-subtle/35 text-fg') : take.status === 'failed' ? 'border-transparent bg-danger-solid/50 text-white' : 'border-dashed border-fg-subtle bg-surface-3 text-fg-muted'} {shown ? 'ring-1 ring-fg' : ''} {isSel ? '' : 'opacity-60'}"
			style:left="{x(starts[i])}px"
			style:top="{3 + r * 14}px"
			style:width="{w}px"
			title={t('storyboard.band.takeTip', { variant: take.variant ?? '', label: take.status === 'done' ? t(`generation.label.${label}`) : take.status === 'failed' ? t('storyboard.band.failed') : take.status === 'running' ? t('generation.state.running') : t('lib.status.queued') })}
			onclick={() => (take.status === 'done' ? previewTake(take) : pickShot(c))}
		>
			{#if take.status === 'running'}<span class="absolute inset-y-0 left-0 bg-signal/50" style:width="{take.progress ?? 0}%"></span>{/if}
			<span class="relative">{#if w > 26}{take.variant ?? ''}{#if isSel && w > 96 && take.status === 'done'} · {t(`generation.label.${label}`)}{/if}{/if}</span>
		</button>
	{/each}
	{#if order.length > 4}<span class="vp-tc absolute text-[10px] text-fg-subtle" style:left="{x(starts[i]) + w - 22}px" style:top="48px">+{order.length - 4}</span>{/if}
{/snippet}

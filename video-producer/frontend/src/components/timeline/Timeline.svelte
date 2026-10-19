<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import {
		ui,
		doc,
		asset,
		select,
		seqDuration,
		act,
		relayout,
		relink,
		clamp,
		round,
		bladeAt,
		undo,
		redo,
		history,
		duplicateSelection,
		deleteSelection,
		addPrompt,
		addFrame,
		addControl,
		addAudioLane,
		addMarker,
		addAssetToTimeline,
		promptIssues,
		toast,
		secs,
		clipLabel,
		sourceLength
	} from '../../lib/state.svelte.js';
	import { takesOf } from '../../lib/production.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { drag, cancelDrag, snap, snapMove, rulerStep, waveform, peakWaveform } from '../../lib/timeline.js';
	import { audioPeaks } from '../../lib/sources.svelte.js';
	import { roleColor, stages, frameRoleLabel } from '../../lib/catalog.js';
	import { clipFilter } from '../../lib/look.js';
	import { assetThumb, clipThumb } from '../../lib/media.js';
	import { addTitle, commandById } from '../../lib/commands.js';
	import { markStale, selectKey, editKey, relinkPlan } from '../../lib/scene.svelte.js';
	import { retime } from '../../lib/scene3d/camera.js';
	import { overlayLayer } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import { wheelZoomFactor } from '../../lib/timebase.js';
	import { ulid } from '../../lib/ulid.js';
	import Icon from '../Icon.svelte';
	import Dropdown from '../shell/Dropdown.svelte';

	const HEAD = 156;
	const BLOCK_ROW = 31;
	const KEY_BAND = 23;
	let scroller = $state();
	let viewW = $state(800);
	let reorder = $state(null);

	const pps = $derived(ui.pxPerSec);
	const total = $derived(seqDuration());
	const contentW = $derived(Math.max(viewW - HEAD, (total + 8) * pps));
	const x = (time) => time * pps;
	const FADE_EDGE = 37;
	const fadeX = (px, w) => (w - 2 < FADE_EDGE * 2 ? px : clamp(px, FADE_EDGE, w - 2 - FADE_EDGE));
	const step = $derived(rulerStep(pps));
	const ticks = $derived(Array.from({ length: Math.ceil(contentW / pps / step) + 1 }, (_, i) => i * step));
	const key = (id) => commandById(id)?.key || undefined;

	const keyed = $derived(doc.plans3d.some((p) => p.source !== 'blender' && p.keyframes.length));
	const rows = $derived([
		{ id: 'titles', label: t('timeline.row.titles'), icon: 'type', h: BLOCK_ROW, color: null },
		{ id: 'prompts', label: t('timeline.row.prompts'), icon: 'sparkles', h: BLOCK_ROW, color: roleColor.Prompts },
		{ id: 'frames', label: t('timeline.row.frames'), icon: 'image', h: 32, color: roleColor.Frames },
		{ id: 'controls', label: t('timeline.row.controls'), icon: 'route', h: BLOCK_ROW, color: roleColor.Guides },
		{ id: 'plans3d', label: t('timeline.row.plans3d'), icon: 'cube', h: keyed ? BLOCK_ROW + KEY_BAND : BLOCK_ROW, color: roleColor.Guides },
		{ id: 'v1', label: t('timeline.row.video'), icon: 'film', h: 60, color: roleColor.Vidéo },
		...doc.lanes.map((l) => ({ id: l.id, lane: l, label: t('timeline.row.lane', { id: l.id, name: l.name }), icon: l.role === 'Dialogue' ? 'mic' : l.role === 'Musique' ? 'music' : 'wave', h: 38, color: roleColor[l.role] }))
	]);

	const tools = $derived([
		{ id: 'select', icon: 'pointer', label: t('timeline.tool.select'), keys: key('tool-select') },
		{ id: 'range', icon: 'range', label: t('timeline.tool.range'), keys: key('tool-range') },
		{ id: 'blade', icon: 'scissors', label: t('timeline.tool.blade'), keys: key('tool-blade') }
	]);

	const addItems = $derived([
		{ label: t('timeline.add.prompt'), icon: 'sparkles', run: () => addPrompt() },
		{ label: t('timeline.add.frame'), icon: 'image', run: () => addFrame() },
		{ label: t('timeline.add.control'), icon: 'route', run: () => addControl() },
		{ label: t('timeline.add.title'), icon: 'type', key: key('title'), run: () => addTitle() },
		{ label: t('timeline.add.marker'), icon: 'bookmark', key: key('marker'), run: () => addMarker() },
		{ label: t('timeline.add.lane'), icon: 'wave', key: key('audio-add'), run: addAudioLane }
	]);

	const isSel = (kind, id) => ui.selection?.kind === kind && ui.selection?.id === id;
	const timeAt = (clientX) => {
		const r = scroller.getBoundingClientRect();
		return Math.max(0, (clientX - r.left - HEAD + scroller.scrollLeft) / pps);
	};
	const tickLabel = (v) => (step < 1 ? formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : `${Math.floor(v / 60)}:${String(Math.floor(v % 60)).padStart(2, '0')}`);

	function setDragText(text, limit = false) {
		if (!ui.drag) return;
		ui.drag.text = text;
		ui.drag.limit = limit;
	}

	function rulerDown(e) {
		if (e.altKey || ui.tool === 'range') return rangeDown(e);
		seek(timeAt(e.clientX));
		drag(e, { undoable: false, onMove: (dx, dy, ev) => seek(snap(timeAt(ev.clientX), null).t) });
	}

	function rangeDown(e) {
		const t0 = snap(timeAt(e.clientX)).t;
		drag(e, {
			undoable: false,
			onMove: (dx, dy, ev) => {
				const t1 = snap(timeAt(ev.clientX)).t;
				ui.range = { in: Math.min(t0, t1), out: Math.max(t0, t1) };
				ui.production.target = 'range';
				setDragText(t('timeline.drag.range', { start: secs(ui.range.in), end: secs(ui.range.out) }));
			},
			onClick: () => (ui.range = null)
		});
	}

	function laneDown(e) {
		if (ui.tool === 'range') return rangeDown(e);
		if (e.target === e.currentTarget) select(null);
	}
	function laneDbl(e, row) {
		if (e.target !== e.currentTarget) return;
		const at = round(timeAt(e.clientX), 0.04);
		if (row.id === 'prompts') addPrompt(at, 4);
		if (row.id === 'frames') addFrame(undefined, at);
		if (row.id === 'controls') addControl();
	}

	function relinkAfter(kind, item) {
		if (kind === 'plan3d') relinkPlan(item);
		else if ('shotId' in item) relink(item);
	}

	function moveBlock(e, kind, item) {
		if (ui.tool === 'blade' && kind === 'audio') {
			select(kind, item.id);
			return bladeAt(timeAt(e.clientX));
		}
		select(kind, item.id);
		const s0 = item.start;
		const lane0 = item.lane;
		drag(e, {
			onMove: (dx, dy, ev) => {
				const r = snapMove(Math.max(0, s0 + dx / pps), item.dur, item.id);
				item.start = Math.max(0, r.start);
				if (kind === 'audio') {
					const laneEl = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('[data-lane]');
					if (laneEl) item.lane = laneEl.dataset.lane;
				}
				if (ui.drag) ui.drag.at = r.at;
				setDragText(kind === 'audio' && item.lane !== lane0 ? t('timeline.drag.moveLane', { start: secs(item.start), lane: item.lane }) : t('timeline.drag.move', { start: secs(item.start), dur: secs(item.dur) }));
			},
			onEnd: () => relinkAfter(kind, item),
			onClick: () => {}
		});
	}
	function trimBlock(e, kind, item, edge) {
		select(kind, item.id);
		const s0 = item.start;
		const d0 = item.dur;
		const in0 = item.srcIn ?? 0;
		const src = kind === 'audio' ? (asset(item.assetId)?.srcDur ?? Infinity) : Infinity;
		drag(e, {
			onMove: (dx) => {
				let limit = false;
				if (edge === 'start') {
					let ns = snap(s0 + dx / pps, item.id).t;
					ns = clamp(ns, Math.max(0, s0 - in0), s0 + d0 - 0.3);
					if (kind === 'audio' && ns <= s0 - in0 + 0.001) limit = true;
					item.dur = s0 + d0 - ns;
					if ('srcIn' in item) item.srcIn = in0 + (ns - s0);
					item.start = ns;
				} else {
					let ne = snap(s0 + d0 + dx / pps, item.id).t;
					ne = clamp(ne, s0 + 0.3, s0 + src - in0);
					if (ne >= s0 + src - in0 - 0.001) limit = true;
					item.dur = ne - s0;
				}
				setDragText(limit ? t('timeline.drag.sourceLimit') : t('timeline.drag.duration', { dur: secs(item.dur) }), limit);
			},
			onEnd: () => {
				relinkAfter(kind, item);
				if (kind !== 'plan3d' || Math.abs(item.dur - d0) < 1e-6) return;
				if (item.source === 'trajectory') item.keyframes = retime(item.keyframes, d0, item.dur);
				markStale(item);
			}
		});
	}

	function fadeDrag(e, kind, item, edge) {
		select(kind, item.id);
		const f0 = edge === 'in' ? item.fadeIn : item.fadeOut;
		drag(e, {
			onMove: (dx) => {
				const v = round(clamp(f0 + (edge === 'in' ? dx : -dx) / pps, 0, item.dur / 2), 0.04);
				if (edge === 'in') item.fadeIn = v;
				else item.fadeOut = v;
				setDragText(edge === 'in' ? t('timeline.drag.fadeIn', { dur: secs(v) }) : t('timeline.drag.fadeOut', { dur: secs(v) }));
			}
		});
	}

	function clipDown(e, c) {
		if (ui.tool === 'blade') {
			select('clip', c.id);
			return bladeAt(timeAt(e.clientX));
		}
		select('clip', c.id);
		drag(e, {
			onMove: (dx, dy, ev) => {
				const at = timeAt(ev.clientX);
				const others = doc.clips.filter((o) => o.id !== c.id);
				const index = others.filter((o) => o.start + o.dur / 2 < at).length;
				reorder = { id: c.id, dx, index, at: index < others.length ? others[index].start : total };
				setDragText(t('timeline.drag.position', { n: index + 1 }));
			},
			onCancel: () => (reorder = null),
			onEnd: () => {
				if (!reorder) return;
				const from = doc.clips.findIndex((o) => o.id === c.id);
				const [moved] = doc.clips.splice(from, 1);
				doc.clips.splice(reorder.index, 0, moved);
				relayout();
				reorder = null;
			}
		});
	}
	function clipTrim(e, c, edge) {
		select('clip', c.id);
		const max = sourceLength(c);
		const d0 = c.dur;
		const in0 = c.srcIn;
		drag(e, {
			onMove: (dx) => {
				const dt = dx / pps;
				let limit = false;
				if (edge === 'start') {
					const nIn = clamp(in0 + dt, 0, in0 + d0 - 0.4);
					limit = nIn <= 0.001;
					c.srcIn = round(nIn, 0.04);
					c.dur = round(d0 - (nIn - in0), 0.04);
				} else {
					const nd = clamp(d0 + dt, 0.4, max - in0);
					limit = nd >= max - in0 - 0.001;
					c.dur = round(nd, 0.04);
				}
				relayout();
				setDragText(limit ? t('timeline.drag.sourceLimitAt', { dur: secs(max) }) : t('timeline.drag.rippled', { dur: secs(c.dur) }), limit);
			}
		});
	}

	function frameDown(e, f) {
		select('frame', f.id);
		const t0 = f.time;
		drag(e, {
			onMove: (dx) => {
				const r = snap(Math.max(0, t0 + dx / pps), f.id);
				f.time = r.t;
				if (ui.drag) ui.drag.at = r.at;
				setDragText(t('timeline.drag.frame', { time: secs(f.time) }));
			},
			onEnd: () => relinkAfter(f)
		});
	}

	function keyDown(e, plan, k) {
		selectKey(plan, k, false);
		const t0 = k.t;
		drag(e, {
			onMove: (dx) => {
				editKey(k, { t: round(clamp(t0 + dx / pps, 0, plan.dur), 0.04) });
				plan.keyframes.sort((a, b) => a.t - b.t);
				setDragText(t('timeline.drag.keyframe', { time: secs(plan.start + k.t) }));
			}
		});
	}

	function markerDown(e, m) {
		const t0 = m.time;
		drag(e, {
			onMove: (dx) => {
				m.time = round(Math.max(0, t0 + dx / pps), 0.04);
				setDragText(t('timeline.drag.marker', { label: m.label, time: secs(m.time) }));
			},
			onClick: () => seek(m.time)
		});
	}

	function onDrop(e, row) {
		e.preventDefault();
		const id = e.dataTransfer.getData('text/x-asset');
		const a = asset(id);
		if (!a) return;
		const at = round(timeAt(e.clientX), 0.04);
		if (row.id === 'frames' && a.kind !== 'audio') return addFrame(id, at);
		if (row.lane && a.kind === 'audio') {
			act(() => doc.audio.push({ id: ulid(), assetId: id, lane: row.id, start: at, dur: Math.min(8, a.srcDur ?? 8), srcIn: 0, fadeIn: 0.5, fadeOut: 0.5, gain: -6 }));
			return toast(t('timeline.toast.dropped', { name: a.name, lane: row.id }));
		}
		if (row.id === 'v1' && a.kind !== 'audio') return addAssetToTimeline(id, at);
		toast(t('timeline.toast.dropHint'), 'warning');
	}

	function wheel(e) {
		if (!(e.ctrlKey || e.metaKey)) return;
		e.preventDefault();
		const at = timeAt(e.clientX);
		const before = e.clientX - scroller.getBoundingClientRect().left - HEAD;
		ui.pxPerSec = clamp(ui.pxPerSec * wheelZoomFactor(e), 8, 220);
		requestAnimationFrame(() => scroller && (scroller.scrollLeft = at * ui.pxPerSec - before));
	}
	function fit() {
		ui.pxPerSec = clamp((viewW - HEAD - 24) / total, 8, 220);
		scroller.scrollLeft = 0;
	}

	$effect(() => {
		if (!ui.playing || !scroller) return;
		const px = x(ui.playhead);
		if (px > scroller.scrollLeft + viewW - HEAD - 40 || px < scroller.scrollLeft) scroller.scrollLeft = px - 40;
	});

	$effect(() => cancelDrag);

	function blockKind(kind) {
		if (kind === 'prompt') return t('timeline.kind.prompt');
		if (kind === 'title') return t('timeline.kind.title');
		if (kind === 'control') return t('timeline.kind.control');
		return t('timeline.kind.plan3d');
	}

	const flagIcon = { favori: 'star', rejet: 'thumb-down' };
</script>

<div class="isolate flex h-full flex-col bg-surface-1">
	<div class="flex h-10 shrink-0 items-center gap-1 border-b border-line px-2" role="toolbar" aria-label={t('timeline.toolbar')}>
		<HostUi name="IconButton" props={{ icon: hostIconName('undo'), label: t('timeline.undo'), size: 'sm', class: 'vp-h7', disabled: !history.canUndo, kbd: key('undo'), onclick: undo }} />
		<HostUi name="IconButton" props={{ icon: hostIconName('redo'), label: t('timeline.redo'), size: 'sm', class: 'vp-h7', disabled: !history.canRedo, kbd: key('redo'), onclick: redo }} />
		<div class="vp-divider"></div>
		<div class="vp-seg" role="group" aria-label={t('timeline.tool.group')}>
			{#each tools as tool (tool.id)}
				<HostUi
					name="IconButton"
					props={{ icon: hostIconName(tool.icon), label: tool.label, size: 'xs', ariaPressed: ui.tool === tool.id, tooltip: tool.label, kbd: tool.keys, onclick: () => (ui.tool = tool.id) }}
				/>
			{/each}
		</div>
		<HostUi name="IconButton" props={{ icon: 'scissors', label: t('timeline.blade'), size: 'sm', class: 'vp-h7', kbd: key('blade'), onclick: () => bladeAt() }} />
		<HostUi name="IconButton" props={{ icon: 'copy', label: t('timeline.duplicate'), size: 'sm', class: 'vp-h7', disabled: !ui.selection, kbd: key('duplicate'), onclick: duplicateSelection }} />
		<HostUi name="IconButton" props={{ icon: 'trash', label: t('timeline.delete'), size: 'sm', class: 'vp-h7', disabled: !ui.selection, kbd: key('delete'), onclick: deleteSelection }} />
		<div class="vp-divider"></div>
		<Dropdown label={t('timeline.add.label')} title={t('timeline.add.tip')} items={addItems} />
		<div class="flex-1"></div>
		<HostUi
			name="IconButton"
			props={{ icon: hostIconName('magnet'), label: t('timeline.snapping'), size: 'sm', class: 'vp-h7 vp-toggle', ariaPressed: ui.snapping, kbd: key('snap'), onclick: () => (ui.snapping = !ui.snapping) }}
		/>
		<HostUi name="IconButton" props={{ icon: 'minus', label: t('timeline.zoomOut'), size: 'sm', class: 'vp-h7', kbd: key('zoom-out'), onclick: () => (ui.pxPerSec = Math.max(8, ui.pxPerSec / 1.25)) }} />
		<input class="vp-slider w-24" type="range" min="8" max="220" bind:value={ui.pxPerSec} aria-label={t('timeline.zoom')} />
		<HostUi name="IconButton" props={{ icon: 'plus', label: t('timeline.zoomIn'), size: 'sm', class: 'vp-h7', kbd: key('zoom-in'), onclick: () => (ui.pxPerSec = Math.min(220, ui.pxPerSec * 1.25)) }} />
		<HostUi name="Tooltip" props={{ text: t('timeline.fitTip') }}>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: fit }}>{t('timeline.fit')}</HostUi>
		</HostUi>
	</div>

	<div class="relative min-h-0 flex-1 overflow-auto" bind:this={scroller} bind:clientWidth={viewW} onwheel={wheel} style:overscroll-behavior-x="contain" style:cursor={ui.tool === 'blade' ? 'crosshair' : ui.tool === 'range' ? 'col-resize' : 'default'}>
		<div class="relative" style:width="{HEAD + contentW}px">
			<div class="sticky top-0 z-40 flex h-7 border-b border-line bg-surface-1">
				<div class="sticky left-0 z-50 flex w-[156px] shrink-0 items-center border-r border-line bg-surface-1 px-3 text-xs text-fg-subtle">{doc.name}</div>
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div class="relative flex-1 cursor-text vp-touch-none" onpointerdown={rulerDown}>
					{#each ticks as tick (tick)}
						<div class="absolute bottom-0 h-2 w-px bg-viz-axis" style:left="{x(tick)}px"></div>
						<span class="vp-tc absolute top-1 pl-1 text-2xs text-fg-subtle" style:left="{x(tick)}px">{tickLabel(tick)}</span>
						{#each [1, 2, 3, 4] as k (k)}<div class="absolute bottom-0 h-1 w-px bg-viz-grid" style:left="{x(tick + (step * k) / 5)}px"></div>{/each}
					{/each}
					{#if ui.range}
						<div class="absolute inset-y-0 bg-signal/25" style:left="{x(ui.range.in)}px" style:width="{x(ui.range.out - ui.range.in)}px"></div>
					{/if}
					{#each doc.markers as m (m.id)}
						<div class="absolute top-0 -ml-3" style:left="{x(m.time)}px">
							<HostUi name="Tooltip" props={{ text: t('timeline.marker.tip', { label: m.label, time: secs(m.time) }), position: 'bottom', wrapperClass: 'flex' }}>
								<button
									type="button"
									class="vp-touch-none flex h-6 w-6 justify-center {m.kind === 'favori' ? 'text-success' : m.kind === 'rejet' ? 'text-danger' : 'text-warning'}"
									aria-label={t('timeline.marker.label', { label: m.label })}
									onpointerdown={(e) => markerDown(e, m)}
									ondblclick={() => select('marker', m.id)}
									onkeydown={(e) => e.key === 'Enter' && (seek(m.time), select('marker', m.id))}
								>
									<svg viewBox="0 0 12 16" class="h-4 w-3" aria-hidden="true"><path d="M0 0h12v11l-6 5-6-5z" fill="currentColor" /></svg>
								</button>
							</HostUi>
						</div>
					{/each}
					<div class="pointer-events-none absolute -top-px z-10 -ml-[6px]" style:left="{x(ui.playhead)}px">
						<svg viewBox="0 0 12 14" class="h-3.5 w-3 text-fg" aria-hidden="true"><path d="M0 0h12v8l-6 6-6-6z" fill="currentColor" /></svg>
					</div>
				</div>
			</div>

			{#each rows as row (row.id)}
				<div class="flex border-b border-line/70" style:height="{row.h}px">
					<div class="sticky left-0 z-30 flex w-[156px] shrink-0 items-center gap-2 border-r border-line bg-surface-1 pl-0 pr-1.5">
						<span class="h-full w-[3px] {row.color ? '' : 'bg-line-hover'}" style:background={row.color ? `rgb(var(--${row.color}))` : null}></span>
						<Icon name={row.icon} class="h-3.5 w-3.5 shrink-0 text-fg-subtle" />
						<span class="flex-1 truncate text-xs text-fg-muted" title={row.label}>{row.label}</span>
						{#if row.lane}
							<button
								type="button"
								class="h-6 w-6 rounded-sm text-2xs font-semibold {row.lane.mute ? 'bg-warning text-black' : 'bg-surface-2 text-fg-muted hover:text-fg'}"
								aria-pressed={row.lane.mute}
								onclick={() => (row.lane.mute = !row.lane.mute)}
								title={t('timeline.lane.mute')}
								aria-label={t('timeline.lane.muteLabel', { lane: row.label })}>{t('timeline.lane.muteShort')}</button
							>
							<button
								type="button"
								class="h-6 w-6 rounded-sm text-2xs font-semibold {row.lane.solo ? 'bg-signal text-accent-contrast' : 'bg-surface-2 text-fg-muted hover:text-fg'}"
								aria-pressed={row.lane.solo}
								onclick={() => (row.lane.solo = !row.lane.solo)}
								title={t('timeline.lane.solo')}
								aria-label={t('timeline.lane.soloLabel', { lane: row.label })}>{t('timeline.lane.soloShort')}</button
							>
						{/if}
					</div>

					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div
						class="relative flex-1 {row.id === 'v1' ? 'bg-canvas/60' : ''}"
						class:vp-touch-none={ui.tool === 'range'}
						data-lane={row.lane ? row.id : null}
						onpointerdown={laneDown}
						ondblclick={(e) => laneDbl(e, row)}
						ondragover={(e) => e.preventDefault()}
						ondrop={(e) => onDrop(e, row)}
					>
						{#if row.id === 'titles'}
							{#each doc.titles as ti (ti.id)}
								{@render block('title', ti, ti.text, null)}
							{/each}
						{:else if row.id === 'prompts'}
							{#each doc.prompts as p (p.id)}
								{@render block('prompt', p, p.text || t('timeline.prompt.empty'), row.color, promptIssues(p))}
							{/each}
							{#if !doc.prompts.length}
								<span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-fg-subtle">{t('timeline.prompt.hint')}</span>
							{/if}
						{:else if row.id === 'frames'}
							{#each doc.frames as f (f.id)}
								{@const fthumb = assetThumb(asset(f.assetId))}
								<button
									type="button"
									class="vp-touch-none group absolute top-1 flex h-[26px] -translate-x-1/2 items-center gap-1 rounded border bg-surface-2 pl-0.5 pr-1.5 {isSel('frame', f.id) ? 'z-10 border-signal ring-1 ring-signal' : 'border-line-hover'}"
									style:left="{x(f.time)}px"
									style:border-left={`3px solid rgb(var(--${row.color}))`}
									title={t('timeline.frame.tip', { role: frameRoleLabel(f.role), time: secs(f.time), strength: f.strength })}
									onpointerdown={(e) => frameDown(e, f)}
									onkeydown={(e) => e.key === 'Enter' && select('frame', f.id)}
								>
									{#if fthumb}
									<img src={fthumb} alt="" class="h-5 w-7 rounded-sm object-cover" draggable="false" />
								{:else}
									<span class="flex h-5 w-7 items-center justify-center rounded-sm bg-surface-3 text-fg-muted"><Icon name={f.sceneId || f.role === 'Capture 3D' ? 'cube' : 'image'} class="h-3 w-3" /></span>
								{/if}
									{#if f.sceneId}<Icon name="cube" class="h-3 w-3 shrink-0 text-fg-muted" />{/if}
									<span class="text-xs text-fg-muted">{frameRoleLabel(f.role)}</span>
								</button>
							{/each}
						{:else if row.id === 'controls'}
							{#each doc.controls as c (c.id)}
								{@render block('control', c, c.name, row.color, c.stale ? [{ level: 'stale', text: t('timeline.control.stale') }] : [])}
							{/each}
						{:else if row.id === 'plans3d'}
							{#each doc.plans3d as s (s.id)}
								{@render block('plan3d', s, s.name, row.color, [], keyed ? KEY_BAND + 2 : null)}
								{#each s.source === 'blender' ? [] : s.keyframes as k (k.id)}
									<button
										type="button"
										tabindex="-1"
										class="vp-touch-none absolute top-0 z-20 -ml-3 flex h-6 w-6 items-center justify-center"
										style:left="{x(s.start + k.t)}px"
										title={t('timeline.keyframe.tip', { time: secs(s.start + k.t) })}
										aria-label={t('timeline.keyframe.label', { time: secs(s.start + k.t) })}
										onpointerdown={(e) => keyDown(e, s, k)}
									><span class="h-3 w-3 rotate-45 border {ui.scene.keyframe === k.id ? 'border-white bg-signal' : 'border-black/40 bg-fg'}"></span></button>
								{/each}
							{/each}
						{:else if row.id === 'v1'}
							{#each doc.clips as c (c.id)}
								{@render clip(c)}
							{/each}
							{#if reorder}
								<div class="absolute inset-y-0 z-20 w-0.5 bg-signal" style:left="{x(reorder.at)}px"></div>
							{/if}
						{:else if row.lane}
							{#each doc.audio.filter((a) => a.lane === row.id) as a (a.id)}
								{@render audioClip(a, row)}
							{/each}
						{/if}
					</div>
				</div>
			{/each}

			<div class="pointer-events-none absolute bottom-0 top-7" style:left="{HEAD}px" style:width="{contentW}px">
				{#if ui.range}
					<div class="absolute inset-y-0 border-x border-signal bg-signal/10" style:left="{x(ui.range.in)}px" style:width="{x(ui.range.out - ui.range.in)}px"></div>
				{/if}
				{#if ui.drag?.at != null}
					<div class="absolute inset-y-0 w-px bg-warning" style:left="{x(ui.drag.at)}px"></div>
				{/if}
				<div class="absolute inset-y-0 w-px bg-fg" style:left="{x(ui.playhead)}px"></div>
			</div>
		</div>
	</div>
</div>

{#if ui.drag?.text}
	<div
		class="pointer-events-none fixed rounded border bg-surface-3 px-2 py-1 text-xs shadow-floating {ui.drag.limit ? 'border-danger text-danger' : 'border-line-strong text-fg'}"
		style:left="{ui.drag.x + 14}px"
		style:top="{ui.drag.y - 30}px"
		use:overlayLayer={'tooltip'}
	>
		{ui.drag.text}
	</div>
{/if}

{#snippet fades(item, kind, w, h, light = false)}
	<svg class="pointer-events-none absolute inset-0" width={w} height={h} aria-hidden="true">
		{#if item.fadeIn > 0}
			<polygon points="0,0 {x(item.fadeIn)},0 0,{h}" fill="rgb(0 0 0 / {light ? 0.35 : 0.5})" />
			<line x1="0" y1={h} x2={x(item.fadeIn)} y2="0" stroke="rgb(255 255 255 / 0.7)" />
		{/if}
		{#if item.fadeOut > 0}
			<polygon points="{w},0 {w - x(item.fadeOut)},0 {w},{h}" fill="rgb(0 0 0 / {light ? 0.35 : 0.5})" />
			<line x1={w} y1={h} x2={w - x(item.fadeOut)} y2="0" stroke="rgb(255 255 255 / 0.7)" />
		{/if}
	</svg>
	<button
		type="button"
		tabindex="-1"
		class="vp-hit absolute top-1.5 z-[25] -ml-[5px] h-2.5 w-2.5 rounded-full border border-black/50 bg-white opacity-0 group-hover:opacity-100 {isSel(kind, item.id) ? 'opacity-100' : ''}"
		style:left="{fadeX(x(item.fadeIn), w)}px"
		aria-label={t('timeline.fade.in')}
		title={t('timeline.fade.inTip', { dur: secs(item.fadeIn) })}
		onpointerdown={(e) => fadeDrag(e, kind, item, 'in')}
	></button>
	<button
		type="button"
		tabindex="-1"
		class="vp-hit absolute top-1.5 z-[25] -ml-[5px] h-2.5 w-2.5 rounded-full border border-black/50 bg-white opacity-0 group-hover:opacity-100 {isSel(kind, item.id) ? 'opacity-100' : ''}"
		style:left="{fadeX(w - x(item.fadeOut), w)}px"
		aria-label={t('timeline.fade.out')}
		title={t('timeline.fade.outTip', { dur: secs(item.fadeOut) })}
		onpointerdown={(e) => fadeDrag(e, kind, item, 'out')}
	></button>
{/snippet}

{#snippet clip(c)}
	{@const thumb = clipThumb(c)}
	{@const media = asset(c.assetId)}
	{@const w = x(c.dur)}
	{@const sel = isSel('clip', c.id)}
	{@const takes = takesOf(c).length}
	<div
		class="vp-touch-none group absolute bottom-1 top-1 overflow-hidden rounded border {sel ? 'z-10 border-signal ring-1 ring-signal' : 'border-black/40'} {reorder?.id === c.id ? 'opacity-60' : ''}"
		style:left="{x(c.start)}px"
		style:width="{w}px"
		style:transform={reorder?.id === c.id ? `translateX(${reorder.dx}px)` : null}
		style:background="rgb(var(--viz-1) / 0.35)"
		onpointerdown={(e) => clipDown(e, c)}
		ondblclick={() => (ui.inspectorOpen = true)}
		role="button"
		tabindex="0"
		aria-label={t('timeline.clip.label', { name: clipLabel(c), stage: stages[c.stage].label, dur: secs(c.dur) })}
		onkeydown={(e) => e.key === 'Enter' && select('clip', c.id)}
	>
		{#if thumb}
			<div class="absolute inset-x-0 bottom-0 top-5 bg-repeat-x" style:background-image="url({thumb})" style:background-size="auto 100%" style:filter={clipFilter(c)}></div>
		{:else}
			<div class="absolute inset-x-0 bottom-0 top-5 bg-surface-2 bg-[repeating-linear-gradient(135deg,rgb(var(--viz-1)/0.35)_0_1px,transparent_1px_8px)]"></div>
			{#if !media?.src}<span class="absolute bottom-1.5 left-1.5 text-2xs text-fg-muted">{media ? t('lib.media.offline') : stages.todo.label}</span>{/if}
		{/if}
		<div class="vp-clip-head absolute inset-x-0 top-0 flex h-5 items-center gap-1 bg-viz-1 px-1.5 text-xs font-semibold">
			<span class="h-1.5 w-1.5 shrink-0 rounded-full {stages[c.stage].dot}" title={stages[c.stage].label}></span>
			{#if c.flag}<Icon name={flagIcon[c.flag]} class="h-3 w-3" />{/if}
			<span class="truncate">{clipLabel(c)}</span>
			{#if takes > 1 && w > 120}<span class="ml-auto shrink-0 rounded-sm border border-current/40 px-1 text-2xs">{t('timeline.clip.takes', { count: takes })}</span>{/if}
		</div>
		{@render fades(c, 'clip', w, 52)}
		<button
			type="button"
			tabindex="-1"
			class="vp-hit vp-edge-start absolute inset-y-0 left-0 z-20 w-2 cursor-ew-resize hover:bg-warning {sel ? 'bg-warning/70' : ''}"
			aria-label={t('timeline.trim.start')}
			title={t('timeline.trim.start')}
			onpointerdown={(e) => clipTrim(e, c, 'start')}
		></button>
		<button
			type="button"
			tabindex="-1"
			class="vp-hit vp-edge-end absolute inset-y-0 right-0 z-20 w-2 cursor-ew-resize hover:bg-warning {sel ? 'bg-warning/70' : ''}"
			aria-label={t('timeline.trim.end')}
			title={t('timeline.trim.end')}
			onpointerdown={(e) => clipTrim(e, c, 'end')}
		></button>
	</div>
{/snippet}

{#snippet audioClip(a, row)}
	{@const src = asset(a.assetId)}
	{@const w = x(a.dur)}
	{@const peaks = audioPeaks(src)}
	{@const sel = isSel('audio', a.id)}
	<div
		class="vp-touch-none group absolute bottom-1 top-1 overflow-hidden rounded border {sel ? 'z-10 border-signal ring-1 ring-signal' : 'border-black/30'} {row.lane.mute ? 'opacity-40' : ''}"
		style:left="{x(a.start)}px"
		style:width="{w}px"
		style:background="rgb(var(--{row.color}) / 0.28)"
		onpointerdown={(e) => moveBlock(e, 'audio', a)}
		role="button"
		tabindex="0"
		aria-label={t('timeline.audio.label', { name: src?.name ?? '', dur: secs(a.dur) })}
		onkeydown={(e) => e.key === 'Enter' && select('audio', a.id)}
	>
		<svg class="absolute inset-x-0 bottom-0" width={w} height="22" aria-hidden="true">
			<polygon points={src?.src ? (peaks ? peakWaveform(peaks, w, 22, a.srcIn, pps) : '') : waveform(a.assetId, w, 22, a.srcIn, pps, src?.synth)} fill="rgb(var(--{row.color}))" opacity="0.85" />
		</svg>
		<div class="absolute left-1.5 top-0.5 truncate text-xs font-medium text-fg">{src?.name}</div>
		{@render fades(a, 'audio', w, 30, true)}
		<button
			type="button"
			tabindex="-1"
			class="vp-hit vp-edge-start absolute inset-y-0 left-0 z-20 w-2 cursor-ew-resize hover:bg-warning {sel ? 'bg-warning/70' : ''}"
			aria-label={t('timeline.trim.start')}
			title={t('timeline.trim.start')}
			onpointerdown={(e) => trimBlock(e, 'audio', a, 'start')}
		></button>
		<button
			type="button"
			tabindex="-1"
			class="vp-hit vp-edge-end absolute inset-y-0 right-0 z-20 w-2 cursor-ew-resize hover:bg-warning {sel ? 'bg-warning/70' : ''}"
			aria-label={t('timeline.trim.end')}
			title={t('timeline.trim.end')}
			onpointerdown={(e) => trimBlock(e, 'audio', a, 'end')}
		></button>
	</div>
{/snippet}

{#snippet block(kind, item, label, color, issues = [], top = null)}
	{@const sel = isSel(kind, item.id)}
	{@const warn = issues.filter((i) => i.level !== 'missing')}
	<div
		class="vp-touch-none group absolute bottom-0.5 top-0.5 flex items-center gap-1 overflow-hidden rounded border px-2 text-xs {sel ? 'z-10 border-signal ring-1 ring-signal' : 'border-line-hover'} {color ? 'text-fg' : 'bg-surface-3 text-fg'}"
		style:left="{x(item.start)}px"
		style:top={top === null ? null : `${top}px`}
		style:width="{Math.max(6, x(item.dur))}px"
		style:background={color ? `rgb(var(--${color}) / ${kind === 'control' ? 0.22 : 0.3})` : null}
		style:background-image={kind === 'control' ? `repeating-linear-gradient(135deg, transparent 0 6px, rgb(var(--${color}) / 0.25) 6px 8px)` : null}
		onpointerdown={(e) => moveBlock(e, kind, item)}
		ondblclick={() => kind === 'prompt' && (ui.modal = { type: 'prompt', id: item.id })}
		role="button"
		tabindex="0"
		aria-label={t('timeline.block.label', { kind: blockKind(kind), label })}
		onkeydown={(e) => e.key === 'Enter' && (kind === 'prompt' ? (ui.modal = { type: 'prompt', id: item.id }) : select(kind, item.id))}
		title={warn.length ? warn.map((i) => i.text).join('\n') : kind === 'prompt' ? t('timeline.block.editTip') : label}
	>
		{#if warn.length}<Icon name="alert" class="h-3.5 w-3.5 shrink-0 text-warning" />{/if}
		<span class="truncate {item.text === '' ? 'italic text-fg-muted' : ''}">{label}</span>
		{#if kind === 'prompt'}<span class="ml-auto shrink-0 text-fg">{t('timeline.block.percent', { value: item.strength })}</span>{/if}
		{#if kind === 'control'}<span class="ml-auto shrink-0 text-fg">{t('timeline.block.percent', { value: item.guidance })}</span>{/if}
		<button
			type="button"
			tabindex="-1"
			class="vp-hit vp-edge-start absolute inset-y-0 left-0 w-2 cursor-ew-resize hover:bg-warning {sel ? 'bg-warning/70' : ''}"
			aria-label={t('timeline.trim.start')}
			onpointerdown={(e) => trimBlock(e, kind, item, 'start')}
		></button>
		<button
			type="button"
			tabindex="-1"
			class="vp-hit vp-edge-end absolute inset-y-0 right-0 w-2 cursor-ew-resize hover:bg-warning {sel ? 'bg-warning/70' : ''}"
			aria-label={t('timeline.trim.end')}
			onpointerdown={(e) => trimBlock(e, kind, item, 'end')}
		></button>
	</div>
{/snippet}

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, clipLabel } from '../../lib/state.svelte.js';
	import { REFINE, REMIX, STRENGTHS, PROMPT_LIMIT, overLimit, shareOf, touchesEnd } from '../../lib/retouch.js';
	import { retouch, retouchTake, retouchOffer, retouchBlock, blockText, closeRetouch, setTask, setEdge, startRetouch, rangeSecs as secs } from '../../lib/retouch.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let { video = null } = $props();

	const take = $derived(retouchTake());
	const offer = $derived(retouchOffer());
	const range = $derived(retouch.range);
	const duration = $derived(take?.durationS ?? 0);
	const selection = $derived(shareOf(range, duration));
	const over = $derived(range ? overLimit(offer, range) : null);
	const overShare = $derived(over ? shareOf(over, duration) : null);
	const block = $derived(retouchBlock());
	const shot = $derived(take ? doc.clips.find((c) => c.id === take.shotId) : null);
	const following = $derived(shot ? doc.clips[doc.clips.indexOf(shot) + 1] : null);
	const seam = $derived(Boolean(range && touchesEnd(range) && following?.firstFromPrevious && shot?.take === take?.id));
	const ticks = $derived(Array.from({ length: Math.floor(duration) + 1 }, (_, i) => i));
	const tasks = $derived([
		{ id: REFINE, label: t('generation.retouch.task.refine') },
		{ id: REMIX, label: t('generation.retouch.task.remix') }
	]);
	const strengths = $derived(STRENGTHS.map((id) => ({ id, label: id === 'light' ? t('generation.retouch.strength.light') : id === 'strong' ? t('generation.retouch.strength.strong') : t('generation.retouch.strength.balanced') })));

	let strip = $state();
	let dragging = $state(null);

	function timeAt(event) {
		const box = strip.getBoundingClientRect();
		return Math.min(Math.max((event.clientX - box.left) / Math.max(1, box.width), 0), 1) * duration;
	}

	function seek(time) {
		retouch.time = time;
		if (video && Math.abs(video.currentTime - time) > 0.01) video.currentTime = time;
	}

	function press(event, edge = null) {
		event.preventDefault();
		strip.setPointerCapture?.(event.pointerId);
		dragging = edge;
		const time = timeAt(event);
		if (edge) setEdge(edge, time);
		seek(edge === 'out' ? Math.max(0, time - 1 / (take?.fps || 24)) : time);
	}

	function move(event) {
		if (!dragging) return;
		const time = timeAt(event);
		setEdge(dragging, time);
		seek(dragging === 'out' ? Math.max(0, time - 1 / (take?.fps || 24)) : time);
	}

	function release() {
		dragging = null;
	}

	function nudge(event, edge) {
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
		event.preventDefault();
		const step = (event.key === 'ArrowLeft' ? -1 : 1) / (take?.fps || 24);
		setEdge(edge, (edge === 'in' ? range.start : range.end) + step);
	}

	$effect(() => {
		const el = video;
		if (!el || !range) return;
		el.loop = false;
		const onTime = () => {
			retouch.time = el.currentTime;
			if (el.currentTime >= retouch.range.end - 0.01 || el.currentTime < retouch.range.start - 0.05) el.currentTime = retouch.range.start;
		};
		el.addEventListener('timeupdate', onTime);
		return () => el.removeEventListener('timeupdate', onTime);
	});

	function keys(event) {
		if (event.key === 'Escape') {
			event.stopPropagation();
			closeRetouch();
		} else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
			event.preventDefault();
			startRetouch();
		}
	}
</script>

{#if take && range}
	<div class="space-y-2 border-t border-line bg-surface-1 px-3 pb-2.5 pt-2" role="region" aria-label={t('generation.retouch.title')} data-retouch-bar onkeydown={keys}>
		<div class="flex min-w-0 items-center gap-2">
			<Icon name="wand" class="h-4 w-4 shrink-0 text-fg-muted" />
			<span class="shrink-0 text-sm font-medium text-fg">{t('generation.retouch.title')}</span>
			<span class="vp-tc truncate rounded-sm border border-line-strong px-1.5 text-2xs {over ? 'text-warning' : 'text-fg-muted'}" data-retouch-range>{t('generation.retouch.range', { start: secs(range.start), end: secs(range.end), length: secs(range.seconds), frames: range.frames })}</span>
			<span class="hidden truncate text-xs text-fg-subtle lg:inline">{t('generation.retouch.keeps', { variant: take.variant })}</span>
			<span class="flex-1"></span>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('x'), onclick: closeRetouch }}>{t('generation.retouch.close')}</HostUi>
		</div>
		<div>
			<div
				bind:this={strip}
				class="relative h-10 cursor-pointer touch-none overflow-hidden rounded border border-line bg-surface-2"
				role="presentation"
				onpointerdown={(e) => press(e)}
				onpointermove={move}
				onpointerup={release}
				onpointercancel={release}
			>
				<div class="absolute inset-y-0 bg-signal/20" style:left="{selection.left}%" style:width="{selection.width}%"></div>
				{#if overShare}<div class="vp-retouch-over absolute inset-y-0" style:left="{overShare.left}%" style:width="{overShare.width}%"></div>{/if}
				<button type="button" class="absolute inset-y-0 w-2 -translate-x-1/2 cursor-ew-resize rounded-sm bg-signal" style:left="{selection.left}%" aria-label={t('generation.retouch.in')} title={t('generation.retouch.inTip')} onpointerdown={(e) => (e.stopPropagation(), press(e, 'in'))} onkeydown={(e) => nudge(e, 'in')}></button>
				<button type="button" class="absolute inset-y-0 w-2 -translate-x-1/2 cursor-ew-resize rounded-sm bg-signal" style:left="{selection.left + selection.width}%" aria-label={t('generation.retouch.out')} title={t('generation.retouch.outTip')} onpointerdown={(e) => (e.stopPropagation(), press(e, 'out'))} onkeydown={(e) => nudge(e, 'out')}></button>
				<div class="pointer-events-none absolute inset-y-0 w-px bg-fg" style:left="{duration ? (retouch.time / duration) * 100 : 0}%"></div>
			</div>
			<div class="vp-tc relative mt-0.5 h-3 text-2xs text-fg-subtle">
				{#each ticks as second (second)}<span class="absolute -translate-x-1/2" style:left="{duration ? (second / duration) * 100 : 0}%">{second} s</span>{/each}
			</div>
		</div>
		<div class="flex flex-wrap items-end gap-3">
			<div class="space-y-1">
				<div class="text-2xs text-fg-subtle">{t('generation.retouch.task.label')}</div>
				<HostUi name="SegmentedControl" props={{ variant: 'toggle', ariaLabel: t('generation.retouch.task.label'), items: tasks, selected: retouch.task, onSelect: setTask }} />
			</div>
			<label class="space-y-1">
				<span class="block text-2xs text-fg-subtle">{t('generation.retouch.engine')}</span>
				<select class="vp-popup" value={retouch.presetId ?? ''} disabled={!offer?.engines.length} onchange={(e) => (retouch.presetId = e.currentTarget.value || null)}>
					{#each offer?.engines ?? [] as engine (engine.presetId)}<option value={engine.presetId}>{engine.name}</option>{/each}
				</select>
			</label>
			{#if retouch.task === REFINE}
				<div class="space-y-1">
					<div class="text-2xs text-fg-subtle">{t('generation.retouch.strength.label')}</div>
					<HostUi name="SegmentedControl" props={{ variant: 'toggle', ariaLabel: t('generation.retouch.strength.label'), items: strengths, selected: retouch.strength, onSelect: (id) => (retouch.strength = id) }} />
				</div>
				<div class="flex items-center gap-3 pb-1">
					<HostUi name="Switch" props={{ id: 'vp-retouch-faces', checked: retouch.faces, size: 'lg', label: t('generation.retouch.faces'), onchange: (v) => (retouch.faces = Boolean(v)) }} />
					<label for="vp-retouch-faces" class="text-xs text-fg-muted">{t('generation.retouch.faces')}</label>
					<HostUi name="Switch" props={{ id: 'vp-retouch-hands', checked: retouch.hands, size: 'lg', label: t('generation.retouch.hands'), onchange: (v) => (retouch.hands = Boolean(v)) }} />
					<label for="vp-retouch-hands" class="text-xs text-fg-muted">{t('generation.retouch.hands')}</label>
				</div>
			{:else}
				<label class="min-w-0 flex-1 space-y-1">
					<span class="block text-2xs text-fg-subtle">{t('generation.retouch.prompt')}</span>
					<input class="input vp-dense w-full" maxlength={PROMPT_LIMIT} bind:value={retouch.prompt} placeholder={t('generation.retouch.promptHint')} />
				</label>
			{/if}
			<span class="flex-1"></span>
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('wand'), disabled: Boolean(block) || retouch.busy, loading: retouch.busy, onclick: startRetouch }}>{t('generation.retouch.start')}</HostUi>
		</div>
		{#if block && block !== 'loading'}
			<p class="flex items-start gap-2 rounded bg-warning/10 px-2 py-1 text-xs text-warning" data-retouch-block={block}><Icon name="alert" class="mt-0.5 h-3 w-3 shrink-0" />{blockText(block)}</p>
		{/if}
		{#if seam}
			<p class="flex items-start gap-2 rounded bg-signal/10 px-2 py-1 text-xs text-signal" data-retouch-seam><Icon name="info" class="mt-0.5 h-3 w-3 shrink-0" />{t('generation.retouch.seam', { variant: take.variant, shot: clipLabel(following) })}</p>
		{/if}
		<p class="flex flex-wrap items-center gap-x-3 text-xs text-fg-muted">
			<span>{t('generation.retouch.result', { shot: shot ? clipLabel(shot) : '—' })}</span>
			<span class="flex-1"></span>
			<span>{retouch.task === REMIX ? t('generation.retouch.keepsSoundRemix') : t('generation.retouch.keepsSound')}</span>
		</p>
	</div>
{/if}

<style>
	.vp-retouch-over {
		background: repeating-linear-gradient(135deg, rgb(var(--warning) / 0.3) 0 6px, rgb(var(--warning) / 0.1) 6px 12px);
		border-left: 1px dashed rgb(var(--warning));
	}
</style>

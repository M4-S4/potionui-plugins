<script>
	import { flip } from 'svelte/animate';
	import { fade } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { getLocale, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, select, act, secs, clipLabel, addShot, moveClip, seqDuration, deleteSelection, promptOf, ensurePrompt } from '../../lib/state.svelte.js';
	import { takesOf, startGeneration, promoteToFinal, shotActivity } from '../../lib/production.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { clipFilter } from '../../lib/look.js';
	import { clipThumb } from '../../lib/media.js';
	import { stages } from '../../lib/catalog.js';
	import { seam } from '../../lib/continuity.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let size = $state('m');
	let dragId = $state(null);
	let overIdx = $state(null);
	let countsEl = $state();
	let compact = $state(false);
	let fullWidth = 0;
	const cols = { s: 'grid-cols-[repeat(auto-fill,minmax(164px,1fr))]', m: 'grid-cols-[repeat(auto-fill,minmax(220px,1fr))]', l: 'grid-cols-[repeat(auto-fill,minmax(320px,1fr))]' };
	const sizes = $derived([
		{ id: 's', label: t('storyboard.size.small'), cls: 'vp-icon-s' },
		{ id: 'm', label: t('storyboard.size.medium'), cls: '' },
		{ id: 'l', label: t('storyboard.size.large'), cls: 'vp-icon-l' }
	]);

	const counts = $derived(Object.keys(stages).map((k) => [k, doc.clips.filter((c) => c.stage === k).length]));
	const isSel = (c) => ui.selection?.kind === 'clip' && ui.selection.id === c.id;
	const primaryIcon = { todo: 'sparkles', draft: 'arrow-up', final: 'layers', source: 'refresh' };

	$effect(() => {
		if (!countsEl) return;
		getLocale();
		counts;
		compact = false;
		fullWidth = 0;
		const observer = new ResizeObserver(() => {
			if (!compact && countsEl.scrollWidth > countsEl.clientWidth + 1) {
				fullWidth = countsEl.scrollWidth;
				compact = true;
			} else if (compact && countsEl.clientWidth >= fullWidth) {
				compact = false;
			}
		});
		observer.observe(countsEl);
		return () => observer.disconnect();
	});

	function primaryLabel(stage) {
		if (stage === 'todo') return t('storyboard.primary.todo');
		if (stage === 'draft') return t('storyboard.primary.draft');
		if (stage === 'final') return t('storyboard.primary.final');
		return t('storyboard.primary.source');
	}

	function pick(c) {
		select('clip', c.id);
		seek(c.start + 0.01);
	}
	function writePrompt(c) {
		const { prompt, created } = ensurePrompt(c);
		if (!prompt) return;
		ui.modal = created ? { type: 'prompt', id: prompt.id, isNew: true } : { type: 'prompt', id: prompt.id };
	}
	function primary(c) {
		select('clip', c.id);
		if (c.stage === 'draft' && c.take) return promoteToFinal(c.take);
		if (c.stage === 'final') return (ui.inspectorOpen = true);
		startGeneration({ clips: [c], quality: 'draft' });
	}
	function inViewer(c) {
		ui.workspace = 'director';
		pick(c);
	}
	function remove(c) {
		select('clip', c.id);
		deleteSelection();
	}

	function onDragStart(e, c) {
		dragId = c.id;
		e.dataTransfer.effectAllowed = 'move';
		e.dataTransfer.setData('text/x-shot', c.id);
	}
	function onDragOver(e, i) {
		if (!dragId) return;
		e.preventDefault();
		const r = e.currentTarget.getBoundingClientRect();
		overIdx = e.clientX < r.left + r.width / 2 ? i : i + 1;
	}
	function onDrop(e) {
		e.preventDefault();
		if (!dragId || overIdx == null) return reset();
		const from = doc.clips.findIndex((c) => c.id === dragId);
		moveClip(from, overIdx > from ? overIdx - 1 : overIdx);
		reset();
	}
	function reset() {
		dragId = null;
		overIdx = null;
	}
</script>

<section class="isolate flex min-w-0 flex-col bg-canvas" aria-label={t('storyboard.title')}>
	<div class="flex h-10 shrink-0 items-center gap-3 border-b border-line px-4">
		<span class="min-w-0 truncate text-sm font-semibold">{t('storyboard.title')}</span>
		<span class="shrink-0 whitespace-nowrap text-xs text-fg-subtle">{t('storyboard.summary', { count: doc.clips.length, duration: secs(seqDuration()) })}</span>
		<div bind:this={countsEl} class="ml-2 flex min-w-0 flex-1 items-center gap-3 overflow-hidden whitespace-nowrap">
			{#each counts as [k, n] (k)}
				<span class="flex shrink-0 items-center gap-1.5 text-xs {n ? 'text-fg-muted' : 'text-fg-subtle'}" title={t('storyboard.stageCount', { stage: stages[k].label, n })}>
					<span class="h-1.5 w-1.5 rounded-full {stages[k].dot} {n ? '' : 'opacity-40'}"></span><span class={compact ? 'sr-only' : ''}>{stages[k].label}</span><span class="vp-tc text-fg">{n}</span>
				</span>
			{/each}
		</div>
		<div class="flex shrink-0 items-center gap-3">
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => addShot() }}>{t('storyboard.addShot')}</HostUi>
			<div class="vp-seg" role="group" aria-label={t('storyboard.size.group')}>
				{#each sizes as s (s.id)}
					<HostUi name="IconButton" props={{ icon: hostIconName('grid'), label: s.label, tooltip: s.label, size: 'xs', class: s.cls, ariaPressed: size === s.id, onclick: () => (size = s.id) }} />
				{/each}
			</div>
		</div>
	</div>

	<div class="min-h-0 flex-1 overflow-auto p-5" role="list" ondragend={reset}>
		<div class="grid {cols[size]} gap-x-5 gap-y-6">
			{#each doc.clips as c, i (c.id)}
				{@const thumb = clipThumb(c)}
				{@const takes = takesOf(c)}
				{@const p = promptOf(c)}
				{@const sm = i > 0 ? seam(i) : null}
				{@const activity = shotActivity(c.id)}
				{@const busy = activity.state === 'running'}
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<article
					animate:flip={{ duration: ms(220) }}
					role="listitem"
					class="group relative rounded-xl border bg-surface-1 p-2 transition-[box-shadow,border-color,opacity] duration-150 {isSel(c) ? 'border-signal shadow-[0_0_0_1px_rgb(var(--signal))]' : 'border-line-strong hover:border-line-hover'} {dragId === c.id ? 'opacity-40' : ''}"
					draggable="true"
					ondragstart={(e) => onDragStart(e, c)}
					ondragover={(e) => onDragOver(e, i)}
					ondrop={onDrop}
					onclick={() => pick(c)}
					ondblclick={() => inViewer(c)}
					onkeydown={(e) => e.key === 'Enter' && pick(c)}
				>
					{#if overIdx === i && dragId && dragId !== c.id}<div class="absolute inset-y-2 -left-3 w-0.5 rounded-full bg-signal" transition:fade={{ duration: ms(100) }}></div>{/if}
					{#if overIdx === i + 1 && dragId && dragId !== c.id && i === doc.clips.length - 1}<div class="absolute inset-y-2 -right-3 w-0.5 rounded-full bg-signal"></div>{/if}

					<div class="relative aspect-video overflow-hidden rounded-lg bg-surface-3">
						{#if thumb}
							<img
								src={thumb}
								alt=""
								class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03] motion-reduce:transition-none motion-reduce:group-hover:scale-100"
								style:filter={clipFilter(c)}
								draggable="false"
							/>
						{:else}
							<div class="absolute inset-0 bg-[repeating-linear-gradient(135deg,rgb(var(--line-strong))_0_1px,transparent_1px_10px)]"></div>
							<div class="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center">
								<Icon name="sparkles" class="h-5 w-5 text-fg-muted" />
								<span class="text-xs text-fg-muted">{t('storyboard.placeholder')}</span>
							</div>
						{/if}
						<span class="vp-tc absolute left-2 top-2 rounded-md bg-black/60 px-1.5 py-0.5 text-xs font-medium text-white backdrop-blur-sm">{String(i + 1).padStart(2, '0')}</span>
						{#if sm?.issues.length}
							<span
								class="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-warning-solid text-black"
								role="img"
								title={sm.issues.map((x) => x.text).join('\n')}
								aria-label={t('storyboard.seamIssue')}
							>
								<Icon name="alert" class="h-3.5 w-3.5" />
							</span>
						{/if}
						<span class="vp-tc absolute bottom-2 right-2 rounded-md bg-black/60 px-1.5 py-0.5 text-xs text-white backdrop-blur-sm">{secs(c.dur)}</span>
						{#if busy}
							<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/60 backdrop-blur-[2px]" transition:fade={{ duration: ms(150) }}>
								<span class="max-w-[90%] truncate text-xs text-white">{activity.step || (activity.running ? t('generation.state.running') : t('generation.state.queued'))}</span>
								<div class="h-1 w-2/3 overflow-hidden rounded-full bg-white/20" role="progressbar" aria-label={t('generation.shotProgress', { shot: clipLabel(c) })} aria-valuemin="0" aria-valuemax="100" aria-valuenow={activity.running ? Math.round(activity.progress) : undefined}>
									<div class="h-full bg-white transition-[width] duration-150" style:width="{activity.progress}%"></div>
								</div>
							</div>
						{/if}
					</div>

					<div class="px-1 pb-1 pt-2.5">
						<input
							class="w-full truncate rounded border border-transparent bg-transparent px-1 py-1 text-sm font-medium text-fg hover:border-line-strong focus:border-signal focus:outline-none"
							value={clipLabel(c)}
							onclick={(e) => e.stopPropagation()}
							onchange={(e) => act(() => (c.label = e.currentTarget.value))}
							aria-label={t('storyboard.shotName', { n: i + 1 })}
						/>
						<div class="flex items-center gap-2 px-1 text-xs">
							<span class="flex items-center gap-1.5 {stages[c.stage].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[c.stage].dot}"></span>{stages[c.stage].label}</span>
							{#if takes.length}<span class="text-fg-subtle">{t('storyboard.takes', { count: takes.length })}</span>{/if}
						</div>
						<button
							type="button"
							class="mt-1 line-clamp-2 min-h-[32px] w-full px-1 text-left text-xs leading-4 {p?.text ? 'text-fg-muted hover:text-fg' : 'italic text-fg-subtle hover:text-fg-muted'}"
							onclick={(e) => (e.stopPropagation(), writePrompt(c))}
						>
							{p?.text || t('storyboard.addPrompt')}
						</button>
						<div class="mt-2 flex items-center gap-1 opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100 {isSel(c) || busy ? 'opacity-100' : ''}">
							<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName(primaryIcon[c.stage]), disabled: busy, onclick: (e) => (e.stopPropagation(), primary(c)) }}>{primaryLabel(c.stage)}</HostUi>
							<div class="flex-1"></div>
							<HostUi name="IconButton" props={{ icon: hostIconName('eye'), label: t('storyboard.inViewer'), size: 'xs', tooltip: t('storyboard.inViewer'), onclick: (e) => (e.stopPropagation(), inViewer(c)) }} />
							<HostUi name="IconButton" props={{ icon: 'plus', label: t('storyboard.insertAfter'), size: 'xs', tooltip: t('storyboard.insertAfter'), onclick: (e) => (e.stopPropagation(), addShot(t('lib.default.shot'), '', 4, c.id)) }} />
							<HostUi name="IconButton" props={{ icon: 'trash', label: t('storyboard.delete'), size: 'xs', tooltip: t('storyboard.delete'), onclick: (e) => (e.stopPropagation(), remove(c)) }} />
						</div>
					</div>
				</article>
			{/each}
			<button
				type="button"
				class="flex aspect-video flex-col items-center justify-center gap-1.5 self-start rounded-xl border border-dashed border-line-hover text-sm text-fg-muted transition-colors hover:border-signal hover:bg-signal/5 hover:text-fg"
				onclick={() => addShot()}
			>
				<Icon name="plus" class="h-5 w-5" />{t('storyboard.newShot')}
				<span class="text-xs text-fg-subtle">{t('storyboard.newShotHint')}</span>
			</button>
		</div>
	</div>
</section>

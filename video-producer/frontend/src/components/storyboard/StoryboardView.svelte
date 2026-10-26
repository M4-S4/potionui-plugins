<script>
	import { flip } from 'svelte/animate';
	import { fade } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { getLocale, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, select, act, secs, clamp, clipLabel, addShot, moveClip, seqDuration, deleteSelection, promptOf } from '../../lib/state.svelte.js';
	import { takesOf, promoteToFinal, shotActivity, shotEngineText, soundOf } from '../../lib/production.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { clipFilter } from '../../lib/look.js';
	import { clipThumb } from '../../lib/media.js';
	import { stages } from '../../lib/catalog.js';
	import { colorIssues, matchAll, seam } from '../../lib/continuity.svelte.js';
	import { shotWaitText } from '../../lib/chain.svelte.js';
	import { overlayLayer } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import { shotStale } from '../../lib/shots.js';
	import { activityStep } from '../../lib/generation.js';
	import Icon from '../Icon.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import SoundNote from '../shots/SoundNote.svelte';
	import BandView from './BandView.svelte';
	import ChainChip from './ChainChip.svelte';
	import SeamPanel from './SeamPanel.svelte';
	import ViewSwitch from './ViewSwitch.svelte';
	import ZoneHeader from '../shell/ZoneHeader.svelte';

	let size = $state('m');
	let dragId = $state(null);
	let editingId = $state(null);
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
	const colorFixes = $derived(doc.clips.length > 1 ? colorIssues() : 0);
	const SEAM_MENU = 'dropdown:seam:';
	const seamClip = $derived(typeof ui.menuOpen === 'string' && ui.menuOpen.startsWith(SEAM_MENU) ? (doc.clips.find((c) => ui.menuOpen === SEAM_MENU + c.id) ?? null) : null);
	let seamAnchor = null;
	const isSel = (c) => ui.selection?.kind === 'clip' && ui.selection.id === c.id;
	const primaryIcon = { draft: 'arrow-up', final: 'layers' };

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
		if (stage === 'draft') return t('storyboard.primary.draft');
		return t('storyboard.primary.final');
	}

	function pick(c) {
		select('clip', c.id);
		seek(c.start + 0.01);
	}
	function editShot(c) {
		select('clip', c.id);
		ui.modal = { type: 'shot', id: c.id };
	}
	const generatesFrom = (stage) => stage === 'todo' || stage === 'source';
	function primary(c) {
		select('clip', c.id);
		if (c.stage === 'draft' && c.take) return promoteToFinal(c.take);
		ui.inspectorOpen = true;
	}
	function inViewer(c) {
		ui.workspace = 'play';
		pick(c);
	}
	function remove(c) {
		select('clip', c.id);
		deleteSelection();
	}
	function openSeamMenu(e, c) {
		e.stopPropagation();
		if (ui.menuOpen === SEAM_MENU + c.id) return (ui.menuOpen = null);
		seamAnchor = e.currentTarget.getBoundingClientRect();
		ui.menuOpen = SEAM_MENU + c.id;
	}
	function placeSeamMenu(node) {
		const r = node.getBoundingClientRect();
		const a = seamAnchor ?? { left: 8, right: 8 + r.width, top: 8, bottom: 8 };
		const below = a.bottom + 6 + r.height <= window.innerHeight - 8;
		node.style.left = `${clamp(a.right - r.width, 8, window.innerWidth - r.width - 8)}px`;
		node.style.top = `${below ? a.bottom + 6 : Math.max(8, a.top - r.height - 6)}px`;
	}
	function closeSeamMenu() {
		if (seamClip) ui.menuOpen = null;
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

{#if ui.storyView === 'band'}
	<BandView />
{:else}
<section class="isolate flex min-w-0 flex-col bg-canvas" aria-label={t('storyboard.title')}>
	<ZoneHeader icon="grid" title={t('storyboard.title')} subtitle={t('storyboard.summary', { count: doc.clips.length, duration: secs(seqDuration()) })}>
		<div bind:this={countsEl} class="ml-2 flex min-w-0 flex-1 items-center gap-3 overflow-hidden whitespace-nowrap">
			{#each counts as [k, n] (k)}
				<span class="flex shrink-0 items-center gap-1.5 text-xs {n ? 'text-fg-muted' : 'text-fg-subtle'}" title={t('storyboard.stageCount', { stage: stages[k].label, n })}>
					<span class="h-1.5 w-1.5 rounded-full {stages[k].dot} {n ? '' : 'opacity-40'}"></span><span class={compact ? 'sr-only' : ''}>{stages[k].label}</span><span class="vp-tc text-fg">{n}</span>
				</span>
			{/each}
		</div>
		<div class="flex shrink-0 items-center gap-3">
			{#if colorFixes}
				<HostUi name="Tooltip" props={{ text: t('storyboard.matchAllTip'), wrapperClass: 'inline-flex' }}>
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('palette'), onclick: matchAll }}>{t('storyboard.matchAll', { count: colorFixes })}</HostUi>
				</HostUi>
			{/if}
			<ViewSwitch />
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => addShot() }}>{t('storyboard.addShot')}</HostUi>
			<div class="vp-seg" role="group" aria-label={t('storyboard.size.group')}>
				{#each sizes as s (s.id)}
					<HostUi name="IconButton" props={{ icon: hostIconName('grid'), label: s.label, tooltip: s.label, size: 'xs', class: s.cls, ariaPressed: size === s.id, onclick: () => (size = s.id) }} />
				{/each}
			</div>
		</div>
	</ZoneHeader>

	<div class="min-h-0 flex-1 overflow-auto p-5" role="list" ondragend={reset} onscroll={closeSeamMenu}>
		<div class="grid {cols[size]} gap-x-5 gap-y-6">
			{#each doc.clips as c, i (c.id)}
				{@const thumb = clipThumb(c)}
				{@const takes = takesOf(c)}
				{@const p = promptOf(c)}
				{@const sm = i > 0 ? seam(i) : null}
				{@const activity = shotActivity(c.id)}
				{@const busy = activity.state === 'running'}
				{@const waiting = busy && !activity.running ? shotWaitText(c.id) : ''}
				{@const stale = shotStale(c, takes)}
				{@const ownEngine = shotEngineText(c)}
				{@const sound = soundOf(c)}
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<article
					animate:flip={{ duration: ms(220) }}
					role="listitem"
					class="group relative rounded-xl border bg-surface-1 p-2 transition-[box-shadow,border-color,opacity] duration-150 {isSel(c) ? 'border-signal shadow-[0_0_0_1px_rgb(var(--signal))]' : 'border-line-strong hover:border-line-hover'} {dragId === c.id ? 'opacity-40' : ''}"
					draggable={editingId !== c.id}
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
						<div class="absolute left-2 top-2 z-10 flex items-center gap-1">
							<span class="vp-tc rounded-md bg-black/60 px-1.5 py-0.5 text-xs font-medium text-white backdrop-blur-sm">{String(i + 1).padStart(2, '0')}</span>
							{#if i > 0}<ChainChip clip={c} />{/if}
						</div>
						{#if sm?.issues.length}
							<button
								type="button"
								class="absolute right-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-warning-solid text-black {seamClip?.id === c.id ? 'ring-2 ring-signal' : ''}"
								title={sm.issues.map((x) => x.text).join('\n')}
								aria-label={t('storyboard.seamIssue')}
								aria-expanded={seamClip?.id === c.id}
								aria-haspopup="dialog"
								data-vp-menu
								data-seam-alert={c.id}
								onclick={(e) => openSeamMenu(e, c)}
							>
								<Icon name="alert" class="h-3.5 w-3.5" />
							</button>
						{/if}
						{#if stale}
							<span class="absolute bottom-2 left-2 flex items-center gap-1 rounded-md bg-warning-solid px-1.5 py-0.5 text-xs font-medium text-black" style:max-width="calc(100% - 4.75rem)" title={t('storyboard.staleTip')}><Icon name="pencil" class="h-3 w-3 shrink-0" /><span class="truncate">{t('storyboard.stale')}</span></span>
						{/if}
						<span class="vp-tc absolute bottom-2 right-2 rounded-md bg-black/60 px-1.5 py-0.5 text-xs text-white backdrop-blur-sm">{secs(c.dur)}</span>
						{#if busy}
							<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/60 backdrop-blur-[2px]" transition:fade={{ duration: ms(150) }}>
								<span class="max-w-[90%] truncate text-xs text-white" data-chain-wait={waiting ? c.id : null}>{activityStep(activity) || (activity.running ? t('generation.state.running') : waiting || t('lib.status.queued'))}</span>
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
							onpointerdown={() => (editingId = c.id)}
							onfocus={() => (editingId = c.id)}
							onblur={() => (editingId = editingId === c.id ? null : editingId)}
							onpointerleave={(e) => document.activeElement !== e.currentTarget && editingId === c.id && (editingId = null)}
							onchange={(e) => act(() => (c.label = e.currentTarget.value))}
							aria-label={t('storyboard.shotName', { n: i + 1 })}
						/>
						<div class="flex items-center gap-2 px-1 text-xs">
							<span class="flex items-center gap-1.5 {stages[c.stage].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[c.stage].dot}"></span>{stages[c.stage].label}</span>
							{#if takes.length}<span class="text-fg-subtle">{t('storyboard.takes', { count: takes.length })}</span>{/if}
							{#if ownEngine}
								<HostUi name="Tooltip" props={{ text: ownEngine, wrapperClass: 'inline-flex' }}>
									<span class="flex items-center text-signal" role="img" aria-label={ownEngine} data-own-engine><Icon name="sliders" class="h-3.5 w-3.5" /></span>
								</HostUi>
							{/if}
							{#if sound?.behavior}<span class="inline-flex" data-shot-sound={sound.behavior}><SoundNote behavior={sound.behavior} compact /></span>{/if}
							<HostUi name="Tooltip" props={{ text: t('storyboard.editTip'), wrapperClass: 'ml-auto inline-flex' }}>
								<button type="button" class="flex min-h-6 items-center gap-1 rounded px-1 text-xs font-medium text-fg-muted hover:bg-surface-2 hover:text-fg" aria-label={t('storyboard.edit', { shot: clipLabel(c) })} onclick={(e) => (e.stopPropagation(), editShot(c))}>
									<Icon name="pencil" class="h-3 w-3" />{#if size !== 's'}{t('storyboard.editShort')}{/if}
								</button>
							</HostUi>
						</div>
						{#if takes.length}
							<p class="mt-1 line-clamp-2 min-h-[32px] w-full px-1 text-xs leading-4 {p?.text ? 'text-fg-muted' : 'italic text-fg-subtle'}">{p?.text || t('storyboard.noPrompt')}</p>
						{:else}
							<button
								type="button"
								class="mt-1 line-clamp-2 min-h-[32px] w-full px-1 text-left text-xs leading-4 {p?.text ? 'text-fg-muted hover:text-fg' : 'italic text-fg-subtle hover:text-fg-muted'}"
								onclick={(e) => (e.stopPropagation(), editShot(c))}
							>
								{p?.text || t('storyboard.addPrompt')}
							</button>
						{/if}
						<div class="mt-2 flex flex-wrap items-center gap-1 opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100 {isSel(c) || busy ? 'opacity-100' : ''}">
							{#if primaryIcon[c.stage]}<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName(primaryIcon[c.stage]), disabled: busy, onclick: (e) => (e.stopPropagation(), primary(c)) }}>{primaryLabel(c.stage)}</HostUi>{/if}
							{#if generatesFrom(c.stage)}<DraftsField clips={[c]} label={false} disabled={busy} />{/if}
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
	{#if seamClip}
		{#key seamClip.id}
			<div class="vp-menu w-80 p-3" style:position="fixed" role="dialog" aria-label={t('storyboard.seamIssue')} data-vp-menu use:overlayLayer use:placeSeamMenu>
				<SeamPanel clip={seamClip} />
			</div>
		{/key}
	{/if}
</section>
{/if}

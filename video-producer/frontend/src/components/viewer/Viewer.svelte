<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, clipAt, tc, seqDuration, addAssetToTimeline, insertResult, clipLabel, promptOf, startGeneration, estimate, fmtDuration } from '../../lib/state.svelte.js';
	import { togglePlay, seek } from '../../lib/playback.svelte.js';
	import { clipFilter, fadeOpacity } from '../../lib/look.js';
	import { assetThumb, clipThumb, takeThumb } from '../../lib/media.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let w = $state(0);
	let h = $state(0);
	const ratios = { '16:9': 16 / 9, '2.39:1': 2.39, '9:16': 9 / 16, '1:1': 1, '4:5': 0.8 };
	const r = $derived(ratios[doc.aspect]);
	const box = $derived(w / h > r ? { w: h * r, h } : { w, h: w / r });

	const time = $derived(ui.playhead);
	const clip = $derived(clipAt(time));
	const a = $derived(clip ? asset(clip.assetId) : null);
	const local = $derived(clip ? (time - clip.start + clip.srcIn) / Math.max(1, a?.srcDur ?? 1) : 0);
	const title = $derived(doc.titles.find((x) => time >= x.start && time < x.start + x.dur));

	const previewAsset = $derived(ui.preview?.kind === 'asset' ? asset(ui.preview.id) : null);
	const previewResult = $derived(ui.preview?.kind === 'result' ? doc.results.find((x) => x.id === ui.preview.id) : null);
	const compareRes = $derived(ui.compare ? ui.compare.map((id) => doc.results.find((x) => x.id === id)).filter(Boolean) : []);
	const localPrompt = $derived(clip ? promptOf(clip) : null);
	const mode = $derived(compareRes.length === 2 ? 'compare' : previewResult ? 'result' : previewAsset ? 'asset' : 'sequence');
	const bare = $derived(mode === 'sequence' && !(clip && a));
	const previewThumb = $derived(previewAsset ? assetThumb(previewAsset) : null);
	const busy = $derived(ui.production.state === 'running' || ui.production.state === 'paused');
	const key = (id) => commandById(id)?.key || undefined;

	function modeLabel(m) {
		if (m === 'compare') return t('viewer.mode.compare');
		if (m === 'result') return t('viewer.mode.result');
		return t('viewer.mode.asset');
	}
	function takeLabel(res) {
		const shot = clipLabel(doc.clips.find((c) => c.id === res.clipId));
		return res.quality === 'final' ? t('viewer.takeFinal', { shot, variant: res.variant }) : t('viewer.takeDraft', { shot, variant: res.variant });
	}

	function backToSequence() {
		ui.preview = null;
		ui.compare = null;
	}
	function addPreviewToCut() {
		addAssetToTimeline(previewAsset.id);
		ui.preview = null;
	}
</script>

<section class="isolate flex min-w-0 flex-col bg-canvas" aria-label={t('viewer.label')}>
	<div class="relative min-h-0 flex-1 p-2">
		{#if mode !== 'sequence'}
			<div class="absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full border border-line-strong bg-surface-3/90 py-1 pl-3 pr-1 text-xs text-fg shadow-floating backdrop-blur-xl">
				{modeLabel(mode)}
				<button type="button" class="flex h-6 items-center gap-1 rounded-full px-2 text-fg-muted hover:bg-surface-2 hover:text-fg" onclick={backToSequence}><Icon name="x" class="h-3 w-3" />{t('viewer.backToSequence')}</button>
			</div>
		{/if}
		<div class="absolute inset-2 flex items-center justify-center" bind:clientWidth={w} bind:clientHeight={h}>
			<div id="viewer-frame" class="relative overflow-hidden {bare ? 'bg-canvas ring-1 ring-inset ring-line-strong' : 'bg-black'}" style:width="{box.w}px" style:height="{box.h}px">
				{#if compareRes.length === 2}
					<div class="grid h-full grid-cols-2 gap-px bg-line">
						{#each compareRes as res (res.id)}
							<div class="relative overflow-hidden">
								<img src={takeThumb(res)} alt="" class="h-full w-full object-cover" />
								<span class="absolute left-2 top-2 rounded-md bg-black/60 px-2 py-0.5 text-xs text-white backdrop-blur-sm">{takeLabel(res)}</span>
							</div>
						{/each}
					</div>
				{:else if previewResult}
					<img src={takeThumb(previewResult)} alt="" class="h-full w-full object-cover" />
					<div class="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2.5 pt-8 text-sm text-white">
						<span class="flex-1">{takeLabel(previewResult)} <span class="text-white/60">{t('viewer.outOfCut')}</span></span>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => insertResult(previewResult.id) }}>{t('viewer.useTake')}</HostUi>
					</div>
				{:else if previewAsset}
					{#if previewThumb}
						<img src={previewThumb} alt={previewAsset.name} class="h-full w-full object-contain" />
					{:else}
						<div class="flex h-full items-center justify-center text-white/60"><Icon name={previewAsset.kind === 'audio' ? 'music' : 'film'} class="h-10 w-10" /></div>
					{/if}
					<div class="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2.5 pt-8 text-sm text-white">
						<span class="flex-1">{previewAsset.name} <span class="text-white/60">{t('viewer.sourceMedia')}</span></span>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: addPreviewToCut }}>{t('viewer.addToCut')}</HostUi>
					</div>
				{:else if clip && !a}
					<div class="absolute inset-0 flex flex-col items-center gap-3 p-8 text-center {title ? 'justify-end' : 'justify-center'}">
						{#if !title}
							<Icon name="sparkles" class="h-7 w-7 text-fg-subtle" />
							<div class="text-md font-medium text-fg">{clipLabel(clip)}</div>
							<p class="max-w-md text-sm text-fg-muted">{localPrompt?.text || t('viewer.placeholderHint')}</p>
						{/if}
						<div class="mt-1">
							<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'sparkles', disabled: busy, onclick: () => startGeneration({ clips: [clip], quality: 'draft' }) }}>
								{t('viewer.generateDrafts')} <span class="opacity-60">{t('viewer.approx', { duration: fmtDuration(estimate({ seconds: clip.dur, quality: 'draft' }).gpuSec) })}</span>
							</HostUi>
						</div>
					</div>
				{:else if clip && a}
					<img
						src={clipThumb(clip)}
						alt={a.name}
						class="h-full w-full object-cover will-change-transform"
						style:opacity={fadeOpacity(clip, time)}
						style:filter={clipFilter(clip)}
						style:transform="scale({1.04 + local * 0.08}) translateX({(local - 0.5) * -2}%)"
					/>
					{#if a.generated && !ui.playing}
						<span class="vp-sim absolute right-2 top-2 !border-white/40 !bg-black/60 !text-white backdrop-blur-sm"><Icon name="flask" class="h-3 w-3" />{a.quality === 'final' ? t('viewer.simFinal') : t('viewer.simDraft')}</span>
					{/if}
				{:else if !doc.clips.length && !title}
					<div class="pointer-events-none absolute inset-0 flex items-center justify-center p-8 text-center text-fg">
						<div class="font-light tracking-[0.12em]" style:font-size="{Math.max(10, box.h * 0.1)}px">{doc.name}</div>
					</div>
				{:else}
					<div class="flex h-full items-center justify-center text-sm {bare ? 'text-fg-muted' : 'text-white/60'}">{t('viewer.end')}</div>
				{/if}

				{#if title && mode === 'sequence'}
					{@const o = fadeOpacity({ ...title, fadeIn: 0.6, fadeOut: 0.6 }, time)}
					<div class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center {bare ? 'text-fg' : 'text-white'}" style:opacity={o}>
						{#if title.sub}<div class="mb-2 uppercase tracking-[0.3em]" style:font-size="{Math.max(10, box.h * 0.03)}px">{title.sub}</div>{/if}
						<div class="font-light tracking-[0.12em]" style:font-size="{Math.max(10, box.h * 0.1)}px" style:text-shadow={bare ? null : '0 2px 24px rgb(0 0 0 / 0.4)'}>{title.text}</div>
					</div>
				{/if}

				{#if ui.guides}
					<div class="pointer-events-none absolute inset-0">
						<div class="absolute inset-[5%] border border-dashed border-white/50"></div>
						<div class="absolute inset-[10%] border border-white/30"></div>
						{#each [33.333, 66.666] as p (p)}
							<div class="absolute inset-y-0 w-px bg-white/30" style:left="{p}%"></div>
							<div class="absolute inset-x-0 h-px bg-white/30" style:top="{p}%"></div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</div>

	<div class="grid h-11 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-3 border-t border-line px-3">
		<div class="flex items-center gap-2">
			<HostUi
				name="IconButton"
				props={{ icon: hostIconName(ui.muted ? 'volume-x' : 'volume'), label: ui.muted ? t('viewer.unmute') : t('viewer.mute'), size: 'sm', class: 'vp-h7', tooltip: t('viewer.monitor'), onclick: () => (ui.muted = !ui.muted) }}
			/>
			<input class="vp-slider w-24" type="range" min="0" max="1" step="0.01" bind:value={ui.monitorVol} aria-label={t('viewer.monitor')} />
		</div>
		<div class="flex items-center gap-1">
			<HostUi name="IconButton" props={{ icon: hostIconName('skip-back'), label: t('viewer.toStart'), size: 'sm', class: 'vp-h7', tooltip: t('viewer.start'), kbd: t('viewer.kbd.home'), onclick: () => seek(0) }} />
			<HostUi name="IconButton" props={{ icon: hostIconName('step-back'), label: t('viewer.prevFrame'), size: 'sm', class: 'vp-h7', kbd: t('viewer.kbd.prev'), onclick: () => seek(ui.playhead - 1 / 25) }} />
			<HostUi name="Tooltip" props={{ text: t('viewer.playPause'), kbd: key('play') }}>
				<button type="button" class="flex h-8 w-8 items-center justify-center rounded-full bg-surface-3 text-fg transition-colors hover:bg-line-hover" onclick={togglePlay} aria-label={ui.playing ? t('viewer.pause') : t('viewer.play')}>
					<Icon name={ui.playing ? 'pause' : 'play'} class="h-4 w-4" strokeWidth={2.25} />
				</button>
			</HostUi>
			<HostUi name="IconButton" props={{ icon: hostIconName('step-fwd'), label: t('viewer.nextFrame'), size: 'sm', class: 'vp-h7', kbd: t('viewer.kbd.next'), onclick: () => seek(ui.playhead + 1 / 25) }} />
			<HostUi
				name="IconButton"
				props={{ icon: hostIconName('repeat'), label: t('viewer.loopLabel'), size: 'sm', class: 'vp-h7 vp-toggle', ariaPressed: ui.loop, tooltip: t('viewer.loop'), kbd: key('loop'), onclick: () => (ui.loop = !ui.loop) }}
			/>
		</div>
		<div class="flex items-center justify-end gap-2">
			<span class="vp-tc mr-1 text-md text-fg">{tc(ui.playhead, doc.fps)}</span>
			<span class="vp-tc hidden text-xs text-fg-subtle min-[1500px]:inline">{t('viewer.total', { tc: tc(seqDuration(), doc.fps) })}</span>
			<HostUi
				name="IconButton"
				props={{ icon: 'grid', label: t('viewer.guides'), size: 'sm', class: 'vp-h7 vp-toggle', ariaPressed: ui.guides, kbd: key('guides'), onclick: () => (ui.guides = !ui.guides) }}
			/>
			<HostUi name="Tooltip" props={{ text: t('viewer.aspect') }}>
				<select class="vp-popup" bind:value={doc.aspect} aria-label={t('viewer.aspect')}>
					{#each Object.keys(ratios) as k (k)}<option value={k}>{k}</option>{/each}
				</select>
			</HostUi>
			<HostUi name="Tooltip" props={{ text: t('viewer.resolutionTip', { fps: doc.fps }) }}>
				<select class="vp-popup" bind:value={doc.resolution} aria-label={t('viewer.resolution')}>
					<option value="720p">720p</option>
					<option value="1080p">1080p</option>
					<option value="4K">{t('viewer.uhd')}</option>
				</select>
			</HostUi>
			<HostUi
				name="IconButton"
				props={{ icon: hostIconName('maximize'), label: t('viewer.fullscreen'), size: 'sm', class: 'vp-h7', kbd: key('fullscreen'), onclick: () => document.getElementById('viewer-frame')?.requestFullscreen?.() }}
			/>
		</div>
	</div>
</section>

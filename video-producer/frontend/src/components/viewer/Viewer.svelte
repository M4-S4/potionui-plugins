<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, clipAt, tc, seqDuration, clipLabel, promptOf } from '../../lib/state.svelte.js';
	import { addToTimeline } from '../../lib/importer.js';
	import { insertResult, findTake } from '../../lib/production.svelte.js';
	import { speedOf } from '../../lib/cadence.js';
	import { togglePlay, seek } from '../../lib/playback.svelte.js';
	import { clipFilter, fadeOpacity } from '../../lib/look.js';
	import { assetThumb, takeThumb } from '../../lib/media.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import { mediaFailure, mediaFormat } from '../../lib/playable.js';
	import { frameDuration } from '../../lib/timebase.js';
	import { lutOf } from '../../lib/match.js';
	import { placedOn } from '../../lib/monitor.js';
	import { aspectOf } from '../../lib/generation.js';
	import { BARS, RESOLUTION_NAMES, formatValue } from '../../lib/formats.js';
	import { fitClass, formatSections, framed, sizeOf } from '../../lib/framing.js';
	import { formatGroupText, setFormat, setResolution } from '../../lib/framing.svelte.js';
	import MatchCanvas from './MatchCanvas.svelte';
	import Icon from '../Icon.svelte';

	let { player = false } = $props();

	let w = $state(0);
	let h = $state(0);
	let sideW = $state(0);
	const formats = $derived(formatSections(doc));
	const r = $derived(aspectOf(doc.aspect, doc.resolution));
	const box = $derived(w / h > r ? { w: h * r, h } : { w, h: w / r });

	const time = $derived(ui.playhead);
	const clip = $derived(clipAt(time));
	const a = $derived(clip ? asset(clip.assetId) : null);

	const title = $derived(doc.titles.find((x) => time >= x.start && time < x.start + x.dur));

	const previewAsset = $derived(!player && ui.preview?.kind === 'asset' ? asset(ui.preview.id) : null);
	const previewResult = $derived(!player && ui.preview?.kind === 'result' ? findTake(ui.preview.id) : null);
	const compareRes = $derived(!player && ui.compare ? ui.compare.map((id) => findTake(id)).filter(Boolean) : []);
	const localPrompt = $derived(clip ? promptOf(clip) : null);
	const mode = $derived(compareRes.length === 2 ? 'compare' : previewResult ? 'result' : previewAsset ? 'asset' : 'sequence');
	const bare = $derived(mode === 'sequence' && !(clip && a));
	const previewThumb = $derived(previewAsset ? assetThumb(previewAsset) : null);
	const playable = (res) => res.status === 'done' && Boolean(res.url);
	const key = (id) => commandById(id)?.key || undefined;
	const liveVideo = $derived(mode === 'sequence' && clip && a?.src && a.kind === 'video' ? a.src : null);
	const liveImage = $derived(mode === 'sequence' && clip && a?.src && a.kind === 'image' ? a.src : null);
	let video = $state();
	let picture = $state();
	const lut = $derived(mode === 'sequence' && clip ? lutOf(clip) : null);
	const resultShot = $derived(previewResult ? placedOn(doc.clips, previewResult) : null);
	const resultLut = $derived(resultShot ? lutOf(resultShot) : null);
	let resultVideo = $state();
	let sides = $state({});
	const graded = (shot) => Boolean(shot) && (clipFilter(shot) !== 'none' || Boolean(lutOf(shot)));
	let failed = $state({});
	let natural = $state({});
	const measure = (src, el) => {
		const size = el.videoWidth ? [el.videoWidth, el.videoHeight] : el.naturalWidth ? [el.naturalWidth, el.naturalHeight] : null;
		if (size) natural[src] = size;
	};
	const fitFor = (src, item) => framed(natural[src] ?? sizeOf(item), doc)?.mode ?? BARS;
	const liveFit = $derived(liveVideo || liveImage ? fitFor(liveVideo ?? liveImage, a) : BARS);
	const resultFit = $derived(previewResult ? fitFor(previewResult.url, previewResult) : BARS);
	const mark = (src, el, withSize = false) => {
		const reason = mediaFailure(el, { video: withSize });
		if (reason) failed[src] = reason;
	};

	$effect(() => {
		const el = video;
		if (!el || !liveVideo || !clip) return;
		const speed = speedOf(clip);
		const target = Math.max(0, (ui.playhead - clip.start) * speed + clip.srcIn);
		if (el.playbackRate !== speed) el.playbackRate = speed;
		if (ui.playing) {
			if (el.paused) el.play().catch(() => {});
			if (Math.abs(el.currentTime - target) > 0.25) el.currentTime = target;
		} else {
			if (!el.paused) el.pause();
			if (Math.abs(el.currentTime - target) > 0.02) el.currentTime = target;
		}
	});

	function modeLabel(m) {
		if (m === 'compare') return t('viewer.mode.compare');
		if (m === 'result') return t('viewer.mode.result');
		return t('viewer.mode.asset');
	}
	function takeLabel(res) {
		const shot = clipLabel(doc.clips.find((c) => c.id === res.shotId));
		return res.quality === 'final' ? t('viewer.takeFinal', { shot, variant: res.variant }) : t('viewer.takeDraft', { shot, variant: res.variant });
	}

	function backToSequence() {
		ui.preview = null;
		ui.compare = null;
	}
	function addPreviewToCut() {
		addToTimeline(previewAsset.id);
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
							{@const shot = placedOn(doc.clips, res)}
							{@const look = shot ? lutOf(shot) : null}
							<div class="relative overflow-hidden bg-black">
								{#if playable(res) && failed[res.url]}
									{@render cannotPlay(failed[res.url], takeLabel(res), res.url)}
								{:else if playable(res)}
									<video
										bind:this={sides[res.id]}
										src={res.url}
										class="h-full w-full object-contain"
										autoplay
										loop
										muted
										playsinline
										preload="auto"
										aria-label={takeLabel(res)}
										style:filter={shot ? clipFilter(shot) : null}
										onerror={(e) => mark(res.url, e.currentTarget)}
										onloadedmetadata={(e) => mark(res.url, e.currentTarget, true)}
									></video>
									{#if look && sides[res.id]}<MatchCanvas source={sides[res.id]} lut={look} filter={clipFilter(shot)} />{/if}
								{:else if takeThumb(res)}
									<img src={takeThumb(res)} alt="" class="h-full w-full object-cover" />
								{/if}
								<span class="absolute bottom-2 left-2 max-w-[calc(100%-1rem)] truncate rounded-md bg-black/60 px-2 py-0.5 text-xs text-white backdrop-blur-sm">{takeLabel(res)}{#if graded(shot)} <span class="text-white/60">{t('viewer.graded')}</span>{/if}</span>
							</div>
						{/each}
					</div>
				{:else if previewResult}
					{#if playable(previewResult) && failed[previewResult.url]}
						{@render cannotPlay(failed[previewResult.url], takeLabel(previewResult), previewResult.url)}
					{:else if playable(previewResult)}
						{#key Boolean(resultLut)}
							<video
								bind:this={resultVideo}
								src={previewResult.url}
								class="h-full w-full {fitClass(resultFit)}"
								controls={!resultLut}
								autoplay={Boolean(resultLut)}
								loop={Boolean(resultLut)}
								muted
								playsinline
								preload={resultLut ? 'auto' : 'metadata'}
								aria-label={takeLabel(previewResult)}
								style:filter={resultShot ? clipFilter(resultShot) : null}
								onerror={(e) => mark(previewResult.url, e.currentTarget)}
								onloadedmetadata={(e) => (mark(previewResult.url, e.currentTarget, true), measure(previewResult.url, e.currentTarget))}
							></video>
							{#if resultLut && resultVideo}<MatchCanvas source={resultVideo} lut={resultLut} filter={clipFilter(resultShot)} cover={resultFit !== BARS} />{/if}
						{/key}
					{:else if takeThumb(previewResult)}
						<img src={takeThumb(previewResult)} alt="" class="h-full w-full object-cover" />
					{/if}
					<div class="absolute inset-x-0 flex items-center gap-2 px-3 text-sm text-white {playable(previewResult) ? 'top-0 bg-gradient-to-b from-black/80 to-transparent pb-8 pt-12' : 'bottom-0 bg-gradient-to-t from-black/80 to-transparent pb-2.5 pt-8'}">
						<span class="flex-1">{takeLabel(previewResult)} <span class="text-white/60">{t('viewer.outOfCut')}{#if graded(resultShot)} {t('viewer.graded')}{/if}</span></span>
						{#if playable(previewResult)}
							<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => insertResult(previewResult.id) }}>{t('viewer.useTake')}</HostUi>
						{/if}
					</div>
				{:else if previewAsset}
					{#if previewAsset.src && previewAsset.kind !== 'image' && failed[previewAsset.src]}
						{@render cannotPlay(failed[previewAsset.src], previewAsset.name, previewAsset.src)}
					{:else if previewAsset.src && previewAsset.kind === 'video'}
						<video
							src={previewAsset.src}
							class="h-full w-full object-contain"
							controls
							muted
							playsinline
							preload="metadata"
							aria-label={previewAsset.name}
							onerror={(e) => mark(previewAsset.src, e.currentTarget)}
							onloadedmetadata={(e) => mark(previewAsset.src, e.currentTarget, true)}
						></video>
					{:else if previewAsset.src && previewAsset.kind === 'audio'}
						<div class="flex h-full flex-col items-center justify-center gap-4 text-white/60">
							<Icon name="music" class="h-10 w-10" />
							<audio src={previewAsset.src} controls preload="metadata" aria-label={previewAsset.name} onerror={(e) => mark(previewAsset.src, e.currentTarget)}></audio>
						</div>
					{:else if previewThumb}
						<img src={previewThumb} alt={previewAsset.name} class="h-full w-full object-contain" />
					{:else}
						<div class="flex h-full items-center justify-center text-white/60"><Icon name={previewAsset.kind === 'audio' ? 'music' : 'film'} class="h-10 w-10" /></div>
					{/if}
					<div class="absolute inset-x-0 flex items-center gap-2 px-3 text-sm text-white {previewAsset.src && previewAsset.kind !== 'image' ? 'top-0 bg-gradient-to-b from-black/80 to-transparent pb-8 pt-12' : 'bottom-0 bg-gradient-to-t from-black/80 to-transparent pb-2.5 pt-8'}">
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
					</div>
				{:else if liveVideo && failed[liveVideo]}
					{@render cannotPlay(failed[liveVideo], a.name, liveVideo)}
				{:else if liveVideo}
					{#key liveVideo}
						<video
							bind:this={video}
							src={liveVideo}
							class="h-full w-full {fitClass(liveFit)}"
							muted
							playsinline
							preload="auto"
							aria-label={a.name}
							style:opacity={fadeOpacity(clip, time)}
							style:filter={clipFilter(clip)}
							onerror={(e) => mark(liveVideo, e.currentTarget)}
							onloadedmetadata={(e) => (mark(liveVideo, e.currentTarget, true), measure(liveVideo, e.currentTarget))}
						></video>
						{#if lut && video}<MatchCanvas source={video} {lut} filter={clipFilter(clip)} fade={fadeOpacity(clip, time)} cover={liveFit !== BARS} />{/if}
					{/key}
				{:else if liveImage}
					<img bind:this={picture} src={liveImage} alt={a.name} class="h-full w-full {fitClass(liveFit)}" style:opacity={fadeOpacity(clip, time)} style:filter={clipFilter(clip)} onload={(e) => measure(liveImage, e.currentTarget)} />
					{#if lut && picture}<MatchCanvas source={picture} {lut} filter={clipFilter(clip)} fade={fadeOpacity(clip, time)} cover={liveFit !== BARS} />{/if}
				{:else if clip && a}
					<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-8 text-center text-white/70">
						<Icon name="film" class="h-7 w-7" />
						<div class="text-md font-medium text-white">{t('lib.media.offline')}</div>
						<p class="max-w-md text-sm">{t('viewer.offlineHint', { name: a.name || clipLabel(clip) })}</p>
					</div>
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

	<div class="grid h-11 shrink-0 items-center gap-3 border-t border-line px-3" style:grid-template-columns="minmax(0, 1fr) auto minmax(max-content, 1fr)">
		<div class="flex min-w-0 items-center gap-2 overflow-hidden" bind:clientWidth={sideW}>
			<HostUi
				name="IconButton"
				props={{ icon: hostIconName(ui.muted ? 'volume-x' : 'volume'), label: ui.muted ? t('viewer.unmute') : t('viewer.mute'), size: 'sm', class: 'vp-h7 shrink-0', tooltip: t('viewer.monitor'), onclick: () => (ui.muted = !ui.muted) }}
			/>
			{#if sideW >= 136}<input class="vp-slider w-24 shrink-0" type="range" min="0" max="1" step="0.01" bind:value={ui.monitorVol} aria-label={t('viewer.monitor')} />{/if}
			{#if player && clip}
				<span class="ml-1 min-w-0 truncate text-sm text-fg-muted">{t('viewer.shot', { index: doc.clips.indexOf(clip) + 1, count: doc.clips.length, name: clipLabel(clip) })}</span>
			{/if}
		</div>
		<div class="flex items-center gap-1">
			<HostUi name="IconButton" props={{ icon: hostIconName('skip-back'), label: t('viewer.toStart'), size: 'sm', class: 'vp-h7', tooltip: t('viewer.start'), kbd: t('viewer.kbd.home'), onclick: () => seek(0) }} />
			<HostUi name="IconButton" props={{ icon: hostIconName('step-back'), label: t('viewer.prevFrame'), size: 'sm', class: 'vp-h7', kbd: t('viewer.kbd.prev'), onclick: () => seek(ui.playhead - frameDuration(doc.fps)) }} />
			<HostUi name="Tooltip" props={{ text: t('viewer.playPause'), kbd: key('play') }}>
				<button type="button" class="flex h-8 w-8 items-center justify-center rounded-full bg-surface-3 text-fg transition-colors hover:bg-line-hover" onclick={togglePlay} aria-label={ui.playing ? t('viewer.pause') : t('viewer.play')}>
					<Icon name={ui.playing ? 'pause' : 'play'} class="h-4 w-4" strokeWidth={2.25} />
				</button>
			</HostUi>
			<HostUi name="IconButton" props={{ icon: hostIconName('step-fwd'), label: t('viewer.nextFrame'), size: 'sm', class: 'vp-h7', kbd: t('viewer.kbd.next'), onclick: () => seek(ui.playhead + frameDuration(doc.fps)) }} />
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
				<select class="vp-popup" value={formatValue(doc.aspect)} onchange={(e) => setFormat(e.currentTarget.value)} aria-label={t('viewer.aspect')}>
					{#each formats as section (section.id)}<optgroup label={formatGroupText(section.id)}>{#each section.rows as row (row.value)}<option value={row.value}>{row.value}</option>{/each}</optgroup>{/each}
				</select>
			</HostUi>
			<HostUi name="Tooltip" props={{ text: t('viewer.resolutionTip', { fps: doc.fps }) }}>
				<select class="vp-popup" value={doc.resolution} onchange={(e) => setResolution(e.currentTarget.value)} aria-label={t('viewer.resolution')}>
					{#each RESOLUTION_NAMES as r (r)}<option value={r}>{r === '4K' ? t('viewer.uhd') : r}</option>{/each}
				</select>
			</HostUi>
			<HostUi
				name="IconButton"
				props={{ icon: hostIconName('maximize'), label: t('viewer.fullscreen'), size: 'sm', class: 'vp-h7', kbd: key('fullscreen'), onclick: () => document.getElementById('viewer-frame')?.requestFullscreen?.() }}
			/>
		</div>
	</div>
</section>

{#snippet cannotPlay(reason, name, src)}
	{@const format = mediaFormat(name, src)}
	<div class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center text-white/70" role="alert">
		<Icon name="alert" class="h-7 w-7" />
		{#if reason === 'offline'}
			<div class="text-md font-medium text-white">{t('lib.media.offline')}</div>
			<p class="max-w-md text-sm">{t('viewer.offlineHint', { name })}</p>
		{:else}
			<div class="text-md font-medium text-white">{t('viewer.cannotPlay')}</div>
			{#if format}<p class="text-sm">{t('viewer.cannotPlayFormat', { format })}</p>{/if}
			<p class="max-w-md text-sm">{t('viewer.cannotPlayHint')}</p>
		{/if}
	</div>
{/snippet}

<script>
	import { ui, doc, asset } from '../../lib/state.svelte.js';
	import { speedOf } from '../../lib/cadence.js';
	import { clipFilter, fadeOpacity } from '../../lib/look.js';
	import { unfaded } from '../../lib/dissolve.js';
	import { lutOf } from '../../lib/match.js';
	import { BARS } from '../../lib/formats.js';
	import { fitClass, framed, sizeOf } from '../../lib/framing.js';
	import MatchCanvas from './MatchCanvas.svelte';

	let { mix, time } = $props();

	const clip = $derived(mix.to);
	const a = $derived(asset(clip.assetId));
	const shown = $derived(unfaded(doc.clips, mix.index));
	const opacity = $derived(mix.progress * fadeOpacity(shown, time));
	const lut = $derived(lutOf(clip));
	let natural = $state(null);
	const fit = $derived(framed(natural ?? sizeOf(a), doc)?.mode ?? BARS);
	let video = $state();
	let picture = $state();

	const measure = (el) => {
		const size = el.videoWidth ? [el.videoWidth, el.videoHeight] : el.naturalWidth ? [el.naturalWidth, el.naturalHeight] : null;
		if (size) natural = size;
	};

	$effect(() => {
		const el = video;
		if (!el) return;
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
</script>

{#if a?.src && a.kind === 'video'}
	{#key a.src}
		<video
			bind:this={video}
			src={a.src}
			class="absolute inset-0 h-full w-full {fitClass(fit)}"
			muted
			playsinline
			preload="auto"
			aria-hidden="true"
			data-dissolve-layer={clip.id}
			style:opacity={opacity}
			style:filter={clipFilter(clip)}
			onloadedmetadata={(e) => measure(e.currentTarget)}
		></video>
		{#if lut && video}<MatchCanvas source={video} {lut} filter={clipFilter(clip)} fade={opacity} cover={fit !== BARS} />{/if}
	{/key}
{:else if a?.src && a.kind === 'image'}
	<img bind:this={picture} src={a.src} alt="" class="absolute inset-0 h-full w-full {fitClass(fit)}" data-dissolve-layer={clip.id} style:opacity={opacity} style:filter={clipFilter(clip)} onload={(e) => measure(e.currentTarget)} />
	{#if lut && picture}<MatchCanvas source={picture} {lut} filter={clipFilter(clip)} fade={opacity} cover={fit !== BARS} />{/if}
{:else}
	<div class="pointer-events-none absolute inset-0 bg-black" data-dissolve-layer={clip.id} style:opacity={opacity}></div>
{/if}

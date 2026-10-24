<script>
	import { FALLBACK_WIDTH, lutRenderer } from '../../lib/lutgl.js';

	const MAX_WIDTH = 1920;

	let { source, lut, filter = 'none', opacity = 1, onlive = () => {} } = $props();
	let canvas = $state();
	let renderer = null;
	let broken = false;

	function paint() {
		if (broken || !canvas || !source || !lut) return;
		const w = source.videoWidth ?? source.naturalWidth ?? 0;
		const h = source.videoHeight ?? source.naturalHeight ?? 0;
		if (!w || !h) return;
		renderer ??= lutRenderer(canvas);
		if (!renderer) {
			broken = true;
			return onlive(false);
		}
		const width = Math.min(w, renderer.gpu ? MAX_WIDTH : FALLBACK_WIDTH);
		const height = Math.max(1, Math.round((width * h) / w));
		if (canvas.width !== width || canvas.height !== height) [canvas.width, canvas.height] = [width, height];
		try {
			renderer.draw(source, lut);
			onlive(true);
		} catch {
			broken = true;
			onlive(false);
		}
	}

	$effect(() => {
		const el = source;
		if (!el || !lut || !canvas) return;
		const video = 'requestVideoFrameCallback' in el || 'videoWidth' in el;
		let alive = true;
		let handle = 0;
		const watch = () => {
			if (!alive) return;
			paint();
			handle = el.requestVideoFrameCallback ? el.requestVideoFrameCallback(watch) : requestAnimationFrame(watch);
		};
		const ready = () => paint();
		const events = video ? ['loadeddata', 'seeked'] : ['load'];
		for (const name of events) el.addEventListener(name, ready);
		if (video) watch();
		else paint();
		return () => {
			alive = false;
			if (el.cancelVideoFrameCallback) el.cancelVideoFrameCallback(handle);
			else cancelAnimationFrame(handle);
			for (const name of events) el.removeEventListener(name, ready);
		};
	});

	$effect(() => () => {
		renderer?.dispose();
		renderer = null;
		onlive(false);
	});
</script>

<canvas bind:this={canvas} class="pointer-events-none absolute inset-0 h-full w-full object-contain" style:filter style:opacity aria-hidden="true"></canvas>

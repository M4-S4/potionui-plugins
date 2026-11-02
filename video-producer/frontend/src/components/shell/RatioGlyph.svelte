<script>
	import { glyph } from '../../lib/framing.js';

	let { ratio, class: className = 'h-3.5 w-3.5' } = $props();

	const box = $derived(glyph(ratio > 0 ? ratio : 1));
</script>

<svg viewBox="0 0 24 24" class="shrink-0 {className}" fill="none" stroke="currentColor" aria-hidden="true">
	<rect x={box.x} y={box.y} width={box.width} height={box.height} stroke-width="1.5" rx="1.5" />
</svg>

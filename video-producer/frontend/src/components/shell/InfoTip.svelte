<script>
	import { tick } from 'svelte';
	import { overlayLayer } from '../../lib/host.js';

	let { lines = [], wrapperClass = 'inline-flex', children } = $props();

	const id = `vp-tip-${Math.random().toString(36).slice(2, 10)}`;
	let trigger = $state();
	let panel = $state();
	let open = $state(false);
	let style = $state('');
	let showTimer = null;
	let hideTimer = null;
	let revealedAt = 0;

	async function reveal() {
		clearTimeout(showTimer);
		clearTimeout(hideTimer);
		if (open || !lines.length) return;
		style = '';
		open = true;
		revealedAt = Date.now();
		await tick();
		place();
	}

	function close() {
		clearTimeout(showTimer);
		clearTimeout(hideTimer);
		open = false;
	}

	function hoverIn() {
		clearTimeout(hideTimer);
		if (open) return;
		clearTimeout(showTimer);
		showTimer = setTimeout(reveal, 200);
	}

	function hoverOut() {
		clearTimeout(showTimer);
		if (trigger?.contains(document.activeElement)) return;
		clearTimeout(hideTimer);
		hideTimer = setTimeout(close, 150);
	}

	function toggle() {
		if (!open) return reveal();
		if (Date.now() - revealedAt > 300) close();
	}

	function blur(event) {
		if (!panel?.contains(event.relatedTarget)) close();
	}

	function place() {
		if (!trigger || !panel) return;
		const r = trigger.getBoundingClientRect();
		const p = panel.getBoundingClientRect();
		const left = Math.min(Math.max(8, r.left + r.width / 2 - p.width / 2), window.innerWidth - p.width - 8);
		const above = r.top - p.height - 8;
		style = `top: ${above >= 8 ? above : r.bottom + 8}px; left: ${Math.max(8, left)}px;`;
	}

	function escape(event) {
		if (event.key !== 'Escape') return;
		event.preventDefault();
		event.stopPropagation();
		close();
	}

	$effect(() => {
		if (!open) return;
		window.addEventListener('keydown', escape, true);
		return () => window.removeEventListener('keydown', escape, true);
	});

	$effect(() => () => {
		clearTimeout(showTimer);
		clearTimeout(hideTimer);
	});
</script>

<button type="button" bind:this={trigger} class="{wrapperClass} text-left" aria-describedby={id} onmouseenter={hoverIn} onmouseleave={hoverOut} onfocus={reveal} onblur={blur} onclick={toggle}>
	{@render children()}
</button>
<div
	bind:this={panel}
	{id}
	role="tooltip"
	hidden={!open}
	use:overlayLayer={'tooltip'}
	onmouseenter={() => clearTimeout(hideTimer)}
	onmouseleave={hoverOut}
	class="fixed w-max max-w-[28rem] rounded-md bg-surface-3 px-2.5 py-1.5 text-xs font-medium text-fg shadow-floating"
	style={style || 'top: 0; left: 0; visibility: hidden;'}
>
	<ul class="space-y-0.5">
		{#each lines as line, i (i)}<li>{line}</li>{/each}
	</ul>
</div>

<script>
	import { onMount } from 'svelte';
	import { fade, scale } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { overlayLayer } from '../../lib/host.js';
	import { focusables } from '../../lib/keyboard.js';
	import { closeLayer, closeTopLayer, focusWithRing, isTopLayer, leaveLayer, openLayer } from '../../lib/focus.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ui } from '../../lib/state.svelte.js';
	import Icon from '../Icon.svelte';

	let { title, subtitle = '', icon = null, width = 560, children, footer, onclose = null } = $props();

	let dialog = $state();
	let layer = null;
	const close = () => (onclose ? onclose() : (ui.modal = null));

	function initialFocus() {
		const candidates = [...dialog.querySelectorAll('input, textarea, select, button')].filter((el) => !el.disabled && !el.closest('[data-close]'));
		const target = dialog.querySelector('[autofocus]') ?? candidates[0];
		if (target) focusWithRing(target);
		else dialog.focus();
	}

	function keydown(e) {
		if (e.key === 'Escape') {
			e.preventDefault();
			e.stopPropagation();
			closeTopLayer();
			return;
		}
		if (e.key !== 'Tab') return;
		const list = focusables(dialog);
		if (!list.length) {
			e.preventDefault();
			return dialog.focus();
		}
		const first = list[0];
		const last = list[list.length - 1];
		if (e.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && document.activeElement === last) {
			e.preventDefault();
			first.focus();
		}
	}

	onMount(() => {
		layer = openLayer(dialog, { refocus: initialFocus, close });
		const frame = requestAnimationFrame(initialFocus);
		return () => {
			cancelAnimationFrame(frame);
			closeLayer(layer);
		};
	});
</script>

<div class="vp-modal-backdrop" role="presentation" use:overlayLayer transition:fade|global={{ duration: ms(140) }} onpointerdown={(e) => e.target === e.currentTarget && isTopLayer(layer) && close()}>
	<div
		bind:this={dialog}
		class="vp-modal"
		style:width="{width}px"
		role="dialog"
		aria-modal="true"
		aria-label={title}
		tabindex="-1"
		onkeydown={keydown}
		onoutrostart={() => leaveLayer(layer)}
		transition:scale|global={{ start: 0.97, duration: ms(180), easing: cubicOut }}
	>
		<div class="vp-modal-head">
			{#if icon}<Icon name={icon} class="mt-0.5 h-4 w-4 shrink-0 text-fg-muted" />{/if}
			<div class="min-w-0 flex-1">
				<h2 class="text-md font-semibold">{title}</h2>
				{#if subtitle}<p class="text-xs text-fg-muted">{subtitle}</p>{/if}
			</div>
			<span class="-mr-1.5 -mt-1 inline-flex" data-close>
				<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('shell.window.close'), tooltip: t('shell.window.close'), kbd: t('commands.kbd.escape'), size: 'sm', class: 'vp-h7', onclick: close }} />
			</span>
		</div>
		<div class="min-h-0 flex-1 overflow-auto">{@render children()}</div>
		{#if footer}
			<div class="vp-modal-foot">{@render footer()}</div>
		{/if}
	</div>
</div>

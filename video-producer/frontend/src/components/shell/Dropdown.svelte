<script>
	import { fly } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { ms } from '../../lib/motion.js';
	import { overlayLayer } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ui } from '../../lib/state.svelte.js';
	import { ulid } from '../../lib/ulid.js';
	import Icon from '../Icon.svelte';

	let { label, labelClass = '', icon = 'plus', items, title = '', variant = 'ghost', size = 'xs', class: className = '', align = 'left' } = $props();

	const id = `dropdown:${ulid()}`;
	const open = $derived(ui.menuOpen === id);
	const button = $derived({ variant, size, icon: hostIconName(icon), class: className, ariaExpanded: open, ariaHaspopup: 'menu', onclick: () => (ui.menuOpen = open ? null : id) });

	function run(item) {
		if (item.disabled) return;
		ui.menuOpen = null;
		item.run();
	}
</script>

<div class="relative" data-vp-menu>
	{#if title}
		<HostUi name="Tooltip" props={{ text: title }}>
			<HostUi name="Button" props={button}><span class={labelClass}>{label}</span><Icon name="chevron-down" class="h-3 w-3 opacity-60" /></HostUi>
		</HostUi>
	{:else}
		<HostUi name="Button" props={button}><span class={labelClass}>{label}</span><Icon name="chevron-down" class="h-3 w-3 opacity-60" /></HostUi>
	{/if}
	{#if open}
		<div class="vp-menu top-8 {align === 'right' ? 'right-0' : 'left-0'}" role="menu" use:overlayLayer in:fly={{ y: -4, duration: ms(120) }}>
			{#each items as item}
				<button type="button" role="menuitem" class={item.disabled ? 'opacity-50' : ''} aria-disabled={item.disabled ? 'true' : null} onclick={() => run(item)}>
					{#if item.icon}<Icon name={item.icon} class="h-3.5 w-3.5 text-fg-muted" />{/if}
					<span class="flex-1">{item.label}</span>
					{#if item.badge}<span class="vp-menu-key rounded-sm border border-line-strong px-1">{item.badge}</span>{/if}
					{#if item.key}<span class="vp-menu-key">{item.key}</span>{/if}
				</button>
				{#if item.hint}<p class="px-2 pb-1.5 pl-8 text-2xs text-fg-subtle" style:max-width="16rem">{item.hint}</p>{/if}
			{/each}
		</div>
	{/if}
</div>

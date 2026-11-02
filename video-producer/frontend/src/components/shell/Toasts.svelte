<script>
	import { fly } from 'svelte/transition';
	import { flip } from 'svelte/animate';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { ms } from '../../lib/motion.js';
	import { overlayLayer } from '../../lib/host.js';
	import { ui } from '../../lib/state.svelte.js';
	import Icon from '../Icon.svelte';

	const icon = { info: 'info', success: 'check', warning: 'alert', error: 'alert' };
	const tone = { info: 'text-fg-muted', success: 'text-success', warning: 'text-warning', error: 'text-danger' };
</script>

<div class="vp-toasts" use:overlayLayer={'toast'} aria-live="polite">
	{#each ui.toasts as item (item.id)}
		<div class="vp-toast" animate:flip={{ duration: ms(180) }} in:fly={{ y: 10, duration: ms(200) }} out:fly={{ y: 6, duration: ms(160) }}>
			<Icon name={icon[item.level] ?? 'info'} class="h-4 w-4 shrink-0 {tone[item.level] ?? 'text-fg-muted'}" />
			<span class="max-w-md">{item.message}</span>
			{#if item.action}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', class: 'ml-1', onclick: () => item.action.run() }}>{item.action.label}</HostUi>
			{/if}
		</div>
	{/each}
</div>

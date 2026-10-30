<script>
	import { drawerFocus } from '../../lib/drawer.js';

	let { side, label = '', drawers = false, open = false, children } = $props();

	const modal = $derived(drawers && open);
</script>

<div class="vp-drawer" data-vp-drawer={side} role={modal ? 'dialog' : undefined} aria-modal={modal ? 'true' : undefined} aria-label={modal ? label : undefined} tabindex="-1" hidden={drawers && !open} use:drawerFocus={modal}>
	{@render children?.()}
</div>

import { tick } from 'svelte';
import { restoreFocus } from './focus.js';

const FOCUSABLE = 'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';
const KEEPS = '.vp-drawer, .vp-deck-drawer, [data-vp-drawer-toggle], .vp-modal-backdrop, .vp-palette-backdrop, .vp-menu, [data-vp-menu], .vp-toasts, .vp-uploads';

export function drawerFocus(node, open) {
	let was = false;
	let trigger = null;
	let run = 0;
	const apply = async (next) => {
		if (next === was) return;
		was = next;
		if (next) {
			trigger = document.activeElement;
			const seq = ++run;
			await tick();
			if (seq !== run || !was) return;
			(node.querySelector(FOCUSABLE) ?? node).focus({ preventScroll: true });
			return;
		}
		run += 1;
		if (node.contains(document.activeElement) || document.activeElement === document.body) restoreFocus(trigger, null);
		trigger = null;
	};
	apply(open);
	return { update: apply, destroy: () => (run += 1) };
}

export function closesOnOutsidePointer(root, target) {
	return root instanceof Node && target instanceof Element && root.contains(target) && !target.closest(KEEPS);
}

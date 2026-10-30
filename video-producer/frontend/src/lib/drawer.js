import { tick } from 'svelte';
import { restoreFocus } from './focus.js';
import { hostOverlayOpen } from './keyboard.js';
import { DECK_MENU } from './deck.js';
import { drawerMode, sidebarShown, ui } from './state.svelte.js';

const FOCUSABLE = 'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';
const KEEPS = '.vp-drawer, .vp-deck-drawer, [data-vp-drawer-toggle], .vp-modal-backdrop, .vp-palette-backdrop, .vp-menu, [data-vp-menu], .vp-toasts, .vp-uploads';
const HOST_KEEPS = '[role="status"], [role="tooltip"]';
const CONTROL = 'a[href], button, input, select, textarea, summary, label, [contenteditable="true"], [tabindex]';
const HOST_CONTROL = `${CONTROL}, [role="button"], [role="link"], [role="menuitem"], [role="option"], [role="tab"], [role="switch"], [role="checkbox"], [role="radio"], [role="slider"]`;
const POINTER_STOPS = ['pointerdown', 'pointercancel', 'contextmenu', 'auxclick'];
const DRAWERS = ['start', 'end', 'deck', 'menu'];
const DECK_MENUS = Object.values(DECK_MENU);
const SHUT = {
	start: () => (ui.sidebarOpen = false),
	end: () => (ui.inspectorOpen = false),
	deck: () => (ui.deckDrawer = false),
	menu: () => (ui.menuOpen = null)
};

let disarm = null;

export function openDrawers() {
	const drawers = drawerMode();
	return { start: drawers && sidebarShown(), end: drawers && ui.inspectorOpen, deck: ui.deckDrawer, menu: DECK_MENUS.includes(ui.menuOpen) };
}

export function soleDrawer(was = {}, now = openDrawers()) {
	const open = DRAWERS.filter((key) => now[key]);
	const kept = open.filter((key) => !was[key]).at(-1) ?? open.at(-1);
	for (const key of open) if (key !== kept) SHUT[key]();
	return openDrawers();
}

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

export function closesOnOutsidePointer(root, target, doc = typeof document === 'undefined' ? undefined : document) {
	if (!(root instanceof Node) || !(target instanceof Element)) return false;
	if (root.contains(target)) return !target.closest(KEEPS);
	return !target.closest(HOST_KEEPS) && !hostOverlayOpen(doc);
}

export function keepsFocus(root, target) {
	if (!(root instanceof Node) || !(target instanceof Element) || !root.contains(target)) return false;
	const control = target.closest(CONTROL);
	return control === null || control === root;
}

export function holdFocus(root, event, doc = typeof document === 'undefined' ? undefined : document) {
	const target = event?.target;
	if (keepsFocus(root, target)) return event.preventDefault();
	if (doc && root instanceof Node && target instanceof Element && !root.contains(target) && !target.closest(HOST_CONTROL)) regainFocus(root, doc);
}

function regainFocus(root, doc) {
	disarm?.();
	let lost = null;
	const blur = (e) => {
		if (!e.relatedTarget && root.contains(e.target)) lost = e.target;
	};
	const stop = () => {
		disarm = null;
		doc.removeEventListener('focusout', blur, true);
		doc.removeEventListener('click', end, true);
		for (const type of POINTER_STOPS) doc.removeEventListener(type, stop, true);
	};
	const end = () => {
		stop();
		if (!lost) return;
		setTimeout(() => {
			const idle = !doc.activeElement || doc.activeElement === doc.body;
			if (idle && !hostOverlayOpen(doc)) restoreFocus(lost, null);
		});
	};
	doc.addEventListener('focusout', blur, true);
	doc.addEventListener('click', end, true);
	for (const type of POINTER_STOPS) doc.addEventListener(type, stop, true);
	disarm = stop;
}

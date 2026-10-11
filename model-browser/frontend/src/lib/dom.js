// Small browser helpers shared by the Model Browser components: Svelte actions for overlays
// (portal, the app's layer stack, a focus trap), one Escape handler for stacked overlays,
// host-component slots, toasts. They touch the DOM, so they are exercised in the browser rather
// than by `node --test`.

/** A toast through the host (`window.__potionui.notifications.toast`). */
export function toast(level, message) {
	window.__potionui?.notifications?.toast?.(level, message);
}

/** Whether the user asked the system for less motion. */
export function prefersReducedMotion() {
	try {
		return window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches === true;
	} catch {
		return false;
	}
}

/** Svelte action: move the element under `<body>`, out of any clipping or transformed ancestor. */
export function portal(node) {
	document.body.appendChild(node);
	return {
		destroy() {
			node.remove();
		}
	};
}

/**
 * Svelte action: give the element the next z-index of the app's overlay stack
 * (`window.__potionui.layers.overlayLayer`), so it sits above the app's own overlays and below
 * its toasts and tooltips.
 */
export function hostLayer(node, tier = 'overlay') {
	const action = window.__potionui?.layers?.overlayLayer;
	if (typeof action === 'function') return action(node, tier);
	node.style.zIndex = tier === 'overlay' ? '1001' : '10001';
	return { destroy() {} };
}

const FOCUSABLE =
	'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), video[controls], [tabindex]:not([tabindex="-1"])';

function focusables(node) {
	return [...node.querySelectorAll(FOCUSABLE)].filter(
		(element) => !element.closest('[hidden]') && element.getClientRects().length > 0
	);
}

function visible(element) {
	return !!element && !element.closest('[hidden]') && element.getClientRects().length > 0;
}

/**
 * Svelte action for a modal surface (give it `tabindex="-1"`): takes focus at once, moves it to
 * `[data-autofocus]` (or the first focusable element) as soon as that is on screen (host
 * components mount a frame or two later), keeps Tab inside, and gives focus back when the
 * surface goes away: to `returnTo` when given (`use:trapFocus={button}`), else to what had it
 * before.
 *
 * @param {HTMLElement} node
 * @param {HTMLElement | null | undefined} [returnTo]
 */
export function trapFocus(node, returnTo) {
	let previous = returnTo ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
	let attempts = 0;
	let timer = null;

	// Not at once: an ancestor may still be moved under <body> (use:portal) in this same update,
	// which would take the focus away again. Then until the wanted element is on screen.
	function focusInitial() {
		timer = null;
		if (!node.isConnected) return;
		const active = document.activeElement;
		// The user already moved inside the surface: leave them there.
		if (active !== node && node.contains(active)) return;
		const wanted = node.querySelector('[data-autofocus]');
		const target = visible(wanted) ? wanted : wanted ? null : focusables(node)[0];
		if (target) {
			target.focus({ preventScroll: true });
			if (document.activeElement === target) return;
		} else if (active !== node) {
			node.focus?.({ preventScroll: true });
		}
		attempts += 1;
		if (attempts < 40) timer = setTimeout(focusInitial, 25);
	}
	queueMicrotask(focusInitial);

	function onKeydown(event) {
		if (event.key !== 'Tab') return;
		const items = focusables(node);
		if (items.length === 0) {
			event.preventDefault();
			node.focus?.();
			return;
		}
		const first = items[0];
		const last = items[items.length - 1];
		const active = document.activeElement;
		if (event.shiftKey && (active === first || !node.contains(active))) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && (active === last || !node.contains(active))) {
			event.preventDefault();
			first.focus();
		}
	}

	node.addEventListener('keydown', onKeydown);
	return {
		update(next) {
			if (next) previous = next;
		},
		destroy() {
			clearTimeout(timer);
			node.removeEventListener('keydown', onKeydown);
			// Give focus back unless the user already moved it somewhere else on purpose.
			const active = document.activeElement;
			if (previous?.isConnected && (!active || active === document.body || node.contains(active))) {
				previous.focus({ preventScroll: true });
			}
		}
	};
}

// One Escape for stacked overlays: the most recent one closes first.
const escapeStack = [];
let listening = false;

function onWindowKeydown(event) {
	if (event.key !== 'Escape' || escapeStack.length === 0 || event.defaultPrevented) return;
	const top = escapeStack[escapeStack.length - 1];
	event.preventDefault();
	event.stopPropagation();
	top();
}

/**
 * Close an overlay on Escape while it is the most recent one open. Returns the function that
 * removes it again (call it when the overlay closes).
 *
 * @param {() => void} close
 * @returns {() => void}
 */
export function onEscape(close) {
	escapeStack.push(close);
	if (!listening) {
		window.addEventListener('keydown', onWindowKeydown, true);
		listening = true;
	}
	return () => {
		const index = escapeStack.lastIndexOf(close);
		if (index !== -1) escapeStack.splice(index, 1);
		if (escapeStack.length === 0 && listening) {
			window.removeEventListener('keydown', onWindowKeydown, true);
			listening = false;
		}
	};
}

/** Svelte action form of `onEscape`: `use:escapeCloses={close}`. */
export function escapeCloses(node, close) {
	let current = close;
	const remove = onEscape(() => current?.());
	return {
		update(next) {
			current = next;
		},
		destroy: remove
	};
}

const homes = new WeakMap();

/**
 * A snippet prop for a host component (`{ slot: (el) => cleanup }`, the only form that crosses
 * the bundle boundary) that shows an element this component renders, usually in a hidden tray:
 * the element is moved into the host's slot, keeping its Svelte bindings alive. The host builds
 * a new slot each time its props are updated; the element then simply moves to the new one, and
 * goes back to its tray when the host lets go of it.
 *
 * @param {() => HTMLElement | null | undefined} getNode
 */
export function slotOf(getNode) {
	return {
		slot: (el) => {
			const node = getNode();
			if (!node) return undefined;
			if (!homes.has(node)) homes.set(node, node.parentNode);
			// Moving an element takes the focus away from it: give it back.
			const active = document.activeElement;
			const hadFocus = active instanceof HTMLElement && node.contains(active);
			el.append(node);
			if (hadFocus && document.activeElement !== active) active.focus({ preventScroll: true });
			return () => {
				if (node.parentNode !== el) return;
				const home = homes.get(node);
				if (home) home.append(node);
				else node.remove();
			};
		}
	};
}

/** The nearest ancestor that scrolls vertically (the root for an IntersectionObserver), or null. */
export function scrollParent(element) {
	let node = element?.parentElement ?? null;
	while (node && node !== document.body) {
		const { overflowY } = getComputedStyle(node);
		if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') return node;
		node = node.parentElement;
	}
	return null;
}

/** Copy text to the clipboard; resolves to whether it worked. */
export async function copyText(text) {
	try {
		await navigator.clipboard.writeText(text);
		return true;
	} catch {
		try {
			const area = document.createElement('textarea');
			area.value = text;
			area.setAttribute('readonly', '');
			area.style.position = 'fixed';
			area.style.opacity = '0';
			document.body.appendChild(area);
			area.select();
			const done = document.execCommand('copy');
			area.remove();
			return done;
		} catch {
			return false;
		}
	}
}

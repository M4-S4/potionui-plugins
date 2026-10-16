const FRESH_MS = 500;

let pluginRoot = null;
let pending = null;

export function setPluginRoot(el) {
	pluginRoot = el ?? null;
}

export function setReturnFocus(el) {
	pending = el ? { el, at: Date.now() } : null;
}

export function takeReturnFocus() {
	const value = pending && Date.now() - pending.at <= FRESH_MS ? pending.el : null;
	pending = null;
	return value;
}

const usable = (el) => typeof HTMLElement !== 'undefined' && el instanceof HTMLElement && el.isConnected && el !== document.body;

export function restoreFocus(previous, fallback) {
	const target = [previous, fallback, pluginRoot].find(usable);
	target?.focus({ preventScroll: true });
}

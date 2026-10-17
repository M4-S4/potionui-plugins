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

export function focusWithRing(el) {
	if (!usable(el)) return;
	el.focus();
	if (el.matches(':focus-visible')) return;
	el.setAttribute('data-focus-ring', '');
	el.addEventListener('blur', () => el.removeAttribute('data-focus-ring'), { once: true });
}

const layers = [];
const activeLayers = () => layers.filter((layer) => !layer.closing);

export function openLayer(el, { refocus, close }) {
	const layer = { el, refocus, close, closing: false, previous: document.activeElement, fallback: takeReturnFocus() };
	layers.push(layer);
	return layer;
}

export function leaveLayer(layer) {
	if (layer) layer.closing = true;
}

export const isTopLayer = (layer) => activeLayers().at(-1) === layer;

export function closeTopLayer() {
	const top = activeLayers().at(-1);
	if (!top) return false;
	top.close();
	return true;
}

export function closeLayer(layer) {
	const index = layers.indexOf(layer);
	if (index < 0) return;
	layers.splice(index, 1);
	const next = layers[index];
	if (!next) return restoreFocus(layer.previous, layer.fallback);
	if (!usable(next.previous) || layer.el?.contains(next.previous)) {
		next.previous = layer.previous;
		next.fallback = next.fallback ?? layer.fallback;
	}
	const top = activeLayers().at(-1);
	if (top && !top.el?.contains(document.activeElement)) top.refocus();
}

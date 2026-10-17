import { hostIcons } from './icons.js';

const FLOORS = { overlay: 1000, toast: 10000, tooltip: 11000 };
const noop = () => {};

function api() {
	return typeof window === 'undefined' ? undefined : window.__potionui;
}

function call(fn, ...args) {
	return typeof fn === 'function' ? fn(...args) : undefined;
}

export function toast(level, message, duration) {
	const notifications = api()?.notifications;
	if (typeof notifications?.toast !== 'function') return false;
	notifications.toast(level, message, duration);
	return true;
}

export async function confirm(options) {
	const host = api()?.confirm;
	if (typeof host === 'function') return Boolean(await host(options));
	if (typeof window !== 'undefined' && typeof window.confirm === 'function') return window.confirm(options?.message ?? '');
	return false;
}

export const chat = {
	open: () => call(api()?.chat?.open),
	close: () => call(api()?.chat?.close),
	toggle: () => call(api()?.chat?.toggle),
	isOpen: () => Boolean(call(api()?.chat?.isOpen)),
	provideContext(key, provider) {
		const off = call(api()?.chat?.provideContext, key, provider);
		return typeof off === 'function' ? off : noop;
	},
	onToolApplied(name, handler) {
		const off = call(api()?.chat?.onToolApplied, name, handler);
		return typeof off === 'function' ? off : noop;
	},
	prefill(text, options) {
		const host = api()?.chat;
		if (typeof host?.prefill !== 'function') return false;
		host.prefill(text, options);
		return true;
	},
	send(text) {
		const host = api()?.chat;
		return typeof host?.send === 'function' ? host.send(text) : false;
	}
};

export const keyboard = {
	suppress() {
		const release = call(api()?.keyboard?.suppress);
		return typeof release === 'function' ? release : noop;
	}
};

export function registerIcons() {
	const register = api()?.registerIcon;
	if (typeof register !== 'function') return [];
	return hostIcons()
		.filter(([name, paths]) => register(name, paths))
		.map(([name]) => name);
}

export function mountHostSlot(target, name, props) {
	const entry = api()?.components?.[name];
	if (!entry) return noop;
	const handle = entry.mount(target, props);
	return () => entry.unmount(handle);
}

export function overlayLayer(node, tier = 'overlay') {
	const action = api()?.layers?.overlayLayer;
	if (typeof action === 'function') return action(node, tier);
	node.style.zIndex = String(FLOORS[tier] ?? FLOORS.overlay);
	return { destroy: noop };
}

export function openHostModal(name, { onClosed, ...props } = {}) {
	const entry = api()?.components?.[name];
	if (!entry || typeof document === 'undefined') return null;
	const target = document.body.appendChild(document.createElement('div'));
	let handle = null;
	let closed = false;
	const close = () => {
		if (closed) return;
		closed = true;
		entry.update?.(handle, { isOpen: false });
		setTimeout(() => {
			entry.unmount(handle);
			target.remove();
		}, 300);
		onClosed?.();
	};
	handle = entry.mount(target, { ...props, isOpen: true, onClose: close });
	return close;
}

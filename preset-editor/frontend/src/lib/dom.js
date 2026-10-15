export function toast(level, message) {
	window.__potionui?.notifications?.toast?.(level, message);
}

export async function confirm({ title, message, variant = 'primary' }) {
	const hostConfirm = window.__potionui?.confirm;
	if (typeof hostConfirm === 'function') return !!(await hostConfirm({ title, message, variant }));
	return window.confirm(title ? `${title}\n\n${message}` : message);
}

export function clickOutside(node, callback) {
	function onPointerDown(event) {
		if (!node.contains(event.target)) callback(event);
	}
	document.addEventListener('pointerdown', onPointerDown, true);
	return {
		destroy() {
			document.removeEventListener('pointerdown', onPointerDown, true);
		}
	};
}

export function onEscape(callback) {
	function onKeydown(event) {
		if (event.key === 'Escape') callback(event);
	}
	window.addEventListener('keydown', onKeydown);
	return () => window.removeEventListener('keydown', onKeydown);
}

export function navigateTo(href) {
	if (typeof document === 'undefined') return;
	const before = window.location.href;
	const anchor = document.createElement('a');
	anchor.href = href;
	anchor.style.display = 'none';
	document.body.appendChild(anchor);
	anchor.click();
	anchor.remove();
	setTimeout(() => {
		if (window.location.href === before) window.location.assign(href);
	}, 300);
}

export function replaceQuery(params) {
	if (typeof window === 'undefined') return;
	const url = new URL(window.location.href);
	url.search = '';
	for (const [key, value] of Object.entries(params)) {
		if (value) url.searchParams.set(key, value);
	}
	window.history.replaceState(window.history.state, '', url);
}

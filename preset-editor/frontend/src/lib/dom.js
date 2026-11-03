import { fetchMedia } from './client.js';

export function toast(level, message) {
	window.__potionui?.notifications?.toast?.(level, message);
}

export async function confirm({ title, message, variant = 'warning' }) {
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

function revokeAll(urls) {
	for (const url of urls) URL.revokeObjectURL(url);
}

export function authMedia(node, params) {
	let current = '';
	let url = null;
	let token = 0;

	async function load(next) {
		const key = JSON.stringify([next?.draftId ?? '', next?.path ?? '', next?.stamp ?? '']);
		if (key === current) return;
		current = key;
		const mine = ++token;
		if (!next?.api || !next.path) return;
		const result = await fetchMedia(next.api, next.draftId, next.path);
		if (mine !== token || !result.ok) return;
		const fresh = URL.createObjectURL(result.data);
		node.src = fresh;
		if (url) URL.revokeObjectURL(url);
		url = fresh;
	}

	load(params);
	return {
		update: load,
		destroy() {
			token += 1;
			if (url) URL.revokeObjectURL(url);
		}
	};
}

export function authImages(node, params) {
	let urls = [];
	let token = 0;

	async function load(next) {
		const mine = ++token;
		const fresh = [];
		const images = [...node.querySelectorAll('img[data-preset-editor-media]')];
		await Promise.all(
			images.map(async (image) => {
				const result = await fetchMedia(next?.api, next?.draftId, image.dataset.presetEditorMedia);
				if (!result.ok) return;
				const url = URL.createObjectURL(result.data);
				fresh.push(url);
				if (mine === token) image.src = url;
			})
		);
		if (mine !== token) {
			revokeAll(fresh);
			return;
		}
		revokeAll(urls);
		urls = fresh;
	}

	load(params);
	return {
		update: load,
		destroy() {
			token += 1;
			revokeAll(urls);
			urls = [];
		}
	};
}

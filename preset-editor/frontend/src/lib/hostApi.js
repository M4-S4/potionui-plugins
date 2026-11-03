const DOWNLOAD_URL_LIFETIME_MS = 60_000;

export function filenameFrom(response, path) {
	const disposition = response?.headers?.get?.('Content-Disposition') ?? '';
	const encoded = disposition.match(/filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/);
	if (encoded) {
		try {
			return decodeURIComponent(encoded[1].trim());
		} catch {
			return encoded[1].trim();
		}
	}
	const plain = disposition.match(/filename\s*=\s*"?([^";]+)"?/);
	if (plain) return plain[1].trim();
	return String(path).split('?')[0].split('/').filter(Boolean).pop() || 'download';
}

export function saveBlob(blob, filename) {
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	link.style.display = 'none';
	document.body.appendChild(link);
	try {
		link.click();
	} finally {
		link.remove();
		setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_LIFETIME_MS);
	}
}

export function hostPluginApi(pluginId = 'preset-editor', host = globalThis.window?.__potionui?.api) {
	if (!host || typeof host.fetch !== 'function' || typeof host.json !== 'function') return null;
	const prefix = `/api/plugins/${encodeURIComponent(pluginId)}`;

	function send(method, path, data) {
		const init = { method };
		if (data !== undefined) {
			init.headers = { 'Content-Type': 'application/json' };
			init.body = JSON.stringify(data);
		}
		return host.json(`${prefix}${path}`, init);
	}

	const fetchRawFromApp = (path, init = {}) => host.fetch(path, { timeout: 0, ...init });
	const fetchRaw = (path, init) => fetchRawFromApp(`${prefix}${path}`, init);

	return {
		get: (path) => send('GET', path),
		post: (path, data) => send('POST', path, data ?? {}),
		put: (path, data) => send('PUT', path, data ?? {}),
		delete: (path) => send('DELETE', path),
		fetchRaw,
		fetchRawFromApp,
		download: async (path, filename) => {
			const response = await fetchRaw(path);
			if (!response.ok) {
				const error = new Error(`Request failed with status ${response.status}`);
				error.status = response.status;
				error.body = await response.json().catch(() => null);
				throw error;
			}
			saveBlob(await response.blob(), filename || filenameFrom(response, path));
		}
	};
}

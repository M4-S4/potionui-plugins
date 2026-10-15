export const AUTH_TOKEN_KEY = 'auth_token';

export function readToken() {
	try {
		return globalThis.localStorage?.getItem(AUTH_TOKEN_KEY) || null;
	} catch {
		return null;
	}
}

export function standaloneApi(pluginId = 'preset-editor', { fetchImpl, token = readToken } = {}) {
	const doFetch = fetchImpl ?? ((...args) => globalThis.fetch(...args));
	const base = `/api/plugins/${encodeURIComponent(pluginId)}`;

	function headers() {
		const bearer = token();
		return {
			'Content-Type': 'application/json',
			Accept: 'application/json',
			...(bearer ? { Authorization: `Bearer ${bearer}` } : {})
		};
	}

	async function call(method, path, body) {
		const init = { method, headers: headers(), credentials: 'include', cache: 'no-store' };
		if (body !== undefined) init.body = JSON.stringify(body);
		const response = await doFetch(`${base}${path}`, init);
		return response.json();
	}

	return {
		getToken: () => token(),
		get: (path) => call('GET', path),
		post: (path, body) => call('POST', path, body ?? {}),
		put: (path, body) => call('PUT', path, body ?? {}),
		delete: (path) => call('DELETE', path)
	};
}

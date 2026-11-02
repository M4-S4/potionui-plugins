const MEDIA_ERR_ABORTED = 1;
const MEDIA_ERR_NETWORK = 2;
const EXTENSION = /\.([a-z0-9]{2,5})(?:[?#].*)?$/i;

export function mediaFormat(...names) {
	for (const name of names) {
		const found = EXTENSION.exec(String(name ?? '').trim());
		if (found) return found[1].toUpperCase();
	}
	return null;
}

export function mediaFailure(el, { video = false } = {}) {
	const code = el?.error?.code;
	if (code === MEDIA_ERR_ABORTED) return null;
	if (code === MEDIA_ERR_NETWORK) return 'offline';
	if (code) return 'unsupported';
	if (video && el?.videoWidth === 0 && el?.videoHeight === 0) return 'unsupported';
	return null;
}

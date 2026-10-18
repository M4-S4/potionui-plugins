function legacyCopy(text, doc) {
	if (!doc?.body || typeof doc.execCommand !== 'function') return false;
	const area = doc.createElement('textarea');
	area.value = text;
	area.setAttribute('readonly', '');
	area.setAttribute('aria-hidden', 'true');
	area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
	const active = doc.activeElement;
	(active?.closest?.('[role="dialog"]') ?? doc.body).appendChild(area);
	let copied = false;
	try {
		area.focus({ preventScroll: true });
		area.select();
		area.setSelectionRange(0, text.length);
		copied = doc.execCommand('copy') === true;
	} catch {}
	area.remove();
	try {
		active?.focus?.({ preventScroll: true });
	} catch {}
	return copied;
}

export async function copyText(text, { nav = globalThis.navigator, doc = globalThis.document } = {}) {
	const value = String(text ?? '');
	if (typeof nav?.clipboard?.writeText === 'function') {
		try {
			await nav.clipboard.writeText(value);
			return true;
		} catch {}
	}
	return legacyCopy(value, doc);
}

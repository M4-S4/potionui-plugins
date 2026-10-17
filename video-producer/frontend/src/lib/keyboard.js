const MODIFIER_ORDER = ['ctrl', 'alt', 'shift', 'mod'];
const MAC_GLYPHS = { ctrl: '⌃', alt: '⌥', shift: '⇧', mod: '⌘' };
const MAC_KEYS = { backspace: '⌫', plus: '+', minus: '−' };
const PC_KEYS = { plus: '+', minus: '−' };
const ACTIVATION = 'button, [role="button"], a, [role="tab"], [role="menuitem"], input, textarea, select, [contenteditable="true"]';
const HOST_OVERLAY = '[aria-modal="true"]:not(.vp-modal), button.ai-chat-trigger[aria-pressed="true"]';

export function detectMac(nav = typeof navigator === 'undefined' ? undefined : navigator) {
	const platform = nav?.userAgentData?.platform || nav?.platform || '';
	return /mac|iphone|ipad|ipod/i.test(platform);
}

export function parseShortcut(spec) {
	const parts = String(spec ?? '')
		.toLowerCase()
		.split('+')
		.filter(Boolean);
	const key = parts.pop() ?? '';
	return { key, mods: new Set(parts) };
}

export function formatShortcut(spec, { mac = detectMac(), names = {} } = {}) {
	if (!spec) return '';
	const { key, mods } = parseShortcut(spec);
	const label = (mac ? MAC_KEYS[key] : undefined) ?? names[key] ?? PC_KEYS[key] ?? key.toUpperCase();
	if (mac) return [...MODIFIER_ORDER.filter((m) => mods.has(m)).map((m) => MAC_GLYPHS[m]), label].join(' ');
	const both = mods.has('ctrl') && mods.has('mod');
	const parts = [];
	if (mods.has('ctrl') || mods.has('mod')) parts.push('Ctrl');
	if (mods.has('alt') || both) parts.push('Alt');
	if (mods.has('shift')) parts.push('Shift');
	return [...parts, label].join('+');
}

export function eventKey(e) {
	if (e.altKey && typeof e.code === 'string') {
		if (/^Key[A-Z]$/.test(e.code)) return e.code.slice(3).toLowerCase();
		if (/^Digit[0-9]$/.test(e.code)) return e.code.slice(5);
		if (e.code === 'BracketLeft') return '[';
		if (e.code === 'BracketRight') return ']';
	}
	return String(e.key ?? '').toLowerCase();
}

export function isTypingTarget(el) {
	return !!el && (el.isContentEditable === true || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
}

export function isActivationTarget(el) {
	return typeof el?.closest === 'function' && el.closest(ACTIVATION) !== null;
}

export function hostOverlayOpen(doc = typeof document === 'undefined' ? undefined : document) {
	return !!doc?.querySelector(HOST_OVERLAY);
}

export function focusables(root) {
	return [
		...root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
	].filter((el) => !el.closest('[hidden]') && el.getAttribute('aria-hidden') !== 'true');
}

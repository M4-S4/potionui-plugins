export const SHOWN_ERRORS = 3;

const REMOVED = 'Its folder leaves the draft and the mode is removed from preset.yml.';

function plain(issue) {
	return String(issue ?? '').replace(/^\[[A-Z]+\]\s*/, '');
}

export function removalMessage(check) {
	const errors = (check?.errors ?? []).map(plain);
	if (!errors.length) return REMOVED;
	const shown = errors.slice(0, SHOWN_ERRORS).join('; ');
	const more = errors.length > SHOWN_ERRORS ? `; and ${errors.length - SHOWN_ERRORS} more` : '';
	const count = errors.length === 1 ? 'one new error' : `${errors.length} new errors`;
	const fixed = errors.length === 1 ? 'it is' : 'they are';
	return `${REMOVED} The lint then reports ${count}, and publishing waits until ${fixed} fixed: ${shown}${more}.`;
}

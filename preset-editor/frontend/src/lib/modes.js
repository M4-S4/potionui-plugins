export const SHOWN_ERRORS = 3;

const REMOVED = 'Its folder leaves the draft and the mode is removed from preset.yml.';
const DELETED = 'The file leaves the draft; publishing writes the draft as it is.';
const LOADS = { mode: ['loads one of its files', 'load its files'], file: ['loads it', 'load it'] };

function plain(issue) {
	return String(issue ?? '').replace(/^\[[A-Z]+\]\s*/, '');
}

function reason(error) {
	return error?.message ? String(error.message) : 'no answer from the server';
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

export function refusalView(data, kind = 'mode') {
	const message = String(data?.message ?? '');
	const pointers = Array.isArray(data?.pointers) ? data.pointers : [];
	const loaders = Array.isArray(data?.loaders) ? data.loaders : [];
	if (!pointers.length && !loaders.length) return { title: message, lines: [], ending: '' };
	const cut = message.indexOf(': ');
	const one = pointers.length + loaders.length === 1;
	return {
		title: cut > 0 ? message.slice(0, cut) : message,
		lines: [...pointers.map((path) => `${path} takes its pipeline from it`), ...loaders.map((path) => `${path} ${LOADS[kind][0]}`)],
		ending: one ? 'Point it elsewhere, or remove that line, first.' : 'Point them elsewhere, or remove those lines, first.'
	};
}

export function removalPlan(result) {
	if (!result?.ok) {
		return {
			action: 'confirm',
			message: `${REMOVED} The check of what the removal leaves did not run (${reason(result?.error)}): the server still refuses a mode that another file uses, and the lint shows the rest once the mode is gone.`
		};
	}
	if (!result.data?.allowed) return { action: 'refuse', refusal: refusalView(result.data, 'mode') };
	return { action: 'confirm', message: removalMessage(result.data) };
}

export function deletionPlan(result) {
	if (!result?.ok) {
		return {
			action: 'confirm',
			message: `${DELETED} The check of what the deletion breaks did not run (${reason(result?.error)}): the lint shows what breaks once the file is gone.`
		};
	}
	if (!result.data?.allowed) return { action: 'refuse', refusal: refusalView(result.data, 'file') };
	return { action: 'confirm', message: DELETED };
}

export function refusalOf(error, kind) {
	return Array.isArray(error?.citing) && error.citing.length ? refusalView(error, kind) : null;
}

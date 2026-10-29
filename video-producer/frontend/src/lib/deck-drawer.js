export const DRAWER_WIDTH = 440;
export const DRAWER_INSET = 24;
export const DRAWER_MAX_HEIGHT = 600;

export function drawerRows({ engine = false, profile = false, sizes = false, guided = false, own = 0 } = {}) {
	const rows = ['engine'];
	if (profile) rows.push('profile');
	if (engine && sizes) rows.push('draftSize', 'finalSize');
	rows.push('drafts');
	if (guided) rows.push('margin');
	if (own > 0) rows.push('own');
	rows.push('edit');
	return rows;
}

export function profileControl({ items = [], current = '' } = {}) {
	if (!items.length) return 'none';
	return items.some((item) => item.id === current) ? 'segmented' : 'popup';
}

export function profileOptions({ items = [], current = '' } = {}) {
	const known = items.some((item) => item.id === current);
	return known || !current ? items : [{ id: current, label: current, unsupported: true }, ...items];
}

export function drawerPlace({ deck, root, width = DRAWER_WIDTH, inset = DRAWER_INSET, maxHeight = DRAWER_MAX_HEIGHT } = {}) {
	const frame = root ?? deck;
	const space = Math.max(0, deck.top - frame.top);
	return {
		width: Math.min(width, Math.max(0, frame.width - inset)),
		maxHeight: Math.min(maxHeight, Math.max(0, space - inset)),
		space
	};
}

export function tabTarget({ shift = false, list = [], active = null, inside = true } = {}) {
	if (!list.length) return null;
	const first = list[0];
	const last = list[list.length - 1];
	if (shift) return active === first || !inside ? last : null;
	return active === last || !inside ? first : null;
}

export function profileHint(mode, t) {
	if (mode === 'FL2VA') return t('production.profile.fl2va');
	if (mode === 'Ref2VA') return t('production.profile.ref2va');
	return t('production.profile.hybrid');
}

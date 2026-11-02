export const TOGGLE = 'toggle';
export const RANGE = 'range';
export const ADD_RANGE = 'add';

export function inOrder(order, ids) {
	const wanted = new Set(ids);
	return order.filter((id) => wanted.has(id));
}

function settled(order, list, active) {
	const kept = inOrder(order, list);
	if (kept.length < 2) return { picked: [], active: kept[0] ?? null };
	return { picked: kept, active: kept.includes(active) ? active : kept.at(-1) };
}

export function toggled(order, picked, active, id) {
	if (!order.includes(id)) return { picked: inOrder(order, picked), active };
	const base = picked.length ? picked : active && order.includes(active) ? [active] : [];
	if (base.includes(id)) return settled(order, base.filter((x) => x !== id), active === id ? null : active);
	return settled(order, [...base, id], id);
}

export function ranged(order, picked, anchor, id, add = false) {
	const to = order.indexOf(id);
	if (to < 0) return { picked: inOrder(order, picked), active: anchor };
	const from = order.indexOf(anchor);
	if (from < 0) return { picked: [], active: id };
	const span = order.slice(Math.min(from, to), Math.max(from, to) + 1);
	const list = add ? [...(picked.length ? picked : [anchor]), ...span] : span;
	return settled(order, list, anchor);
}

export function picking(order, picked, active, id, mode) {
	if (mode === TOGGLE) return toggled(order, picked, active, id);
	return ranged(order, picked, active, id, mode === ADD_RANGE);
}

export function pruned(order, picked) {
	const kept = inOrder(order, picked);
	return kept.length < 2 ? [] : kept;
}

const total = (sizes, gap) => sizes.reduce((sum, size, index) => sum + size + (index ? gap : 0), 0);
const least = (item) => (item.pinned ? item.width : Math.min(item.min ?? item.width, item.width));

function place(ranked, budget, gap) {
	const inside = new Map(ranked.filter((item) => item.pinned || item.keep).map((item) => [item.id, least(item)]));
	const outside = new Map();
	const cost = () => total([...inside.values()], gap) + total([...outside.values()], 0);
	for (const item of ranked) {
		const sizes = item.outside ? outside : inside;
		const before = sizes.get(item.id);
		if (item.pinned || before === item.width) continue;
		sizes.set(item.id, item.width);
		if (cost() <= budget) continue;
		if (before === undefined) sizes.delete(item.id);
		else sizes.set(item.id, before);
	}
	return { inside, outside };
}

export function fitInline(room, items, { gap = 8, more = 28 } = {}) {
	const shown = items.filter((item) => item.show !== false);
	const ranked = [...shown].sort((a, b) => a.rank - b.rank);
	const folding = shown.filter((item) => !item.pinned && !item.keep && !item.outside && item.folds !== false);
	let placed = place(ranked, room, gap);
	if (folding.some((item) => !placed.inside.has(item.id))) placed = place(ranked, room - more - gap, gap);
	const inline = new Set([...placed.inside.keys(), ...placed.outside.keys()]);
	return {
		inline,
		wide: new Set(shown.filter((item) => item.keep && placed.inside.get(item.id) === item.width).map((item) => item.id)),
		overflow: folding.filter((item) => !inline.has(item.id)).map((item) => item.id)
	};
}

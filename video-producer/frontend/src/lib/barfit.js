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

export const shortPresetName = (label) => String(label ?? '').replace(/\s*\([^()]*\)\s*$/, '').trim() || String(label ?? '').trim();

export const CHIP_TIERS = ['full', 'profile', 'engine'];

export function fitChip({ room, engine = 0, short = null, prefixes = [], ellipsis = 0, sep = 0, profile = 0, size = 0, drafts = 0, cell = 0, cellGap = 0 } = {}) {
	const join = (name, parts) => parts.filter((w) => w > 0).reduce((sum, w) => sum + sep + w, name);
	const tiers = (name) => [
		['full', join(name, [profile, size, drafts])],
		['profile', join(name, [profile])],
		['engine', join(name, [])]
	];
	const last = short != null && short !== engine ? 'short' : 'full';
	const candidates = [['full', ...tiers(engine)[0]], ...tiers(last === 'short' ? short : engine).slice(last === 'short' ? 0 : 1).map((tier) => [last, ...tier])];
	for (const withCell of cell > 0 ? [true, false] : [false]) {
		const budget = room - (withCell ? cell + cellGap : 0);
		for (const [name, tier, width] of candidates) if (width <= budget + 0.5) return { cell: withCell, engine: name, tier, cut: null };
	}
	let cut = -1;
	prefixes.forEach((width, index) => {
		if (width + ellipsis <= room + 0.5) cut = index;
	});
	return { cell: false, engine: 'cut', tier: 'engine', cut };
}

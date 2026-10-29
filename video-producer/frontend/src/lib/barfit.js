export const shortPresetName = (label) => String(label ?? '').replace(/\s*\([^()]*\)\s*$/, '').trim() || String(label ?? '').trim();

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

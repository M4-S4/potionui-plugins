const width = (list, gap) => list.reduce((sum, item, index) => sum + item.width + (index ? gap : 0), 0);

function fill(kept, ranked, budget, gap) {
	for (const item of ranked) {
		if (!kept.includes(item) && (item.pinned || width([...kept, item], gap) <= budget)) kept.push(item);
	}
	return kept;
}

export function fitInline(room, items, { gap = 8, more = 28 } = {}) {
	const shown = items.filter((item) => item.show !== false);
	const ranked = [...shown].sort((a, b) => a.rank - b.rank);
	const core = shown.filter((item) => item.folds !== false);
	const kept = width(core, gap) <= room ? fill([...core], ranked, room, gap) : fill([], ranked, room - more - gap, gap);
	const inline = new Set(kept.map((item) => item.id));
	return { inline, overflow: core.filter((item) => !inline.has(item.id)).map((item) => item.id) };
}

const isId = (value) => typeof value === 'string' && value.length > 0;

export function removedIds(value) {
	return Array.isArray(value) ? [...new Set(value.filter(isId))] : [];
}

export const isRemoved = (doc, takeId) => Array.isArray(doc?.removedTakes) && doc.removedTakes.includes(takeId);

export const takeOfAsset = (a) => (a?.generated === true && a.kind === 'video' && isId(a.resultId) && a.id === `gen-${a.resultId}` ? a.resultId : null);

function setRemoved(doc, ids) {
	if (ids.length) doc.removedTakes = ids;
	else delete doc.removedTakes;
}

export function markRemoved(doc, takeId) {
	if (!isId(takeId) || isRemoved(doc, takeId)) return false;
	setRemoved(doc, [...removedIds(doc.removedTakes), takeId]);
	return true;
}

export function clearRemoved(doc, takeId) {
	if (!isRemoved(doc, takeId)) return false;
	setRemoved(doc, doc.removedTakes.filter((id) => id !== takeId));
	return true;
}

export function pruneRemoved(doc, takes) {
	if (!Array.isArray(doc?.removedTakes)) return false;
	const known = new Set((takes ?? []).map((take) => take?.id));
	const kept = doc.removedTakes.filter((id) => known.has(id));
	if (kept.length === doc.removedTakes.length) return false;
	setRemoved(doc, kept);
	return true;
}

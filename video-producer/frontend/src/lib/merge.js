const ABSENT = Symbol('absent');

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const keyed = (list) => Array.isArray(list) && list.every((x) => isObject(x) && typeof x.id === 'string' && x.id) && new Set(list.map((x) => x.id)).size === list.length;

export function same(a, b) {
	if (a === b) return true;
	if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((x, i) => same(x, b[i]));
	if (!isObject(a) || !isObject(b)) return false;
	const keys = Object.keys(a);
	return keys.length === Object.keys(b).length && keys.every((k) => k in b && same(a[k], b[k]));
}

const at = (record, key) => (isObject(record) && key in record ? record[key] : ABSENT);

function mergeObject(base, mine, theirs, out) {
	const merged = {};
	for (const key of new Set([...Object.keys(mine), ...Object.keys(theirs), ...Object.keys(base)])) {
		const value = mergeValue(at(base, key), at(mine, key), at(theirs, key), out);
		if (value !== ABSENT) merged[key] = value;
	}
	return merged;
}

const ids = (list) => list.map((x) => x.id);

function placed(order, other, kept) {
	const list = order.filter((id) => kept.has(id));
	const seen = new Set(list);
	let previous = null;
	for (const id of other) {
		if (kept.has(id) && !seen.has(id)) {
			list.splice(previous === null ? 0 : list.indexOf(previous) + 1, 0, id);
			seen.add(id);
		}
		if (seen.has(id)) previous = id;
	}
	return list;
}

function moved(base, list) {
	const inBase = new Set(base);
	const inList = new Set(list);
	return !same(
		list.filter((id) => inBase.has(id)),
		base.filter((id) => inList.has(id))
	);
}

function mergeList(base, mine, theirs, out) {
	const byId = (list) => new Map(list.map((x) => [x.id, x]));
	const [b, m, t] = [byId(base), byId(mine), byId(theirs)];
	const kept = new Map();
	for (const id of new Set([...ids(mine), ...ids(theirs), ...ids(base)])) {
		const value = mergeValue(b.has(id) ? b.get(id) : ABSENT, m.has(id) ? m.get(id) : ABSENT, t.has(id) ? t.get(id) : ABSENT, out);
		if (value !== ABSENT) kept.set(id, value);
	}
	const mineMoved = moved(ids(base), ids(mine));
	if (mineMoved && moved(ids(base), ids(theirs))) out.conflicts += 1;
	const order = mineMoved ? placed(ids(mine), ids(theirs), kept) : placed(ids(theirs), ids(mine), kept);
	return order.map((id) => kept.get(id));
}

function mergeValue(base, mine, theirs, out) {
	if (same(mine, theirs)) return mine;
	if (same(base, mine)) return theirs;
	if (same(base, theirs)) return mine;
	if (isObject(mine) && isObject(theirs)) return mergeObject(isObject(base) ? base : {}, mine, theirs, out);
	if (keyed(mine) && keyed(theirs)) return mergeList(keyed(base) ? base : [], mine, theirs, out);
	out.conflicts += 1;
	return mine;
}

export function merge3(base, mine, theirs) {
	const out = { conflicts: 0 };
	const value = mergeValue(base, mine, theirs, out);
	return { value, conflicts: out.conflicts };
}

import { migrateVrefs } from './vrefs.js';

const ABSENT = Symbol('absent');
const SETS = new Set(['removedTakes', 'characters', 'exclude', 'excludeLanes', 'excludeVrefs']);
const CONTAINERS = new Set(['cast', 'referenceOverrides']);
const LINKED = ['prompts', 'frames'];

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const keyed = (list) => Array.isArray(list) && list.every((x) => isObject(x) && typeof x.id === 'string' && x.id) && new Set(list.map((x) => x.id)).size === list.length;
const strings = (value) => value === ABSENT || (Array.isArray(value) && value.every((x) => typeof x === 'string'));
const objectOrAbsent = (value) => value === ABSENT || isObject(value);

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
		const value = mergeField(key, at(base, key), at(mine, key), at(theirs, key), out);
		if (value !== ABSENT) merged[key] = value;
	}
	return merged;
}

function mergeSet(base, mine, theirs) {
	const [b, m, t] = [base, mine, theirs].map((value) => (value === ABSENT ? [] : value));
	const known = new Set(b);
	const dropped = new Set(b.filter((x) => !m.includes(x) || !t.includes(x)));
	const value = [...new Set([...m, ...t.filter((x) => !known.has(x))])].filter((x) => !dropped.has(x));
	return value.length ? value : ABSENT;
}

function mergeField(key, base, mine, theirs, out) {
	const both = !same(mine, theirs) && !same(base, mine) && !same(base, theirs);
	if (both && SETS.has(key) && [base, mine, theirs].every(strings)) return mergeSet(base, mine, theirs);
	if (both && CONTAINERS.has(key) && [base, mine, theirs].every(objectOrAbsent)) {
		const value = mergeObject(...[base, mine, theirs].map((x) => (x === ABSENT ? {} : x)), out);
		return Object.keys(value).length ? value : ABSENT;
	}
	return mergeValue(base, mine, theirs, out);
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

const snap = (value) => +(Math.round(value / 0.04) * 0.04).toFixed(3);
const fixed = (value) => +value.toFixed(3);
const timeKey = (item) => ('time' in item ? 'time' : 'start');
const clipsOf = (doc) => (Array.isArray(doc?.clips) ? doc.clips.filter(isObject) : []);
const startsOf = (doc) => new Map(clipsOf(doc).map((c) => [c.id, c.start]));
const sequenceOf = (doc) => clipsOf(doc).map((c) => [c.id, c.dur]);
const ownedBy = (reference, shots) => isObject(reference?.scope) && reference.scope.type === 'shot' && shots.has(reference.scope.shotId);

function shifted(doc, starts, move) {
	const next = { ...doc };
	for (const key of LINKED) {
		if (!Array.isArray(doc[key])) continue;
		next[key] = doc[key].map((item) => {
			const k = isObject(item) ? timeKey(item) : null;
			const start = k ? starts.get(item.shotId) : undefined;
			return typeof start === 'number' && typeof item[k] === 'number' ? { ...item, [k]: move(item[k], start) } : item;
		});
	}
	return next;
}

function relative(doc) {
	if (!isObject(doc) || !Array.isArray(doc.clips)) return doc;
	const next = shifted(doc, startsOf(doc), (time, start) => fixed(time - start));
	next.clips = doc.clips.map((c) => {
		if (!isObject(c)) return c;
		const { start, ...rest } = c;
		return rest;
	});
	return next;
}

function laidOut(clips) {
	const starts = new Map();
	let time = 0;
	for (const c of clips) {
		starts.set(c.id, snap(time));
		time += typeof c.dur === 'number' ? c.dur : 0;
	}
	return starts;
}

function absolute(doc, mine, theirs) {
	if (!isObject(doc) || !Array.isArray(doc.clips)) return doc;
	const sequence = sequenceOf(doc);
	const source = [mine, theirs].find((side) => same(sequenceOf(side), sequence));
	const starts = source ? startsOf(source) : laidOut(clipsOf(doc));
	const next = shifted(doc, starts, (offset, start) => fixed(start + offset));
	next.clips = doc.clips.map((c) => (isObject(c) && starts.has(c.id) ? { ...c, start: starts.get(c.id) } : c));
	return next;
}

function shotParts(doc, id) {
	return {
		clip: clipsOf(doc).find((c) => c.id === id) ?? null,
		linked: LINKED.flatMap((key) => (Array.isArray(doc?.[key]) ? doc[key].filter((x) => x?.shotId === id) : [])),
		references: Array.isArray(doc?.references) ? doc.references.filter((r) => ownedBy(r, new Set([id]))) : []
	};
}

function withoutShots(doc, gone) {
	if (!gone.size || !isObject(doc)) return doc;
	const next = { ...doc, clips: doc.clips.filter((c) => !gone.has(c?.id)) };
	for (const key of LINKED) if (Array.isArray(doc[key])) next[key] = doc[key].filter((x) => !gone.has(x?.shotId));
	if (Array.isArray(doc.references)) next.references = doc.references.filter((r) => !ownedBy(r, gone));
	return next;
}

export function mergeDocs(base, mine, theirs) {
	const [b, m, t] = [base, mine, theirs].map(relative);
	const out = { conflicts: 0, dropped: 0 };
	const present = (doc) => new Set(clipsOf(doc).map((c) => c.id));
	const [inMine, inTheirs] = [present(m), present(t)];
	const gone = new Set([...present(b)].filter((id) => !inMine.has(id) || !inTheirs.has(id)));
	for (const id of gone) {
		const before = shotParts(b, id);
		if (inMine.has(id) && !same(before, shotParts(m, id))) out.dropped += 1;
		if (inTheirs.has(id) && !same(before, shotParts(t, id))) out.conflicts += 1;
	}
	const value = mergeValue(...[b, m, t].map((doc) => withoutShots(doc, gone)), out);
	const settled = migrateVrefs(value);
	if (!same(settled, value)) out.conflicts += 1;
	return { value: absolute(settled, mine, theirs), conflicts: out.conflicts, dropped: out.dropped };
}

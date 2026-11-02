import { isInFlight, sortTakes } from './generation.js';

export const takeStore = $state({ projectId: null, list: [], loaded: false });

const listeners = new Set();

export function onTake(listener) {
	listeners.add(listener);
	return () => listeners.delete(listener);
}

function told(take, live) {
	for (const listener of listeners) listener(take, live);
}

export function resetTakes(projectId = null) {
	takeStore.projectId = projectId;
	takeStore.list = [];
	takeStore.loaded = false;
}

export function setTakes(projectId, list) {
	takeStore.projectId = projectId;
	takeStore.list = list;
	takeStore.loaded = true;
	for (const take of takeStore.list) told(take, false);
}

export function takeById(id) {
	return id ? (takeStore.list.find((t) => t.id === id) ?? null) : null;
}

export function upsertTake(take) {
	if (!take || (take.projectId && takeStore.projectId && take.projectId !== takeStore.projectId)) return null;
	const i = takeStore.list.findIndex((t) => t.id === take.id);
	if (i < 0) takeStore.list.push(take);
	else Object.assign(takeStore.list[i], take);
	const stored = takeById(take.id);
	told(stored, true);
	return stored;
}

export function patchTake(id, fields) {
	const take = takeById(id);
	if (take) Object.assign(take, fields);
	return take;
}

export function removeTake(id) {
	const i = takeStore.list.findIndex((t) => t.id === id);
	if (i >= 0) takeStore.list.splice(i, 1);
}

export function realTakesOf(shotId) {
	return sortTakes(takeStore.list.filter((t) => t.shotId === shotId));
}

export function flyingTakes() {
	return takeStore.list.filter(isInFlight);
}

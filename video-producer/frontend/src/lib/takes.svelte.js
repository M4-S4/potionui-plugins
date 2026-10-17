import { isInFlight, sortTakes } from './generation.js';

export const takeStore = $state({ projectId: null, list: [], loaded: false });

export function resetTakes(projectId = null) {
	takeStore.projectId = projectId;
	takeStore.list = [];
	takeStore.loaded = false;
}

export function setTakes(projectId, list) {
	takeStore.projectId = projectId;
	takeStore.list = list;
	takeStore.loaded = true;
}

export function takeById(id) {
	return id ? (takeStore.list.find((t) => t.id === id) ?? null) : null;
}

export function upsertTake(take) {
	if (!take || (take.projectId && takeStore.projectId && take.projectId !== takeStore.projectId)) return null;
	const i = takeStore.list.findIndex((t) => t.id === take.id);
	if (i < 0) takeStore.list.push(take);
	else Object.assign(takeStore.list[i], take);
	return takeById(take.id);
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

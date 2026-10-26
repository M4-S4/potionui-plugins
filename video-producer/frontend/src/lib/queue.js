import { isInFlight } from './generation.js';

export const handedOver = (take) => take?.status === 'running' || Boolean(take?.generationId);
export const isWaiting = (take) => take?.status === 'queued' && !take?.generationId && take?.chain?.state !== 'waiting';

function byQueue(a, b) {
	const handed = Number(handedOver(b)) - Number(handedOver(a));
	if (handed) return handed;
	const priority = (b.priority ?? 0) - (a.priority ?? 0);
	if (priority) return priority;
	const at = a.createdAt ?? '';
	const bt = b.createdAt ?? '';
	if (at !== bt) return at < bt ? -1 : 1;
	return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

export function queueOrder(takes) {
	return (takes ?? []).filter(isInFlight).sort(byQueue);
}

export function canPrioritize(take, ordered) {
	if (!isWaiting(take)) return false;
	const head = ordered.find(isWaiting);
	return Boolean(head) && head.id !== take.id;
}

export function prioritized(takes, takeId) {
	const ordered = queueOrder(takes);
	const take = ordered.find((x) => x.id === takeId);
	if (!take || !canPrioritize(take, ordered)) return null;
	return Math.max(...ordered.filter(isWaiting).map((x) => x.priority ?? 0)) + 1;
}

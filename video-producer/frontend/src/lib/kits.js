export const KIT_PICKER = 'MediaPickerModal';
export const LEFT_REASONS = ['text', 'missing', 'kind', 'unread'];

export function kitsAvailable() {
	return typeof window !== 'undefined' && Boolean(window.__potionui?.components?.[KIT_PICKER]);
}

export const kindSet = (kinds) => (kinds.includes('image') && kinds.includes('video') ? 'media' : kinds[0]);

const filled = (value) => typeof value === 'string' && value.length > 0;

export const pickKey = (origin) => (origin?.kind === 'history' ? `history:${origin.generationId}:${origin.fileId}` : origin?.kind === 'library' ? `library:${origin.itemId}` : null);

export function fromKitItem(item) {
	if (!item || typeof item !== 'object' || !('media_ref' in item)) return { left: 'unread' };
	if (item.kind === 'text') return { left: 'text' };
	if (item.missing || !filled(item.media_ref)) return { left: 'missing' };
	return { origin: { kind: 'library', itemId: item.media_ref }, filename: item.name || null, mediaType: item.kind };
}

export function fromPicked(picked) {
	if (!picked || typeof picked !== 'object') return { left: 'unread' };
	if (picked.kitItem || picked.origin?.kind === 'kit') return fromKitItem(picked.kitItem);
	const origin = picked.origin;
	if (origin?.kind === 'library' && filled(origin.itemId)) return { origin: { kind: 'library', itemId: origin.itemId }, filename: picked.filename ?? null, mediaType: picked.mediaType ?? null };
	if (origin?.kind === 'history' && filled(origin.generationId) && (filled(origin.fileId) || Number.isFinite(origin.fileId))) {
		return { origin: { kind: 'history', generationId: origin.generationId, fileId: origin.fileId }, filename: picked.filename ?? null, mediaType: picked.mediaType ?? null };
	}
	return { left: 'unread' };
}

export const emptyLeft = () => ({ text: 0, missing: 0, kind: 0, unread: 0 });

export const leftTotal = (left) => LEFT_REASONS.reduce((sum, reason) => sum + (left?.[reason] ?? 0), 0);

function inKitOrder(items) {
	return (Array.isArray(items) ? items : []).map((item, index) => ({ item, index })).sort((a, b) => (a.item?.position ?? a.index) - (b.item?.position ?? b.index) || a.index - b.index).map(({ item }) => item);
}

export function gatherPicks({ items = [], kits = [] }, allowed) {
	const picks = [];
	const left = emptyLeft();
	const seen = new Set();
	const take = (pick) => {
		if (pick.left) {
			left[pick.left] += 1;
			return;
		}
		if (pick.mediaType && !allowed.includes(pick.mediaType)) {
			left.kind += 1;
			return;
		}
		const key = pickKey(pick.origin);
		if (seen.has(key)) return;
		seen.add(key);
		picks.push(pick);
	};
	for (const picked of items) take(fromPicked(picked));
	for (const kit of kits) for (const item of inKitOrder(kit?.items)) take(fromKitItem(item));
	return { picks, left };
}

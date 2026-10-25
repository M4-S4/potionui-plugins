import { roleKind } from './seam.js';
import { releaseShot } from './shots.js';
import { markRemoved, takeOfAsset } from './removedtakes.js';

export const USE_KINDS = ['shots', 'sounds', 'references', 'edges', 'frames'];

const using = (list, id) => (list ?? []).filter((item) => item?.assetId === id);

export function assetUses(doc, id) {
	const frames = using(doc.frames, id);
	return {
		shots: using(doc.clips, id),
		sounds: using(doc.audio, id),
		references: using(doc.references, id),
		edges: frames.filter((f) => roleKind(f.role)),
		frames: frames.filter((f) => !roleKind(f.role))
	};
}

export const useCount = (uses) => USE_KINDS.reduce((n, kind) => n + uses[kind].length, 0);

function drop(list, gone) {
	const ids = new Set(gone.map((item) => item.id));
	for (let i = (list?.length ?? 0) - 1; i >= 0; i--) if (ids.has(list[i]?.id)) list.splice(i, 1);
}

export function removeAsset(doc, id) {
	const index = (doc.assets ?? []).findIndex((a) => a?.id === id);
	if (index < 0) return null;
	const uses = assetUses(doc, id);
	const released = uses.shots.map(releaseShot);
	for (const item of uses.references) item.assetId = null;
	drop(doc.audio, uses.sounds);
	drop(doc.frames, [...uses.edges, ...uses.frames]);
	const [asset] = doc.assets.splice(index, 1);
	markRemoved(doc, takeOfAsset(asset));
	return { asset, uses, released };
}

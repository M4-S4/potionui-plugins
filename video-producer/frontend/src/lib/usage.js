import { roleKind } from './seam.js';
import { releaseShot } from './shots.js';

export const USE_KINDS = ['shots', 'sounds', 'references', 'edges', 'frames', 'renders', 'controls', 'scenes'];

const using = (list, id, key = 'assetId') => (list ?? []).filter((item) => item?.[key] === id);

export function assetUses(doc, id) {
	const frames = using(doc.frames, id);
	const guides = using(doc.controls, id);
	return {
		shots: using(doc.clips, id),
		sounds: using(doc.audio, id),
		references: using(doc.references, id),
		edges: frames.filter((f) => roleKind(f.role)),
		frames: frames.filter((f) => !roleKind(f.role)),
		renders: guides.filter((c) => c.planId),
		controls: guides.filter((c) => !c.planId),
		scenes: using(doc.scenes, id, 'sourceAssetId')
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
	for (const item of [...uses.references, ...uses.renders]) item.assetId = null;
	for (const scene of uses.scenes) scene.sourceAssetId = null;
	drop(doc.audio, uses.sounds);
	drop(doc.frames, [...uses.edges, ...uses.frames]);
	drop(doc.controls, uses.controls);
	const [asset] = doc.assets.splice(index, 1);
	return { asset, uses, released };
}

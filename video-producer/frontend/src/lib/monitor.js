const shotAt = (clips, time) => clips.find((c) => time >= c.start && time < c.start + c.dur) ?? null;

export function placedOn(clips, take) {
	if (!take) return null;
	return clips.find((c) => c.id === take.shotId && c.take === take.id && c.assetId === `gen-${take.id}`) ?? null;
}

export function seamShots(clips, shotId) {
	const i = shotId ? clips.findIndex((c) => c.id === shotId) : -1;
	return i > 0 ? [clips[i - 1].id, clips[i].id] : [];
}

export function shownShots({ clips, playhead, preview = null, compare = null, seam = null }, find) {
	if (seam) return seamShots(clips, seam);
	const pair = (compare ?? []).map((id) => find.take(id)).filter(Boolean);
	const single = preview?.kind === 'result' ? find.take(preview.id) : null;
	const takes = pair.length === 2 ? pair : single ? [single] : null;
	if (takes) return takes.map((take) => placedOn(clips, take)?.id).filter(Boolean);
	if (preview?.kind === 'asset' && find.asset(preview.id)) return [];
	const clip = shotAt(clips, playhead);
	return clip ? [clip.id] : [];
}

export const LABELS = ['draft', 'rejected', 'candidate', 'final'];
export const GROUP_ORDER = ['final', 'candidate', 'draft', 'rejected'];
export const LABEL_TONES = { final: 'border-signal text-signal', candidate: 'border-success/60 text-success', rejected: 'border-danger/60 text-danger', draft: 'border-line-strong text-fg-muted' };

export function legacyLabel(chosen, flag) {
	if (chosen === true || chosen === 1) return 'final';
	if (flag === 'keep') return 'candidate';
	if (flag === 'reject') return 'rejected';
	return 'draft';
}

export function takeLabelOf(take) {
	if (!take) return 'draft';
	return LABELS.includes(take.label) ? take.label : legacyLabel(take.chosen, take.flag);
}

export const marksOf = (label) => ({ label, chosen: label === 'final', flag: label === 'candidate' ? 'keep' : label === 'rejected' ? 'reject' : null });

export function relabel(takes, takeId, label) {
	const take = takes.find((x) => x.id === takeId);
	if (!take || !LABELS.includes(label)) return {};
	const changes = { [takeId]: label };
	if (label !== 'final') return changes;
	for (const other of takes) if (other.id !== takeId && other.shotId === take.shotId && takeLabelOf(other) === 'final') changes[other.id] = 'candidate';
	return changes;
}

export const releasedLabel = (take) => (take && (takeLabelOf(take) === 'final' || takeLabelOf(take) === 'candidate') ? 'draft' : null);

export function canLabel(take, label) {
	if (!take || !LABELS.includes(label)) return false;
	if (label === 'final') return take.status === 'done' && Boolean(take.url);
	return takeLabelOf(take) !== 'final';
}

export function toggledLabel(take, label) {
	if (label === 'final') return 'final';
	return takeLabelOf(take) === label ? 'draft' : label;
}

export function visibleTakes(takes, hideRejected) {
	return hideRejected ? takes.filter((x) => takeLabelOf(x) !== 'rejected') : [...takes];
}

export function labelGroups(takes, hideRejected = false) {
	const shown = visibleTakes(takes, hideRejected);
	return GROUP_ORDER.map((label) => [label, shown.filter((x) => takeLabelOf(x) === label)]).filter(([, list]) => list.length);
}

export function rejectedCount(takes) {
	return takes.filter((x) => takeLabelOf(x) === 'rejected').length;
}

export function finalsToSync(clips, takes) {
	const changes = [];
	for (const clip of clips) {
		const own = takes.filter((x) => x.shotId === clip.id);
		const placed = own.find((x) => x.id === clip.take && x.status === 'done' && x.url);
		if (placed) {
			if (takeLabelOf(placed) !== 'final') changes.push([placed.id, 'final']);
		} else for (const x of own) if (takeLabelOf(x) === 'final') changes.push([x.id, 'candidate']);
	}
	return changes;
}

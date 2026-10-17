export const ANNOUNCE_STEP = 10;
export const ANNOUNCE_GAP_MS = 3000;

export function announcer(step = ANNOUNCE_STEP, gap = ANNOUNCE_GAP_MS) {
	let last = null;
	return {
		next(label, progress, now = Date.now()) {
			const value = Math.floor(Math.min(100, Math.max(0, Number(progress) || 0)) / step) * step;
			if (last && ((label === last.label && value === last.value) || now - last.at < gap)) return null;
			last = { label, value, at: now };
			return { label, value };
		},
		reset() {
			last = null;
		}
	};
}

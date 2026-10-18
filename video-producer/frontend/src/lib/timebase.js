export const DEFAULT_FPS = 25;
const WHEEL_NOTCH = 100;
const WHEEL_STEP = 1.15;
const WHEEL_LIMIT = WHEEL_NOTCH * 3;
const LINE_PIXELS = 33;
const PAGE_PIXELS = 400;
const WHEEL_RATE = Math.log(WHEEL_STEP) / WHEEL_NOTCH;

export function frameDuration(fps) {
	const rate = Number(fps);
	return 1 / (Number.isFinite(rate) && rate > 0 ? rate : DEFAULT_FPS);
}

export function wheelZoomFactor(e) {
	const unit = e.deltaMode === 1 ? LINE_PIXELS : e.deltaMode === 2 ? PAGE_PIXELS : 1;
	const delta = Number(e.deltaY) * unit;
	if (!Number.isFinite(delta)) return 1;
	return Math.exp(-Math.max(-WHEEL_LIMIT, Math.min(WHEEL_LIMIT, delta)) * WHEEL_RATE);
}

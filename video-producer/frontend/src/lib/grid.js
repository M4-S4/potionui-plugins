export const GRID_STEP = 0.04;

export function onStep(v, s = 0.1) {
	const value = Number(v);
	const step = Math.round(s * 1e6);
	if (!Number.isFinite(value)) return +(Math.round(value / s) * s).toFixed(3);
	return +(Math.floor((2 * Math.round(+value.toFixed(6) * 1e6) + step) / (2 * step)) * s).toFixed(3);
}

export const onGrid = (v) => onStep(v, GRID_STEP);

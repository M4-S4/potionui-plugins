export function advance(at, step, { loop = false, range = null, end }) {
	let t = at + step;
	if (loop && range && t >= range.out) t = range.in;
	if (t < end) return { t, stop: false };
	if (loop && !range) return { t: 0, stop: false };
	return { t: end, stop: true };
}

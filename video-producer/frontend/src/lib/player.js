export function advance(at, step, { loop = false, range = null, end }) {
	let t = at + step;
	if (loop && range && t >= range.out) t = range.in;
	if (t < end) return { t, stop: false };
	if (loop && !range) return { t: 0, stop: false };
	return { t: end, stop: true };
}

export function fractionOf(t, duration) {
	return duration > 0 ? Math.min(1, Math.max(0, t / duration)) : 0;
}

export function timeAt(clientX, rect, duration) {
	if (!(rect?.width > 0)) return 0;
	return fractionOf(clientX - rect.left, rect.width) * duration;
}

export function shotMarks(clips, duration) {
	return clips.map((c, index) => {
		const left = fractionOf(c.start, duration) * 100;
		return { id: c.id, index, left, width: fractionOf(c.start + c.dur, duration) * 100 - left };
	});
}

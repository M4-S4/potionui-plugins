export const DISSOLVE_KEY = 'dissolve';
export const MAX_DISSOLVE = 2;
export const DISSOLVE_CHOICES = [0.4, 0.6, 1, 1.2, 2];
export const GRID = 0.04;
export const MIN_STEPS = 2;
export const MIN_DISSOLVE = MIN_STEPS * GRID;

const STEP_SLACK = 1e-6;
const EPSILON = 1e-6;
const NEAR = 2 * EPSILON;
const positive = (value) => (typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0);
const finite = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : 0);
const rounded = (value) => +value.toFixed(6);

export const framesOf = (seconds, fps) => Math.floor(finite(seconds) * positive(fps) + 0.5);

export function limitOf(before, clip) {
	const asked = positive(clip?.[DISSOLVE_KEY]);
	if (!before || !clip || !asked) return { seconds: 0, by: null };
	const wanted = Math.min(asked, MAX_DISSOLVE);
	const half = Math.min(positive(before.dur), positive(clip.dur)) / 2;
	const steps = Math.floor(Math.min(wanted, half) / GRID + STEP_SLACK);
	const seconds = steps >= MIN_STEPS ? rounded(steps * GRID) : 0;
	if (wanted < MIN_DISSOLVE - STEP_SLACK) return { seconds: 0, by: 'brief' };
	if (!seconds) return { seconds, by: 'half' };
	if (half < wanted) return { seconds, by: 'half' };
	return { seconds, by: wanted - seconds > STEP_SLACK ? 'grid' : null };
}

export const dissolveOf = (before, clip) => limitOf(before, clip).seconds;

export function played(before, clip) {
	const length = dissolveOf(before, clip);
	if (!length) return 0;
	const overlap = finite(before.start) + finite(before.dur) - finite(clip.start);
	if (overlap <= GRID / 2 || overlap > length + EPSILON) return 0;
	return rounded(overlap);
}

export function placement(clips) {
	const places = (clips ?? []).map(() => null);
	let last = null;
	(clips ?? []).forEach((clip, index) => {
		const dur = positive(clip.dur);
		if (dur <= EPSILON) return;
		let start = finite(clip.start);
		let overlap = 0;
		if (last !== null) {
			const before = places[last];
			const joined = last === index - 1 && before.start === finite(clips[last].start) ? played(clips[last], clip) : 0;
			if (joined) overlap = joined;
			else if (start < before.end - EPSILON) {
				if (start > before.start + before.overlap + EPSILON) places[last] = { start: before.start, end: start, overlap: before.overlap };
				else start = before.end;
			}
		}
		places[index] = { start, end: rounded(start + dur), overlap };
		last = index;
	});
	return places;
}

export const moved = (clip, place) => !!place && (place.start !== finite(clip.start) || place.end !== rounded(place.start + positive(clip.dur)));

export const joins = (clips) => placement(clips).map((place) => place?.overlap ?? 0);

export const dissolving = (clips) => joins(clips).some(Boolean);

export const onFrame = (time, fps) => (positive(fps) ? rounded(Math.round(finite(time) * fps) / fps) : finite(time));

export function splitKeepsDissolves(clips, i, kept) {
	const clip = clips[i];
	if (!clip) return true;
	const before = i > 0 ? clips[i - 1] : null;
	const after = clips[i + 1] ?? null;
	const first = { ...clip, dur: kept };
	const second = { ...clip, dur: rounded(finite(clip.dur) - kept) };
	delete second[DISSOLVE_KEY];
	const head = before ? dissolveOf(before, clip) : 0;
	const tail = after ? dissolveOf(clip, after) : 0;
	return (!head || dissolveOf(before, first) === head) && (!tail || dissolveOf(second, after) === tail);
}

export const LEAST_SHOT = 0.4;

export function headTrim(srcIn, dur, speed, shift) {
	const from = finite(srcIn);
	const length = finite(dur);
	const rate = positive(speed) ? speed : 1;
	const moved = Math.min(Math.max(Math.round(finite(shift) / GRID) * GRID, -from / rate), Math.max(length - LEAST_SHOT, 0));
	return { srcIn: rounded(Math.max(from + moved * rate, 0)), dur: rounded(length - moved) };
}

export const tailTrim = (start, end, most) => rounded(Math.min(Math.max(finite(end) - finite(start), LEAST_SHOT), Math.max(finite(most), LEAST_SHOT)));

export const playedLengths = (clips) => (chained(clips) ? Object.fromEntries(clips.map((clip, i) => [clip.id, i > 0 ? dissolveOf(clips[i - 1], clip) : 0])) : null);

function limitedSince(before, clips, kept) {
	if (!before) return [];
	return (clips ?? []).flatMap((clip, i) => {
		if (!i || !(clip.id in before)) return [];
		const limit = limitOf(clips[i - 1], clip);
		return limit.by === 'half' && kept(limit.seconds, before[clip.id]) ? [limit.seconds] : [];
	});
}

export const newlyLimited = (before, clips) => limitedSince(before, clips, (now, was) => Math.abs(now - was) > EPSILON);

export const droppedDissolves = (before, clips) => limitedSince(before, clips, (now, was) => now < was - EPSILON);

export const chained = (clips) => (clips ?? []).some((clip, i) => i > 0 && dissolveOf(clips[i - 1], clip) > 0);

export function layout(clips, snap) {
	const exact = chained(clips);
	let at = 0;
	const starts = [];
	clips.forEach((clip, i) => {
		if (!exact) starts.push(snap(at));
		else starts.push(i ? rounded(starts[i - 1] + finite(clips[i - 1].dur) - dissolveOf(clips[i - 1], clip)) : 0);
		at += finite(clip.dur);
	});
	return starts;
}

export const dissolveBefore = (clips, i) => (i > 0 ? (joins(clips)[i] ?? 0) : 0);

export const dissolveAfter = (clips, i) => (i >= 0 ? (joins(clips)[i + 1] ?? 0) : 0);

export const lostSeconds = (clips) => rounded(joins(clips).reduce((sum, d) => sum + d, 0));

export function asked(clip) {
	return positive(clip?.[DISSOLVE_KEY]);
}

export function setDissolve(clips, i, value) {
	const clip = clips[i];
	if (!clip || i <= 0) return false;
	const length = positive(value);
	if (!length) {
		delete clip[DISSOLVE_KEY];
		return true;
	}
	clip[DISSOLVE_KEY] = Math.min(length, MAX_DISSOLVE);
	if (dissolveOf(clips[i - 1], clip) > 0) {
		clips[i - 1].fadeOut = 0;
		clip.fadeIn = 0;
	}
	return true;
}

export function unfaded(clips, i, places = placement(clips)) {
	const clip = clips[i];
	const overlaps = places.map((place) => place?.overlap ?? 0);
	const head = i > 0 && overlaps[i] > 0;
	const tail = overlaps[i + 1] > 0;
	return head || tail ? { ...clip, ...(head ? { fadeIn: 0 } : {}), ...(tail ? { fadeOut: 0 } : {}) } : clip;
}

function spans(clips) {
	const places = placement(clips);
	if (!places.some((place) => place?.overlap)) return (clips ?? []).map((clip) => ({ start: clip.start, end: clip.start + clip.dur, dur: clip.dur, head: 0, tail: 0 }));
	const starts = places.map((place, i) => (place ? place.start + place.overlap / 2 : finite(clips[i].start)));
	const ends = places.map((place, i) => (place ? place.end : starts[i]));
	places.forEach((place, i) => {
		if (!place || !(places[i + 1]?.overlap > 0)) return;
		starts[i + 1] = Math.max(starts[i + 1], starts[i]);
		ends[i] = starts[i + 1];
	});
	return places.map((place, i) => {
		const end = Math.max(ends[i], starts[i]);
		return { start: starts[i], end, dur: end - starts[i], head: (place?.overlap ?? 0) / 2, tail: (places[i + 1]?.overlap ?? 0) / 2 };
	});
}

export const shownSpans = (clips) => spans(clips);

export const shownSpan = (clips, i) => spans(clips)[i];

export function indexAt(clips, time) {
	return spans(clips).findIndex((span) => time >= span.start && time < span.end);
}

export function holderAt(clips, time, kind) {
	const inside = (clips ?? []).flatMap((clip, i) => (time >= finite(clip.start) - NEAR && time <= finite(clip.start) + finite(clip.dur) + NEAR ? [i] : []));
	if (!inside.length) return -1;
	return kind === 'last' ? inside[0] : inside.at(-1);
}

export function startingAt(clips, time) {
	if (!dissolving(clips)) return indexAt(clips, time);
	const places = placement(clips);
	const starting = places.findIndex((place) => place && Math.abs(place.start - time) <= NEAR);
	return starting >= 0 ? starting : indexAt(clips, time);
}

export function dissolveMarks(clips) {
	const places = placement(clips);
	const marks = [];
	places.forEach((place, i) => {
		if (place?.overlap > 0) marks.push({ id: clips[i].id, from: clips[i - 1], to: clips[i], start: place.start, dur: place.overlap });
	});
	return marks;
}

export function mixAt(clips, time) {
	const places = placement(clips);
	for (let i = 1; i < places.length; i++) {
		const place = places[i];
		if (place?.overlap > 0 && time >= place.start && time < place.start + place.overlap) return { from: clips[i - 1], to: clips[i], index: i, progress: (time - place.start) / place.overlap };
	}
	return null;
}

export function dissolveGain(clips, i, time, places = placement(clips)) {
	const place = places[i];
	if (!place) return 1;
	let gain = 1;
	if (place.overlap > 0 && time < place.start + place.overlap) gain *= Math.sin((Math.max(time - place.start, 0) / place.overlap) * (Math.PI / 2));
	const next = places[i + 1];
	if (next?.overlap > 0 && time >= next.start) gain *= Math.cos((Math.min(time - next.start, next.overlap) / next.overlap) * (Math.PI / 2));
	return Math.min(Math.max(gain, 0), 1);
}

export function cuts(clips, frames) {
	const places = placement(clips);
	if (!places.some((place) => place?.overlap)) return clips.map(() => null);
	const starts = places.map((place) => (place ? frames(place.start) : 0));
	const ends = places.map((place) => (place ? frames(place.end) : 0));
	const overlaps = clips.map(() => 0);
	for (let i = 1; i < clips.length; i++) {
		if (places[i]?.overlap) {
			ends[i - 1] = Math.max(ends[i - 1], starts[i] + 1);
			overlaps[i] = ends[i - 1] - starts[i];
		} else if (places[i]) ends[i - 1] = Math.min(ends[i - 1], starts[i]);
	}
	const edits = starts.map((start, i) => start + Math.floor(overlaps[i] / 2));
	return clips.map((clip, i) => {
		const place = places[i];
		const following = i + 1 < clips.length && overlaps[i + 1] > 0;
		if (!place || !(overlaps[i] || following || moved(clip, place))) return null;
		const start = overlaps[i] ? edits[i] : starts[i];
		const end = following ? edits[i + 1] : ends[i];
		return { start, end, overlap: overlaps[i], head: start - starts[i] };
	});
}

const finite = (value, fallback) => (typeof value === 'number' && Number.isFinite(value) ? value : fallback);

export const gainOf = (rule, db) => {
	const value = finite(db, 0);
	return value <= rule.silentAt ? 0 : Math.pow(10, value / 20);
};

const insertOf = (lane, type) => (Array.isArray(lane.inserts) ? lane.inserts.find((i) => i?.type === type && i.on === true) : null) ?? null;

export function makeupOf(rule, threshold, ratio) {
	if (!(ratio > 1) || !(threshold < 0)) return 1;
	const reduced = -threshold * (1 - 1 / ratio);
	return Math.min(Math.pow(10, (reduced * rule.comp.makeupPower) / 20), rule.comp.maxMakeup);
}

export function panOf(pan) {
	const p = Math.min(1, Math.max(-1, finite(pan, 0)));
	const x = p <= 0 ? p + 1 : p;
	const near = Math.cos((x * Math.PI) / 2);
	const far = Math.sin((x * Math.PI) / 2);
	return p <= 0 ? { ll: 1, rl: near, lr: 0, rr: far } : { ll: near, rl: 0, lr: far, rr: 1 };
}

export function sendOf(rule, lane, aux, id) {
	const bus = (Array.isArray(aux) ? aux : []).find((a) => a?.id === id);
	if (bus?.mute) return 0;
	return gainOf(rule, finite(lane.sends?.[id], rule.silentAt)) * gainOf(rule, finite(bus?.vol, 0));
}

const within = ([low, high], value) => Math.min(high, Math.max(low, value));

function compOf(rule, comp) {
	if (!comp) return null;
	const bounds = rule.comp;
	const threshold = within(bounds.threshold, finite(comp.threshold, 0));
	const ratio = within(bounds.ratio, finite(comp.ratio, 1));
	if (!(ratio > 1) || !(threshold < 0)) return null;
	const attack = within(bounds.attack, finite(comp.attack, bounds.attack[0]));
	const release = within(bounds.release, finite(comp.release, bounds.release[0]));
	return { threshold, ratio, attack, release, knee: bounds.knee, makeup: makeupOf(rule, threshold, ratio) };
}

export function stripOf(rule, lane, aux, audible = true) {
	const eq = insertOf(lane, 'eq');
	const filter = insertOf(lane, 'filter');
	const band = (key) => (eq ? within(rule.eq.gain, finite(eq[key], 0)) : 0);
	return {
		eq: { low: band('low'), mid: band('mid'), high: band('high') },
		cutoff: filter && finite(filter.cutoff, null) !== null ? within(rule.filter.cutoff, filter.cutoff) : null,
		comp: compOf(rule, insertOf(lane, 'comp')),
		pan: Math.min(1, Math.max(-1, finite(lane.pan, 0))),
		fader: audible ? gainOf(rule, lane.vol) : 0,
		sends: { [rule.reverb.id]: sendOf(rule, lane, aux, rule.reverb.id), [rule.delay.id]: sendOf(rule, lane, aux, rule.delay.id) }
	};
}

export function random(seed) {
	let a = seed | 0;
	return () => {
		a = (a + 0x6d2b79f5) | 0;
		let t = Math.imul(a ^ (a >>> 15), 1 | a);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

export const impulseLength = (rule, rate) => Math.floor(rate * rule.reverb.seconds + 0.5);

export function reverbImpulse(rule, rate) {
	const { decay, seed, calibration, calibrationRate } = rule.reverb;
	const length = impulseLength(rule, rate);
	const next = random(seed);
	const channels = [new Float64Array(length), new Float64Array(length)];
	let power = 0;
	for (const data of channels)
		for (let i = 0; i < length; i++) {
			const fall = 1 - i / length;
			let envelope = 1;
			for (let k = 0; k < decay; k++) envelope *= fall;
			const value = (next() * 2 - 1) * envelope;
			data[i] = value;
			power += value * value;
		}
	const scale = (calibration / Math.sqrt(power / (2 * length))) * (calibrationRate / rate);
	return channels.map((data) => Float32Array.from(data, (value) => value * scale));
}

export function delayTaps(rule) {
	const { seconds, feedback, floor } = rule.delay;
	const least = Math.pow(10, floor / 20);
	const taps = [];
	for (let gain = 1, k = 1; gain >= least; gain *= feedback, k++) taps.push({ seconds: seconds * k, gain });
	return taps;
}

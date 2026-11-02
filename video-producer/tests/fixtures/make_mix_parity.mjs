import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { delayTaps, gainOf, impulseLength, makeupOf, panOf, random, reverbImpulse, sendOf, stripOf } from '../../frontend/src/lib/mix.js';

const here = dirname(fileURLToPath(import.meta.url));
const rulePath = join(here, '..', '..', 'frontend', 'src', 'lib', 'mix.json');
const rule = JSON.parse(readFileSync(rulePath, 'utf-8'));

const sorted = (value) => {
	if (Array.isArray(value)) return value.map(sorted);
	if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sorted(value[key])]));
	return value;
};

const AUX = [
	[
		{ id: 'R1', name: 'Reverb', vol: -6, mute: false },
		{ id: 'D1', name: 'Delay', vol: -10, mute: false }
	],
	[
		{ id: 'R1', name: 'Reverb', vol: 0, mute: true },
		{ id: 'D1', name: 'Delay', vol: -59, mute: false }
	],
	[],
	[{ id: 'R1', name: 'Reverb', vol: 3, mute: false }]
];

const lane = (extra) => ({ id: 'a', name: 'A1', role: 'Dialogue', vol: 0, pan: 0, mute: false, solo: false, sends: { R1: -18, D1: -60 }, inserts: [], ...extra });

const LANES = [
	lane({}),
	lane({ vol: -6.5, pan: -0.4, sends: { R1: -12, D1: -20 } }),
	lane({ vol: -59, pan: 1 }),
	lane({ vol: 4, pan: 0.25, inserts: [{ type: 'eq', on: true, low: 3, mid: -2.5, high: 1 }] }),
	lane({ inserts: [{ type: 'eq', on: false, low: 6, mid: 6, high: 6 }, { type: 'filter', on: true, cutoff: 8000 }] }),
	lane({ inserts: [{ type: 'comp', on: true, threshold: -18, ratio: 3, attack: 10, release: 120 }] }),
	lane({ inserts: [{ type: 'comp', on: true, threshold: -60, ratio: 20, attack: 1, release: 1000 }, { type: 'filter', on: true, cutoff: 50000 }] }),
	lane({ inserts: [{ type: 'comp', on: true, threshold: 0, ratio: 4, attack: 10, release: 120 }] }),
	lane({ inserts: [{ type: 'comp', on: true, threshold: -30, ratio: 1, attack: 10, release: 120 }] }),
	lane({ inserts: [{ type: 'comp', on: true, threshold: -90, ratio: 40, attack: 5000, release: 0 }, { type: 'eq', on: true, low: 40, mid: -40, high: 0 }] }),
	lane({ pan: -3, vol: -60, sends: { R1: 0, D1: 0 } }),
	lane({ pan: 2, sends: { R1: -59, D1: -58.5 } })
];

const strips = [];
for (const [laneIndex, l] of LANES.entries())
	for (const [auxIndex, aux] of AUX.entries())
		for (const audible of [true, false]) strips.push({ lane: laneIndex, aux: auxIndex, audible, strip: stripOf(rule, l, aux, audible) });

const levels = [-80, -60, -59.5, -59, -58.9, -24, -6, 0, 0.5, 6, null, 'x'].map((db) => ({ db, gain: gainOf(rule, db) }));
const makeups = [];
for (const threshold of [-60, -45, -30, -18, -6, -0.5, 0])
	for (const ratio of [1, 1.5, 2, 3, 8, 20]) makeups.push({ threshold, ratio, makeup: makeupOf(rule, threshold, ratio) });
const pans = [-1, -0.75, -0.5, -0.25, -0.1, 0, 0.1, 0.25, 0.5, 0.75, 1, -2, 2, null].map((pan) => ({ pan, gains: panOf(pan) }));
const sends = [];
for (const [laneIndex, l] of LANES.entries())
	for (const [auxIndex, aux] of AUX.entries()) for (const id of ['R1', 'D1']) sends.push({ lane: laneIndex, aux: auxIndex, id, gain: sendOf(rule, l, aux, id) });

const next = random(rule.reverb.seed);
const sequence = Array.from({ length: 16 }, () => next());
const impulses = [44100, 48000].map((rate) => {
	const channels = reverbImpulse(rule, rate);
	const hash = createHash('sha256');
	for (const data of channels) hash.update(Buffer.from(data.buffer, data.byteOffset, data.byteLength));
	return {
		rate,
		length: impulseLength(rule, rate),
		sha256: hash.digest('hex'),
		head: channels.map((data) => Array.from(data.slice(0, 4))),
		tail: channels.map((data) => Array.from(data.slice(-2)))
	};
});

const out = {
	mixSha256: createHash('sha256').update(JSON.stringify(sorted(rule))).digest('hex'),
	lanes: LANES,
	aux: AUX,
	strips,
	levels,
	makeups,
	pans,
	sends,
	sequence,
	impulses,
	taps: delayTaps(rule)
};
writeFileSync(join(here, 'mix_parity.json'), JSON.stringify(out) + '\n');
console.log(`${strips.length} strips, ${makeups.length} make-up gains, ${impulses.length} impulse responses, ${out.taps.length} echoes`);

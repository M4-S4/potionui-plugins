import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { delayTaps, gainOf, impulseLength, makeupOf, panOf, random, reverbImpulse, sendOf, stripOf } from './mix.js';

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const rule = read('./mix.json');
const PARITY = read('../../../tests/fixtures/mix_parity.json');

test('the page copy of mix.json is identical to the backend one', () => {
	assert.deepEqual(rule, read('../../../backend/exports/mix.json'));
});

test('the parity cases the backend checks are what the page computes today', () => {
	for (const c of PARITY.strips) assert.deepEqual(stripOf(rule, PARITY.lanes[c.lane], PARITY.aux[c.aux], c.audible), c.strip);
	for (const c of PARITY.levels) assert.equal(gainOf(rule, c.db), c.gain);
	for (const c of PARITY.makeups) assert.equal(makeupOf(rule, c.threshold, c.ratio), c.makeup);
	for (const c of PARITY.pans) assert.deepEqual(panOf(c.pan), c.gains);
	for (const c of PARITY.sends) assert.equal(sendOf(rule, PARITY.lanes[c.lane], PARITY.aux[c.aux], c.id), c.gain);
	assert.deepEqual(delayTaps(rule), PARITY.taps);
	const next = random(rule.reverb.seed);
	assert.deepEqual(PARITY.sequence.map(() => next()), PARITY.sequence);
	for (const c of PARITY.impulses) {
		const channels = reverbImpulse(rule, c.rate);
		assert.deepEqual(channels.map((data) => data.length), [c.length, c.length]);
		assert.deepEqual(channels.map((data) => Array.from(data.slice(0, 4))), c.head);
	}
});

test('a strip passes its sound untouched until an insert, a pan or a fader changes it', () => {
	const lane = { vol: 0, pan: 0, sends: { R1: -60, D1: -60 }, inserts: [{ type: 'comp', on: false, threshold: -18, ratio: 3, attack: 10, release: 120 }] };
	assert.deepEqual(stripOf(rule, lane, []), { eq: { low: 0, mid: 0, high: 0 }, cutoff: null, comp: null, pan: 0, fader: 1, sends: { R1: 0, D1: 0 } });
	assert.equal(stripOf(rule, lane, [], false).fader, 0);
});

test('the compressor is hard-kneed, bounded like the console, and makes up what it takes off full scale', () => {
	const lane = { vol: 0, pan: 0, sends: {}, inserts: [{ type: 'comp', on: true, threshold: -18, ratio: 3, attack: 10, release: 120 }] };
	const comp = stripOf(rule, lane, []).comp;
	assert.equal(comp.knee, 0);
	assert.ok(Math.abs(20 * Math.log10(comp.makeup) - 7.2) < 1e-9);
	const wild = stripOf(rule, { ...lane, inserts: [{ type: 'comp', on: true, threshold: -90, ratio: 40, attack: 5000, release: 0 }] }).comp;
	assert.deepEqual([wild.threshold, wild.ratio, wild.attack, wild.release], [-60, 20, 1000, 0.01]);
	assert.equal(stripOf(rule, { ...lane, inserts: [{ type: 'comp', on: true, threshold: 0, ratio: 4, attack: 10, release: 120 }] }).comp, null);
});

test('a send is post-fader, scaled by its bus and silent when the bus is muted', () => {
	const lane = { vol: 0, pan: 0, sends: { R1: -12, D1: -59 }, inserts: [] };
	const aux = [{ id: 'R1', vol: -6, mute: false }, { id: 'D1', vol: 0, mute: false }];
	assert.ok(Math.abs(sendOf(rule, lane, aux, 'R1') - Math.pow(10, -18 / 20)) < 1e-15);
	assert.equal(sendOf(rule, lane, aux, 'D1'), 0);
	assert.equal(sendOf(rule, lane, [{ id: 'R1', vol: 0, mute: true }], 'R1'), 0);
	assert.ok(Math.abs(sendOf(rule, lane, [], 'R1') - Math.pow(10, -12 / 20)) < 1e-15);
});

test('the reverb impulse is seeded, as long as the rule says at any rate, and the same every time', () => {
	assert.equal(impulseLength(rule, 48000), 115200);
	assert.equal(impulseLength(rule, 44100), 105840);
	const [a, b] = [reverbImpulse(rule, 48000), reverbImpulse(rule, 48000)];
	assert.deepEqual(a[0].slice(0, 32), b[0].slice(0, 32));
	assert.notDeepEqual(a[0].slice(0, 32), a[1].slice(0, 32));
});

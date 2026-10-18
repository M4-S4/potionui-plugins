import { t } from '../i18n/index.svelte.js';
import { ui, doc, asset, seqDuration, clamp, toast } from './state.svelte.js';
import { mediaFailure } from './playable.js';

export const meters = $state({ lanes: {}, master: [0, 0] });

let raf = 0;
let last = 0;

export function togglePlay() {
	ui.playing ? pause() : play();
}
export function play() {
	if (ui.playing) return;
	const end = ui.range && ui.loop ? ui.range.out : seqDuration();
	if (ui.playhead >= end - 0.05) ui.playhead = ui.range && ui.loop ? ui.range.in : 0;
	ui.playing = true;
	ensureAudio();
	updateAudio();
	unlockVoices();
	last = performance.now();
	raf = requestAnimationFrame(frame);
}
export function pause() {
	ui.playing = false;
	cancelAnimationFrame(raf);
	silence();
}
export function seek(t) {
	ui.playhead = clamp(t, 0, seqDuration());
}

function frame(now) {
	const dt = Math.min(0.5, (now - last) / 1000);
	last = now;
	let t = ui.playhead + dt;
	if (ui.loop && ui.range && t >= ui.range.out) t = ui.range.in;
	const end = seqDuration();
	if (t >= end) {
		ui.playhead = end;
		return pause();
	}
	ui.playhead = t;
	updateAudio();
	if (ui.playing) raf = requestAnimationFrame(frame);
}

let ctx = null;
let master = null;
let masterAn = null;
let monitor = null;
const voices = new Map();
const strips = new Map();
let reverb = null;
let delay = null;

function ensureAudio() {
	try {
		if (!ctx) {
			ctx = new (window.AudioContext || window.webkitAudioContext)();
			monitor = ctx.createGain();
			master = ctx.createGain();
			masterAn = ctx.createAnalyser();
			masterAn.fftSize = 512;
			master.connect(masterAn).connect(monitor).connect(ctx.destination);
			reverb = makeReverb();
			delay = makeDelay();
		}
		if (ctx.state === 'suspended') ctx.resume();
	} catch {
		ctx = null;
	}
}

function makeReverb() {
	const len = ctx.sampleRate * 2.4;
	const buf = ctx.createBuffer(2, len, ctx.sampleRate);
	for (let ch = 0; ch < 2; ch++) {
		const d = buf.getChannelData(ch);
		for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
	}
	const input = ctx.createGain();
	const conv = ctx.createConvolver();
	conv.buffer = buf;
	const out = ctx.createGain();
	input.connect(conv).connect(out).connect(master);
	return { input, out };
}
function makeDelay() {
	const input = ctx.createGain();
	const d = ctx.createDelay(1);
	d.delayTime.value = 0.32;
	const fb = ctx.createGain();
	fb.gain.value = 0.35;
	const out = ctx.createGain();
	input.connect(d).connect(out).connect(master);
	d.connect(fb).connect(d);
	return { input, out };
}

const db = (v) => (v <= -59 ? 0 : Math.pow(10, v / 20));

function strip(lane) {
	let s = strips.get(lane.id);
	if (s) return s;
	const input = ctx.createGain();
	const lo = ctx.createBiquadFilter();
	lo.type = 'lowshelf';
	lo.frequency.value = 200;
	const mid = ctx.createBiquadFilter();
	mid.type = 'peaking';
	mid.frequency.value = 1200;
	const hi = ctx.createBiquadFilter();
	hi.type = 'highshelf';
	hi.frequency.value = 5000;
	const filt = ctx.createBiquadFilter();
	filt.type = 'lowpass';
	filt.frequency.value = 20000;
	const comp = ctx.createDynamicsCompressor();
	const pan = ctx.createStereoPanner();
	const fader = ctx.createGain();
	const an = ctx.createAnalyser();
	an.fftSize = 512;
	const sendR = ctx.createGain();
	const sendD = ctx.createGain();
	input.connect(lo).connect(mid).connect(hi).connect(filt).connect(comp).connect(pan).connect(fader).connect(an).connect(master);
	fader.connect(sendR).connect(reverb.input);
	fader.connect(sendD).connect(delay.input);
	s = { input, lo, mid, hi, filt, comp, pan, fader, an, sendR, sendD };
	strips.set(lane.id, s);
	return s;
}

const unplayable = new Set();
const unlocked = new WeakSet();
let refusalShown = false;

function refused(error) {
	if (error?.name !== 'NotAllowedError' || refusalShown) return;
	refusalShown = true;
	toast(t('lib.toast.audioBlocked'), 'warning');
}

function unlockVoices() {
	for (const v of voices.values()) {
		const el = v.el;
		if (!el || !el.paused || unlocked.has(el)) continue;
		unlocked.add(el);
		el.play().then(
			() => {
				if (!v.live) el.pause();
			},
			() => unlocked.delete(el)
		);
	}
}

function warnUnplayable(el, clip, src) {
	if (mediaFailure(el) !== 'unsupported' || unplayable.has(src)) return;
	unplayable.add(src);
	toast(t('lib.toast.audioUnplayable', { name: asset(clip.assetId)?.name ?? '' }), 'warning');
}

function mediaVoice(clip, src) {
	const out = ctx.createGain();
	out.gain.value = 0;
	const el = new Audio();
	el.preload = 'auto';
	el.onerror = () => warnUnplayable(el, clip, src);
	el.src = src;
	ctx.createMediaElementSource(el).connect(out);
	const stop = () => {
		el.onerror = null;
		el.pause();
		el.removeAttribute('src');
		el.load();
	};
	const v = { out, stop, lane: null, el, src };
	voices.set(clip.id, v);
	return v;
}

const SYNTH_BY_ROLE = { Dialogue: 'voice', Musique: 'pad', Ambiance: 'wind', SFX: 'steps' };

function voice(clip) {
	let v = voices.get(clip.id);
	const a = asset(clip.assetId);
	const src = a?.src ?? null;
	if (v && (v.src ?? null) === src) return v;
	if (v) {
		v.stop();
		v.out.disconnect();
		voices.delete(clip.id);
	}
	if (src) return mediaVoice(clip, src);
	const out = ctx.createGain();
	out.gain.value = 0;
	const stops = [];
	const synth = a?.synth ?? SYNTH_BY_ROLE[a?.role] ?? 'pad';
	if (synth === 'pad') {
		const f = ctx.createBiquadFilter();
		f.type = 'lowpass';
		f.frequency.value = 900;
		f.connect(out);
		for (const [hz, type] of [[110, 'sawtooth'], [164.8, 'triangle'], [220.5, 'sine'], [277.2, 'triangle'], [329.6, 'sine']]) {
			const o = ctx.createOscillator();
			o.type = type;
			o.frequency.value = hz;
			o.detune.value = (Math.random() - 0.5) * 12;
			const g = ctx.createGain();
			g.gain.value = type === 'sawtooth' ? 0.03 : 0.06;
			o.connect(g).connect(f);
			o.start();
			stops.push(o);
		}
		const lfo = ctx.createOscillator();
		lfo.frequency.value = 0.08;
		const lg = ctx.createGain();
		lg.gain.value = 400;
		lfo.connect(lg).connect(f.frequency);
		lfo.start();
		stops.push(lfo);
	} else {
		const len = ctx.sampleRate * 2;
		const buf = ctx.createBuffer(1, len, ctx.sampleRate);
		const d = buf.getChannelData(0);
		let b = 0;
		for (let i = 0; i < len; i++) {
			b = 0.97 * b + 0.03 * (Math.random() * 2 - 1);
			d[i] = synth === 'wind' ? b * 6 : Math.random() * 2 - 1;
		}
		const src = ctx.createBufferSource();
		src.buffer = buf;
		src.loop = true;
		const f = ctx.createBiquadFilter();
		const g = ctx.createGain();
		if (synth === 'wind') {
			f.type = 'bandpass';
			f.frequency.value = 500;
			f.Q.value = 0.7;
			const lfo = ctx.createOscillator();
			lfo.frequency.value = 0.15;
			const lg = ctx.createGain();
			lg.gain.value = 300;
			lfo.connect(lg).connect(f.frequency);
			lfo.start();
			stops.push(lfo);
			g.gain.value = 0.5;
		} else if (synth === 'steps') {
			f.type = 'bandpass';
			f.frequency.value = 2200;
			g.gain.value = 0;
			const lfo = ctx.createOscillator();
			lfo.type = 'square';
			lfo.frequency.value = 1.8;
			const lg = ctx.createGain();
			lg.gain.value = 0.25;
			lfo.connect(lg).connect(g.gain);
			lfo.start();
			stops.push(lfo);
		} else {
			f.type = 'bandpass';
			f.frequency.value = 700;
			f.Q.value = 4;
			g.gain.value = 0;
			const lfo = ctx.createOscillator();
			lfo.frequency.value = 4.2;
			const lg = ctx.createGain();
			lg.gain.value = 0.35;
			lfo.connect(lg).connect(g.gain);
			lfo.start();
			stops.push(lfo);
		}
		src.connect(f).connect(g).connect(out);
		src.start();
		stops.push(src);
	}
	v = { out, stop: () => stops.forEach((s) => s.stop()), lane: null, el: null, src: null };
	voices.set(clip.id, v);
	return v;
}

function envelope(c, t) {
	if (t < c.start || t > c.start + c.dur) return 0;
	const local = t - c.start;
	let g = 1;
	if (c.fadeIn > 0) g = Math.min(g, local / c.fadeIn);
	if (c.fadeOut > 0) g = Math.min(g, (c.dur - local) / c.fadeOut);
	return clamp(g, 0, 1) * db(c.gain ?? 0);
}

function updateAudio() {
	if (!ctx) return;
	const t = ui.playhead;
	const now = ctx.currentTime;
	monitor.gain.setTargetAtTime(ui.muted ? 0 : ui.monitorVol, now, 0.03);
	master.gain.setTargetAtTime(db(doc.master.vol), now, 0.03);
	const anySolo = doc.lanes.some((l) => l.solo);
	for (const lane of doc.lanes) {
		const s = strip(lane);
		const audible = !lane.mute && (!anySolo || lane.solo);
		s.fader.gain.setTargetAtTime(audible ? db(lane.vol) : 0, now, 0.03);
		s.pan.pan.setTargetAtTime(lane.pan, now, 0.03);
		const eq = lane.inserts.find((i) => i.type === 'eq');
		s.lo.gain.value = eq?.on ? eq.low : 0;
		s.mid.gain.value = eq?.on ? eq.mid : 0;
		s.hi.gain.value = eq?.on ? eq.high : 0;
		const fl = lane.inserts.find((i) => i.type === 'filter');
		s.filt.frequency.value = fl?.on ? fl.cutoff : 20000;
		const cp = lane.inserts.find((i) => i.type === 'comp');
		s.comp.threshold.value = cp?.on ? cp.threshold : 0;
		s.comp.ratio.value = cp?.on ? cp.ratio : 1;
		const aux = (id) => doc.aux.find((a) => a.id === id);
		s.sendR.gain.value = aux('R1')?.mute ? 0 : db(lane.sends.R1) * db(aux('R1')?.vol ?? 0);
		s.sendD.gain.value = aux('D1')?.mute ? 0 : db(lane.sends.D1) * db(aux('D1')?.vol ?? 0);
	}
	const live = new Set();
	for (const c of doc.audio) {
		live.add(c.id);
		const lane = doc.lanes.find((l) => l.id === c.lane);
		if (!lane) continue;
		const v = voice(c);
		if (v.lane !== lane.id) {
			v.out.disconnect();
			v.out.connect(strip(lane).input);
			v.lane = lane.id;
		}
		if (v.el) follow(v, c, t);
		v.out.gain.setTargetAtTime(envelope(c, t) * (v.el ? 1 : 0.5), now, 0.02);
	}
	for (const [id, v] of voices)
		if (!live.has(id)) {
			v.stop();
			v.out.disconnect();
			voices.delete(id);
		}
	readMeters();
}

function follow(v, c, t) {
	const el = v.el;
	v.live = ui.playing && t >= c.start && t < c.start + c.dur;
	if (!v.live) {
		if (!el.paused) el.pause();
		return;
	}
	const target = t - c.start + c.srcIn;
	if (el.paused) {
		el.currentTime = target;
		el.play().catch(refused);
	} else if (Math.abs(el.currentTime - target) > 0.25) el.currentTime = target;
}

const buf = new Float32Array(512);
function level(an) {
	an.getFloatTimeDomainData(buf);
	let peak = 0;
	for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i]));
	return clamp((20 * Math.log10(peak + 1e-6) + 60) / 66, 0, 1);
}
function readMeters() {
	for (const [id, s] of strips) {
		const prev = meters.lanes[id] ?? 0;
		const v = level(s.an);
		meters.lanes[id] = v > prev ? v : prev * 0.9;
	}
	const m = level(masterAn);
	meters.master = [m, m * (0.92 + Math.random() * 0.08)];
}

let silenceTimer = 0;
function resetMeters() {
	for (const k of Object.keys(meters.lanes)) meters.lanes[k] = 0;
	meters.master = [0, 0];
}
function silence() {
	if (!ctx) return;
	for (const v of voices.values()) {
		v.out.gain.setTargetAtTime(0, ctx.currentTime, 0.02);
		v.el?.pause();
	}
	clearTimeout(silenceTimer);
	silenceTimer = setTimeout(resetMeters, 120);
}

export function audition(type, seconds = 2.5) {
	ensureAudio();
	if (!ctx) return;
	monitor.gain.value = ui.muted ? 0 : ui.monitorVol;
	const o = ctx.createOscillator();
	const g = ctx.createGain();
	o.type = type === 'Impact' ? 'sine' : 'triangle';
	o.frequency.value = type === 'Impact' ? 60 : type === 'Musique' ? 220 : 400;
	if (type === 'Impact') o.frequency.exponentialRampToValueAtTime(35, ctx.currentTime + seconds);
	g.gain.setValueAtTime(0.0001, ctx.currentTime);
	g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + 0.02);
	g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + seconds);
	o.connect(g).connect(master);
	o.start();
	o.stop(ctx.currentTime + seconds);
}

export function dispose() {
	ui.playing = false;
	cancelAnimationFrame(raf);
	raf = 0;
	clearTimeout(silenceTimer);
	silenceTimer = 0;
	for (const v of voices.values()) {
		try {
			v.stop();
		} catch {}
		v.out.disconnect();
	}
	voices.clear();
	strips.clear();
	unplayable.clear();
	refusalShown = false;
	const closing = ctx;
	ctx = null;
	master = null;
	masterAn = null;
	monitor = null;
	reverb = null;
	delay = null;
	resetMeters();
	if (closing && closing.state !== 'closed') return closing.close().catch(() => {});
	return Promise.resolve();
}

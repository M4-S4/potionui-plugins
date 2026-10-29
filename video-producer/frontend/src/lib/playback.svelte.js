import { t } from '../i18n/index.svelte.js';
import { ui, doc, asset, seqDuration, clamp, toast } from './state.svelte.js';
import { mediaFailure } from './playable.js';
import { clipSoundAudible, laneAudible } from './tracks.js';
import { speedOf } from './cadence.js';
import { advance } from './player.js';
import mixRule from './mix.json';
import { gainOf, reverbImpulse, stripOf } from './mix.js';

export const meters = $state({ lanes: {}, video: 0, master: [0, 0] });

const CLIP_LEAD = 1.5;
const SILENT_AFTER = 1;

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
	const next = advance(ui.playhead, dt, { loop: ui.loop, range: ui.range, end: seqDuration() });
	ui.playhead = next.t;
	if (next.stop) return pause();
	updateAudio();
	if (ui.playing) raf = requestAnimationFrame(frame);
}

let ctx = null;
let master = null;
let masterAn = null;
let monitor = null;
let videoBus = null;
let videoAn = null;
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
			videoBus = ctx.createGain();
			videoAn = ctx.createAnalyser();
			videoAn.fftSize = 512;
			videoBus.connect(videoAn).connect(master);
		}
		if (ctx.state === 'suspended') ctx.resume();
	} catch {
		ctx = null;
	}
}

function makeReverb() {
	const channels = reverbImpulse(mixRule, ctx.sampleRate);
	const buf = ctx.createBuffer(2, channels[0].length, ctx.sampleRate);
	channels.forEach((data, ch) => buf.copyToChannel(data, ch));
	const input = ctx.createGain();
	const conv = ctx.createConvolver();
	conv.normalize = false;
	conv.buffer = buf;
	const out = ctx.createGain();
	input.connect(conv).connect(out).connect(master);
	return { input, out };
}
function makeDelay() {
	const input = ctx.createGain();
	const d = ctx.createDelay(1);
	d.delayTime.value = mixRule.delay.seconds;
	const fb = ctx.createGain();
	fb.gain.value = mixRule.delay.feedback;
	const out = ctx.createGain();
	input.connect(d).connect(out).connect(master);
	d.connect(fb).connect(d);
	return { input, out };
}

const db = (v) => gainOf(mixRule, v);

function strip(lane) {
	let s = strips.get(lane.id);
	if (s) return s;
	const input = ctx.createGain();
	input.channelCount = 2;
	input.channelCountMode = 'explicit';
	input.channelInterpretation = 'speakers';
	const band = ({ type, frequency, q }) => {
		const node = ctx.createBiquadFilter();
		node.type = type;
		node.frequency.value = frequency;
		if (q) node.Q.value = q;
		return node;
	};
	const lo = band(mixRule.eq.low);
	const mid = band(mixRule.eq.mid);
	const hi = band(mixRule.eq.high);
	const filt = ctx.createBiquadFilter();
	filt.type = mixRule.filter.type;
	filt.Q.value = mixRule.filter.qDb;
	filt.frequency.value = ctx.sampleRate / 2;
	const comp = ctx.createDynamicsCompressor();
	comp.knee.value = mixRule.comp.knee;
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
const silent = new Set();
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

function mediaVoice(clip, src, warn = true) {
	const out = ctx.createGain();
	out.gain.value = 0;
	const el = new Audio();
	el.preload = 'auto';
	if (warn) el.onerror = () => warnUnplayable(el, clip, src);
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

function voice(clip) {
	const v = voices.get(clip.id);
	const src = asset(clip.assetId)?.src ?? null;
	if (v && v.src === src) return v;
	if (v) {
		v.stop();
		v.out.disconnect();
		voices.delete(clip.id);
	}
	return src ? mediaVoice(clip, src) : null;
}

function dropVoice(id) {
	const v = voices.get(id);
	if (!v) return;
	v.stop();
	v.out.disconnect();
	voices.delete(id);
}

function clipVoice(c, src) {
	const v = voices.get(c.id);
	if (v && v.src === src) return v;
	if (v) dropVoice(c.id);
	const made = mediaVoice(c, src, false);
	made.out.connect(videoBus);
	made.lane = 'video';
	return made;
}

function clipSource(c) {
	const a = asset(c.assetId);
	return a?.kind === 'video' && a.src && !silent.has(a.src) ? a.src : null;
}

function heardNothing(v) {
	const el = v.el;
	if (!('webkitAudioDecodedByteCount' in el) || el.webkitAudioDecodedByteCount > 0) return false;
	return v.from != null && el.currentTime - v.from >= SILENT_AFTER;
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
	for (const [id, s] of strips)
		if (!doc.lanes.some((l) => l.id === id)) {
			s.fader.disconnect();
			strips.delete(id);
			delete meters.lanes[id];
		}
	for (const lane of doc.lanes) {
		const s = strip(lane);
		const st = stripOf(mixRule, lane, doc.aux, laneAudible(doc, lane));
		s.fader.gain.setTargetAtTime(st.fader, now, 0.03);
		s.pan.pan.setTargetAtTime(st.pan, now, 0.03);
		s.lo.gain.value = st.eq.low;
		s.mid.gain.value = st.eq.mid;
		s.hi.gain.value = st.eq.high;
		s.filt.frequency.value = st.cutoff ?? ctx.sampleRate / 2;
		s.comp.threshold.value = st.comp ? st.comp.threshold : 0;
		s.comp.ratio.value = st.comp ? st.comp.ratio : 1;
		if (st.comp) {
			s.comp.attack.value = st.comp.attack / 1000;
			s.comp.release.value = st.comp.release / 1000;
		}
		s.sendR.gain.value = st.sends[mixRule.reverb.id];
		s.sendD.gain.value = st.sends[mixRule.delay.id];
	}
	const live = new Set();
	for (const c of doc.audio) {
		live.add(c.id);
		const lane = doc.lanes.find((l) => l.id === c.lane);
		if (!lane) continue;
		const v = voice(c);
		if (!v) continue;
		if (v.lane !== lane.id) {
			v.out.disconnect();
			v.out.connect(strip(lane).input);
			v.lane = lane.id;
		}
		follow(v, c, t);
		v.out.gain.setTargetAtTime(envelope(c, t), now, 0.02);
	}
	for (const c of doc.clips) {
		if (t < c.start - CLIP_LEAD || t >= c.start + c.dur) continue;
		const src = clipSource(c);
		if (!src) continue;
		live.add(c.id);
		const v = clipVoice(c, src);
		follow(v, c, t);
		if (heardNothing(v)) {
			silent.add(src);
			live.delete(c.id);
			continue;
		}
		v.out.gain.setTargetAtTime(clipSoundAudible(doc, c) ? envelope(c, t) : 0, now, 0.02);
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
	const target = (t - c.start) * speedOf(c) + c.srcIn;
	if (el.paused) {
		el.currentTime = target;
		v.from = target;
		el.play().catch(refused);
	} else if (Math.abs(el.currentTime - target) > 0.25) {
		el.currentTime = target;
		v.from = target;
	}
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
	const vm = level(videoAn);
	meters.video = vm > meters.video ? vm : meters.video * 0.9;
	const m = level(masterAn);
	meters.master = [m, m * (0.92 + Math.random() * 0.08)];
}

let silenceTimer = 0;
function resetMeters() {
	for (const k of Object.keys(meters.lanes)) meters.lanes[k] = 0;
	meters.video = 0;
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
	silent.clear();
	refusalShown = false;
	const closing = ctx;
	ctx = null;
	master = null;
	masterAn = null;
	monitor = null;
	videoBus = null;
	videoAn = null;
	reverb = null;
	delay = null;
	resetMeters();
	if (closing && closing.state !== 'closed') return closing.close().catch(() => {});
	return Promise.resolve();
}

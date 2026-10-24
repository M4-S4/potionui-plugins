import { SvelteMap } from 'svelte/reactivity';

const THUMB_WIDTH = 480;
const PEAK_RATE = 50;
const DECODE_RATE = 8000;
const TIMEOUT = 20000;
const SEEK_FLOOR = 0.001;
const FRAME_STEP = 0.04;
const KEPT_FRAMES = 24;

const thumbs = new SvelteMap();
const frames = new SvelteMap();
const peaks = new SvelteMap();
const wanted = new Map();
const busy = new Set();

function withTimeout(start) {
	return new Promise((resolve) => {
		let done = false;
		const finish = (value) => {
			if (done) return;
			done = true;
			clearTimeout(timer);
			resolve(value);
		};
		const timer = setTimeout(() => finish(null), TIMEOUT);
		start(finish);
	});
}

function loadImage(url) {
	return withTimeout((finish) => {
		const img = new Image();
		img.decoding = 'async';
		img.onload = () => finish(img.naturalWidth > 0 ? img : null);
		img.onerror = () => finish(null);
		img.src = url;
	});
}

function releaseMedia(el) {
	el.removeAttribute('src');
	el.load();
}

function captureFrame(src, duration, at = null) {
	return withTimeout((finish) => {
		const video = document.createElement('video');
		video.muted = true;
		video.playsInline = true;
		video.preload = 'auto';
		const done = (value) => {
			releaseMedia(video);
			finish(value);
		};
		video.onloadedmetadata = () => {
			const length = Number.isFinite(video.duration) ? video.duration : duration;
			video.currentTime = at === null ? Math.min(1, (length || 0) / 2) : Math.max(SEEK_FLOOR, at);
		};
		video.onseeked = () => {
			const w = video.videoWidth;
			const h = video.videoHeight;
			if (!w || !h) return done(null);
			const canvas = document.createElement('canvas');
			canvas.width = THUMB_WIDTH;
			canvas.height = Math.round((THUMB_WIDTH * h) / w);
			const g = canvas.getContext('2d');
			if (!g) return done(null);
			try {
				g.drawImage(video, 0, 0, canvas.width, canvas.height);
				done(canvas.toDataURL('image/jpeg', 0.82));
			} catch {
				done(null);
			}
		};
		video.onerror = () => done(null);
		video.src = src;
	});
}

const sized = (src, size) => `${src}${src.includes('?') ? '&' : '?'}size=${size}`;

async function resolveVideoThumb(a) {
	const key = `thumb|${a.src}`;
	if (busy.has(key)) return;
	busy.add(key);
	let url = null;
	if (a.origin) {
		const candidate = sized(a.src, 'medium');
		if (await loadImage(candidate)) url = candidate;
	}
	if (!url) url = await captureFrame(a.src, a.srcDur);
	thumbs.set(a.src, url ?? '');
	busy.delete(key);
}

export function videoThumb(a) {
	if (!a?.src || typeof document === 'undefined') return null;
	const known = thumbs.get(a.src);
	if (known !== undefined) return known || null;
	resolveVideoThumb(a);
	return null;
}

const frameKey = (src, at) => `${src}|${at}`;

async function resolveFrames(src, duration) {
	const key = `frame|${src}`;
	if (busy.has(key)) return;
	busy.add(key);
	for (let at = wanted.get(src); at !== undefined && !frames.has(frameKey(src, at)); at = wanted.get(src)) {
		const url = await captureFrame(src, duration, at);
		frames.set(frameKey(src, at), url ?? '');
		for (const old of frames.keys()) {
			if (frames.size <= KEPT_FRAMES) break;
			frames.delete(old);
		}
	}
	busy.delete(key);
}

export function videoFrame(a, at) {
	if (!a?.src || a.kind !== 'video' || typeof document === 'undefined') return null;
	const time = +(Math.round(Math.max(0, Number(at) || 0) / FRAME_STEP) * FRAME_STEP).toFixed(3);
	const known = frames.get(frameKey(a.src, time));
	if (known !== undefined) return known || null;
	wanted.set(a.src, time);
	resolveFrames(a.src, a.srcDur);
	return null;
}

export function probeMedia(a) {
	if (!a?.src || typeof document === 'undefined') return Promise.resolve(null);
	if (a.kind === 'image') return loadImage(a.src).then((img) => (img ? { srcDur: null, width: img.naturalWidth, height: img.naturalHeight } : null));
	return withTimeout((finish) => {
		const el = document.createElement(a.kind === 'audio' ? 'audio' : 'video');
		el.preload = 'metadata';
		el.muted = true;
		const done = (value) => {
			releaseMedia(el);
			finish(value);
		};
		el.onloadedmetadata = () => {
			const srcDur = Number.isFinite(el.duration) && el.duration > 0 ? Math.round(el.duration * 1000) / 1000 : null;
			if (a.kind === 'audio') return done({ srcDur, width: null, height: null });
			done({ srcDur, width: el.videoWidth || null, height: el.videoHeight || null });
		};
		el.onerror = () => done(null);
		el.src = a.src;
	});
}

async function decodePeaks(src) {
	const key = `peaks|${src}`;
	if (busy.has(key)) return;
	busy.add(key);
	let out = null;
	try {
		const response = await fetch(src, { credentials: 'include' });
		if (response.ok) {
			const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
			const ctx = new Offline(1, 1, DECODE_RATE);
			const buffer = await ctx.decodeAudioData(await response.arrayBuffer());
			const step = Math.max(1, Math.round(buffer.sampleRate / PEAK_RATE));
			const count = Math.ceil(buffer.length / step);
			const values = new Float32Array(count);
			for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
				const data = buffer.getChannelData(ch);
				for (let i = 0; i < count; i++) {
					let max = values[i];
					const end = Math.min(data.length, (i + 1) * step);
					for (let j = i * step; j < end; j++) {
						const v = Math.abs(data[j]);
						if (v > max) max = v;
					}
					values[i] = max;
				}
			}
			let top = 0;
			for (const v of values) top = Math.max(top, v);
			if (top > 0) for (let i = 0; i < count; i++) values[i] /= top;
			out = { rate: buffer.sampleRate / step, values };
		}
	} catch {
		out = null;
	}
	peaks.set(src, out ?? false);
	busy.delete(key);
}

export function audioPeaks(a) {
	if (!a?.src || a.kind !== 'audio' || typeof window === 'undefined') return null;
	const known = peaks.get(a.src);
	if (known !== undefined) return known || null;
	decodePeaks(a.src);
	return null;
}

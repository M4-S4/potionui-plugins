import { t } from '../i18n/index.svelte.js';
import { doc, asset, clipLabel } from './state.svelte.js';
import { videoThumb } from './sources.svelte.js';

const WIDTH = 480;
const HEIGHT = 270;
const SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI Variable", "Segoe UI", system-ui, Roboto, "Helvetica Neue", Arial, sans-serif';
const MONO = '"IBM Plex Mono", ui-monospace, SFMono-Regular, "Cascadia Mono", Menlo, Consolas, monospace';
const thumbs = new Map();

function tokens() {
	const style = getComputedStyle(document.documentElement);
	return (name, alpha = 1, fallback = '128 128 128') => `rgb(${style.getPropertyValue(`--${name}`).trim() || fallback} / ${alpha})`;
}

function fit(g, text, max) {
	if (g.measureText(text).width <= max) return text;
	let s = text;
	while (s.length > 1 && g.measureText(`${s}…`).width > max) s = s.slice(0, -1);
	return `${s.trimEnd()}…`;
}

function roundRect(g, x, y, w, h, r) {
	g.beginPath();
	g.moveTo(x + r, y);
	g.arcTo(x + w, y, x + w, y + h, r);
	g.arcTo(x + w, y + h, x, y + h, r);
	g.arcTo(x, y + h, x, y, r);
	g.arcTo(x, y, x + w, y, r);
	g.closePath();
}

function draw(g, shotIndex, label, badge) {
	const color = tokens();
	const n = Math.max(0, shotIndex);
	g.fillStyle = color('canvas');
	g.fillRect(0, 0, WIDTH, HEIGHT);
	const wash = g.createLinearGradient(0, 0, WIDTH, HEIGHT);
	wash.addColorStop(0, color(`viz-${(n % 8) + 1}`, 0.9));
	wash.addColorStop(1, color(`viz-${((n + 3) % 8) + 1}`, 0.55));
	g.fillStyle = wash;
	g.fillRect(0, 0, WIDTH, HEIGHT);
	const shade = g.createLinearGradient(0, HEIGHT * 0.35, 0, HEIGHT);
	shade.addColorStop(0, 'rgb(0 0 0 / 0)');
	shade.addColorStop(1, 'rgb(0 0 0 / 0.5)');
	g.fillStyle = shade;
	g.fillRect(0, 0, WIDTH, HEIGHT);

	g.textAlign = 'center';
	g.textBaseline = 'middle';
	g.fillStyle = 'rgb(255 255 255 / 0.92)';
	g.font = `600 112px ${MONO}`;
	g.fillText(String(n + 1).padStart(2, '0'), WIDTH / 2, HEIGHT * 0.45);
	if (label) {
		g.fillStyle = 'rgb(255 255 255 / 0.85)';
		g.font = `500 22px ${SANS}`;
		g.fillText(fit(g, label, WIDTH - 64), WIDTH / 2, HEIGHT - 34);
	}

	g.font = `500 20px ${SANS}`;
	g.textAlign = 'left';
	const w = Math.ceil(g.measureText(badge).width) + 24;
	const x = WIDTH - w - 14;
	const y = 14;
	roundRect(g, x, y, w, 36, 4);
	g.fillStyle = color('surface-1', 0.92);
	g.fill();
	g.setLineDash([6, 4]);
	g.lineWidth = 2;
	g.strokeStyle = color('line-hover');
	g.stroke();
	g.setLineDash([]);
	g.fillStyle = color('fg-muted');
	g.fillText(badge, x + 12, y + 19);
}

export function placeholderThumb(shotIndex, label = '') {
	if (typeof document === 'undefined') return null;
	const badge = t('shell.window.simulated');
	const key = `${shotIndex}|${label}|${badge}|${document.documentElement.dataset.theme ?? ''}`;
	if (thumbs.has(key)) return thumbs.get(key);
	const canvas = document.createElement('canvas');
	canvas.width = WIDTH;
	canvas.height = HEIGHT;
	const g = canvas.getContext('2d');
	if (!g) return null;
	draw(g, shotIndex, label, badge);
	const url = canvas.toDataURL('image/png');
	thumbs.set(key, url);
	return url;
}

export function realThumb(a) {
	if (!a?.src) return null;
	if (a.kind === 'image') return a.src;
	if (a.kind === 'video') return videoThumb(a);
	return null;
}

export function takeThumb(r) {
	if (!r) return null;
	const own = asset(`gen-${r.id}`);
	if (own?.src) return realThumb(own);
	const c = doc.clips.find((x) => x.id === r.clipId);
	return placeholderThumb(c ? doc.clips.indexOf(c) : 0, c ? clipLabel(c) : '');
}

export function clipThumb(c) {
	const a = asset(c?.assetId);
	if (!a || a.kind === 'audio') return null;
	if (a.src) return realThumb(a);
	return placeholderThumb(doc.clips.indexOf(c), clipLabel(c));
}

export function assetThumb(a) {
	if (!a) return null;
	if (a.src) return realThumb(a);
	if (!a.generated || !a.resultId) return null;
	return takeThumb(doc.results.find((r) => r.id === a.resultId));
}

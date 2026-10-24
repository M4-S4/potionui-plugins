import { applyLut } from './match.js';

export function lookSteps(clip) {
	if (!clip) return [];
	const steps = [];
	if (clip.exposure) steps.push(['brightness', 1 + clip.exposure * 0.25]);
	if (clip.contrast !== 100) steps.push(['contrast', clip.contrast / 100]);
	if (clip.saturation !== 100) steps.push(['saturate', clip.saturation / 100]);
	if (clip.temperature > 0) steps.push(['sepia', clip.temperature / 250]);
	if (clip.temperature < 0) steps.push(['hue-rotate', clip.temperature / 5], ['saturate', 1 + clip.temperature / 400]);
	return steps;
}

export function filterOf(steps) {
	return steps.map(([name, value]) => `${name}(${value}${name === 'hue-rotate' ? 'deg' : ''})`).join(' ') || 'none';
}

function saturate(s) {
	return [
		0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s,
		0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s,
		0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s
	];
}

function sepia(amount) {
	const b = 1 - Math.min(1, Math.max(0, amount));
	return [
		0.393 + 0.607 * b, 0.769 - 0.769 * b, 0.189 - 0.189 * b,
		0.349 - 0.349 * b, 0.686 + 0.314 * b, 0.168 - 0.168 * b,
		0.272 - 0.272 * b, 0.534 - 0.534 * b, 0.131 + 0.869 * b
	];
}

function hueRotate(degrees) {
	const c = Math.cos((degrees * Math.PI) / 180);
	const s = Math.sin((degrees * Math.PI) / 180);
	return [
		0.213 + 0.787 * c - 0.213 * s, 0.715 - 0.715 * c - 0.715 * s, 0.072 - 0.072 * c + 0.928 * s,
		0.213 - 0.213 * c + 0.143 * s, 0.715 + 0.285 * c + 0.14 * s, 0.072 - 0.072 * c - 0.283 * s,
		0.213 - 0.213 * c - 0.787 * s, 0.715 - 0.715 * c + 0.715 * s, 0.072 + 0.928 * c + 0.072 * s
	];
}

function operation([name, value]) {
	if (name === 'brightness') return { slope: value, intercept: 0 };
	if (name === 'contrast') return { slope: value, intercept: 0.5 - 0.5 * value };
	if (name === 'saturate') return { matrix: saturate(value) };
	if (name === 'sepia') return { matrix: sepia(value) };
	return { matrix: hueRotate(value) };
}

const unit = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

export function gradePixels(data, steps, lut = null) {
	if (lut) applyLut(data, lut);
	if (!steps.length || steps.some(([, value]) => !Number.isFinite(value))) return data;
	const ops = steps.map(operation);
	for (let i = 0; i < data.length; i += 4) {
		let r = data[i] / 255;
		let g = data[i + 1] / 255;
		let b = data[i + 2] / 255;
		for (const op of ops) {
			const m = op.matrix;
			if (m) {
				const [x, y, z] = [r, g, b];
				r = m[0] * x + m[1] * y + m[2] * z;
				g = m[3] * x + m[4] * y + m[5] * z;
				b = m[6] * x + m[7] * y + m[8] * z;
			} else {
				r = r * op.slope + op.intercept;
				g = g * op.slope + op.intercept;
				b = b * op.slope + op.intercept;
			}
			r = unit(r);
			g = unit(g);
			b = unit(b);
		}
		data[i] = Math.round(r * 255);
		data[i + 1] = Math.round(g * 255);
		data[i + 2] = Math.round(b * 255);
	}
	return data;
}

export function drawGraded(g, img, width, height, steps, lut = null) {
	const native = !lut && 'filter' in g;
	if (native) g.filter = filterOf(steps);
	else if ('filter' in g) g.filter = 'none';
	g.drawImage(img, 0, 0, width, height);
	const data = g.getImageData(0, 0, width, height).data;
	return native ? data : gradePixels(data, steps, lut);
}

export function lumaHistogram(data, bins = 64) {
	const counts = new Array(bins).fill(0);
	for (let i = 0; i < data.length; i += 4) counts[Math.min(bins - 1, Math.floor(((0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) * bins) / 256))]++;
	const max = Math.max(...counts);
	return counts.map((v) => (max ? v / max : 0));
}

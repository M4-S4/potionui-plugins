export const TILE = 32;
export const MIN_PIXELS = 65536;
export const MAX_PIXELS = 16777216;
export const FPS = 24;
export const SAMPLE_FPS = 2;
export const TEMPORAL_PATCH = 2;
export const MAX_RATIO = 4;
export const CANVAS_SHORT_EDGE = 768;
export const CANVAS_MAX_PIXELS = 768 * 1344;
export const LIMIT_12GB = 2200;
export const TWELVE_GB_PRESETS = ['01M54HN72B0KY7H63BKQ16T253', '01M54HN72PABVRE54YNQA2Q7ZT'];

const sized = (size) => Array.isArray(size) && size[0] > 0 && size[1] > 0;

export function maxPixels(budget, output) {
	const value = Number(budget);
	if (!Number.isFinite(value) || value <= 0 || !sized(output)) return MAX_PIXELS;
	return Math.max(Math.trunc(value * output[0] * output[1]), MIN_PIXELS);
}

const roundHalfEven = (value) => {
	const floor = Math.floor(value);
	const diff = value - floor;
	if (diff > 0.5) return floor + 1;
	if (diff < 0.5) return floor;
	return floor % 2 === 0 ? floor : floor + 1;
};

export function smartGrid(height, width, limit) {
	let h = roundHalfEven(height / TILE) * TILE;
	let w = roundHalfEven(width / TILE) * TILE;
	if (h * w > limit) {
		const beta = Math.sqrt((height * width) / limit);
		h = Math.max(TILE, Math.trunc(height / beta / TILE) * TILE);
		w = Math.max(TILE, Math.trunc(width / beta / TILE) * TILE);
	} else if (h * w < MIN_PIXELS) {
		const beta = Math.sqrt(MIN_PIXELS / (height * width));
		h = Math.ceil(Math.trunc(height * beta) / TILE) * TILE;
		w = Math.ceil(Math.trunc(width * beta) / TILE) * TILE;
	}
	return [h, w];
}

const tiles = ([h, w]) => Math.trunc(h / TILE) * Math.trunc(w / TILE);

export function padded(picture) {
	const [width, height] = [Math.trunc(picture[0]), Math.trunc(picture[1])];
	if (width > height * MAX_RATIO) return [width, Math.ceil(width / MAX_RATIO)];
	if (width < height / MAX_RATIO) return [Math.ceil(height / MAX_RATIO), height];
	return [width, height];
}

export function imageTokens(picture, limit) {
	if (!sized(picture)) return Math.trunc(limit / (TILE * TILE));
	const [width, height] = padded(picture);
	return tiles(smartGrid(height, width, limit));
}

const snap = (length, source) => Math.max(TILE, Math.min(roundHalfEven(length / TILE), Math.trunc(source / TILE)) * TILE);

export function videoCanvas(size) {
	const [width, height] = [Math.trunc(size[0]), Math.trunc(size[1])];
	const ratio = width / height;
	let [cw, ch] = ratio >= 1 ? [CANVAS_SHORT_EDGE * ratio, CANVAS_SHORT_EDGE] : [CANVAS_SHORT_EDGE, CANVAS_SHORT_EDGE / ratio];
	const area = cw * ch;
	if (area > CANVAS_MAX_PIXELS) {
		const scale = Math.sqrt(CANVAS_MAX_PIXELS / area);
		[cw, ch] = [cw * scale, ch * scale];
	}
	ch = Math.max(TILE, roundHalfEven(ch / TILE) * TILE);
	cw = Math.max(TILE, roundHalfEven(cw / TILE) * TILE);
	const [sh, sw] = [snap(ch, height), snap(cw, width)];
	return [Math.min(sh, sw * MAX_RATIO), Math.min(sw, sh * MAX_RATIO)];
}

export function sampledFrames(frames) {
	const stride = FPS / SAMPLE_FPS;
	const indices = [];
	let cursor = 0;
	while (roundHalfEven(cursor) < frames) {
		const index = roundHalfEven(cursor);
		if (!indices.length || index > indices[indices.length - 1]) indices.push(index);
		cursor += stride;
	}
	return indices;
}

export function videoTokens(frames, size, limit) {
	if (!(frames > 0) || !sized(size)) return 0;
	const blocks = Math.ceil(sampledFrames(frames).length / TEMPORAL_PATCH);
	const [height, width] = videoCanvas(size);
	return blocks * tiles(smartGrid(height, width, limit));
}

export function visionTokens(pictures, videos, limit) {
	return pictures.reduce((sum, picture) => sum + imageTokens(picture, limit), 0) + videos.reduce((sum, [frames, size]) => sum + videoTokens(frames, size, limit), 0);
}

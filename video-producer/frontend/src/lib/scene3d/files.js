export const MAX_SCENE_FILE = 1024 ** 3;
export const SCENE_FILE_ACCEPT = '.ply,.spz,.splat,.glb,.gltf';

const GLB_MAGIC = 0x46546c67;
const JSON_CHUNK = 0x4e4f534a;
const HEADER_LIMIT = 65536;

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const bytesOf = (data) => (data instanceof Uint8Array ? data : data instanceof ArrayBuffer ? new Uint8Array(data) : ArrayBuffer.isView(data) ? new Uint8Array(data.buffer, data.byteOffset, data.byteLength) : null);

export function sceneFileKind(name) {
	const ext = String(name ?? '')
		.toLowerCase()
		.match(/\.([a-z0-9]+)$/)?.[1];
	if (ext === 'ply' || ext === 'spz' || ext === 'splat') return { kind: 'splat', format: ext };
	if (ext === 'glb' || ext === 'gltf') return { kind: 'glb', format: ext };
	return null;
}

export function sceneName(filename) {
	const base = String(filename ?? '')
		.split(/[\\/]/)
		.pop();
	return base.replace(/\.[^.]+$/, '') || base;
}

export function plyHeader(data) {
	if (typeof data === 'string') {
		const end = data.indexOf('end_header');
		return end < 0 ? null : data.slice(0, end);
	}
	const bytes = bytesOf(data);
	if (!bytes) return null;
	const head = bytes.subarray(0, Math.min(bytes.length, HEADER_LIMIT));
	let text = '';
	for (let i = 0; i < head.length; i++) text += String.fromCharCode(head[i]);
	if (!text.startsWith('ply')) return null;
	const end = text.indexOf('end_header');
	return end < 0 ? null : text.slice(0, end);
}

export function plyView(data) {
	const header = plyHeader(data);
	if (!header) return null;
	const line = header.split(/\r?\n/).find((l) => /^comment\s+potionui_view\b/.test(l.trim()));
	if (!line) return null;
	const fields = {};
	for (const [, key, value] of line.matchAll(/(\w+)=(\S+)/g)) fields[key] = value;
	const fov = Number(fields.fov_y);
	const aspect = Number(fields.aspect);
	const depth = Number(fields.depth);
	if (!(fov > 0 && fov < 180) || !(aspect > 0) || !(depth > 0)) return null;
	if (fields.convention && fields.convention !== 'opencv') return null;
	const view = { fov, aspect, depth };
	const width = Number(fields.width);
	const height = Number(fields.height);
	if (Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0) Object.assign(view, { width, height });
	return view;
}

export function gltfJson(data) {
	if (isObject(data) && !ArrayBuffer.isView(data) && !(data instanceof ArrayBuffer)) return data;
	const bytes = typeof data === 'string' ? null : bytesOf(data);
	try {
		if (bytes && bytes.length >= 20) {
			const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
			if (view.getUint32(0, true) === GLB_MAGIC) {
				const size = view.getUint32(12, true);
				if (view.getUint32(16, true) !== JSON_CHUNK || 20 + size > bytes.length) return null;
				return JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + size)));
			}
		}
		const text = typeof data === 'string' ? data : bytes ? new TextDecoder().decode(bytes) : '';
		const json = JSON.parse(text);
		return isObject(json) ? json : null;
	} catch {
		return null;
	}
}

function animationEnd(json, sampler) {
	const accessor = json.accessors?.[sampler?.input];
	const max = Array.isArray(accessor?.max) ? Number(accessor.max[0]) : NaN;
	return Number.isFinite(max) && max > 0 ? max : 0;
}

export function gltfCameras(data) {
	const json = gltfJson(data);
	if (!json || !Array.isArray(json.nodes)) return [];
	const seen = new Map();
	const cameras = [];
	json.nodes.forEach((node, index) => {
		if (!isObject(node) || !Number.isInteger(node.camera)) return;
		const camera = json.cameras?.[node.camera];
		if (camera && camera.type && camera.type !== 'perspective') return;
		let duration = 0;
		for (const animation of json.animations ?? []) {
			for (const channel of animation?.channels ?? []) {
				if (channel?.target?.node !== index) continue;
				duration = Math.max(duration, animationEnd(json, animation.samplers?.[channel.sampler]));
			}
		}
		const base = (typeof node.name === 'string' && node.name.trim()) || (typeof camera?.name === 'string' && camera.name.trim()) || `Camera ${cameras.length + 1}`;
		const count = (seen.get(base) ?? 0) + 1;
		seen.set(base, count);
		cameras.push({ name: count > 1 ? `${base} ${count}` : base, animated: duration > 0, duration: duration > 0 ? +duration.toFixed(4) : null });
	});
	return cameras;
}

export function cameraNode(data, name) {
	const json = gltfJson(data);
	if (!json || !Array.isArray(json.nodes)) return -1;
	const names = gltfCameras(json).map((c) => c.name);
	let n = 0;
	for (let i = 0; i < json.nodes.length; i++) {
		const node = json.nodes[i];
		if (!isObject(node) || !Number.isInteger(node.camera)) continue;
		const camera = json.cameras?.[node.camera];
		if (camera && camera.type && camera.type !== 'perspective') continue;
		if (names[n] === name) return i;
		n += 1;
	}
	return -1;
}

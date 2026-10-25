import * as THREE from 'three';
import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';

const SPLAT_TYPES = { ply: 'ply', spz: 'spz', splat: 'splat' };
const COVERED_ALPHA = 128;

export function webglAvailable() {
	try {
		const canvas = document.createElement('canvas');
		return Boolean(canvas.getContext('webgl2'));
	} catch {
		return false;
	}
}

function applyPose(camera, pose, aspect) {
	camera.position.set(pose.pos[0], pose.pos[1], pose.pos[2]);
	camera.up.set(0, 1, 0);
	camera.lookAt(pose.target[0], pose.target[1], pose.target[2]);
	camera.rotateZ(((pose.roll ?? 0) * Math.PI) / 180);
	camera.fov = pose.fov;
	camera.aspect = aspect;
	camera.updateProjectionMatrix();
	camera.updateMatrixWorld(true);
}

function upright(src, width, height) {
	const out = new Uint8ClampedArray(width * height * 4);
	const row = width * 4;
	let covered = 0;
	for (let y = 0; y < height; y++) out.set(src.subarray((height - 1 - y) * row, (height - y) * row), y * row);
	for (let i = 3; i < out.length; i += 4) {
		if (out[i] >= COVERED_ALPHA) covered += 1;
		out[i] = 255;
	}
	return { pixels: out, coverage: covered / (width * height) };
}

async function blobUrl(blob) {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => resolve(reader.result);
		reader.onerror = () => reject(reader.error);
		reader.readAsDataURL(blob);
	});
}

export async function encode(pixels, width, height, type = 'image/png', quality) {
	const offscreen = typeof OffscreenCanvas === 'function';
	const canvas = offscreen ? new OffscreenCanvas(width, height) : Object.assign(document.createElement('canvas'), { width, height });
	canvas.getContext('2d').putImageData(new ImageData(pixels, width, height), 0, 0);
	const blob = offscreen ? await canvas.convertToBlob({ type, quality }) : await new Promise((resolve) => canvas.toBlob(resolve, type, quality));
	if (!blob) throw new Error('encode_failed');
	return blobUrl(blob);
}

export function createStage({ onLost } = {}) {
	const canvas = document.createElement('canvas');
	canvas.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
	const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true, powerPreference: 'high-performance' });
	renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
	renderer.setClearColor(0x000000, 0);
	renderer.outputColorSpace = THREE.SRGBColorSpace;
	const scene = new THREE.Scene();
	const camera = new THREE.PerspectiveCamera(50, 16 / 9, 0.01, 1000);
	const shot = new THREE.PerspectiveCamera(50, 16 / 9, 0.01, 1000);
	let raf = 0;
	let dirty = true;
	let busy = 0;
	let disposed = false;
	let content = null;
	let offline = null;
	let generation = 0;
	let pendingClear = false;
	let kill = null;
	const killed = new Promise((_, reject) => (kill = reject));
	killed.catch(() => {});
	canvas.addEventListener('webglcontextlost', () => {
		if (!disposed) onLost?.();
	});
	const request = () => {
		dirty = true;
		if (!raf && !disposed) raf = requestAnimationFrame(frame);
	};
	const live = new SparkRenderer({ renderer, enableLod: false, onDirty: request });
	scene.add(live);

	function frame() {
		raf = 0;
		if (disposed || busy || !dirty || !canvas.isConnected) return;
		dirty = false;
		renderer.render(scene, camera);
	}

	function clear() {
		if (!content) return;
		scene.remove(content.root);
		content.splat.dispose();
		content = null;
	}

	function fitClipping(bounds) {
		const radius = Math.max(bounds.radius, 0.01);
		const far = Math.max(1000, radius * 200);
		const near = Math.min(0.01, radius / 1000);
		for (const cam of [camera, shot]) {
			cam.near = near;
			cam.far = far;
			cam.updateProjectionMatrix();
		}
	}

	async function loadSplat(bytes, format) {
		const fileType = SPLAT_TYPES[format];
		if (!fileType) throw new Error('unsupported_format');
		const splat = new SplatMesh({ fileBytes: bytes, fileType, fileName: `scene.${format}` });
		try {
			await splat.initialized;
		} catch (err) {
			splat.dispose();
			throw err;
		}
		const root = new THREE.Group();
		root.rotation.x = Math.PI;
		root.add(splat);
		root.updateMatrixWorld(true);
		const box = splat.getBoundingBox(true).applyMatrix4(root.matrixWorld);
		const sphere = box.isEmpty() ? null : box.getBoundingSphere(new THREE.Sphere());
		return { root, splat, count: splat.packedSplats?.numSplats ?? null, bounds: sphere ? { center: sphere.center.toArray(), radius: sphere.radius } : { center: [0, 0, -4], radius: 4 } };
	}

	function offlineFor(width, height) {
		if (offline && offline.width === width && offline.height === height) return offline.spark;
		offline?.spark.dispose();
		const spark = new SparkRenderer({ renderer, enableLod: false, autoUpdate: false, target: { width, height } });
		if (spark.target.texture.colorSpace !== THREE.SRGBColorSpace) throw new Error('target_not_srgb');
		offline = { spark, width, height };
		return spark;
	}

	async function draw(pose, width, height) {
		const spark = offlineFor(width, height);
		applyPose(shot, pose, width / height);
		await spark.update({ scene, camera: shot });
		const raw = await spark.renderReadTarget({ scene, camera: shot });
		return upright(raw, width, height);
	}

	const pixels = (pose, width, height) => Promise.race([draw(pose, width, height), killed]);

	async function exclusive(task) {
		busy += 1;
		try {
			return await task();
		} finally {
			busy -= 1;
			if (!busy && pendingClear) {
				pendingClear = false;
				clear();
			}
			request();
		}
	}

	return {
		canvas,
		get busy() {
			return busy > 0;
		},
		async load({ bytes, format }) {
			const mine = ++generation;
			if (!busy) clear();
			const loaded = await loadSplat(bytes, format);
			if (disposed || mine !== generation) {
				loaded.splat.dispose();
				return null;
			}
			clear();
			pendingClear = false;
			content = loaded;
			scene.add(content.root);
			fitClipping(content.bounds);
			request();
			return { bounds: content.bounds, count: content.count ?? null };
		},
		unload() {
			generation += 1;
			if (busy) pendingClear = true;
			else clear();
			request();
		},
		setPose(pose) {
			applyPose(camera, pose, camera.aspect);
			request();
		},
		resize(width, height) {
			if (!(width > 0 && height > 0)) return;
			renderer.setSize(width, height, false);
			camera.aspect = width / height;
			camera.updateProjectionMatrix();
			request();
		},
		refresh: request,
		capture(pose, width, height) {
			return exclusive(async () => {
				const { pixels: image, coverage } = await pixels(pose, width, height);
				return { url: await encode(image, width, height, 'image/png'), coverage };
			});
		},
		dispose() {
			if (disposed) return;
			disposed = true;
			generation += 1;
			kill(new DOMException('disposed', 'AbortError'));
			cancelAnimationFrame(raf);
			clear();
			offline?.spark.dispose();
			live.dispose();
			renderer.dispose();
			renderer.forceContextLoss();
		}
	};
}

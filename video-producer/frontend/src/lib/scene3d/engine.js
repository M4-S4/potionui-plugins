import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
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

function disposeObject(root) {
	root.traverse((node) => {
		node.geometry?.dispose?.();
		const materials = Array.isArray(node.material) ? node.material : node.material ? [node.material] : [];
		for (const material of materials) {
			for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
			material.dispose?.();
		}
	});
}

function animate(content, time) {
	if (!content?.mixer) return;
	for (const action of content.actions) {
		action.paused = false;
		action.enabled = true;
	}
	content.mixer.setTime(Math.max(0, time));
	content.root.updateMatrixWorld(true);
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

export function createStage() {
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
	let environment = null;
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
		content.splat?.dispose();
		if (content.gltf) disposeObject(content.gltf.scene);
		content.mixer?.stopAllAction();
		content = null;
		scene.environment = null;
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

	function boundsOf(object) {
		const box = new THREE.Box3().setFromObject(object, true);
		if (box.isEmpty()) return { center: [0, 0, 0], radius: 1 };
		const sphere = box.getBoundingSphere(new THREE.Sphere());
		return { center: sphere.center.toArray(), radius: sphere.radius };
	}

	async function loadSplat(bytes, format) {
		const fileType = SPLAT_TYPES[format];
		if (!fileType) throw new Error('unsupported_format');
		const splat = new SplatMesh({ fileBytes: bytes, fileType, fileName: `scene.${format}` });
		await splat.initialized;
		const root = new THREE.Group();
		root.rotation.x = Math.PI;
		root.add(splat);
		root.updateMatrixWorld(true);
		const box = splat.getBoundingBox(true).applyMatrix4(root.matrixWorld);
		const sphere = box.isEmpty() ? null : box.getBoundingSphere(new THREE.Sphere());
		return { root, splat, count: splat.packedSplats?.numSplats ?? null, bounds: sphere ? { center: sphere.center.toArray(), radius: sphere.radius } : { center: [0, 0, -4], radius: 4 } };
	}

	async function loadGltf(bytes) {
		const buffer = bytes instanceof ArrayBuffer ? bytes : bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
		const gltf = await new GLTFLoader().parseAsync(buffer, '');
		const root = new THREE.Group();
		root.add(gltf.scene);
		let mixer = null;
		const actions = [];
		if (gltf.animations?.length) {
			mixer = new THREE.AnimationMixer(gltf.scene);
			for (const clip of gltf.animations) {
				const action = mixer.clipAction(clip);
				action.setLoop(THREE.LoopOnce, 1);
				action.clampWhenFinished = true;
				actions.push(action.play());
			}
			mixer.setTime(0);
		}
		root.updateMatrixWorld(true);
		if (!environment) {
			const pmrem = new THREE.PMREMGenerator(renderer);
			environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
			pmrem.dispose();
		}
		return { root, gltf, mixer, actions, bounds: boundsOf(gltf.scene) };
	}

	function cameraObject(node) {
		if (node?.isCamera) return node;
		let found = null;
		node?.traverse((child) => {
			if (!found && child.isCamera) found = child;
		});
		return found;
	}

	async function sampleCamera(nodeIndex, times) {
		if (!content?.gltf) return [];
		const parser = content.gltf.parser;
		const nodeDef = parser.json.nodes?.[nodeIndex];
		const own = parser.json.cameras?.[nodeDef?.camera]?.perspective?.aspectRatio ?? null;
		const cam = cameraObject(await parser.getDependency('node', nodeIndex));
		if (!cam) return [];
		const position = new THREE.Vector3();
		const quaternion = new THREE.Quaternion();
		const samples = times.map((t) => {
			animate(content, t);
			cam.getWorldPosition(position);
			cam.getWorldQuaternion(quaternion);
			return { t, pos: position.toArray(), quat: quaternion.toArray(), yfov: cam.fov, aspect: own };
		});
		animate(content, 0);
		return samples;
	}

	function offlineFor(width, height) {
		if (offline && offline.width === width && offline.height === height) return offline.spark;
		offline?.spark.dispose();
		const spark = new SparkRenderer({ renderer, enableLod: false, autoUpdate: false, target: { width, height } });
		if (spark.target.texture.colorSpace !== THREE.SRGBColorSpace) throw new Error('target_not_srgb');
		offline = { spark, width, height };
		return spark;
	}

	async function pixels(pose, width, height, time = 0) {
		const spark = offlineFor(width, height);
		applyPose(shot, pose, width / height);
		animate(content, time);
		await spark.update({ scene, camera: shot });
		const raw = await spark.renderReadTarget({ scene, camera: shot });
		return upright(raw, width, height);
	}

	async function exclusive(task) {
		busy += 1;
		try {
			return await task();
		} finally {
			busy -= 1;
			animate(content, 0);
			request();
		}
	}

	return {
		canvas,
		async load({ kind, bytes, format }) {
			clear();
			const loaded = kind === 'glb' ? await loadGltf(bytes) : await loadSplat(bytes, format);
			if (disposed) {
				loaded.splat?.dispose();
				if (loaded.gltf) disposeObject(loaded.gltf.scene);
				return null;
			}
			content = { kind, ...loaded };
			scene.add(content.root);
			if (content.gltf) scene.environment = environment;
			fitClipping(content.bounds);
			request();
			return { bounds: content.bounds, count: content.count ?? null };
		},
		unload() {
			clear();
			request();
		},
		sampleCamera,
		setPose(pose) {
			applyPose(camera, pose, camera.aspect);
			request();
		},
		setTime(time) {
			if (!content?.mixer || busy) return;
			animate(content, time);
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
		capture(pose, width, height, time = 0) {
			return exclusive(async () => {
				const { pixels: image, coverage } = await pixels(pose, width, height, time);
				return { url: await encode(image, width, height, 'image/png'), coverage };
			});
		},
		async render(poses, width, height, { fps, quality = 0.92, onFrame, signal } = {}) {
			return exclusive(async () => {
				for (let i = 0; i < poses.length; i++) {
					if (signal?.aborted || disposed) throw new DOMException('aborted', 'AbortError');
					const { pixels: image } = await pixels(poses[i], width, height, i / fps);
					await onFrame(i, await encode(image, width, height, 'image/jpeg', quality));
				}
			});
		},
		dispose() {
			disposed = true;
			cancelAnimationFrame(raf);
			clear();
			offline?.spark.dispose();
			live.dispose();
			environment?.dispose();
			renderer.dispose();
			renderer.forceContextLoss();
		}
	};
}

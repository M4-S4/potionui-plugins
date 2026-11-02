import { applyLut, lutBytes } from './match.js';

export const FALLBACK_WIDTH = 640;

const VERTEX = `#version 300 es
in vec2 corner;
out vec2 uv;
void main() {
	uv = vec2(corner.x + 1.0, 1.0 - corner.y) * 0.5;
	gl_Position = vec4(corner, 0.0, 1.0);
}`;

const FRAGMENT = `#version 300 es
precision highp float;
precision highp sampler3D;
uniform sampler2D picture;
uniform sampler3D lut;
uniform float size;
in vec2 uv;
out vec4 color;
void main() {
	vec3 rgb = texture(picture, uv).rgb;
	color = vec4(texture(lut, rgb * ((size - 1.0) / size) + 0.5 / size).rgb, 1.0);
}`;

function shader(gl, type, source) {
	const s = gl.createShader(type);
	gl.shaderSource(s, source);
	gl.compileShader(s);
	return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null;
}

function texture(gl, target, unit) {
	const tex = gl.createTexture();
	gl.activeTexture(gl.TEXTURE0 + unit);
	gl.bindTexture(target, tex);
	gl.texParameteri(target, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
	gl.texParameteri(target, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
	for (const wrap of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) gl.texParameteri(target, wrap, gl.CLAMP_TO_EDGE);
	return tex;
}

function glRenderer(canvas) {
	const gl = canvas.getContext('webgl2', { alpha: false, antialias: false, depth: false, premultipliedAlpha: false });
	if (!gl) return null;
	const vertex = shader(gl, gl.VERTEX_SHADER, VERTEX);
	const fragment = shader(gl, gl.FRAGMENT_SHADER, FRAGMENT);
	if (!vertex || !fragment) return false;
	const program = gl.createProgram();
	gl.attachShader(program, vertex);
	gl.attachShader(program, fragment);
	gl.linkProgram(program);
	if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return false;
	gl.useProgram(program);
	gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
	gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
	const corner = gl.getAttribLocation(program, 'corner');
	gl.enableVertexAttribArray(corner);
	gl.vertexAttribPointer(corner, 2, gl.FLOAT, false, 0, 0);
	const picture = texture(gl, gl.TEXTURE_2D, 0);
	const cube = texture(gl, gl.TEXTURE_3D, 1);
	gl.uniform1i(gl.getUniformLocation(program, 'picture'), 0);
	gl.uniform1i(gl.getUniformLocation(program, 'lut'), 1);
	const size = gl.getUniformLocation(program, 'size');
	let loaded = null;
	return {
		draw(source, lut) {
			if (lut !== loaded) {
				gl.activeTexture(gl.TEXTURE1);
				gl.bindTexture(gl.TEXTURE_3D, cube);
				gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA8, lut.size, lut.size, lut.size, 0, gl.RGBA, gl.UNSIGNED_BYTE, lutBytes(lut));
				gl.uniform1f(size, lut.size);
				loaded = lut;
			}
			gl.activeTexture(gl.TEXTURE0);
			gl.bindTexture(gl.TEXTURE_2D, picture);
			gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
			gl.viewport(0, 0, canvas.width, canvas.height);
			gl.drawArrays(gl.TRIANGLES, 0, 3);
		},
		dispose() {
			gl.getExtension('WEBGL_lose_context')?.loseContext();
		}
	};
}

function canvasRenderer(canvas) {
	const g = canvas.getContext('2d', { willReadFrequently: true });
	if (!g) return null;
	return {
		draw(source, lut) {
			g.drawImage(source, 0, 0, canvas.width, canvas.height);
			const frame = g.getImageData(0, 0, canvas.width, canvas.height);
			applyLut(frame.data, lut);
			g.putImageData(frame, 0, 0);
		},
		dispose() {}
	};
}

export function lutRenderer(canvas) {
	const gl = glRenderer(canvas);
	if (gl) return { ...gl, gpu: true };
	const flat = gl === null ? canvasRenderer(canvas) : null;
	return flat ? { ...flat, gpu: false } : null;
}

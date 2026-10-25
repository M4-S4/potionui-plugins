const HEADER_LIMIT = 65536;

const bytesOf = (data) => (data instanceof Uint8Array ? data : data instanceof ArrayBuffer ? new Uint8Array(data) : ArrayBuffer.isView(data) ? new Uint8Array(data.buffer, data.byteOffset, data.byteLength) : null);

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

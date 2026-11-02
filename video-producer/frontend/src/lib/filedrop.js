import { dragVerdict, hasFiles } from './upload.js';

export function fileDrop(node, params) {
	let options = params;
	let depth = 0;
	const verdict = (e) => (options.kinds.length ? dragVerdict(e.dataTransfer, options.kinds) : 'reject');
	const enter = (e) => {
		if (!hasFiles(e.dataTransfer)) return;
		e.preventDefault();
		depth += 1;
		options.hover?.(verdict(e), e);
	};
	const over = (e) => {
		if (!hasFiles(e.dataTransfer)) return;
		e.preventDefault();
		e.dataTransfer.dropEffect = 'copy';
		options.hover?.(verdict(e), e);
	};
	const leave = (e) => {
		if (!hasFiles(e.dataTransfer)) return;
		depth = Math.max(0, depth - 1);
		if (!depth) options.hover?.(null, e);
	};
	const drop = (e) => {
		if (!hasFiles(e.dataTransfer)) return;
		e.preventDefault();
		depth = 0;
		options.hover?.(null, e);
		options.drop(e.dataTransfer.files, e);
	};
	const events = { dragenter: enter, dragover: over, dragleave: leave, drop };
	for (const [name, handler] of Object.entries(events)) node.addEventListener(name, handler);
	return {
		update(next) {
			options = next;
		},
		destroy() {
			for (const [name, handler] of Object.entries(events)) node.removeEventListener(name, handler);
		}
	};
}

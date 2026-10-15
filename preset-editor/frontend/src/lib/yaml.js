import yaml from 'js-yaml';

export function parseYaml(text) {
	try {
		const data = yaml.load(typeof text === 'string' ? text : '');
		return { ok: true, data: data === undefined ? null : data };
	} catch (err) {
		const mark = err?.mark;
		return {
			ok: false,
			error: {
				message: err?.reason ?? err?.message ?? 'Invalid YAML',
				line: mark && Number.isInteger(mark.line) ? mark.line + 1 : null,
				column: mark && Number.isInteger(mark.column) ? mark.column + 1 : null
			}
		};
	}
}

export function dumpYaml(data, options = {}) {
	return yaml.dump(data, { lineWidth: 120, noRefs: true, quotingType: '"', forceQuotes: false, ...options });
}

function escapeRegExp(value) {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function topLevelBlockSpan(text, key) {
	const source = typeof text === 'string' ? text : '';
	const head = new RegExp(`^${escapeRegExp(key)}:(?:[ \\t][^\\n]*)?$`, 'm');
	const match = head.exec(source);
	if (!match) return null;
	const following = /^(?=[^\s#-])/gm;
	const floor = match.index + match[0].length;
	following.lastIndex = floor;
	const next = following.exec(source);
	let end = next ? next.index : source.length;
	while (end > floor) {
		const previous = source.lastIndexOf('\n', end - 2) + 1;
		const line = source.slice(previous, end).replace(/\n$/, '');
		if (line.trim() && !line.startsWith('#')) break;
		end = previous;
	}
	return { start: match.index, end };
}

export function replaceTopLevelBlock(text, key, block) {
	const source = typeof text === 'string' ? text : '';
	const span = topLevelBlockSpan(source, key);
	if (!span) {
		if (block === null || block === undefined) return source;
		const base = source && !source.endsWith('\n') ? `${source}\n` : source;
		return `${base}${block}\n`;
	}
	const before = source.slice(0, span.start);
	let after = source.slice(span.end);
	if (block === null || block === undefined) {
		if (after.startsWith('\n') && before.endsWith('\n')) after = after.slice(1);
		return before + after;
	}
	return `${before}${block}\n${after}`;
}

export function commentLines(text) {
	const lines = typeof text === 'string' ? text.split('\n') : [];
	const found = [];
	lines.forEach((line, index) => {
		let quote = null;
		for (let i = 0; i < line.length; i += 1) {
			const char = line[i];
			if (quote) {
				if (char === '\\' && quote === '"') i += 1;
				else if (char === quote) quote = null;
				continue;
			}
			if (char === '"' || char === "'") {
				quote = char;
				continue;
			}
			if (char === '#' && (i === 0 || /\s/.test(line[i - 1]))) {
				found.push(index + 1);
				return;
			}
		}
	});
	return found;
}

export function hasComments(text) {
	return commentLines(text).length > 0;
}

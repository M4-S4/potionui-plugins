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

export function dumpYaml(data) {
	return yaml.dump(data, { lineWidth: 120, noRefs: true, quotingType: '"', forceQuotes: false });
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

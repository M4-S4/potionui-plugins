const NAMED_ENTITIES = {
	amp: '&',
	lt: '<',
	gt: '>',
	quot: '"',
	apos: "'",
	nbsp: '\u00a0',
	colon: ':',
	tab: '\t',
	newline: '\n',
	sol: '/',
	bsol: '\\',
	lpar: '(',
	rpar: ')',
	period: '.',
	comma: ',',
	semi: ';',
	equals: '=',
	quest: '?',
	num: '#',
	percnt: '%',
	excl: '!',
	lbrack: '[',
	rbrack: ']',
	lsqb: '[',
	rsqb: ']',
	lcub: '{',
	rcub: '}',
	lbrace: '{',
	rbrace: '}',
	grave: '`',
	plus: '+',
	dollar: '$',
	commat: '@',
	ast: '*',
	lowbar: '_',
	hyphen: '-',
	dash: '-',
	verbar: '|',
	vert: '|'
};

const ENTITY_RE = /&(?:#(\d+)|#[xX]([0-9a-fA-F]+)|([a-zA-Z][a-zA-Z0-9]*));?/g;
const MAX_DECODE_PASSES = 16;
const STRIPPED_CHARS_RE =
	/[\u0000-\u0020\u007f-\u009f\u00ad\u061c\u115f\u1160\u180e\u200b-\u200f\u2028-\u202f\u2060-\u206f\u3000\u3164\ufeff\uffa0]/g;
const SAFE_LINK_SCHEMES = new Set(['http:', 'https:', 'mailto:']);

function codePointToString(code) {
	if (!Number.isFinite(code) || code < 0 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) {
		return '\ufffd';
	}
	return String.fromCodePoint(code);
}

function decodeEntitiesOnce(input) {
	return input.replace(ENTITY_RE, (match, dec, hex, name) => {
		if (dec !== undefined) return codePointToString(parseInt(dec, 10));
		if (hex !== undefined) return codePointToString(parseInt(hex, 16));
		const decoded = NAMED_ENTITIES[name.toLowerCase()];
		return decoded === undefined ? match : decoded;
	});
}

function decodeUntilStable(input) {
	let current = input;
	for (let i = 0; i < MAX_DECODE_PASSES; i++) {
		const next = decodeEntitiesOnce(current);
		if (next === current) return current;
		current = next;
	}
	return null;
}

function escapeAttribute(value) {
	return value
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

function isRelative(normalized) {
	if (normalized.startsWith('//') || normalized.startsWith('/\\') || normalized.startsWith('\\')) return false;
	return (
		normalized.startsWith('/') ||
		normalized.startsWith('#') ||
		normalized.startsWith('?') ||
		normalized.startsWith('./') ||
		normalized.startsWith('../')
	);
}

function sanitize(raw, schemes, allowMailto) {
	if (!raw) return null;
	const decoded = decodeUntilStable(raw);
	if (decoded === null) return null;

	const normalized = decoded.replace(STRIPPED_CHARS_RE, '').toLowerCase();
	if (!normalized) return null;

	if (!isRelative(normalized)) {
		const scheme = /^([a-z][a-z0-9+.-]*:)/.exec(normalized)?.[1];
		if (!scheme || !schemes.has(scheme)) return null;
		if (scheme === 'mailto:' && !allowMailto) return null;
		try {
			new URL(normalized);
		} catch {
			return null;
		}
	}

	const visible = decoded.replace(
		/[\u0000-\u001f\u007f-\u009f\u00ad\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]/g,
		''
	);
	return escapeAttribute(visible.trim().replace(/\s/g, '%20'));
}

export function sanitizeLinkUrl(raw) {
	return sanitize(raw, SAFE_LINK_SCHEMES, true);
}

function splitTableRow(line) {
	let l = line.trim().replace(/\\\|/g, '\x01PIPE\x01');
	if (l.startsWith('|')) l = l.slice(1);
	if (l.endsWith('|')) l = l.slice(0, -1);
	return l.split('|').map((cell) => cell.replace(/\x01PIPE\x01/g, '|').trim());
}

function isTableSeparatorRow(line) {
	const trimmed = line.trim();
	if (!trimmed || !trimmed.includes('-')) return false;
	const cells = splitTableRow(trimmed);
	return cells.length > 0 && cells.every((c) => /^:?-+:?$/.test(c));
}

function columnAlign(sepCell) {
	const left = sepCell.startsWith(':');
	const right = sepCell.endsWith(':');
	if (left && right) return 'center';
	if (right) return 'right';
	if (left) return 'left';
	return null;
}

function alignClass(align) {
	if (align === 'right') return ' text-right';
	if (align === 'center') return ' text-center';
	return '';
}

function renderTable(header, aligns, rows) {
	const thCells = header
		.map((cell, i) => `<th class="text-left font-semibold px-3 py-1.5 border-b border-line-strong${alignClass(aligns[i])}">${cell}</th>`)
		.join('');
	const bodyRows = rows
		.map((row) => {
			const tds = header.map((_, i) => `<td class="px-3 py-1.5 border-b border-line align-top${alignClass(aligns[i])}">${row[i] ?? ''}</td>`).join('');
			return `<tr>${tds}</tr>`;
		})
		.join('');
	return `<div class="overflow-x-auto"><table class="w-full text-sm my-3 border-collapse"><thead><tr>${thCells}</tr></thead><tbody>${bodyRows}</tbody></table></div>`;
}

function processBlockElements(text) {
	const lines = text.split('\n');
	const output = [];
	let i = 0;
	while (i < lines.length) {
		const line = lines[i];
		if (line.trim().includes('|') && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
			const headerCells = splitTableRow(line);
			const aligns = splitTableRow(lines[i + 1]).map(columnAlign);
			let j = i + 2;
			const rows = [];
			while (j < lines.length && lines[j].trim().includes('|')) {
				rows.push(splitTableRow(lines[j]));
				j++;
			}
			output.push(renderTable(headerCells, aligns, rows));
			i = j;
			continue;
		}
		if (/^- (.*)$/.test(line)) {
			const items = [];
			while (i < lines.length) {
				const m = lines[i].match(/^- (.*)$/);
				if (!m) break;
				items.push(m[1]);
				i++;
			}
			output.push(`<ul class="list-disc pl-5 my-2 space-y-0.5">${items.map((it) => `<li>${it}</li>`).join('')}</ul>`);
			continue;
		}
		const olStart = line.match(/^(\d+)\. (.*)$/);
		if (olStart) {
			const items = [];
			const firstNum = parseInt(olStart[1], 10);
			while (i < lines.length) {
				const m = lines[i].match(/^\d+\. (.*)$/);
				if (!m) break;
				items.push(m[1]);
				i++;
			}
			const startAttr = firstNum !== 1 ? ` start="${firstNum}"` : '';
			output.push(`<ol class="list-decimal pl-5 my-2 space-y-0.5"${startAttr}>${items.map((it) => `<li>${it}</li>`).join('')}</ol>`);
			continue;
		}
		output.push(line);
		i++;
	}
	return output.join('\n');
}

export function processMarkdown(text) {
	if (!text) return '';
	const codeBlocks = [];
	let processed = text.replace(/```[\s\S]*?```/g, (match) => {
		const inner = match.replace(/^```[^\n]*\n?/, '').replace(/\n?```$/, '');
		const placeholder = `\x00CODEBLOCK${codeBlocks.length}\x00`;
		codeBlocks.push(inner);
		return placeholder;
	});
	processed = processed
		.replace(/&(?!amp;|lt;|gt;|quot;|#\d+;|#x[\da-fA-F]+;)/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;');
	processed = processed.replace(/\n{3,}/g, '\n\n');
	processed = processed
		.replace(/^### (.*$)/gim, '<h3 class="text-lg font-semibold mb-1 mt-3">$1</h3>')
		.replace(/^## (.*$)/gim, '<h2 class="text-xl font-semibold mb-1.5 mt-3">$1</h2>')
		.replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mb-2 mt-4">$1</h1>')
		.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
		.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')
		.replace(/`(.*?)`/g, '<code class="bg-surface-2 px-1 py-0.5 rounded text-sm font-mono text-fg-muted">$1</code>')
		.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => {
			const safe = sanitizeLinkUrl(href);
			if (!safe) return label;
			return `<a href="${safe}" class="text-signal hover:underline" target="_blank" rel="noopener noreferrer">${label}</a>`;
		});
	processed = processBlockElements(processed);
	processed = processed.replace(/^&gt; (.*$)/gim, '<blockquote class="border-l-4 border-line-strong pl-4 italic text-fg-muted my-1">$1</blockquote>');
	processed = processed.replace(/\n\n/g, '<span class="block mt-2"></span>').replace(/\n/g, '<br>');
	processed = processed
		.replace(/(<\/h[1-3]>)(<br>|<span class="block mt-2"><\/span>)+/gi, '$1')
		.replace(/(<br>|<span class="block mt-2"><\/span>)+(<h[1-3]\s)/gi, '$2')
		.replace(/(<\/li>)(<br>)/gi, '$1')
		.replace(/(<\/blockquote>)(<br>|<span class="block mt-2"><\/span>)+/gi, '$1')
		.replace(/(<\/(?:ul|ol)>)(<br>|<span class="block mt-2"><\/span>)+/gi, '$1')
		.replace(/(<br>|<span class="block mt-2"><\/span>)+(<(?:ul|ol)[\s>])/gi, '$2')
		.replace(/(<\/div>)(<br>|<span class="block mt-2"><\/span>)+/gi, '$1')
		.replace(/(<br>|<span class="block mt-2"><\/span>)+(<div class="overflow-x-auto")/gi, '$2');
	processed = processed.replace(/\x00CODEBLOCK(\d+)\x00/g, (_, index) => {
		const code = codeBlocks[parseInt(index, 10)].replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
		return `<pre><code class="bg-surface-2 block p-3 rounded-lg text-sm font-mono text-fg-muted my-2 overflow-x-auto">${code}</code></pre>`;
	});
	return processed;
}

export function renderMarkdown(source) {
	return processMarkdown(String(source ?? '').replace(/\r\n?/g, '\n'));
}

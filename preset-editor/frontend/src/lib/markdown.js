const SAFE_URL_SCHEMES = ['http:', 'https:', 'mailto:'];

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

function sanitizeUrl(raw) {
	const url = raw.trim();
	if (!url) return null;
	const isRelative = url.startsWith('/') || url.startsWith('#') || url.startsWith('./');
	if (!isRelative) {
		const scheme = url.slice(0, url.indexOf(':') + 1).toLowerCase();
		const hasScheme = scheme.length > 1 && !url.slice(0, url.indexOf(':')).includes('/');
		if (hasScheme && !SAFE_URL_SCHEMES.includes(scheme)) return null;
	}
	return url.replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/\s/g, '%20');
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
			const safe = sanitizeUrl(href);
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

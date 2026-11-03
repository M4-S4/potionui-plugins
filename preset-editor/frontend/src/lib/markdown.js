const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const SAFE_URL = /^(?:https?:\/\/|mailto:|\/(?!\/)|#)/i;

export function escapeHtml(value) {
	return String(value ?? '').replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

function unescapeHtml(value) {
	return value.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

export function safeHref(url) {
	const trimmed = String(url ?? '').trim();
	return SAFE_URL.test(trimmed) ? trimmed : null;
}

export function renderInline(raw, { resolveImage } = {}) {
	const codes = [];
	let html = escapeHtml(raw).replace(/`([^`\n]+)`/g, (_, code) => {
		codes.push(`<code>${code}</code>`);
		return `\u0000${codes.length - 1}\u0000`;
	});
	html = html.replace(/!\[([^\]]*)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g, (_, alt, src) => {
		const target = unescapeHtml(src);
		const resolved = typeof resolveImage === 'function' ? resolveImage(target) : safeHref(target);
		if (resolved && typeof resolved === 'object' && typeof resolved.media === 'string') {
			return `<img data-preset-editor-media="${escapeHtml(resolved.media)}" alt="${alt}">`;
		}
		return typeof resolved === 'string' && resolved ? `<img src="${escapeHtml(resolved)}" alt="${alt}" loading="lazy">` : alt;
	});
	html = html.replace(/\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g, (_, label, href) => {
		const safe = safeHref(unescapeHtml(href));
		return safe ? `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${label}</a>` : label;
	});
	html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
	html = html.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>');
	html = html.replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g, '$1<em>$2</em>');
	return html.replace(/\u0000(\d+)\u0000/g, (_, index) => codes[Number(index)]);
}

export function renderMarkdown(source, options = {}) {
	const lines = String(source ?? '').replace(/\r\n?/g, '\n').split('\n');
	const out = [];
	let paragraph = [];
	let list = null;
	let code = null;
	const flushParagraph = () => {
		if (paragraph.length) out.push(`<p>${renderInline(paragraph.join(' '), options)}</p>`);
		paragraph = [];
	};
	const flushList = () => {
		if (list) out.push(`<${list.tag}>${list.items.map((item) => `<li>${renderInline(item, options)}</li>`).join('')}</${list.tag}>`);
		list = null;
	};
	const flush = () => {
		flushParagraph();
		flushList();
	};
	for (const line of lines) {
		if (code) {
			if (/^```/.test(line)) {
				out.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
				code = null;
			} else code.push(line);
			continue;
		}
		if (/^```/.test(line)) {
			flush();
			code = [];
			continue;
		}
		const heading = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
		if (heading) {
			flush();
			out.push(`<h${heading[1].length}>${renderInline(heading[2], options)}</h${heading[1].length}>`);
			continue;
		}
		if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
			flush();
			out.push('<hr>');
			continue;
		}
		const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
		const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
		if (bullet || numbered) {
			flushParagraph();
			const tag = bullet ? 'ul' : 'ol';
			if (!list || list.tag !== tag) {
				flushList();
				list = { tag, items: [] };
			}
			list.items.push((bullet ?? numbered)[1]);
			continue;
		}
		const quote = /^\s*>\s?(.*)$/.exec(line);
		if (quote) {
			flush();
			out.push(`<blockquote>${renderInline(quote[1], options)}</blockquote>`);
			continue;
		}
		if (!line.trim()) {
			flush();
			continue;
		}
		if (list) {
			list.items[list.items.length - 1] += ` ${line.trim()}`;
			continue;
		}
		paragraph.push(line.trim());
	}
	if (code) out.push(`<pre><code>${escapeHtml(code.join('\n'))}</code></pre>`);
	flush();
	return out.join('\n');
}

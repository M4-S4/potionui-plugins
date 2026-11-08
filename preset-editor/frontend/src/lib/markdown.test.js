import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { processMarkdown, renderMarkdown } from './markdown.js';

const CORE_MARKDOWN = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', '..', '..', '..', 'frontend', 'src', 'lib', 'utils', 'markdown.ts');
const skip = existsSync(CORE_MARKDOWN) ? false : 'the plugin is not inside a core checkout (content/plugins/<kind>/preset-editor)';

const SAMPLES = {
	'single line breaks': 'First line.\nSecond line.\n\nNew paragraph.\n\n\n\nAfter many blank lines.',
	'every heading level': '# One\n## Two\n### Three\n#### Four\n##### Five\n###### Six\n#No space\nText after.',
	'table with alignment': '| Mode | Speed | Notes |\n|:-----|------:|:-----:|\n| Fast | 2 s | `low` |\n| Slow | 9 s | a \\| b |\n\nAfter the table.',
	'table without outer pipes': 'Mode | Speed\n--- | ---\nFast | 2 s\nShort row\n\nNext.',
	'relative and absolute links': '[a](public/guide.md) [b](./guide.md) [c](/generate) [d](#top) [e](https://example.com/?a=1&b=2) [f](mailto:me@example.com) [g](docs/a b.md)',
	'unsafe links': '[x](javascript:alert(1)) [y](data:text/html,x) [z](" onmouseover="alert(1)) [w](vbscript:msgbox)',
	images: '![Cover](public/cover.webp)\n\n![Remote](https://example.com/c.webp)\n\n- ![a](https://example.com/a.png)\n\n> ![b](/b.png)',
	'lists and quotes': '- one\n- **two**\n\n3. three\n4. four\n\n1. first\n\n> quoted *soft*\n> again\n\n* star item\n  - nested',
	'code spans and blocks': 'Use `<b>` here.\n\n```yaml\nkey: <value> & more\n```\n\nAfter.',
	'html and entities': '<script>alert(1)</script> &amp; & &copy; &#169; &#xA9; "quotes" \'single\'',
	'emphasis edge cases': '**bold** *italic* ***both*** snake_case_name _under_ 2*3*4',
	'rule and empty lines': 'Above\n\n---\n\nBelow\n',
	'description of a preset': '# Wan 2.2 Lightning\n\nFast text-to-video.\nFour steps, 960×544 cap.\n\n## Modes\n\n| Mode | Steps |\n|---|---|\n| Fast | 4 |\n\nSee [the guide](docs/guide.md).\n'
};

test('renderMarkdown gives the same HTML as the core processMarkdown on every sample', { skip }, async () => {
	const core = await import(pathToFileURL(CORE_MARKDOWN).href);
	for (const [name, source] of Object.entries(SAMPLES)) {
		assert.equal(renderMarkdown(source), core.processMarkdown(source), name);
		assert.equal(processMarkdown(source), core.processMarkdown(source), name);
	}
	assert.equal(processMarkdown(''), core.processMarkdown(''));
});

test('a single line break becomes <br> and a blank line a block gap', () => {
	assert.equal(renderMarkdown('First line.\nSecond line.\n\nNext.'), 'First line.<br>Second line.<span class="block mt-2"></span>Next.');
	assert.equal(renderMarkdown('plain\r\ntext\rend'), 'plain<br>text<br>end');
});

test('headings stop at ### as in the core', () => {
	assert.equal(renderMarkdown('### Three'), '<h3 class="text-lg font-semibold mb-1 mt-3">Three</h3>');
	assert.equal(renderMarkdown('#### Four'), '#### Four');
});

test('a GFM table renders with the core classes and alignment', () => {
	const html = renderMarkdown('| A | B |\n|:--|--:|\n| 1 | 2 |');
	assert.equal(
		html,
		'<div class="overflow-x-auto"><table class="w-full text-sm my-3 border-collapse"><thead><tr><th class="text-left font-semibold px-3 py-1.5 border-b border-line-strong">A</th><th class="text-left font-semibold px-3 py-1.5 border-b border-line-strong text-right">B</th></tr></thead><tbody><tr><td class="px-3 py-1.5 border-b border-line align-top">1</td><td class="px-3 py-1.5 border-b border-line align-top text-right">2</td></tr></tbody></table></div>'
	);
});

test('a relative link is a link, an unsafe one keeps its text only', () => {
	assert.equal(renderMarkdown('[guide](docs/guide.md)'), '<a href="docs/guide.md" class="text-signal hover:underline" target="_blank" rel="noopener noreferrer">guide</a>');
	assert.equal(renderMarkdown('[x](javascript:alert(1))'), 'x)');
	assert.doesNotMatch(renderMarkdown('[z](" onmouseover="alert(1))'), /href="[^"]*" onmouseover/);
});

test('an image is no picture, the exclamation mark and the link, as in the core', () => {
	assert.equal(renderMarkdown('![Cover](public/cover.webp)'), '!<a href="public/cover.webp" class="text-signal hover:underline" target="_blank" rel="noopener noreferrer">Cover</a>');
	assert.doesNotMatch(renderMarkdown(SAMPLES.images), /<img/);
});

test('HTML is escaped and fenced code stays literal', () => {
	assert.equal(renderMarkdown('<script>x</script>'), '&lt;script&gt;x&lt;/script&gt;');
	assert.equal(renderMarkdown('```\n<i>\n```'), '<pre><code class="bg-surface-2 block p-3 rounded-lg text-sm font-mono text-fg-muted my-2 overflow-x-auto">&lt;i&gt;</code></pre>');
	assert.equal(renderMarkdown(''), '');
	assert.equal(renderMarkdown(null), '');
});

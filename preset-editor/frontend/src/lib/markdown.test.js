import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderInline, renderMarkdown, safeHref } from './markdown.js';

test('renderMarkdown builds headings, paragraphs, lists, quotes and code blocks', () => {
	const html = renderMarkdown('# Title\n\nSome **bold**, *soft* and `code`.\nSecond line.\n\n- a\n- b\n\n1. one\n2. two\n\n> quoted\n\n---\n\n```\n<script>alert(1)</script>\n```');
	assert.equal(html.includes('<h1>Title</h1>'), true);
	assert.equal(html.includes('<p>Some <strong>bold</strong>, <em>soft</em> and <code>code</code>. Second line.</p>'), true);
	assert.equal(html.includes('<ul><li>a</li><li>b</li></ul>'), true);
	assert.equal(html.includes('<ol><li>one</li><li>two</li></ol>'), true);
	assert.equal(html.includes('<blockquote>quoted</blockquote>'), true);
	assert.equal(html.includes('<hr>'), true);
	assert.equal(html.includes('<pre><code>&lt;script&gt;alert(1)&lt;/script&gt;</code></pre>'), true);
	assert.equal(html.includes('<script>'), false);
});

test('renderInline escapes HTML and keeps only safe links', () => {
	assert.equal(renderInline('<b>x</b> & "y"'), '&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;');
	assert.equal(renderInline('[site](https://example.com/?a=1&b=2)'), '<a href="https://example.com/?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">site</a>');
	assert.equal(renderInline('[x](javascript:alert(1))'), 'x');
	assert.equal(renderInline('`<i>` stays code'), '<code>&lt;i&gt;</code> stays code');
	assert.equal(safeHref(' /generate '), '/generate');
	assert.equal(safeHref('//evil'), null);
	assert.equal(safeHref('data:text/html,x'), null);
});

test('an image renders as the core shows it: no picture, the exclamation mark and the link', () => {
	assert.equal(renderInline('![Cover](public/cover.webp)'), '!Cover');
	assert.equal(renderInline('![Cover](https://example.com/c.webp)'), '!<a href="https://example.com/c.webp" target="_blank" rel="noopener noreferrer">Cover</a>');
	assert.equal(renderInline('![Cover "x"](public/cover.webp)'), '!Cover &quot;x&quot;');
	assert.equal(renderInline('![x](ftp://a)'), '!x');
	assert.doesNotMatch(renderMarkdown('# Title\n\n![Cover](public/cover.webp)\n\n- ![a](https://example.com/a.png)\n\n> ![b](/b.png)'), /<img/);
	assert.equal(renderMarkdown(''), '');
	assert.equal(renderMarkdown('plain\r\ntext'), '<p>plain text</p>');
});

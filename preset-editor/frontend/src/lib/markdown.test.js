import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { processMarkdown, renderMarkdown, sanitizeLinkUrl } from './markdown.js';

const CORE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', '..', '..', '..');
const CORE_UTILS = join(CORE_ROOT, 'frontend', 'src', 'lib', 'utils');
const CORE_MARKDOWN = join(CORE_UTILS, 'markdown.ts');
const CORE_SAFE_URL = join(CORE_UTILS, 'safeUrl.ts');
const insideCore = existsSync(join(CORE_ROOT, 'src', 'plugin_api'));
const coreHasMarkdown = existsSync(CORE_MARKDOWN);
const skip = coreHasMarkdown ? false : 'the plugin is not inside a core checkout, or the core has no frontend/src/lib/utils/markdown.ts (the shape test tells which)';
const SAFE_URL_IMPORT = "import { sanitizeLinkUrl } from './safeUrl';";
const coreSource = coreHasMarkdown ? readFileSync(CORE_MARKDOWN, 'utf8') : '';
const coreImports = [...coreSource.matchAll(/^\s*(?:import|export)\s[^;]*?\sfrom\s+(['"])([^'"]+)\1|^\s*import\s+(['"])([^'"]+)\3/gm)].map((match) => match[2] ?? match[4]);
const coreHasSafeUrl = coreHasMarkdown && existsSync(CORE_SAFE_URL);
const ruleCopies = existsSync(CORE_UTILS)
	? readdirSync(CORE_UTILS).filter((name) => /\.(ts|js)$/.test(name) && !/\.test\.(ts|js)$/.test(name) && name !== 'safeUrl.ts' && /\b(?:function|const|let)\s+sanitizeLinkUrl\b/.test(readFileSync(join(CORE_UTILS, name), 'utf8')))
	: [];
const knownShape =
	coreHasMarkdown &&
	ruleCopies.length === 0 &&
	(coreHasSafeUrl ? coreSource.includes(SAFE_URL_IMPORT) && coreImports.length === 1 : coreImports.length === 0 && /\bfunction sanitizeUrl\(/.test(coreSource));

registerHooks({
	resolve(specifier, context, nextResolve) {
		if (context.parentURL?.endsWith('.ts') && /^\.\.?\//.test(specifier) && !/\.[a-z]+$/.test(specifier)) {
			return nextResolve(`${specifier}.ts`, context);
		}
		return nextResolve(specifier, context);
	}
});

const hrefs = (html) => [...html.matchAll(/<a href="([^"]*)"/g)].map((match) => match[1]);

const SAMPLES = {
	'single line breaks': 'First line.\nSecond line.\n\nNew paragraph.\n\n\n\nAfter many blank lines.',
	'every heading level': '# One\n## Two\n### Three\n#### Four\n##### Five\n###### Six\n#No space\nText after.',
	'table with alignment': '| Mode | Speed | Notes |\n|:-----|------:|:-----:|\n| Fast | 2 s | `low` |\n| Slow | 9 s | a \\| b |\n\nAfter the table.',
	'table without outer pipes': 'Mode | Speed\n--- | ---\nFast | 2 s\nShort row\n\nNext.',
	'relative and absolute links': '[a](public/guide.md) [b](./guide.md) [c](/generate) [d](#top) [e](https://example.com/?a=1&b=2) [f](mailto:me@example.com) [g](docs/a b.md)',
	'unsafe links': '[x](javascript:alert(1)) [y](data:text/html,x) [z](" onmouseover="alert(1)) [w](vbscript:msgbox)',
	'encoded and hidden schemes': '[a](&#106;avascript:alert(1)) [b](&#x6A;avascript:x) [c](java&#x09;script:x) [d](JaVaScRiPt:x) [e](java\u200bscript:x) [f](&amp;#106;avascript:x) [g](%6Aavascript:x) [h](javascript&colon;x)',
	'data and other schemes': '[a](data:image/png;base64,AAAA) [b](DATA:text/html,x) [c](file:///etc/passwd) [d](ftp://example.com/x) [e](HTTPS://Example.com/Path) [f](mailto:a@example.com?subject=hi)',
	'relative links and anchors': '[a](./guide.md) [b](../up.md) [c](/generate?x=1) [d](#modes) [e](?tab=2) [f](guide.md) [g](public/cover.webp) [h](//evil.example/x) [i](/\\evil.example) [j](https://example.com/a b)',
	images: '![Cover](public/cover.webp)\n\n![Remote](https://example.com/c.webp)\n\n- ![a](https://example.com/a.png)\n\n> ![b](/b.png)',
	'lists and quotes': '- one\n- **two**\n\n3. three\n4. four\n\n1. first\n\n> quoted *soft*\n> again\n\n* star item\n  - nested',
	'code spans and blocks': 'Use `<b>` here.\n\n```yaml\nkey: <value> & more\n```\n\nAfter.',
	'html and entities': '<script>alert(1)</script> &amp; & &copy; &#169; &#xA9; "quotes" \'single\'',
	'emphasis edge cases': '**bold** *italic* ***both*** snake_case_name _under_ 2*3*4',
	'rule and empty lines': 'Above\n\n---\n\nBelow\n',
	'entity-encoded colons and letters': '[a](javascript&#58;x) [b](javascript&#x3a;x) [c](javascript&#X3A;x) [d](javascript&#0000058;x) [e](javascript&#58x) [f](javascript&amp;#58;x) [g](&#x6A;&#x61;&#x76;&#x61;&#x73;&#x63;&#x72;&#x69;&#x70;&#x74;&#x3A;x) [h](jav&#x61;script:x) [i](java&#13;script:x) [j](java&#10;script:x) [k](java&Tab;script:x) [l](javascript&NewLine;:x) [m](&#0;javascript:x) [n](vbscript&#58;x) [o](data&#58;text/html,x)',
	'raw html': '<a href="javascript:x">a</a> <img src=x onerror=alert(1)> <svg onload=alert(1)> <iframe src="javascript:x"></iframe> <math><mi>x</mi></math>',
	'table with links': '| Link | Note |\n|---|---|\n| [ok](https://example.com/) | [bad](javascript&#58;x) |\n| [rel](./guide.md) | `code` |\n',
	'description of a preset': '# Wan 2.2 Lightning\n\nFast text-to-video.\nFour steps, 960×544 cap.\n\n## Modes\n\n| Mode | Steps |\n|---|---|\n| Fast | 4 |\n\nSee [the guide](docs/guide.md).\n'
};

test('the core Markdown module has a shape this test knows how to load', { skip: !insideCore && 'the plugin is not inside a core checkout (content/plugins/<kind>/preset-editor)' }, () => {
	assert.ok(
		knownShape,
		`markdown.ts is ${coreHasMarkdown ? 'there' : 'missing'} in frontend/src/lib/utils of the core, imports ${JSON.stringify(coreImports)}, safeUrl.ts is ${coreHasSafeUrl ? 'there' : 'missing'}, ` +
			`and sanitizeLinkUrl is defined in ${JSON.stringify(ruleCopies)} besides safeUrl.ts. ` +
			`This test knows two shapes: markdown.ts with its own sanitizeUrl, no import and no safeUrl.ts (before 0.2.0), and markdown.ts with exactly ${SAFE_URL_IMPORT} and the rule in safeUrl.ts only (0.2.0). ` +
			'Teach the paths, the resolve hook and knownShape of markdown.test.js where the rule now lives, then compare markdown.js with the link rule of the core again.'
	);
});

test('renderMarkdown gives the same HTML as the core processMarkdown on every sample', { skip: skip || (!coreHasSafeUrl && 'this core links without its safeUrl rule (before 0.2.0)') }, async () => {
	const core = await import(pathToFileURL(CORE_MARKDOWN).href);
	for (const [name, source] of Object.entries(SAMPLES)) {
		assert.equal(renderMarkdown(source), core.processMarkdown(source), name);
		assert.equal(processMarkdown(source), core.processMarkdown(source), name);
	}
	assert.equal(processMarkdown(''), core.processMarkdown(''));
});

test('the link rule is the core safeUrl rule on every link of the samples', { skip: skip || (!coreHasSafeUrl && 'this core has no safeUrl rule (before 0.2.0)') }, async () => {
	const core = await import(pathToFileURL(CORE_SAFE_URL).href);
	const links = Object.values(SAMPLES).flatMap((source) => [...source.matchAll(/\]\(([^)]+)\)/g)].map((match) => match[1]));
	assert.ok(links.length >= 40, `${links.length} links`);
	for (const link of links) assert.equal(sanitizeLinkUrl(link), core.sanitizeLinkUrl(link), link);
});

test('on a core without the safeUrl rule the preview links nothing that core leaves as text', { skip: skip || (coreHasSafeUrl && 'this core has the safeUrl rule: the samples are compared whole') }, async () => {
	const core = await import(pathToFileURL(CORE_MARKDOWN).href);
	for (const [name, source] of Object.entries(SAMPLES)) {
		const mine = hrefs(renderMarkdown(source));
		const theirs = hrefs(core.processMarkdown(source));
		const left = [...theirs];
		for (const href of mine) {
			const at = left.indexOf(href);
			assert.ok(at >= 0, `${name}: the preview links ${href}, the core does not`);
			left.splice(at, 1);
		}
		if (mine.length === theirs.length) assert.equal(renderMarkdown(source), core.processMarkdown(source), name);
	}
});

test('a link the core 0.2.0 refuses is text in the preview', () => {
	for (const source of ['[x](&#106;avascript:alert(1))', '[x](java&#x09;script:x)', '[x](data:image/png;base64,AAAA)', '[x](//evil.example/x)', '[x](guide.md)', '[x](file:///etc/passwd)']) {
		assert.deepEqual(hrefs(renderMarkdown(source)), [], source);
	}
	for (const [link] of SAMPLES['entity-encoded colons and letters'].matchAll(/\[[a-z]\]\([^)]+\)/g)) {
		assert.deepEqual(hrefs(renderMarkdown(link)), [], link);
	}
	let deep = '[x](javascript&#58;x)';
	for (let level = 0; level < 17; level += 1) deep = deep.replace('&', '&amp;');
	for (const source of [
		'[x](javascript&colon;x)',
		'[x](javascript&COLON;x)',
		'[x](JaVaScRiPt:x)',
		'[x](DATA:text/html,x)',
		'[x](java\u200bscript:x)',
		'[x](java\u00adscript:x)',
		'[x](%6Aavascript:x)',
		'[x](vbscript:msgbox)',
		'[x](javascript&#x0003a;x)',
		'[x](javascript&#x3ax)',
		'[x](/\\evil.example)',
		'[x](\\\\evil.example)',
		'[x](/\t/evil.example)',
		deep
	]) {
		assert.deepEqual(hrefs(renderMarkdown(source)), [], JSON.stringify(source));
	}
	assert.deepEqual(hrefs(renderMarkdown(SAMPLES['table with links'])), ['https://example.com/', './guide.md']);
	assert.doesNotMatch(renderMarkdown(SAMPLES['raw html']), /<(a|img|svg|iframe|math)\b/);
	assert.deepEqual(hrefs(renderMarkdown('[a](./guide.md) [b](#modes) [c](?tab=2) [d](https://example.com/?a=1&b=2) [e](mailto:a@example.com)')), ['./guide.md', '#modes', '?tab=2', 'https://example.com/?a=1&amp;b=2', 'mailto:a@example.com']);
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
	assert.equal(renderMarkdown('[guide](./docs/guide.md)'), '<a href="./docs/guide.md" class="text-signal hover:underline" target="_blank" rel="noopener noreferrer">guide</a>');
	assert.equal(renderMarkdown('[x](javascript:alert(1))'), 'x)');
	assert.doesNotMatch(renderMarkdown('[z](" onmouseover="alert(1))'), /href="[^"]*" onmouseover/);
});

test('an image is no picture, the exclamation mark and the link, as in the core', () => {
	assert.equal(renderMarkdown('![Cover](./public/cover.webp)'), '!<a href="./public/cover.webp" class="text-signal hover:underline" target="_blank" rel="noopener noreferrer">Cover</a>');
	assert.equal(renderMarkdown('![Cover](public/cover.webp)'), '!Cover');
	assert.doesNotMatch(renderMarkdown(SAMPLES.images), /<img/);
});

test('HTML is escaped and fenced code stays literal', () => {
	assert.equal(renderMarkdown('<script>x</script>'), '&lt;script&gt;x&lt;/script&gt;');
	assert.equal(renderMarkdown('```\n<i>\n```'), '<pre><code class="bg-surface-2 block p-3 rounded-lg text-sm font-mono text-fg-muted my-2 overflow-x-auto">&lt;i&gt;</code></pre>');
	assert.equal(renderMarkdown(''), '');
	assert.equal(renderMarkdown(null), '');
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { detectLocale, formatBytes, formatDuration, formatTimecode, hasKey, normalizeLocale, translate } from './core.js';

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(here, '..');
const DYNAMIC_PREFIXES = ['error.'];
const PLURAL_SUFFIX = /\.(zero|one|two|few|many|other)$/;
const SKIPPED_DIRS = new Set(['dist', 'node_modules']);

function load(name) {
	return JSON.parse(readFileSync(join(here, name), 'utf-8'));
}

const dictionaries = { en: load('en.json'), fr: load('fr.json') };

function params(value) {
	return [...value.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
}

function sourceFiles(dir) {
	const files = [];
	for (const entry of readdirSync(dir, { withFileTypes: true })) {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) {
			if (!SKIPPED_DIRS.has(entry.name)) files.push(...sourceFiles(path));
		} else if (/\.(svelte|js)$/.test(entry.name) && !entry.name.endsWith('.test.js')) {
			files.push(path);
		}
	}
	return files;
}

function scanCalls() {
	const keys = new Map();
	const dynamic = [];
	const opaque = [];
	const literal = /(?<![\w$.])t\(\s*(?:'([^'\\\n]*)'|"([^"\\\n]*)"|`([^`\\]*)`)\s*([,)+])/g;
	const anyCall = /(?<![\w$.])(?<!function\s+)t\(\s*([^\s)])/g;
	for (const file of sourceFiles(srcRoot)) {
		const source = readFileSync(file, 'utf-8');
		const where = relative(srcRoot, file).replaceAll('\\', '/');
		for (const match of source.matchAll(literal)) {
			const [, single, double, template, next] = match;
			const value = single ?? double ?? template;
			const interpolated = template !== undefined && template.includes('${');
			if (interpolated || next === '+') {
				dynamic.push({ prefix: interpolated ? template.slice(0, template.indexOf('${')) : value, where });
			} else {
				keys.set(value, [...(keys.get(value) ?? []), where]);
			}
		}
		for (const match of source.matchAll(anyCall)) {
			if (!`'"\``.includes(match[1])) opaque.push(`${where}: ${source.slice(match.index, match.index + 40).split('\n')[0]}`);
		}
	}
	return { keys, dynamic, opaque };
}

const scan = scanCalls();

test('en and fr declare exactly the same keys', () => {
	const en = Object.keys(dictionaries.en).sort();
	const fr = Object.keys(dictionaries.fr).sort();
	assert.deepEqual(
		en.filter((key) => !fr.includes(key)),
		[],
		'keys missing from fr.json'
	);
	assert.deepEqual(
		fr.filter((key) => !en.includes(key)),
		[],
		'keys missing from en.json'
	);
});

test('every value is a non-empty string', () => {
	for (const [locale, dictionary] of Object.entries(dictionaries)) {
		for (const [key, value] of Object.entries(dictionary)) {
			assert.equal(typeof value, 'string', `${locale}.json ${key} is not a string`);
			assert.ok(value.trim(), `${locale}.json ${key} is empty`);
		}
	}
});

test('each key has the same {params} in en and fr', () => {
	for (const [key, value] of Object.entries(dictionaries.en)) {
		assert.deepEqual(params(dictionaries.fr[key] ?? ''), params(value), `params differ for ${key}`);
	}
});

test('the scan finds the t() calls of the page', () => {
	assert.ok(scan.keys.size > 0, 'no t() call found under frontend/src');
});

test('every t() call uses a literal key or a declared dynamic prefix', () => {
	assert.deepEqual(scan.opaque, [], 't() called with a non-literal key');
	for (const { prefix, where } of scan.dynamic) {
		assert.ok(
			DYNAMIC_PREFIXES.some((declared) => prefix.startsWith(declared)),
			`${where}: dynamic key prefix "${prefix}" is not declared in DYNAMIC_PREFIXES`
		);
	}
});

test('every t() key exists in en.json', () => {
	const unknown = [...scan.keys]
		.filter(([key]) => !(key in dictionaries.en) && !(`${key}.other` in dictionaries.en))
		.map(([key, files]) => `${key} (${files.join(', ')})`);
	assert.deepEqual(unknown, [], 'unknown translation keys');
});

test('every key of en.json is used', () => {
	const prefixes = scan.dynamic.map(({ prefix }) => prefix).filter(Boolean);
	const unused = Object.keys(dictionaries.en).filter((key) => {
		if (scan.keys.has(key) || scan.keys.has(key.replace(PLURAL_SUFFIX, ''))) return false;
		return !prefixes.some((prefix) => key.startsWith(prefix));
	});
	assert.deepEqual(unused, [], 'unused translation keys');
});

test('translate interpolates, pluralises and falls back to en then to the key', () => {
	const dicts = {
		en: { hello: 'Hello {name}', 'take.one': '{count} take', 'take.other': '{count} takes', only: 'English only' },
		fr: { hello: 'Bonjour {name}', 'take.one': '{count} prise', 'take.other': '{count} prises' }
	};
	const missing = [];
	const report = (key, locale, fellBack) => missing.push([key, locale, fellBack]);
	assert.equal(translate(dicts, 'fr', 'hello', { name: 'Léa' }, report), 'Bonjour Léa');
	assert.equal(translate(dicts, 'fr', 'take', { count: 0 }, report), '0 prise');
	assert.equal(translate(dicts, 'en', 'take', { count: 0 }, report), '0 takes');
	assert.equal(translate(dicts, 'en', 'take', { count: 1 }, report), '1 take');
	assert.equal(translate(dicts, 'fr', 'hello', {}, report), 'Bonjour {name}');
	assert.deepEqual(missing, []);
	assert.equal(translate(dicts, 'fr', 'only', undefined, report), 'English only');
	assert.equal(translate(dicts, 'fr', 'nope', undefined, report), 'nope');
	assert.deepEqual(missing, [
		['only', 'fr', true],
		['nope', 'fr', false]
	]);
	assert.ok(hasKey(dicts, 'fr', 'take'));
	assert.ok(hasKey(dicts, 'fr', 'only'));
	assert.ok(!hasKey(dicts, 'fr', 'nope'));
});

test('locale detection prefers the saved value, then a French browser, then en', () => {
	assert.equal(normalizeLocale('fr-CA'), 'fr');
	assert.equal(normalizeLocale('de'), null);
	assert.equal(detectLocale('en', 'fr-FR'), 'en');
	assert.equal(detectLocale(null, 'fr-BE'), 'fr');
	assert.equal(detectLocale('xx', 'en-US'), 'en');
	assert.equal(detectLocale(undefined, 'de-DE'), 'en');
});

test('formats follow the locale', () => {
	assert.equal(formatTimecode(3661.5, 24), '01:01:01:12');
	assert.equal(formatTimecode(-3), '00:00:00:00');
	assert.equal(formatTimecode(1.999, 25), '00:00:01:24');
	assert.match(formatDuration('fr', 90), /^1\smin 30\ss$/);
	assert.match(formatDuration('en', 0), /^0\ssec$/);
	assert.match(formatDuration('en', 3725), /^1\shr 2\smin$/);
	assert.match(formatBytes('fr', 1.5 * 1024 ** 3), /^1,5\s?Go$/);
	assert.match(formatBytes('en', 1.5 * 1024 ** 2), /^1\.5\s?MB$/);
});

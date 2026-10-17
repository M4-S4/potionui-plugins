import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DOMAINS, LOCALES, detectLocale, formatBytes, formatDuration, formatRelative, formatTimecode, hasKey, mergeDomains, normalizeLocale, translate } from './core.js';
import { FAILURE_CODES } from '../lib/generation.js';
import { EXPORT_ERROR_CODES } from '../lib/exports.js';

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(here, '..');
const DYNAMIC_PREFIXES = ['shell.error.', 'shell.menu.', 'commands.cmd.', 'generation.failed.', 'exports.error.'];
const PLURAL_SUFFIX = /\.(zero|one|two|few|many|other)$/;
const SKIPPED_DIRS = new Set(['dist', 'node_modules']);

function readDomain(locale, domain) {
	return readFileSync(join(here, locale, `${domain}.json`), 'utf-8');
}

const raw = Object.fromEntries(LOCALES.map((locale) => [locale, Object.fromEntries(DOMAINS.map((domain) => [domain, readDomain(locale, domain)]))]));
const domains = Object.fromEntries(LOCALES.map((locale) => [locale, Object.fromEntries(DOMAINS.map((domain) => [domain, JSON.parse(raw[locale][domain])]))]));
const dictionaries = Object.fromEntries(LOCALES.map((locale) => [locale, mergeDomains(domains[locale])]));

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
const commandsSource = readFileSync(join(srcRoot, 'lib', 'commands.js'), 'utf-8');
const commandIds = [...commandsSource.matchAll(/(?<![\w$.])command\(\s*'([a-z0-9-]+)'/g)].map((match) => match[1]);
const menuIds = [...commandsSource.matchAll(/(?<![\w$.])menu\(\s*'([a-z0-9-]+)'/g)].map((match) => match[1]);

test('each locale has one JSON file per domain, and nothing else', () => {
	for (const locale of LOCALES) {
		const files = readdirSync(join(here, locale)).sort();
		assert.deepEqual(files, DOMAINS.map((domain) => `${domain}.json`).sort(), `${locale}/ does not match DOMAINS`);
	}
});

test('index.svelte.js imports every domain file of every locale', () => {
	const source = readFileSync(join(here, 'index.svelte.js'), 'utf-8');
	for (const locale of LOCALES) {
		for (const domain of DOMAINS) assert.ok(source.includes(`'./${locale}/${domain}.json'`), `index.svelte.js does not import ${locale}/${domain}.json`);
	}
});

test('a global key is "<domain>.<key of the domain file>", so a domain file never repeats its own prefix', () => {
	assert.deepEqual(mergeDomains({ shell: { 'menu.file': 'File' }, panels: {} }), { 'shell.menu.file': 'File' });
	for (const locale of LOCALES) {
		for (const domain of DOMAINS) {
			const repeated = Object.keys(domains[locale][domain]).filter((key) => key.startsWith(`${domain}.`));
			assert.deepEqual(repeated, [], `${locale}/${domain}.json repeats its prefix`);
		}
	}
});

test('no domain file declares the same key twice', () => {
	for (const locale of LOCALES) {
		for (const domain of DOMAINS) {
			const seen = new Set();
			const twice = [];
			for (const match of raw[locale][domain].matchAll(/^\s*"((?:[^"\\]|\\.)*)"\s*:/gm)) {
				if (seen.has(match[1])) twice.push(match[1]);
				seen.add(match[1]);
			}
			assert.deepEqual(twice, [], `${locale}/${domain}.json declares keys twice`);
		}
	}
});

test('global keys are unique across domains', () => {
	for (const locale of LOCALES) {
		const total = DOMAINS.reduce((sum, domain) => sum + Object.keys(domains[locale][domain]).length, 0);
		assert.equal(Object.keys(dictionaries[locale]).length, total, `${locale}: keys collide after merging`);
	}
});

test('en and fr declare the same keys, domain by domain, empty domains included', () => {
	for (const domain of DOMAINS) {
		const en = Object.keys(domains.en[domain]).sort();
		const fr = Object.keys(domains.fr[domain]).sort();
		assert.deepEqual(
			en.filter((key) => !fr.includes(key)),
			[],
			`keys missing from fr/${domain}.json`
		);
		assert.deepEqual(
			fr.filter((key) => !en.includes(key)),
			[],
			`keys missing from en/${domain}.json`
		);
	}
});

test('every value is a non-empty string', () => {
	for (const locale of LOCALES) {
		for (const [key, value] of Object.entries(dictionaries[locale])) {
			assert.equal(typeof value, 'string', `${locale} ${key} is not a string`);
			assert.ok(value.trim(), `${locale} ${key} is empty`);
		}
	}
});

test('each key has the same {params} in en and fr, domain by domain', () => {
	for (const domain of DOMAINS) {
		for (const [key, value] of Object.entries(domains.en[domain])) {
			assert.deepEqual(params(domains.fr[domain][key] ?? ''), params(value), `params differ for ${domain}.${key}`);
		}
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

test('every t() key exists in en', () => {
	const unknown = [...scan.keys]
		.filter(([key]) => !(key in dictionaries.en) && !(`${key}.other` in dictionaries.en))
		.map(([key, files]) => `${key} (${files.join(', ')})`);
	assert.deepEqual(unknown, [], 'unknown translation keys');
});

test('every declared key is used by a literal t() call or by a declared dynamic prefix', () => {
	const unused = Object.keys(dictionaries.en).filter((key) => {
		if (scan.keys.has(key) || scan.keys.has(key.replace(PLURAL_SUFFIX, ''))) return false;
		return !DYNAMIC_PREFIXES.some((prefix) => key.startsWith(prefix));
	});
	assert.deepEqual(unused, [], 'unused translation keys');
});

test('every declared dynamic prefix is used by the page and declares keys', () => {
	for (const prefix of DYNAMIC_PREFIXES) {
		assert.ok(
			scan.dynamic.some((call) => call.prefix.startsWith(prefix)),
			`no t() call builds a key from "${prefix}"`
		);
		assert.ok(
			Object.keys(dictionaries.en).some((key) => key.startsWith(prefix)),
			`no key starts with "${prefix}"`
		);
	}
});

test('generation.failed.<code> matches the failure codes the take cards translate', () => {
	const declared = Object.keys(dictionaries.en).filter((key) => key.startsWith('generation.failed.')).map((key) => key.slice('generation.failed.'.length));
	assert.deepEqual(declared.sort(), [...FAILURE_CODES].sort());
	assert.equal(new Set(FAILURE_CODES).size, FAILURE_CODES.length);
	assert.equal(translate(dictionaries, 'fr', 'generation.failed.cuda_oom').startsWith('La mémoire du GPU'), true);
	assert.match(translate(dictionaries, 'en', 'generation.failed.unclassified', { id: 'G1' }), /Error ID: G1$/);
});

test('exports.error.<code> matches the export error codes the export window translates', () => {
	const declared = Object.keys(dictionaries.en).filter((key) => key.startsWith('exports.error.')).map((key) => key.slice('exports.error.'.length));
	assert.deepEqual(declared.sort(), [...EXPORT_ERROR_CODES].sort());
	assert.equal(new Set(EXPORT_ERROR_CODES).size, EXPORT_ERROR_CODES.length);
	assert.equal(translate(dictionaries, 'fr', 'exports.error.ffmpeg_failed'), 'ffmpeg n’a pas pu assembler la vidéo.');
	assert.equal(translate(dictionaries, 'en', 'exports.error.invalid_doc').startsWith('The saved project'), true);
});

test('every command and menu of lib/commands.js has a label, and every label has a command', () => {
	assert.equal(commandIds.length, 97, 'the source editor has 97 commands, minus the theme switch, plus the version history');
	assert.equal(new Set(commandIds).size, commandIds.length, 'duplicate command id');
	assert.equal(menuIds.length, 10);
	assert.ok(!commandIds.includes('theme'), 'the theme command belongs to the host');
	const labels = Object.keys(dictionaries.en).filter((key) => key.startsWith('commands.cmd.')).map((key) => key.slice('commands.cmd.'.length));
	assert.deepEqual(labels.sort(), [...commandIds].sort());
	const menus = Object.keys(dictionaries.en).filter((key) => key.startsWith('shell.menu.')).map((key) => key.slice('shell.menu.'.length));
	assert.deepEqual(menus.sort(), [...menuIds].sort());
	const errors = Object.keys(dictionaries.en).filter((key) => key.startsWith('shell.error.'));
	assert.ok(errors.includes('shell.error.unknown') && errors.includes('shell.error.server_error'));
});

test('Help › Simulated features lists the seven simulated items, each with a title and a text', () => {
	const items = ['identity', 'lipSync', 'scene', 'voice', 'console', 'formats', 'engine'];
	const declared = Object.keys(dictionaries.en).filter((key) => /^shell\.simulations\.[^.]+\.title$/.test(key)).map((key) => key.split('.')[2]);
	assert.deepEqual(declared, items);
	const modals = readFileSync(join(srcRoot, 'components', 'modals', 'Modals.svelte'), 'utf-8');
	for (const item of items) {
		for (const locale of LOCALES) assert.ok(dictionaries[locale][`shell.simulations.${item}.text`], `${locale} shell.simulations.${item}.text`);
		assert.ok(modals.includes(`t('shell.simulations.${item}.title'), t('shell.simulations.${item}.text')`), `Modals.svelte does not list ${item}`);
	}
});

test('translate interpolates, pluralises and falls back to en then to the key', () => {
	const dicts = {
		en: { hello: 'Hello {name}', 'take.one': '{count} take', 'take.other': '{count} takes', only: 'English only' },
		fr: { hello: 'Bonjour {name}', 'take.one': '{count} prise', 'take.other': '{count} prises' }
	};
	const missing = [];
	const report = (key, locale, fellBack) => missing.push([key, locale, fellBack]);
	assert.equal(translate(dicts, 'fr', 'hello', { name: 'Yann' }, report), 'Bonjour Yann');
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

test('the merged dictionaries translate real keys in both locales', () => {
	assert.equal(translate(dictionaries, 'fr', 'commands.cmd.dir-global'), 'Direction globale');
	assert.equal(translate(dictionaries, 'en', 'shell.menu.edit-timeline'), 'Cut');
	assert.equal(translate(dictionaries, 'fr', 'shell.status.issues', { count: 1 }), '1 point de direction à vérifier');
	assert.equal(translate(dictionaries, 'en', 'lib.toast.takesDraft', { count: 2 }), '2 draft takes ready');
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

test('relative times count back from now in the locale, and never into the future', () => {
	const now = Date.parse('2026-10-16T12:00:00Z');
	assert.equal(formatRelative('en', '2026-10-16T11:55:00Z', now), '5 minutes ago');
	assert.equal(formatRelative('fr', '2026-10-16T11:55:00Z', now), 'il y a 5 minutes');
	assert.equal(formatRelative('en', '2026-10-15T11:00:00Z', now), 'yesterday');
	assert.equal(formatRelative('fr', '2026-10-15T11:00:00Z', now), 'hier');
	assert.equal(formatRelative('en', '2026-10-02T12:00:00Z', now), '2 weeks ago');
	assert.equal(formatRelative('en', '2026-10-16T12:00:30Z', now), 'now');
	assert.equal(formatRelative('en', 'not a date', now), '');
	assert.equal(formatRelative('en', null, now), '');
});

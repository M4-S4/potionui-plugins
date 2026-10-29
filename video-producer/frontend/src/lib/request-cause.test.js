import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { translate } from '../i18n/core.js';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const shell = (locale) => JSON.parse(read(`../i18n/${locale}/shell.json`));
const dictionaries = Object.fromEntries(['en', 'fr'].map((locale) => [locale, Object.fromEntries(Object.entries(shell(locale)).map(([key, value]) => [`shell.${key}`, value]))]));

test('errors: one function names the cause of a failed request, from its code, else from the message the server returned, else from its status', () => {
	const index = read('../i18n/index.svelte.js');
	assert.match(index, /export function requestCause\(error\) \{\n\tconst code = error\?\.code;\n\tif \(code && has\(`shell\.error\.\$\{code\}`\)\) return t\(`shell\.error\.\$\{code\}`\);\n\tif \(error\?\.message\) return t\('shell\.error\.returned', \{ message: error\.message \}\);\n\tif \(error\?\.status >= 500\) return t\('shell\.error\.server_error'\);\n\treturn t\('shell\.error\.unknown'\);\n\}/);
	assert.match(read('../VideoProducerPage.svelte'), /const errorText = \$derived\(requestCause\(loadError\)\);/);
	assert.equal(translate(dictionaries, 'fr', 'shell.error.returned', { message: 'boom' }), 'Le serveur a renvoyé une erreur : boom');
	assert.equal(translate(dictionaries, 'en', 'shell.error.returned', { message: 'boom' }), 'The server returned an error: boom');
	assert.match(translate(dictionaries, 'fr', 'shell.error.invalid_response'), /n’a pas répondu/);
	assert.match(translate(dictionaries, 'fr', 'shell.error.network_error'), /Impossible de joindre le serveur/);
});

test('errors: the shot editor says why the prompt could not be composed and offers Retry, which calls the server again at once', () => {
	const composed = read('../components/shots/ComposedPrompt.svelte');
	assert.match(composed, /\{t\('modals\.shot\.composedError'\)\} \{requestCause\(composed\.error\)\}/);
	assert.match(composed, /<HostUi name="Button" props=\{\{ variant: 'ghost', size: 'xs', icon: 'refresh', onclick: retry \}\}>\{t\('shell\.app\.retry'\)\}<\/HostUi>/);
	assert.match(composed, /function retry\(\) \{\n\t\tcomposed\.error = null;\n\t\tattempt \+= 1;\n\t\}/);
	assert.match(composed, /const retrying = attempt !== tried;\n\t\ttried = attempt;/);
	assert.match(composed, /\}, retrying \? 0 : DELAY\);/);
});

test('errors: the start and end images say why the estimate failed and offer Retry, which asks for the estimate again', () => {
	const candidates = read('../components/shots/KeyframeCandidates.svelte');
	assert.match(candidates, /\{#if keyframeState\.error && !keyframeState\.estimating\}/);
	assert.match(candidates, /\{t\('keyframes\.estimate\.failed'\)\} \{requestCause\(keyframeState\.error\)\}/);
	assert.match(candidates, /onclick: \(\) => body && scheduleKeyframeEstimate\(body, true\) \}\}>\{t\('shell\.app\.retry'\)\}<\/HostUi>/);
	const store = read('keyframes.svelte.js');
	assert.match(store, /export function scheduleKeyframeEstimate\(body, force = false\) \{\n\tconst key = requestKey\(body\);\n\tif \(key === estimateKey && !force\) return;/);
});

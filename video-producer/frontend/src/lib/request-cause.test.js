import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import './svelte-harness.js';
import { translate } from '../i18n/core.js';
import enShell from '../i18n/en/shell.json' with { type: 'json' };
import frShell from '../i18n/fr/shell.json' with { type: 'json' };

const dictionaries = Object.fromEntries([['en', enShell], ['fr', frShell]].map(([locale, shell]) => [locale, Object.fromEntries(Object.entries(shell).map(([key, value]) => [`shell.${key}`, value]))]));

const { requestCause, setLocale, t } = await import('../i18n/index.svelte.js');
const { project, bindClient } = await import('./project.svelte.js');
const { keyframeState, openKeyframes, closeKeyframes, scheduleKeyframeEstimate } = await import('./keyframes.svelte.js');
const { doc, dispose } = await import('./state.svelte.js');

after(() => {
	closeKeyframes();
	dispose();
});

test('errors: one function names the cause of a failed request, from its code, else from the message the server returned, else from its status', () => {
	setLocale('en');
	assert.equal(requestCause({ code: 'network_error', status: 0 }), t('shell.error.network_error'));
	assert.equal(requestCause({ code: 'odd_code', message: 'boom', status: 400 }), 'The server returned an error: boom');
	assert.equal(requestCause({ code: 'odd_code', status: 503 }), t('shell.error.server_error'));
	assert.equal(requestCause({ status: 404 }), t('shell.error.unknown'));
	assert.equal(requestCause(null), t('shell.error.unknown'));
	setLocale('fr');
	assert.equal(requestCause({ message: 'boom' }), 'Le serveur a renvoyé une erreur : boom');
	setLocale('en');
	assert.equal(translate(dictionaries, 'fr', 'shell.error.returned', { message: 'boom' }), 'Le serveur a renvoyé une erreur : boom');
	assert.equal(translate(dictionaries, 'en', 'shell.error.returned', { message: 'boom' }), 'The server returned an error: boom');
	assert.match(translate(dictionaries, 'fr', 'shell.error.invalid_response'), /n’a pas répondu/);
	assert.match(translate(dictionaries, 'fr', 'shell.error.network_error'), /Impossible de joindre le serveur/);
});

test('errors: a failed estimate of the start and end images keeps its cause until Retry asks for the same estimate again at once', async () => {
	const asked = [];
	let answer = { ok: false, error: { status: 500, code: 'server_error', message: '', data: null } };
	bindClient({
		async estimateKeyframes(projectId, shotId, body) {
			asked.push([projectId, shotId, body.count]);
			return answer;
		},
		async keyframes() {
			return { ok: true, data: [] };
		},
		async saveProject(id, next, version) {
			return { ok: true, data: { version: version + 1, updatedAt: null } };
		},
		saveLastProject() {}
	});
	project.id = 'p1';
	openKeyframes('s1');
	const body = { option: { preset: 'x', model: null }, role: 'first', count: 2, prompt: 'a', pictures: [] };
	const settled = () => new Promise((resolve) => setTimeout(resolve, 700));
	scheduleKeyframeEstimate(body);
	scheduleKeyframeEstimate(body);
	await settled();
	assert.deepEqual(asked, [['p1', 's1', 2]]);
	assert.deepEqual([keyframeState.estimating, keyframeState.error?.code], [false, 'server_error']);
	answer = { ok: true, data: { blocks: [], warnings: [], quota: null } };
	scheduleKeyframeEstimate(body);
	await settled();
	assert.equal(asked.length, 1);
	scheduleKeyframeEstimate(body, true);
	await settled();
	assert.equal(asked.length, 2);
	assert.deepEqual([keyframeState.error, keyframeState.estimate?.blocks], [null, []]);
});

test('errors: an estimate overtaken by a newer one leaves Make to the newer, which frees Make when the project cannot be saved before it', async () => {
	const answers = [];
	let saved = { ok: true, data: { version: 2, updatedAt: null } };
	bindClient({
		estimateKeyframes: () => new Promise((resolve) => answers.push(resolve)),
		async keyframes() {
			return { ok: true, data: [] };
		},
		async saveProject() {
			return saved;
		},
		saveLastProject() {}
	});
	project.id = 'p1';
	openKeyframes('s1');
	const body = (count) => ({ option: { preset: 'x', model: null }, role: 'first', count, prompt: 'a', pictures: [] });
	const settled = () => new Promise((resolve) => setTimeout(resolve, 700));
	scheduleKeyframeEstimate(body(2));
	await settled();
	assert.deepEqual([answers.length, keyframeState.estimating], [1, true]);
	saved = { ok: false, error: { status: 500, code: 'server_error', message: '', data: null } };
	doc.name = 'Harbour at dawn';
	scheduleKeyframeEstimate(body(3));
	await settled();
	assert.deepEqual([answers.length, keyframeState.estimating], [1, false]);
	answers[0]({ ok: true, data: { blocks: [], warnings: [], quota: null } });
	await new Promise((resolve) => setImmediate(resolve));
	assert.deepEqual([keyframeState.estimating, keyframeState.estimate, keyframeState.error], [false, null, null]);
});

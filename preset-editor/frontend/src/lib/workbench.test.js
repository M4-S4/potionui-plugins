import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const COMPONENTS = join(dirname(fileURLToPath(import.meta.url)), '..', 'components');
const read = (name) => readFileSync(join(COMPONENTS, name), 'utf8');

function order(source, start, steps) {
	const body = source.slice(source.indexOf(start));
	const at = steps.map((step) => body.indexOf(step));
	assert.ok(at.every((value, index) => value >= 0 && (index === 0 || value > at[index - 1])), `${start}: ${JSON.stringify(at)}`);
}

test('removing a mode asks the server first, then shows a refusal or the confirmation, whatever the check answered', () => {
	order(read('Workbench.svelte'), 'async function dropMode(mode) {', [
		'const plan = removalPlan(await modeRemoval(api, draft.draft_id, mode));',
		"if (plan.action === 'refuse') {",
		'refusal = plan.refusal;',
		'const ok = await confirm({ title: `Remove the mode ${mode}?`, message: plan.message, variant: \'danger\' });',
		'const result = await removeMode(api, draft.draft_id, mode);',
		"refusal = refusalOf(result.error, 'mode');"
	]);
});

test('the busy mark of a removal is on the mode being removed', () => {
	const source = read('Workbench.svelte');
	assert.equal([...source.matchAll(/busy = `remove:\$\{mode\}`;/g)].length, 2);
	assert.match(source, /\{#if busy === `remove:\$\{mode\}`\}\s*<span class="block h-3\.5 w-3\.5 animate-spin/);
	assert.match(source, /\{#if refusal\}\s*<div class="mt-2"><RefusalNotice \{refusal\}/);
});

test('deleting a file asks the server first, then shows a refusal or the confirmation', () => {
	const source = read('TextEditor.svelte');
	order(source, 'async function remove() {', [
		'const plan = deletionPlan(await fileDeletion(api, draftId, path));',
		"if (plan.action === 'refuse') {",
		'refusal = plan.refusal;',
		'const ok = await confirm({ title: `Delete ${path}?`, message: plan.message, variant: \'danger\' });',
		'const result = await deleteFile(api, draftId, path);',
		"refusal = refusalOf(result.error, 'file');"
	]);
	assert.match(source, /\{#if refusal\}\s*<div class="border-b border-line px-3 py-2"><RefusalNotice \{refusal\}/);
});

test('the refusal notice stays until it is closed and lists one file per line', () => {
	const source = read('RefusalNotice.svelte');
	assert.match(source, /role="alert"/);
	assert.match(source, /<ul class="[^"]*break-all[^"]*">/);
	assert.match(source, /\{#each refusal\.lines as line, position \(position\)\}\s*<li>\{line\}<\/li>/);
	assert.match(source, /onclick=\{onClose\}/);
	assert.doesNotMatch(source, /setTimeout|toast/);
});

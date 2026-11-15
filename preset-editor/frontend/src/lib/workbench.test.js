import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'components', 'Workbench.svelte'), 'utf8');

test('removing a mode asks the server what the removal leaves before the confirmation', () => {
	const body = SOURCE.slice(SOURCE.indexOf('async function dropMode(mode) {'));
	const check = body.indexOf('const check = await modeRemoval(api, draft.draft_id, mode);');
	const refused = body.indexOf("if (!check.data.allowed) {\n\t\t\ttoast('error', check.data.message);\n\t\t\treturn;");
	const asked = body.indexOf('const ok = await confirm({ title: `Remove the mode ${mode}?`, message: removalMessage(check.data), variant: \'danger\' });');
	const removed = body.indexOf('const result = await removeMode(api, draft.draft_id, mode);');

	assert.ok(check > 0 && refused > check && asked > refused && removed > asked, `${check} ${refused} ${asked} ${removed}`);
});

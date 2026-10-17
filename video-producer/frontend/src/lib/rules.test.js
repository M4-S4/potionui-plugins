import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileRules, conflictIds, namesCamera } from './rules.js';

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => JSON.parse(readFileSync(path, 'utf-8'));
const pageCopy = read(join(here, 'rules.json'));
const shared = read(join(here, '..', '..', '..', 'backend', 'chat', 'rules.json'));
const rules = compileRules(pageCopy);

test('the page copy of rules.json is identical to the backend one', () => {
	assert.deepEqual(pageCopy, shared);
});

test('both languages declare the same rules, each with a translated issue text', () => {
	const ids = (language) => pageCopy.conflicts[language].map((rule) => rule.id);
	assert.deepEqual(ids('fr'), ids('en'));
	assert.deepEqual(Object.keys(pageCopy.cameraWords).sort(), ['en', 'fr']);
	for (const locale of ['en', 'fr']) {
		const lib = read(join(here, '..', 'i18n', locale, 'lib.json'));
		for (const id of ids('en')) assert.ok(lib[`issue.${id}`], `${locale}/lib.json has no issue.${id}`);
	}
});

test('conflictIds: a shot prompt that contradicts the global direction, in the prompt language', () => {
	assert.deepEqual(conflictIds(rules, 'en', 'Cold dawn, no neon, natural colors.', 'Neon signs in monochrome.'), ['noNeon', 'naturalColors']);
	assert.deepEqual(conflictIds(rules, 'en', 'No on-screen text.', 'A context shot of the harbour.'), []);
	assert.deepEqual(conflictIds(rules, 'en', 'No on-screen text.', 'The title text fades in.'), ['noText']);
	assert.deepEqual(conflictIds(rules, 'en', 'Slow, steady camera.', 'Handheld, fast pan.'), ['stableCamera']);
	assert.deepEqual(conflictIds(rules, 'fr', 'Aube froide, aucun néon, couleurs naturelles.', 'Enseignes au NÉON en noir et blanc.'), ['noNeon', 'naturalColors']);
	assert.deepEqual(conflictIds(rules, 'fr', 'Caméra stable.', 'Caméra à l’épaule, rapide.'), ['stableCamera']);
	assert.deepEqual(conflictIds(rules, 'fr', 'Sans texte.', 'Un contexte calme.'), []);
});

test('namesCamera: the camera words of each language', () => {
	assert.ok(namesCamera(rules, 'en', 'Slow dolly in on the hands.'));
	assert.ok(namesCamera(rules, 'en', 'A wide pan over the bay.'));
	assert.ok(!namesCamera(rules, 'en', 'A panorama of the bay.'));
	assert.ok(namesCamera(rules, 'fr', 'Travelling latéral le long du quai.'));
	assert.ok(!namesCamera(rules, 'fr', 'Les mains du pêcheur.'));
});

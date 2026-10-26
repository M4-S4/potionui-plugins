import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CARD_ICONS, FAMILY_ICONS, PICTURE_ICONS, TYPE_ICONS, TYPE_KEYS, referenceTags, typeIcon } from './reftags.js';
import { typesOf } from './refmedia.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

function project() {
	return {
		clips: [{ id: 's1' }, { id: 's2' }],
		references: [],
		bible: {
			characters: [{ id: 'c-lea', label: 'Léa', text: '', props: '', references: ['r-lea', 'r-hat'], voiceRef: 'r-voice' }],
			places: [{ id: 'p-cafe', label: 'Café', text: '', references: ['r-cafe'] }]
		}
	};
}

const brief = (tags) => tags.map((tag) => (tag.kind === 'type' ? `type:${tag.type}:${tag.icon}` : tag.kind === 'role' ? `role:${tag.role}` : tag.kind === 'scope' ? `scope:${tag.global ? 'project' : (tag.number ?? 'gone')}` : `card:${tag.card.label}:${tag.icon}${tag.voice ? ':voice' : ''}`));

test('a reference shows its type, its role when the type does not say it, its scope and the cards of the bible it belongs to', () => {
	const doc = project();

	assert.deepEqual(brief(referenceTags(doc, { id: 'r-lea', space: 'identite', type: 'Personnage', role: 'Identité', scope: { type: 'global' } })), ['type:Personnage:user', 'scope:project', 'card:Léa:user']);
	assert.deepEqual(brief(referenceTags(doc, { id: 'r-hat', space: 'identite', type: 'Objet', role: 'Objet', scope: { type: 'shot', shotId: 's2' } })), ['type:Objet:diamond', 'scope:2', 'card:Léa:user']);
	assert.deepEqual(brief(referenceTags(doc, { id: 'r-cafe', space: 'decors3d', type: 'Capture 3D', role: 'Décor', scope: null })), ['type:Capture 3D:cube', 'scope:project', 'card:Café:mountain']);
	assert.deepEqual(brief(referenceTags(doc, { id: 'r-voice', space: 'son', type: 'Voix', role: 'Son', scope: { type: 'global' } })), ['type:Voix:mic', 'scope:project', 'card:Léa:user:voice']);
	assert.deepEqual(brief(referenceTags(doc, { id: 'r-x', space: 'identite', type: 'Personnage', role: 'Style', scope: { type: 'shot', shotId: 'gone' } })), ['type:Personnage:user', 'role:Style', 'scope:gone']);
	assert.deepEqual(brief(referenceTags(doc, { id: 'r-y', space: 'identite', type: 'Style', role: 'Style', scope: { type: 'global' } })), ['type:Style:palette', 'scope:project']);
	assert.deepEqual(brief(referenceTags(doc, { id: 'r-z', space: 'mouvement', type: 'Control video', role: 'Caméra', scope: { type: 'global' } })), ['type:Control video:film', 'role:Caméra', 'scope:project']);
	assert.deepEqual(referenceTags(doc, null), []);
});

test('one table names and draws every type of every family, the cards and the pictures of a start image', () => {
	for (const space of Object.keys(FAMILY_ICONS)) for (const type of typesOf(space)) assert.ok(TYPE_KEYS[type] && TYPE_ICONS[type], `${space} · ${type}`);
	assert.equal(typeIcon({ space: 'identite', type: 'Inconnu' }), 'user');
	assert.equal(typeIcon({ space: 'ailleurs', type: 'Inconnu' }), 'bookmark');
	assert.deepEqual(CARD_ICONS, { characters: 'user', places: 'mountain' });
	assert.deepEqual(PICTURE_ICONS, { frame: 'image', setting: 'mountain', character: 'user', object: 'diamond', style: 'palette' });
});

test('Director AI › Bible and References, the shot editor and the Inspector show a reference with the same tags', () => {
	const tags = '<RefTags reference=';
	assert.match(source('../components/references/ReferenceBoard.svelte'), new RegExp(`${tags}\\{r\\} />`));
	assert.match(source('../components/director/BibleAside.svelte'), new RegExp(`${tags}\\{r\\} />`));
	assert.match(source('../components/director/BibleView.svelte'), /title=\{`\$\{r\.name\} · \$\{referenceTagText\(r\)\}`\}/);
	const editor = source('../components/modals/ShotEditor.svelte');
	assert.match(editor, new RegExp(`${tags}\\{r\\} />`));
	assert.match(editor, /<RefTags reference=\{\{ \.\.\.r, scope: \{ type: 'shot', shotId: clip\.id \} \}\} class="pl-14" \/>/);
	assert.match(source('../components/inspector/Inspector.svelte'), new RegExp(`${tags}\\{item\\} />`));
	assert.match(source('../components/modals/Modals.svelte'), /<li>\{r\.name\} · \{referenceTagText\(r\)\}<\/li>/);
	for (const path of ['../components/references/ReferenceBoard.svelte', '../components/modals/ShotEditor.svelte', '../components/director/BibleAside.svelte']) {
		const text = source(path);
		assert.doesNotMatch(text, /f\?\.label \?\? r\.space|refRoleLabel\(r\.role\)|globalBadge/, path);
	}
	const references = source('./references.js');
	assert.match(references, /export const refTypeLabel = \(type\) => \(TYPE_KEYS\[type\]/);
	assert.match(references, /export const refRoleLabel = \(role\) => \(ROLE_KEYS\[role\]/);
	assert.match(source('../components/references/RefTags.svelte'), /const tags = \$derived\(referenceTags\(doc, reference\)\);/);
});

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { renderComponent, textOf } from './svelte-harness.js';
import { CARD_ICONS, FAMILY_ICONS, PICTURE_ICONS, TYPE_ICONS, TYPE_KEYS, referenceTags, typeIcon } from './reftags.js';
import { typesOf } from './refmedia.js';

const { doc, ui, dispose } = await import('./state.svelte.js');
const { t } = await import('../i18n/index.svelte.js');
const { refRoleLabel, refTypeLabel, referenceTagText } = await import('./references.js');
const url = (path) => new URL(path, import.meta.url).href;
const REF_TAGS = url('../components/references/RefTags.svelte');
const BOARD = url('../components/references/ReferenceBoard.svelte');
const BIBLE_ASIDE = url('../components/director/BibleAside.svelte');
const BIBLE_VIEW = url('../components/director/BibleView.svelte');
const SHOT_EDITOR = url('../components/modals/ShotEditor.svelte');
const INSPECTOR = url('../components/inspector/Inspector.svelte');
const MODALS = url('../components/modals/Modals.svelte');

after(() => dispose());

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

test('Director AI › Bible and References, the shot editor and the Inspector show a reference with the same tags', async () => {
	const film = project();
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo' }, { id: 's2', start: 4, dur: 4, label: 'Two', stage: 'todo' }];
	doc.assets = [{ id: 'pic', kind: 'image', name: 'Léa', src: '/m/lea.png' }];
	doc.bible = film.bible;
	doc.references = [
		{ id: 'r-lea', name: 'Léa face', space: 'identite', type: 'Personnage', assetId: 'pic', role: 'Style', scope: { type: 'global' } },
		{ id: 'r-hat', name: 'Hat', space: 'identite', type: 'Objet', assetId: null, role: 'Objet', scope: { type: 'shot', shotId: 's2' } }
	];
	Object.assign(ui, { selection: null, modal: null, bibleCard: null, refSpace: 'all' });
	const lea = doc.references[0];
	const kinds = referenceTags(doc, lea).map((tag) => tag.kind);
	const labels = referenceTagText(lea).split(' · ');
	assert.deepEqual(kinds, ['type', 'role', 'scope', 'card']);
	const alone = await renderComponent(REF_TAGS, { reference: lea });
	assert.deepEqual([...alone.matchAll(/data-ref-tag="([a-z]+)"/g)].map((found) => found[1]), kinds);
	for (const label of labels) assert.ok(textOf(alone).includes(label), label);
	const shows = async (component, props = {}) => {
		const html = await renderComponent(component, props);
		assert.match(html, /data-ref-tags/, component);
		for (const label of labels) assert.ok(textOf(html).includes(label), `${component} ${label}`);
		return html;
	};
	await shows(BOARD);
	ui.bibleCard = 'c-lea';
	await shows(BIBLE_ASIDE);
	ui.bibleCard = null;
	ui.selection = { kind: 'reference', id: 'r-lea' };
	await shows(INSPECTOR);
	ui.selection = null;
	await shows(SHOT_EDITOR, { id: 's1' });
	const view = await renderComponent(BIBLE_VIEW);
	assert.ok(view.includes(`title="${lea.name} · ${referenceTagText(lea)}" data-ref-thumb`));
	ui.modal = { type: 'recap' };
	assert.ok(textOf(await renderComponent(MODALS)).includes(`${lea.name} · ${referenceTagText(lea)}`));
	ui.modal = null;
	assert.equal(refTypeLabel('Personnage'), t(`lib.refType.${TYPE_KEYS.Personnage}`));
	assert.equal(refTypeLabel('Whatever'), 'Whatever');
	assert.notEqual(refRoleLabel('Identité'), 'Identité');
	assert.equal(refRoleLabel('Whatever'), 'Whatever');
});

import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, select, toast, productionRange, secs, clipAt, clipLabel, overlaps, openDirector } from './state.svelte.js';
import { ulid } from './ulid.js';
import { SOUND_SPACE } from './sound.js';
import { refMediaKind, typesOf } from './refmedia.js';
import { CHARACTERS } from './bible.js';
import { DEFAULT_ROLES, FAMILY_ICONS, ROLE_KEYS, TYPE_KEYS, referenceTags } from './reftags.js';

export const families = [
	{
		id: 'identite',
		icon: FAMILY_ICONS.identite,
		get label() {
			return t('lib.family.identite.label');
		},
		get short() {
			return t('lib.family.identite.short');
		},
		get hint() {
			return t('lib.family.identite.hint');
		}
	},
	{
		id: 'decors3d',
		icon: FAMILY_ICONS.decors3d,
		get label() {
			return t('lib.family.decors3d.label');
		},
		get short() {
			return t('lib.family.decors3d.short');
		},
		get hint() {
			return t('lib.family.decors3d.hint');
		}
	},
	{
		id: 'mouvement',
		icon: FAMILY_ICONS.mouvement,
		get label() {
			return t('lib.family.mouvement.label');
		},
		get short() {
			return t('lib.family.mouvement.short');
		},
		get hint() {
			return t('lib.family.mouvement.hint');
		}
	},
	{
		id: SOUND_SPACE,
		icon: FAMILY_ICONS[SOUND_SPACE],
		get label() {
			return t('lib.family.son.label');
		},
		get short() {
			return t('lib.family.son.short');
		},
		get hint() {
			return t('lib.family.son.hint');
		}
	}
];
const roles = DEFAULT_ROLES;

export { refMediaKind, typesOf };

export const refTypeLabel = (type) => (TYPE_KEYS[type] ? t(`lib.refType.${TYPE_KEYS[type]}`) : type);

export const refRoleLabel = (role) => (ROLE_KEYS[role] ? t(`lib.refRole.${ROLE_KEYS[role]}`) : role);

const cardName = (card) => card.label?.trim() || t('panels.dock.bible.unnamed');

export function refTagLabel(tag) {
	if (tag.kind === 'type') return refTypeLabel(tag.type);
	if (tag.kind === 'role') return t('lib.refTag.role', { role: refRoleLabel(tag.role) });
	if (tag.kind === 'scope') return tag.global ? t('lib.refTag.project') : tag.number ? t('lib.refTag.shot', { number: String(tag.number).padStart(2, '0') }) : t('lib.refTag.shotGone');
	return cardName(tag.card);
}

export function refTagTip(tag) {
	if (tag.kind === 'type') return t('lib.refTag.typeTip', { family: families.find((f) => f.id === tag.space)?.label ?? tag.space, type: refTypeLabel(tag.type) });
	if (tag.kind === 'role') return t('lib.refTag.roleTip', { role: refRoleLabel(tag.role) });
	if (tag.kind === 'scope') return tag.shot ? t('lib.refTag.shotTip', { shot: clipLabel(tag.shot), start: secs(tag.shot.start), end: secs(tag.shot.start + tag.shot.dur) }) : t('lib.refTag.projectTip');
	if (tag.voice) return t('lib.refTag.voice', { name: cardName(tag.card) });
	return tag.cardKind === CHARACTERS ? t('lib.refTag.character', { name: cardName(tag.card) }) : t('lib.refTag.place', { name: cardName(tag.card) });
}

export const referenceTagText = (reference) => referenceTags(doc, reference).map(refTagLabel).join(' · ');

export function openReferences(space = 'all') {
	openDirector('references');
	ui.refSpace = space;
}

export function addReference(space = ui.refSpace === 'all' ? 'identite' : ui.refSpace) {
	const type = typesOf(space)[0];
	const r = { id: ulid(), name: t('lib.default.reference', { type: refTypeLabel(type) }), space, type, assetId: null, role: roles[space], scope: { type: 'global' } };
	act(() => doc.references.push(r));
	select('reference', r.id);
	toast(t('lib.refs.added'));
}

export function addCardImage(card, space, assetId) {
	if (!card || !assetId) return null;
	const type = typesOf(space)[0];
	const r = { id: ulid(), name: card.label || t('lib.default.reference', { type: refTypeLabel(type) }), space, type, assetId, role: roles[space], scope: { type: 'global' } };
	act(() => {
		doc.references.push(r);
		card.references = [...(card.references ?? []), r.id];
	});
	return r;
}

export function attachToRange() {
	const s = ui.selection?.kind === 'reference' ? doc.references.find((r) => r.id === ui.selection.id) : null;
	if (!s) return toast(t('lib.refs.selectOne'), 'warning');
	const [a, b] = productionRange();
	const shot = clipAt((a + b) / 2) ?? doc.clips.find((c) => overlaps(c.start, c.dur, [a, b]));
	if (!shot) return toast(t('lib.block.noRange'), 'warning');
	act(() => (s.scope = { type: 'shot', shotId: shot.id }));
	toast(t('lib.refs.attached', { name: s.name, start: secs(shot.start), end: secs(shot.start + shot.dur) }));
}

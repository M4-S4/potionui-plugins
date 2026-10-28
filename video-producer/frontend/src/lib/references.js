import { t } from '../i18n/index.svelte.js';
import { ui, doc, act, select, toast, productionRange, secs, clipAt, clipLabel, overlaps, openDirector } from './state.svelte.js';
import { ulid } from './ulid.js';
import { SOUND_SPACE, shotSound } from './sound.js';
import { refMediaKind, typesOf } from './refmedia.js';
import { CHARACTERS, cardsOf } from './bible.js';
import { DEFAULT_ROLES, FAMILY_ICONS, ROLE_KEYS, TYPE_KEYS, referenceTags } from './reftags.js';
import { effectiveEngine } from './engine.js';
import { optionFor, withProfile } from './generation.js';
import { engineChoices, engineOptionLabel } from './production.svelte.js';
import { excludedOf, setExcluded, touch } from './shots.js';
import { LIMITS, cardReception, projectReception, receptionOf, shotReception, takesReferences } from './reception.js';

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
	if (tag.kind === 'scope') return tag.shot ? t('lib.refTag.shotTip', { shot: clipLabel(tag.shot), number: String(tag.number).padStart(2, '0') }) : t('lib.refTag.projectTip');
	if (tag.voice) return t('lib.refTag.voice', { name: cardName(tag.card) });
	return tag.cardKind === CHARACTERS ? t('lib.refTag.character', { name: cardName(tag.card) }) : t('lib.refTag.place', { name: cardName(tag.card) });
}

export const referenceTagText = (reference) => referenceTags(doc, reference).map(refTagLabel).join(' · ');

export function openReferences(space = 'all') {
	openDirector('references');
	ui.refSpace = space;
}

export function addReference(space = ui.refSpace === 'all' ? 'identite' : ui.refSpace, scope = { type: 'global' }) {
	const type = typesOf(space)[0];
	const r = { id: ulid(), name: t('lib.default.reference', { type: refTypeLabel(type) }), space, type, assetId: null, role: roles[space], scope };
	act(() => doc.references.push(r));
	select('reference', r.id);
	toast(t('lib.refs.added'));
	return r;
}

export function addShotReference(clip) {
	return clip ? addReference(undefined, { type: 'shot', shotId: clip.id }) : null;
}

export function engineOf(clip, source = doc) {
	const engine = effectiveEngine(clip, source);
	const option = optionFor(engineChoices(), engine);
	return { ...engine, info: option ? { ...option.info, cloud: option.kind === 'cloud' || option.info.cloud } : null, label: option?.label ?? null };
}

export function engineOfTake(take) {
	const engine = { preset: take?.presetId ?? null, model: take?.modelId ?? null, profile: take?.profile ?? null };
	const option = optionFor(engineChoices(), engine);
	return { ...engine, info: option ? { ...option.info, cloud: option.kind === 'cloud' || option.info.cloud } : null, label: option?.label ?? null };
}

function tracksFor(source) {
	return (clip) => {
		const engine = engineOf(clip, source);
		return engine.info && takesReferences(engine.profile) ? (shotSound(source, clip, engine.info, engine.profile)?.lanes.length ?? 0) : 0;
	};
}

export const reception = (reference, source = doc) => receptionOf(reference, source, (clip) => engineOf(clip, source), tracksFor(source));
export const shotReceptionFor = (clip) => shotReception(doc, clip, engineOf(clip), tracksFor(doc)(clip));
export const takeReceptionFor = (clip, take) => shotReception(doc, clip, engineOfTake(take));
export const shotReceptionIn = (source, clip) => shotReception(source, clip, engineOf(clip, source), tracksFor(source)(clip));
export const projectReceptionFor = () => projectReception(doc, (clip) => engineOf(clip), tracksFor(doc));
export const cardReceptionFor = (kind, card) => cardReception(doc, kind, card, (clip) => engineOf(clip), tracksFor(doc));

export const engineTitle = (engine) => withProfile(engine?.label ?? engineOptionLabel(engine?.preset ?? null, engine?.model ?? null), engine?.profile ?? '');

const GOT = { image: () => t('panels.director.refs.got.image'), video: () => t('panels.director.refs.got.video'), audio: () => t('panels.director.refs.got.audio') };
const NOT = { image: () => t('panels.director.refs.not.image'), video: () => t('panels.director.refs.not.video'), audio: () => t('panels.director.refs.not.audio') };

export function receptionVerdict(status, kind, profile = '') {
	const media = Object.hasOwn(GOT, kind) ? kind : 'image';
	if (status === 'sent') return { text: GOT[media](), tone: 'text-success', ok: true };
	if (status === 'mixed') return { text: t('panels.director.refs.mixed'), tone: 'text-success', ok: true };
	if (status === 'ignored') return { text: NOT[media](), tone: 'text-fg-subtle', ok: false };
	if (status === 'trimmed') return { text: t('panels.director.refs.trimmed', { limit: LIMITS[media] }), tone: 'text-warning', ok: false };
	if (status === 'missing') return { text: t('panels.director.refs.missing'), tone: 'text-warning', ok: false };
	if (status === 'excluded') return { text: t('panels.director.refs.left'), tone: 'text-fg-subtle', ok: false };
	if (status === 'not_cast') return { text: t('panels.director.refs.notCast'), tone: 'text-fg-subtle', ok: false };
	if (status === 'blocked') return { text: t('panels.director.refs.blocked', { profile }), tone: 'text-warning', ok: false };
	return { text: t('panels.director.refs.unknown'), tone: 'text-fg-subtle', ok: false };
}

export function setReferenceShot(reference, shotId) {
	if (!reference) return;
	const scope = shotId ? { type: 'shot', shotId } : { type: 'global' };
	if (reference.scope?.type === scope.type && reference.scope?.shotId === scope.shotId) return;
	act(() => (reference.scope = scope));
}

export function linkReferenceCard(reference, kind, cardId) {
	if (!reference) return;
	act(() => {
		for (const card of cardsOf(doc, kind)) {
			const linked = (card.references ?? []).includes(reference.id);
			if (card.id === cardId && !linked) card.references = [...(card.references ?? []), reference.id];
			else if (card.id !== cardId && linked) card.references = card.references.filter((id) => id !== reference.id);
		}
	});
}

export function setSent(clip, referenceId, sent) {
	const excluded = excludedOf(clip);
	if (!clip || sent !== excluded.includes(referenceId)) return;
	act(() => {
		setExcluded(clip, sent ? excluded.filter((id) => id !== referenceId) : [...excluded, referenceId]);
		touch(clip);
	});
}

export function startImage(clip) {
	if (clip) ui.modal = { type: 'shot', id: clip.id, focus: 'keyframes' };
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

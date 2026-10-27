import { t } from '../i18n/index.svelte.js';
import { doc, act, toast, undo } from './state.svelte.js';
import { takeById } from './takes.svelte.js';
import { FRAMINGS, formatValue, framingOf, resolutionValue } from './formats.js';
import { engineSize, formatChange } from './framing.js';

const UNDO_HOLD = 8000;

export function setFormat(value) {
	const next = formatValue(value);
	if (next === doc.aspect) return;
	act(() => (doc.aspect = next));
	const counts = formatChange(doc.clips, takeById, doc);
	const parts = [counts.crop ? t('project.format.cropped', { count: counts.crop }) : '', counts.bars ? t('project.format.bars', { count: counts.bars }) : ''].filter(Boolean);
	const text = parts.length ? t('project.format.changedTakes', { format: next, takes: parts.join(', ') }) : t('project.format.changed', { format: next });
	toast(text, 'info', { label: t('shell.toast.undo'), run: undo }, UNDO_HOLD);
}

export function formatGroupText(id) {
	if (id === 'cinema') return t('project.format.group.cinema');
	if (id === 'screen') return t('project.format.group.screen');
	if (id === 'social') return t('project.format.group.social');
	return t('project.format.group.custom');
}

export function formatNameText(id) {
	if (id === '2.39:1') return t('project.format.name.scope');
	if (id === '2:1') return t('project.format.name.univisium');
	if (id === '1.85:1') return t('project.format.name.flat');
	if (id === '16:9') return t('project.format.name.hd');
	if (id === '4:3') return t('project.format.name.classic');
	if (id === '1:1') return t('project.format.name.square');
	if (id === '4:5') return t('project.format.name.portrait');
	if (id === '9:16') return t('project.format.name.vertical');
	return '';
}

export function setResolution(value) {
	const next = resolutionValue(value);
	if (next !== doc.resolution) act(() => (doc.resolution = next));
}

export function setFraming(mode) {
	if (FRAMINGS.includes(mode) && mode !== framingOf(doc)) act(() => (doc.framing = mode));
}

export function setEngineSize(presetId, quality, value) {
	if (presetId) act(() => engineSize(doc.engine, presetId, quality, value));
}

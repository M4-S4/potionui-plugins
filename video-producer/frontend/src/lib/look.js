import { t } from '../i18n/index.svelte.js';
import { filterOf, lookSteps } from './grade.js';

export const colorPresets = {
	Original: { exposure: 0, contrast: 100, saturation: 100, temperature: 0 },
	'Lumière dorée': { exposure: 0.2, contrast: 105, saturation: 112, temperature: 35 },
	'Matin froid': { exposure: 0, contrast: 98, saturation: 90, temperature: -35 },
	'Film 35 mm': { exposure: -0.1, contrast: 112, saturation: 92, temperature: 12 },
	'Nuit bleue': { exposure: -0.6, contrast: 110, saturation: 80, temperature: -50 },
	Doux: { exposure: 0.15, contrast: 88, saturation: 95, temperature: 5 }
};

export function colorPresetLabel(name) {
	if (name === 'Original') return t('lib.colorPreset.original');
	if (name === 'Lumière dorée') return t('lib.colorPreset.golden');
	if (name === 'Matin froid') return t('lib.colorPreset.coldMorning');
	if (name === 'Film 35 mm') return t('lib.colorPreset.film35');
	if (name === 'Nuit bleue') return t('lib.colorPreset.blueNight');
	if (name === 'Doux') return t('lib.colorPreset.soft');
	if (name === 'Raccord') return t('lib.colorPreset.match');
	return name;
}

export function clipFilter(clip) {
	return filterOf(lookSteps(clip));
}

export function fadeOpacity(item, time) {
	const local = time - item.start;
	let o = 1;
	if (item.fadeIn > 0) o = Math.min(o, local / item.fadeIn);
	if (item.fadeOut > 0) o = Math.min(o, (item.dur - local) / item.fadeOut);
	return Math.max(0, Math.min(1, o));
}

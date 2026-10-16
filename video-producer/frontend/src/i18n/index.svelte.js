import enShell from './en/shell.json';
import enCommands from './en/commands.json';
import enLib from './en/lib.json';
import enPanels from './en/panels.json';
import enStoryboard from './en/storyboard.json';
import enViewer from './en/viewer.json';
import enTimeline from './en/timeline.json';
import enReferences from './en/references.json';
import enScene from './en/scene.json';
import enInspector from './en/inspector.json';
import enProduction from './en/production.json';
import enMixer from './en/mixer.json';
import enModals from './en/modals.json';
import enLibrary from './en/library.json';
import enStarter from './en/starter.json';
import frShell from './fr/shell.json';
import frCommands from './fr/commands.json';
import frLib from './fr/lib.json';
import frPanels from './fr/panels.json';
import frStoryboard from './fr/storyboard.json';
import frViewer from './fr/viewer.json';
import frTimeline from './fr/timeline.json';
import frReferences from './fr/references.json';
import frScene from './fr/scene.json';
import frInspector from './fr/inspector.json';
import frProduction from './fr/production.json';
import frMixer from './fr/mixer.json';
import frModals from './fr/modals.json';
import frLibrary from './fr/library.json';
import frStarter from './fr/starter.json';
import {
	DEFAULT_LOCALE,
	LOCALES,
	detectLocale,
	formatBytes as bytesIn,
	formatDate as dateIn,
	formatDuration as durationIn,
	formatNumber as numberIn,
	formatTimecode,
	hasKey,
	mergeDomains,
	normalizeLocale,
	translate
} from './core.js';

const DICTIONARIES = {
	en: mergeDomains({
		shell: enShell,
		commands: enCommands,
		lib: enLib,
		panels: enPanels,
		storyboard: enStoryboard,
		viewer: enViewer,
		timeline: enTimeline,
		references: enReferences,
		scene: enScene,
		inspector: enInspector,
		production: enProduction,
		mixer: enMixer,
		modals: enModals,
		library: enLibrary,
		starter: enStarter
	}),
	fr: mergeDomains({
		shell: frShell,
		commands: frCommands,
		lib: frLib,
		panels: frPanels,
		storyboard: frStoryboard,
		viewer: frViewer,
		timeline: frTimeline,
		references: frReferences,
		scene: frScene,
		inspector: frInspector,
		production: frProduction,
		mixer: frMixer,
		modals: frModals,
		library: frLibrary,
		starter: frStarter
	})
};
const reported = new Set();

let current = $state(DEFAULT_LOCALE);

function reportMissing(key, locale, fellBack) {
	if (process.env.NODE_ENV === 'production') return;
	const id = `${locale}:${key}`;
	if (reported.has(id)) return;
	reported.add(id);
	console.warn(
		fellBack
			? `[video-producer] missing "${key}" in ${locale}, using en`
			: `[video-producer] unknown translation key "${key}"`
	);
}

export { LOCALES, detectLocale, formatTimecode };

export function getLocale() {
	return current;
}

export function setLocale(value) {
	const next = normalizeLocale(value);
	if (next) current = next;
	return current;
}

export function t(key, params) {
	return translate(DICTIONARIES, current, key, params, reportMissing);
}

export function has(key) {
	return hasKey(DICTIONARIES, current, key);
}

export function formatNumber(value, options) {
	return numberIn(current, value, options);
}

export function formatDate(value, options) {
	return dateIn(current, value, options);
}

export function formatTime(value) {
	return dateIn(current, value, { timeStyle: 'short' });
}

export function formatDuration(seconds) {
	return durationIn(current, seconds);
}

export function formatBytes(bytes) {
	return bytesIn(current, bytes);
}

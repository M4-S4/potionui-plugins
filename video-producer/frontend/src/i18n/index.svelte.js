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
import enProject from './en/project.json';
import frProject from './fr/project.json';
import enGeneration from './en/generation.json';
import frGeneration from './fr/generation.json';
import enAssistant from './en/assistant.json';
import frAssistant from './fr/assistant.json';
import enExports from './en/exports.json';
import frExports from './fr/exports.json';
import enKeyframes from './en/keyframes.json';
import frKeyframes from './fr/keyframes.json';
import {
	DEFAULT_LOCALE,
	LOCALES,
	detectLocale,
	formatBytes as bytesIn,
	formatDate as dateIn,
	formatDuration as durationIn,
	formatNumber as numberIn,
	formatRelative as relativeIn,
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
		starter: enStarter,
		project: enProject,
		generation: enGeneration,
		assistant: enAssistant,
		exports: enExports,
		keyframes: enKeyframes
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
		starter: frStarter,
		project: frProject,
		generation: frGeneration,
		assistant: frAssistant,
		exports: frExports,
		keyframes: frKeyframes
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

const resolve = (locale) => (locale && normalizeLocale(locale)) || current;

export function t(key, params, locale) {
	return translate(DICTIONARIES, resolve(locale), key, params ?? undefined, reportMissing);
}

export function tFor(locale) {
	return (key, params) => translate(DICTIONARIES, resolve(locale), key, params ?? undefined, reportMissing);
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

export function formatRelative(value, now) {
	return relativeIn(current, value, now);
}

export function formatDuration(seconds) {
	return durationIn(current, seconds);
}

export function formatBytes(bytes) {
	return bytesIn(current, bytes);
}

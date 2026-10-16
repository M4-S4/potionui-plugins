import { getLocale, t } from '../i18n/index.svelte.js';
import { doc } from './state.svelte.js';

export const libraries = ['Intégrée', 'Personnelle', 'Projet', 'Favoris', 'Historique'];
export const categories = ['Cinéma', 'Caméra', 'Éclairage', 'Styles cinématographiques', 'Dialogue', 'Photographie', 'Son', 'Continuité', 'À éviter'];
export const profiles = ['FL2VA', 'Ref2VA', 'Hybrid AV'];

export function libraryLabel(lib) {
	if (lib === 'Intégrée') return t('library.lib.builtin');
	if (lib === 'Personnelle') return t('library.lib.personal');
	if (lib === 'Projet') return t('library.lib.project');
	if (lib === 'Favoris') return t('library.lib.favorites');
	if (lib === 'Historique') return t('library.lib.history');
	return lib;
}

export function categoryLabel(cat) {
	if (cat === 'Cinéma') return t('library.cat.cinema');
	if (cat === 'Caméra') return t('library.cat.camera');
	if (cat === 'Éclairage') return t('library.cat.lighting');
	if (cat === 'Styles cinématographiques') return t('library.cat.styles');
	if (cat === 'Dialogue') return t('library.cat.dialogue');
	if (cat === 'Photographie') return t('library.cat.photo');
	if (cat === 'Son') return t('library.cat.sound');
	if (cat === 'Continuité') return t('library.cat.continuity');
	if (cat === 'À éviter') return t('library.cat.avoid');
	return cat;
}

const builtin = {
	t1: () => [t('library.tpl.t1.name'), t('library.tpl.t1.description'), t('library.tpl.t1.keywords'), t('library.tpl.t1.text')],
	t2: () => [t('library.tpl.t2.name'), t('library.tpl.t2.description'), t('library.tpl.t2.keywords'), t('library.tpl.t2.text')],
	t3: () => [t('library.tpl.t3.name'), t('library.tpl.t3.description'), t('library.tpl.t3.keywords'), t('library.tpl.t3.text')],
	t4: () => [t('library.tpl.t4.name'), t('library.tpl.t4.description'), t('library.tpl.t4.keywords'), t('library.tpl.t4.text')],
	t5: () => [t('library.tpl.t5.name'), t('library.tpl.t5.description'), t('library.tpl.t5.keywords'), t('library.tpl.t5.text')],
	t6: () => [t('library.tpl.t6.name'), t('library.tpl.t6.description'), t('library.tpl.t6.keywords'), t('library.tpl.t6.text')],
	t7: () => [t('library.tpl.t7.name'), t('library.tpl.t7.description'), t('library.tpl.t7.keywords'), t('library.tpl.t7.text')],
	t8: () => [t('library.tpl.t8.name'), t('library.tpl.t8.description'), t('library.tpl.t8.keywords'), t('library.tpl.t8.text')],
	t9: () => [t('library.tpl.t9.name'), t('library.tpl.t9.description'), t('library.tpl.t9.keywords'), t('library.tpl.t9.text')],
	t10: () => [t('library.tpl.t10.name'), t('library.tpl.t10.description'), t('library.tpl.t10.keywords'), t('library.tpl.t10.text')],
	t11: () => [t('library.tpl.t11.name'), t('library.tpl.t11.description'), t('library.tpl.t11.keywords'), t('library.tpl.t11.text')],
	t12: () => [t('library.tpl.t12.name'), t('library.tpl.t12.description'), t('library.tpl.t12.keywords'), t('library.tpl.t12.text')],
	t13: () => [t('library.tpl.t13.name'), t('library.tpl.t13.description'), t('library.tpl.t13.keywords'), t('library.tpl.t13.text')],
	t14: () => [t('library.tpl.t14.name'), t('library.tpl.t14.description'), t('library.tpl.t14.keywords'), t('library.tpl.t14.text')],
	t15: () => [t('library.tpl.t15.name'), t('library.tpl.t15.description'), t('library.tpl.t15.keywords'), t('library.tpl.t15.text')],
	t16: () => [t('library.tpl.t16.name'), t('library.tpl.t16.description'), t('library.tpl.t16.keywords'), t('library.tpl.t16.text')],
	t17: () => [t('library.tpl.t17.name'), t('library.tpl.t17.description'), t('library.tpl.t17.keywords'), t('library.tpl.t17.text')],
	t18: () => [t('library.tpl.t18.name'), t('library.tpl.t18.description'), t('library.tpl.t18.keywords'), t('library.tpl.t18.text')],
	t19: () => [t('library.tpl.t19.name'), t('library.tpl.t19.description'), t('library.tpl.t19.keywords'), t('library.tpl.t19.text')],
	t20: () => [t('library.tpl.t20.name'), t('library.tpl.t20.description'), t('library.tpl.t20.keywords'), t('library.tpl.t20.text')],
	t21: () => [t('library.tpl.t21.name'), t('library.tpl.t21.description'), t('library.tpl.t21.keywords'), t('library.tpl.t21.text')],
	t22: () => [t('library.tpl.t22.name'), t('library.tpl.t22.description'), t('library.tpl.t22.keywords'), t('library.tpl.t22.text')],
	t23: () => [t('library.tpl.t23.name'), t('library.tpl.t23.description'), t('library.tpl.t23.keywords'), t('library.tpl.t23.text')],
	p1: () => [t('library.tpl.p1.name'), t('library.tpl.p1.description'), t('library.tpl.p1.keywords'), t('library.tpl.p1.text')]
};

const T = (id, lib, cat, profiles, extra = {}) => ({ id, lib, cat, profiles, fav: false, ...extra });

export const templates = $state([
	T('t1', 'Intégrée', 'Caméra', ['FL2VA', 'Ref2VA']),
	T('t2', 'Intégrée', 'Caméra', ['FL2VA', 'Ref2VA']),
	T('t3', 'Intégrée', 'Caméra', ['FL2VA', 'Ref2VA', 'Hybrid AV']),
	T('t4', 'Intégrée', 'Caméra', ['FL2VA']),
	T('t5', 'Intégrée', 'Éclairage', ['FL2VA', 'Ref2VA']),
	T('t6', 'Intégrée', 'Éclairage', ['Ref2VA']),
	T('t7', 'Intégrée', 'Éclairage', ['Ref2VA', 'Hybrid AV']),
	T('t8', 'Intégrée', 'Styles cinématographiques', ['Ref2VA']),
	T('t9', 'Intégrée', 'Styles cinématographiques', ['FL2VA', 'Ref2VA', 'Hybrid AV']),
	T('t10', 'Intégrée', 'Styles cinématographiques', ['FL2VA', 'Ref2VA']),
	T('t11', 'Intégrée', 'Styles cinématographiques', ['FL2VA']),
	T('t12', 'Intégrée', 'Dialogue', ['Hybrid AV']),
	T('t13', 'Intégrée', 'Dialogue', ['Hybrid AV']),
	T('t14', 'Intégrée', 'Dialogue', ['Hybrid AV', 'Ref2VA']),
	T('t15', 'Intégrée', 'Dialogue', ['Hybrid AV']),
	T('t16', 'Intégrée', 'Photographie', ['FL2VA', 'Ref2VA']),
	T('t17', 'Intégrée', 'Photographie', ['Ref2VA']),
	T('t18', 'Intégrée', 'Son', ['Hybrid AV']),
	T('t19', 'Intégrée', 'Continuité', ['FL2VA', 'Ref2VA']),
	T('t20', 'Intégrée', 'Continuité', ['Ref2VA']),
	T('t21', 'Intégrée', 'À éviter', ['FL2VA', 'Ref2VA', 'Hybrid AV']),
	T('t22', 'Intégrée', 'À éviter', ['FL2VA', 'Ref2VA', 'Hybrid AV']),
	T('t23', 'Intégrée', 'Cinéma', ['FL2VA']),
	T('p1', 'Personnelle', 'Caméra', ['FL2VA'])
]);

function fields(tpl) {
	const own = builtin[tpl.id];
	if (!own) return { name: tpl.name ?? '', description: tpl.description ?? '', keywords: tpl.keywords ?? [], text: tpl.text ?? '' };
	const [name, description, keywords, text] = own();
	return { name, description, keywords: keywords.split(/\s*,\s*/).filter(Boolean), text: localizeVars(text) };
}

export const tplName = (tpl) => fields(tpl).name;
export const tplDescription = (tpl) => fields(tpl).description;
export const tplKeywords = (tpl) => fields(tpl).keywords;
export const tplText = (tpl) => fields(tpl).text;
export const materialize = (tpl) => fields(tpl);

export const variablesList = ['subject', 'action', 'place', 'emotion', 'lens', 'light', 'duration'];

export function varToken(id) {
	if (id === 'subject') return t('library.varToken.subject');
	if (id === 'action') return t('library.varToken.action');
	if (id === 'place') return t('library.varToken.place');
	if (id === 'emotion') return t('library.varToken.emotion');
	if (id === 'lens') return t('library.varToken.lens');
	if (id === 'light') return t('library.varToken.light');
	if (id === 'duration') return t('library.varToken.duration');
	return id;
}

export function varLabel(id) {
	if (id === 'subject') return t('library.var.subject');
	if (id === 'action') return t('library.var.action');
	if (id === 'place') return t('library.var.place');
	if (id === 'emotion') return t('library.var.emotion');
	if (id === 'lens') return t('library.var.lens');
	if (id === 'light') return t('library.var.light');
	if (id === 'duration') return t('library.var.duration');
	return id;
}

const VAR = /\{([^{}]+)\}/g;

function canonical(name) {
	if (variablesList.includes(name)) return name;
	return variablesList.find((id) => varToken(id) === name) ?? name;
}

export const varName = (id) => (variablesList.includes(id) ? varToken(id) : id);
export const localizeVars = (text) => text.replace(VAR, (m, k) => (variablesList.includes(k) ? `{${varToken(k)}}` : m));
export const fillVars = (text, vars) =>
	text.replace(VAR, (m, k) => {
		const value = vars[canonical(k)];
		return value?.trim() ? value : m;
	});
export const missingVars = (text) => [...new Set([...text.matchAll(VAR)].map((m) => canonical(m[1])))];

export function defaultVars() {
	const ref = doc.references.find((r) => r.role === 'Identité' && r.type === 'Personnage');
	const subject = ref?.name ? ref.name.split(/\s+[—–-]\s+/)[0].trim() : '';
	return { subject, place: t('library.default.place'), action: '', emotion: '', lens: t('library.default.lens'), light: t('library.default.light'), duration: t('library.default.duration') };
}

export const assistantParts = {
	camera: ['dolly', 'lateral', 'arc', 'static', 'rise'],
	light: ['window', 'backlight', 'neon', 'overcast', 'morning'],
	style: ['noir', 'naturalism', 'adventure', 'film35', 'contemplative'],
	acting: ['confidence', 'tension', 'decision', 'deadpan', 'silence']
};

export function partLabel(part) {
	if (part === 'camera') return t('library.part.camera');
	if (part === 'light') return t('library.part.light');
	if (part === 'style') return t('library.part.style');
	return t('library.part.acting');
}

export function optionLabel(id) {
	if (id === 'dolly') return t('library.option.dolly');
	if (id === 'lateral') return t('library.option.lateral');
	if (id === 'arc') return t('library.option.arc');
	if (id === 'static') return t('library.option.static');
	if (id === 'rise') return t('library.option.rise');
	if (id === 'window') return t('library.option.window');
	if (id === 'backlight') return t('library.option.backlight');
	if (id === 'neon') return t('library.option.neon');
	if (id === 'overcast') return t('library.option.overcast');
	if (id === 'morning') return t('library.option.morning');
	if (id === 'noir') return t('library.option.noir');
	if (id === 'naturalism') return t('library.option.naturalism');
	if (id === 'adventure') return t('library.option.adventure');
	if (id === 'film35') return t('library.option.film35');
	if (id === 'contemplative') return t('library.option.contemplative');
	if (id === 'confidence') return t('library.option.confidence');
	if (id === 'tension') return t('library.option.tension');
	if (id === 'decision') return t('library.option.decision');
	if (id === 'deadpan') return t('library.option.deadpan');
	if (id === 'silence') return t('library.option.silence');
	return id ?? '';
}

const PREPOSITIONS = {
	fr: /^(sous|sur|dans|au|aux|à|après|entre|vers|devant|derrière|face|près)\s/i,
	en: /^(in|on|at|under|over|inside|into|onto|near|by|behind|beside|between|across|along|through|toward|towards|around|above|below|before|after|facing)\s/i
};

export function composePrompt(parts, vars, profile, cameraLocked) {
	const locale = getLocale();
	const lower = (s) => s.toLocaleLowerCase(locale);
	const subject = vars.subject || `{${varToken('subject')}}`;
	const place = vars.place || `{${varToken('place')}}`;
	const where = (PREPOSITIONS[locale] ?? PREPOSITIONS.en).test(place) ? place : t('library.compose.inPlace', { place });
	const bits = {
		camera: parts.camera && !cameraLocked ? t('library.compose.cameraOn', { camera: lower(parts.camera), subject }) : '',
		light: parts.light ? lower(parts.light) : '',
		style: parts.style ? t('library.compose.style', { style: lower(parts.style) }) : '',
		acting: parts.acting
			? vars.emotion
				? t('library.compose.actingEmotion', { acting: lower(parts.acting), emotion: vars.emotion })
				: t('library.compose.acting', { acting: lower(parts.acting) })
			: ''
	};
	const action = t('library.compose.action', { subject, action: vars.action || `{${varToken('action')}}` });
	let order;
	if (profile === 'FL2VA') order = [t('library.compose.fl2va', { action, where }), bits.camera, bits.light, bits.style, bits.acting, t('library.compose.fl2vaEnd')];
	else if (profile === 'Ref2VA') order = [t('library.compose.ref2va', { action, where }), t('library.compose.ref2vaIdentity'), bits.light, bits.style, bits.camera, bits.acting];
	else order = [t('library.compose.hybrid', { action }), bits.acting, t('library.compose.hybridSync'), bits.camera, bits.light, bits.style];
	const s = order.filter(Boolean).join(', ');
	return s.charAt(0).toLocaleUpperCase(locale) + s.slice(1) + '.';
}

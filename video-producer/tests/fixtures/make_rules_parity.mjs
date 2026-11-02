import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileRules, conflictIds, namesCamera } from '../../frontend/src/lib/rules.js';

const here = dirname(fileURLToPath(import.meta.url));
const rulesPath = join(here, '..', '..', 'frontend', 'src', 'lib', 'rules.json');
const shared = JSON.parse(readFileSync(rulesPath, 'utf-8'));
const rules = compileRules(shared);

const sorted = (value) => {
	if (Array.isArray(value)) return value.map(sorted);
	if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sorted(value[key])]));
	return value;
};

const vocabulary = {
	en: {
		global: ['no neon', 'No Neons', 'without neon', 'no neonlight', 'no on-screen text', 'no text', 'without text', 'natural colors', 'Natural Colours', 'natural colourss', 'steady camera', 'stable camera', 'slow', 'slowly', 'Slow motion', 'a bright palette', 'NO NEON', 'no  neon', 'no\nneon', 'text', 'context', 'néon', 'the neon is off'],
		local: ['neon', 'Neon sign', 'neons', 'neonlight', 'néon', 'éneon', '_neon', '9neon', 'text', 'context', 'texts', 'subtitle', 'subtitles', 'Logo', 'logos', 'sublogo', 'monochrome', 'black and white', 'black-and-white', 'fluo', 'fluorescent', 'handheld', 'shaky camera', 'fast', 'faster', 'rapid', 'rapidly', 'frantic', 'dolly', 'pan', 'panning', 'panorama', 'orbit', 'zoom', 'crane', 'tracking shot', 'static shot', 'fly-over', 'flyover', 'lateral move', 'camera arc', 'fluid movement', 'travelling', 'NEON', 'Pan.', '(pan)', 'span', 'pan-left']
	},
	fr: {
		global: ['aucun néon', 'aucun neon', 'pas de néon', 'sans néon', 'aucun texte', 'sans texte', 'couleurs naturelles', 'caméra stable', 'camera stable', 'lente', 'lentement', 'plan lent', 'Caméra Stable', 'AUCUN NÉON', 'néon', 'texte', 'un ciel clair'],
		local: ['néon', 'NÉON', 'neon', 'texte', 'textes', 'contexte', 'sous-titre', 'sous-titres', 'logo', 'monochrome', 'noir et blanc', 'fluo', 'caméra à l’épaule', 'caméra tremblée', 'camera a l’épaule', 'rapide', 'rapidement', 'frénétique', 'travelling', 'survol', 'panoramique', 'orbite', 'arc de cam', 'dolly', 'zoom', 'élévation', 'ÉLÉVATION', 'plan fixe', 'mouvement fluide', 'déplacement latéral', 'sous-texte', 'le texte.']
	}
};

const fillers = {
	en: ['The rider', 'wide shot', 'under the rain', 'at dusk', 'on the bridge', ''],
	fr: ['Le cavalier', 'plan large', 'sous la pluie', 'à la tombée du jour', 'sur le pont', '']
};
const separators = [' ', ', ', '. ', '\n', ' and ', ' — '];

function random(seed) {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

const pick = (next, list) => list[Math.floor(next() * list.length)];

function sentence(next, parts, extra) {
	const count = 1 + Math.floor(next() * 3);
	const chosen = Array.from({ length: count }, () => pick(next, parts));
	if (extra) chosen.splice(Math.floor(next() * (chosen.length + 1)), 0, pick(next, extra));
	return chosen.filter(Boolean).reduce((text, part, index) => (index === 0 ? part : text + pick(next, separators) + part), '');
}

const ROWS = 400;
const rows = [];
for (const [language, words] of Object.entries(vocabulary)) {
	const next = random(language === 'en' ? 20261017 : 17102026);
	for (let index = 0; index < ROWS; index += 1) {
		const global = sentence(next, words.global);
		const prompt = sentence(next, words.local, fillers[language]);
		rows.push({ language, global, prompt, conflicts: conflictIds(rules, language, global, prompt), camera: namesCamera(rules, language, prompt) });
	}
}

const out = { rulesSha256: createHash('sha256').update(JSON.stringify(sorted(shared))).digest('hex'), rows };
writeFileSync(join(here, 'rules_parity.json'), JSON.stringify(out) + '\n');
const hits = rows.filter((row) => row.conflicts.length).length;
const moves = rows.filter((row) => row.camera).length;
console.log(`${rows.length} rows, ${hits} with a conflict, ${moves} naming a camera move`);

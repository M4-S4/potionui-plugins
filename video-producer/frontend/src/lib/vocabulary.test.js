import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf-8');
const json = (locale, domain) => JSON.parse(read(`../i18n/${locale}/${domain}.json`));
const DOMAINS = ['generation', 'panels', 'storyboard', 'inspector', 'commands', 'shell', 'lib', 'modals', 'production'];

test('vocabulary: the mark of a take is Retenue / Selected, the quality stays Brouillon | Final, and the final quality pass is Rendu final / Final render', () => {
	const fr = { generation: json('fr', 'generation'), panels: json('fr', 'panels'), lib: json('fr', 'lib'), storyboard: json('fr', 'storyboard'), commands: json('fr', 'commands') };
	const en = { generation: json('en', 'generation'), panels: json('en', 'panels'), lib: json('en', 'lib'), storyboard: json('en', 'storyboard'), commands: json('en', 'commands') };
	assert.equal(fr.generation['label.final'], 'Retenue');
	assert.equal(fr.generation['card.finalShort'], 'Retenue');
	assert.equal(fr.generation['labels.group.final'], 'Retenue');
	assert.equal(fr.panels['director.review.filter.final'], 'Retenues');
	assert.match(fr.panels['director.sum.review'], /Retenues \{final\}$/);
	assert.equal(fr.panels['director.review.finals.other'], '{count} plans avec une prise retenue sur {total}');
	assert.equal(fr.lib['stage.draft'], 'Brouillon');
	assert.equal(fr.lib['stage.final'], 'Final');
	assert.equal(fr.generation['card.qualityFinal'], 'Qualité finale');
	assert.equal(fr.generation['finalPass.button'], 'Rendu final');
	assert.equal(fr.generation['finalPass.count'], '{done}/{total}');
	for (const key of ['finalPass.tipReady', 'finalPass.tipMissing', 'finalPass.tipRunning']) assert.match(fr.generation[key], /prise retenue est rendue en qualité finale/, key);
	assert.equal(fr.generation['finalPass.start.other'], 'Lancer le rendu final de {count} plans');
	assert.equal(fr.storyboard['primary.draft'], 'Rendu final…');
	assert.equal(fr.commands['cmd.final-pass'], 'Rendu final du film…');
	assert.equal(en.generation['label.final'], 'Selected');
	assert.equal(en.generation['card.finalShort'], 'Selected');
	assert.equal(en.panels['director.review.filter.final'], 'Selected');
	assert.match(en.panels['director.sum.review'], /Selected \{final\}$/);
	assert.equal(en.lib['stage.final'], 'Final');
	assert.equal(en.generation['finalPass.button'], 'Final render');
	assert.match(en.generation['finalPass.tipReady'], /selected take is rendered at final quality/);
	assert.equal(en.storyboard['primary.draft'], 'Final render…');
	assert.equal(en.commands['cmd.final-pass'], 'Final render of the film…');
});

test('vocabulary: no French text calls a take Finale, the pass Film final or Passer en final; no English text says Final film, Make final or Final take', () => {
	for (const domain of DOMAINS) {
		const fr = Object.entries(json('fr', domain)).filter(([, text]) => /\bFinales?\b|Film final|Passer (?:en|le film en|la prise en) final|prise Finale/.test(text));
		assert.deepEqual(fr, [], `fr/${domain}`);
		const en = Object.entries(json('en', domain)).filter(([, text]) => /Final film|Make (?:take |the film |\{count\} shots? )?final\b|Final take\b/.test(text));
		assert.deepEqual(en, [], `en/${domain}`);
	}
});

test('vocabulary: a take card shows the quality, the duration, the engine and the mark first, and keeps the profile, the size, the seed and the backend under Take details', () => {
	const card = read('../components/takes/TakeCard.svelte');
	const quality = card.indexOf('{qualityText()}');
	const engine = card.indexOf('data-take-engine>{engineName}</div>');
	const mark = card.indexOf('{t(`generation.label.${label}`)}');
	const details = card.indexOf('<details class="text-fg-subtle" data-take-details>');
	assert.ok(quality > 0 && quality < engine && engine < mark && mark < details);
	const inside = card.slice(details, card.indexOf('</details>'));
	assert.match(inside, /\{t\('generation\.card\.technical'\)\}<\/summary>/);
	assert.match(inside, /onclick=\{\(e\) => e\.stopPropagation\(\)\}/);
	for (const part of ['{modeText()}', '{resolution}', "t('generation.card.seed'", '{backendText}']) assert.ok(inside.includes(part), part);
	assert.doesNotMatch(card.slice(0, details), /modeText\(\)\}|\{resolution\}|card\.seed|\{backendText\}<\/div>/);
	assert.match(card, /const backendText = \$derived\(take\.backendId \? backendName\(take\.backendId\) : ''\);/);
	for (const locale of ['en', 'fr']) assert.ok(json(locale, 'generation')['card.technical'], locale);
});

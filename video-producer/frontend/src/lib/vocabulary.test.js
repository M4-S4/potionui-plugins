import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { clean, renderComponent, textOf } from './svelte-harness.js';
import enGeneration from '../i18n/en/generation.json' with { type: 'json' };
import frGeneration from '../i18n/fr/generation.json' with { type: 'json' };
import enPanels from '../i18n/en/panels.json' with { type: 'json' };
import frPanels from '../i18n/fr/panels.json' with { type: 'json' };
import enStoryboard from '../i18n/en/storyboard.json' with { type: 'json' };
import frStoryboard from '../i18n/fr/storyboard.json' with { type: 'json' };
import enInspector from '../i18n/en/inspector.json' with { type: 'json' };
import frInspector from '../i18n/fr/inspector.json' with { type: 'json' };
import enCommands from '../i18n/en/commands.json' with { type: 'json' };
import frCommands from '../i18n/fr/commands.json' with { type: 'json' };
import enShell from '../i18n/en/shell.json' with { type: 'json' };
import frShell from '../i18n/fr/shell.json' with { type: 'json' };
import enLib from '../i18n/en/lib.json' with { type: 'json' };
import frLib from '../i18n/fr/lib.json' with { type: 'json' };
import enModals from '../i18n/en/modals.json' with { type: 'json' };
import frModals from '../i18n/fr/modals.json' with { type: 'json' };
import enProduction from '../i18n/en/production.json' with { type: 'json' };
import frProduction from '../i18n/fr/production.json' with { type: 'json' };

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const TAKE_CARD = new URL('../components/takes/TakeCard.svelte', import.meta.url).href;
const WAN = '01KX47WANVIDEO0000000000TV';
const fr = { generation: frGeneration, panels: frPanels, storyboard: frStoryboard, inspector: frInspector, commands: frCommands, shell: frShell, lib: frLib, modals: frModals, production: frProduction };
const en = { generation: enGeneration, panels: enPanels, storyboard: enStoryboard, inspector: enInspector, commands: enCommands, shell: enShell, lib: enLib, modals: enModals, production: enProduction };

after(() => dispose());

test('vocabulary: the mark of a take is Retenue / Selected, the quality stays Brouillon | Final, and the final quality pass is Rendu final / Final render', () => {
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

test('vocabulary: no French text calls a take Finale or prise finale, the pass Film final or Passer en final; no English text says Final film, Make final or Final take, whatever the case', () => {
	for (const domain of Object.keys(fr)) {
		const french = Object.entries(fr[domain]).filter(([, text]) => /\bFinales?\b/.test(text) || /prises? finales?|film final|passer (?:en|le film en|la prise en) final/i.test(text));
		assert.deepEqual(french, [], `fr/${domain}`);
		const english = Object.entries(en[domain]).filter(([, text]) => /Final film|Make (?:take |the film |\{count\} shots? )?final\b|Final takes?\b/i.test(text));
		assert.deepEqual(english, [], `en/${domain}`);
	}
});

test('vocabulary: a take card shows the quality, the duration, the engine and the mark first, and keeps the profile, the size, the seed and the backend under Take details', async () => {
	project.id = 'p1';
	ui.me = { engines: [{ id: 'native', kind: 'local', name: 'Studio GPU' }], presets: [{ id: WAN, name: 'Wan 2.2', video: true, cloud: false, profiles: ['FL2VA'] }] };
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'draft', take: null }];
	const take = { id: 'ta', shotId: 's1', status: 'done', label: 'candidate', quality: 'draft', variant: 'A', url: '/a.mp4', durationS: 4, width: 832, height: 480, seed: 4242, directorMode: 'i2v', profile: 'FL2VA', presetId: WAN, backendId: 'native', generationId: 'g-1', createdAt: '2026-10-29T10:00:00Z' };
	setTakes('p1', [take]);
	const html = clean(await renderComponent(TAKE_CARD, { take, clip: doc.clips[0] }));
	const at = (needle) => {
		const index = html.indexOf(needle);
		assert.ok(index >= 0, needle);
		return index;
	};
	const quality = at(`>${t('generation.card.qualityDraft')}<`);
	const engine = at('data-take-engine="">Wan 2.2</div>');
	const mark = at(`>${t('generation.label.candidate')}</span>`);
	const details = at('data-take-details="">');
	assert.ok(quality < engine && engine < mark && mark < details);
	const inside = html.slice(details, html.indexOf('</details>'));
	assert.match(inside, new RegExp(`<summary>${t('generation.card.technical')}</summary>`));
	for (const part of [`FL2VA · ${t('generation.mode.i2v')}`, '832×480', t('generation.card.seed', { seed: '4242' }), 'Studio GPU']) assert.ok(textOf(inside).includes(part), part);
	const before = textOf(html.slice(0, details));
	for (const part of [t('generation.mode.i2v'), '832×480', '4242', 'Studio GPU']) assert.ok(!before.includes(part), part);
	assert.equal(fr.lib['toast.useTakeFinal'], '« {shot} » utilise la prise en qualité finale {variant}');
	assert.equal(en.lib['toast.useTakeFinal'], '“{shot}” uses final-quality take {variant}');
	assert.equal(en.generation['finalPass.state.ready'], 'To render');
	assert.equal(en.generation['finalPass.runningTitle'], 'Final renders in progress');
	assert.equal(fr.generation['finalPass.runningTitle'], 'Rendus finaux en cours');
});

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';

const { doc, dispose } = await import('./state.svelte.js');
const { project } = await import('./project.svelte.js');
const { setTakes } = await import('./takes.svelte.js');
const { lookState } = await import('./looks.svelte.js');
const { normalizeLooks } = await import('./looks.js');

const REVIEW_TAKE = new URL('../components/director/ReviewTake.svelte', import.meta.url).href;
const QUICK_EDIT = new URL('../components/storyboard/ShotQuickEdit.svelte', import.meta.url).href;

const draft = { id: 'td', shotId: 's1', status: 'done', label: 'draft', quality: 'draft', variant: 'A', url: '/d.mp4', createdAt: '2026-10-29T10:00:00Z' };
const final = { id: 'tf', shotId: 's1', status: 'done', label: 'final', quality: 'final', variant: 'A', url: '/f.mp4', parentTakeId: 'td', createdAt: '2026-10-29T10:00:01Z' };

function scene(looks) {
	project.id = 'p1';
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'draft', take: 'tf', cast: { characters: ['c1', 'c2'] } }];
	doc.bible = { characters: [{ id: 'c1', label: 'Visual tag', text: '', references: [], props: '' }, { id: 'c2', label: 'Visual tag', text: '', references: [], props: '' }], places: [] };
	setTakes('p1', [draft, final]);
	lookState.projectId = 'p1';
	lookState.data = normalizeLooks({ embedder: { available: true }, ...looks });
}

after(() => dispose());

test('review: a final take not measured yet, whose draft is, shows the score of its draft without breaking the panel', async () => {
	scene({ takes: [{ take_id: 'td', status: 'done', cards: [{ card_id: 'c1', label: 'Ana', status: 'done', score: 0.9 }] }], finals: [{ take_id: 'tf', parent_id: 'td', status: 'done', score: 0.95 }] });

	const html = await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: final });

	assert.match(html, /data-take-looks/);
	assert.match(html, /data-look-final/);
	assert.doesNotMatch(html, /data-take-look=/);
	assert.match(textOf(html), /95 %/);
});

test('review: a measured take lists one line per card, with its score', async () => {
	scene({ takes: [{ take_id: 'td', status: 'done', cards: [{ card_id: 'c1', label: 'Ana', status: 'done', score: 0.9 }, { card_id: 'c2', label: 'Bar', status: 'done', score: 0.4 }] }] });

	const html = await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: draft });

	assert.equal((html.match(/data-take-look="done"/g) ?? []).length, 2);
	assert.match(textOf(html), /Ana 90 %/);
	assert.match(textOf(html), /Bar 40 %/);
});

test('review: a take without any look and without a measured draft has no look section', async () => {
	scene({});

	const html = await renderComponent(REVIEW_TAKE, { clip: doc.clips[0], take: final });

	assert.doesNotMatch(html, /data-take-looks/);
});

test('quick edit: two cast cards that share a label give two chips', async () => {
	scene({});

	const html = await renderComponent(QUICK_EDIT, { clip: doc.clips[0] });

	assert.equal((textOf(html).match(/Visual tag/g) ?? []).length, 2);
	assert.ok(hostUis(html, 'IconButton').length >= 2);
});

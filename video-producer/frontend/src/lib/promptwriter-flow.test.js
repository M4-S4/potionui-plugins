import { test, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { hostUis, renderComponent, textOf } from './svelte-harness.js';

const { doc, ui, dispose } = await import('./state.svelte.js');
const { project, bindClient } = await import('./project.svelte.js');
const { createWriter, forgetWriterStatus, parkWriter, writerFor, parkedShots } = await import('./promptwriter.svelte.js');
const { t } = await import('../i18n/index.svelte.js');

const BUTTON = new URL('../components/shots/WritePromptButton.svelte', import.meta.url).href;
const PANEL = new URL('../components/shots/WritePromptPanel.svelte', import.meta.url).href;
const SHOT_EDITOR = new URL('../components/modals/ShotEditor.svelte', import.meta.url).href;
const READY = { available: true, vision: true, name: 'Qwen3-VL', code: null, message: null };
const OPTION = { preset: 'MiniMax-H3-12GB', model: null };
const settle = async () => {
	for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
};

after(() => dispose());
beforeEach(() => forgetWriterStatus());

function fakeClient({ status = READY, answer = null } = {}) {
	const calls = { status: 0, writes: [] };
	const client = {
		async promptWriter() {
			calls.status += 1;
			return typeof status === 'function' ? status() : { ok: true, data: status };
		},
		async writePrompt(projectId, shotId, body, signal) {
			calls.writes.push({ projectId, shotId, body, signal });
			if (answer) return answer(signal);
			return { ok: true, data: { text: 'The fisherman lights his lantern.', name: 'Qwen3-VL', images: 2, imagesSkipped: 0 } };
		}
	};
	return { client, calls };
}

const aborting = (signal) => new Promise((resolve) => signal.addEventListener('abort', () => resolve({ ok: false, error: { status: 0, code: 'aborted', message: '', data: null } })));

async function asked(client, request = 'the lantern', options = {}) {
	const writer = createWriter({ client: () => client, ...options });
	await writer.check();
	writer.open();
	writer.edit(request);
	return writer;
}

test('the status is asked once a minute, and a failed check reads as no writer', async () => {
	const { client, calls } = fakeClient();
	const writer = createWriter({ client: () => client });
	assert.equal(writer.status, null);
	await writer.check();
	assert.deepEqual(writer.status, READY);
	await createWriter({ client: () => client }).check();
	assert.equal(calls.status, 1);
	await writer.check({ force: true });
	assert.equal(calls.status, 2);
	forgetWriterStatus();
	const down = fakeClient({ status: () => ({ ok: false, error: { status: 503, code: 'unavailable', message: 'Down.' } }) });
	const blind = createWriter({ client: () => down.client });
	await blind.check();
	assert.deepEqual([blind.status.available, blind.status.code, blind.status.message], [false, 'unavailable', 'Down.']);
	assert.equal(blind.ready(), false);
});

test('writing sends the request for the shot, shows the proposal, and accept then undo give back the prompt of before', async () => {
	const { client, calls } = fakeClient();
	const writer = await asked(client);
	const source = { clips: [{ id: 's1' }] };
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: source });
	assert.equal(calls.writes.length, 1);
	assert.deepEqual([calls.writes[0].projectId, calls.writes[0].shotId], ['p1', 's1']);
	assert.deepEqual(calls.writes[0].body, { request: 'the lantern', preset_id: 'MiniMax-H3-12GB', model_id: null, doc: source });
	assert.equal(writer.state.phase, 'proposed');
	const placed = writer.accept('My own words.');
	assert.equal(placed, 'The fisherman lights his lantern.');
	assert.equal(writer.undoable(placed), true);
	assert.equal(writer.undo('Edited after.'), null);
	assert.equal(writer.undo(placed), 'My own words.');
	assert.equal(writer.undo(placed), null);
});

test('without a request, a model or a project nothing is sent', async () => {
	const { client, calls } = fakeClient();
	const writer = await asked(client, '  ');
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	writer.edit('the lantern');
	await writer.write({ projectId: null, shotId: 's1', option: OPTION, doc: {} });
	await writer.write({ projectId: 'p1', shotId: 's1', option: null, doc: {} });
	forgetWriterStatus();
	const none = fakeClient({ status: { available: false, vision: false, name: null, code: 'no_llm', message: 'None.' } });
	const off = await asked(none.client);
	await off.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	assert.equal(calls.writes.length + none.calls.writes.length, 0);
});

test('cancel stops the wait and aborts the request, and its late answer is dropped', async () => {
	const { client, calls } = fakeClient({ answer: aborting });
	const writer = await asked(client);
	const pending = writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	assert.equal(writer.state.phase, 'writing');
	assert.equal(writer.busy, true);
	writer.cancel();
	await pending;
	assert.equal(calls.writes[0].signal.aborted, true);
	assert.deepEqual([writer.state.phase, writer.state.error, writer.state.proposal], ['open', null, null]);
});

test('a writing past the time limit fails with its own message and the request can be sent again', async () => {
	const { client, calls } = fakeClient({ answer: aborting });
	const writer = await asked(client, 'the lantern', { timeout: 5 });
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	assert.equal(calls.writes[0].signal.aborted, true);
	assert.deepEqual([writer.state.phase, writer.state.error.code], ['failed', 'write_timeout']);
	assert.equal(writer.ready(), true);
});

test('a refusal of the core is shown with its code', async () => {
	const { client } = fakeClient({ answer: async () => ({ ok: false, error: { status: 422, code: 'vision_not_supported', message: 'Cannot see.', data: null } }) });
	const writer = await asked(client);
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	assert.deepEqual([writer.state.phase, writer.state.error.code], ['failed', 'vision_not_supported']);
	const html = await renderComponent(PANEL, { writer, text: '', frames: 2 });
	assert.match(html, /data-writer-error="vision_not_supported"/);
	assert.ok(textOf(html).includes(t('modals.shot.writer.error.vision_not_supported')));
	assert.ok(hostUis(html, 'Button').some((props) => props.disabled === false));
});

test('the button is grey with its reason before any click, and opens the panel once a model is there', async () => {
	const none = fakeClient({ status: { available: false, vision: false, name: null, code: 'no_llm', message: 'None.' } });
	const off = createWriter({ client: () => none.client });
	await off.check();
	const grey = await renderComponent(BUTTON, { writer: off });
	assert.match(grey, /data-write-prompt="off"/);
	assert.match(grey, /aria-disabled="true"/);
	assert.equal(hostUis(grey, 'Tooltip')[0].text, t('modals.shot.writer.error.no_llm'));
	off.open();
	assert.equal(off.state.phase, 'open');
	forgetWriterStatus();
	const { client } = fakeClient();
	const on = createWriter({ client: () => client });
	await on.check();
	const ready = await renderComponent(BUTTON, { writer: on });
	assert.match(ready, /data-write-prompt="on"/);
	assert.equal(hostUis(ready, 'Tooltip')[0].text, t('modals.shot.writer.tip', { name: 'Qwen3-VL' }));
	assert.match(await renderComponent(BUTTON, { writer: on, saved: false }), /data-write-prompt="off"/);
	assert.equal(hostUis(await renderComponent(BUTTON, { writer: on, engine: false }), 'Tooltip')[0].text, t('modals.shot.composedNone'));
});

test('the panel shows the wait with a cancel, then the proposal with accept and discard, then the undo line', async () => {
	let release;
	const { client } = fakeClient({ answer: () => new Promise((resolve) => (release = resolve)) });
	const writer = await asked(client);
	assert.doesNotMatch(await renderComponent(PANEL, { writer: createWriter({ client: () => client }), text: '' }), /data-writer/);
	const opened = await renderComponent(PANEL, { writer, text: 'Old.', frames: 2 });
	assert.match(opened, /data-writer="open"/);
	assert.ok(textOf(opened).includes(t('modals.shot.writer.sourcesFrames', { name: 'Qwen3-VL', count: 2 })));
	const pending = writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	const waiting = await renderComponent(PANEL, { writer, text: 'Old.', frames: 2 });
	assert.match(waiting, /data-writer-waiting/);
	assert.ok(hostUis(waiting, 'Button').length === 1);
	assert.ok(textOf(waiting).includes(t('modals.shot.writer.cancel')));
	release({ ok: true, data: { text: 'The fisherman lights his lantern.', name: 'Qwen3-VL', images: 2, imagesSkipped: 0 } });
	await pending;
	const proposed = await renderComponent(PANEL, { writer, text: 'Old.', frames: 2 });
	assert.match(proposed, /data-writer-proposal[^>]*>The fisherman lights his lantern\.</);
	assert.ok(textOf(proposed).includes(t('modals.shot.writer.accept')));
	assert.ok(textOf(proposed).includes(t('modals.shot.writer.reject')));
	assert.ok(textOf(proposed).includes(t('modals.shot.writer.replaces')));
	const placed = writer.accept('Old.');
	const applied = await renderComponent(PANEL, { writer, text: placed, frames: 2 });
	assert.match(applied, /data-writer-applied/);
	assert.ok(textOf(applied).includes(t('modals.shot.writer.undo')));
	assert.doesNotMatch(await renderComponent(PANEL, { writer, text: `${placed} More.`, frames: 2 }), /data-writer-applied/);
});

test('a model that cannot see says the shot images are not sent', async () => {
	const { client } = fakeClient({ status: { ...READY, vision: false } });
	const writer = await asked(client);
	const html = await renderComponent(PANEL, { writer, text: '', frames: 2 });
	assert.match(html, /data-writer-blind/);
	assert.ok(textOf(html).includes(t('modals.shot.writer.blind', { name: 'Qwen3-VL', count: 2 })));
	assert.ok(textOf(html).includes(t('modals.shot.writer.sources', { name: 'Qwen3-VL' })));
});

test('the shot editor carries the button beside the prompt library and the card words of a shot that sets its own', async () => {
	const { client } = fakeClient();
	bindClient(client);
	project.id = 'p1';
	ui.me = null;
	doc.assets = [];
	doc.clips = [{ id: 's1', start: 0, dur: 4, label: 'One', stage: 'todo' }];
	doc.prompts = [{ id: 'p1', shotId: 's1', start: 0, dur: 4, strength: 75, text: 'A quay.' }];
	doc.frames = [];
	const plain = await renderComponent(SHOT_EDITOR, { id: 's1' });
	assert.match(plain, /data-write-prompt=/);
	assert.ok(textOf(plain).includes(t('modals.shot.writer.button')));
	assert.doesNotMatch(plain, /data-shot-card-words/);
	doc.clips[0].cardWords = 'label';
	const own = await renderComponent(SHOT_EDITOR, { id: 's1' });
	assert.match(own, /data-shot-card-words="label"/);
	assert.ok(textOf(own).includes(t('modals.shot.asProject', { value: t('project.cardWords.card') })));
	assert.ok(textOf(own).includes(t('modals.shot.cardWords.unused')));
	await settle();
	delete doc.clips[0].cardWords;
	project.id = null;
});

test('a proposal that dropped a reference video tag says which one before it is used', async () => {
	const { client } = fakeClient({ answer: async () => ({ ok: true, data: { text: 'The fisherman walks along the quay.', name: 'Qwen3-VL', images: 0, imagesSkipped: 0, lostTags: ['@vref1', '@vref2'] } }) });
	const writer = await asked(client);
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	const html = await renderComponent(PANEL, { writer, text: 'She walks past @vref1 and @vref2.', frames: 0 });
	assert.match(html, /data-writer-lost-tags="@vref1 @vref2"/);
	assert.ok(textOf(html).includes(t('modals.shot.writer.lostTags', { tags: '@vref1, @vref2', count: 2 })));
	const kept = createWriter({ client: () => fakeClient().client });
	await kept.check();
	kept.open();
	kept.edit('x');
	await kept.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	assert.doesNotMatch(await renderComponent(PANEL, { writer: kept, text: '', frames: 0 }), /data-writer-lost-tags/);
});

test('a writing still held by the server after a cancel is asked again, and given up after a few tries', async () => {
	const busy = { ok: false, error: { status: 409, code: 'write_busy', message: 'Busy.', data: null } };
	let answers = [busy, busy, { ok: true, data: { text: 'The fisherman lights his lantern.', name: 'Qwen3-VL', images: 0, imagesSkipped: 0, lostTags: [] } }];
	const { client, calls } = fakeClient({ answer: async () => answers.shift() });
	const writer = await asked(client, 'the lantern', { busyDelay: 1 });
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	assert.equal(calls.writes.length, 3);
	assert.equal(writer.state.phase, 'proposed');
	forgetWriterStatus();
	const held = fakeClient({ answer: async () => busy });
	const stuck = await asked(held.client, 'the lantern', { busyDelay: 1 });
	await stuck.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	assert.equal(held.calls.writes.length, 5);
	assert.deepEqual([stuck.state.phase, stuck.state.error.code], ['failed', 'write_busy']);
	const html = await renderComponent(PANEL, { writer: stuck, text: '', frames: 0 });
	assert.ok(textOf(html).includes(t('modals.shot.writer.error.write_busy')));
});

test('a proposal written without a key frame that could not be prepared says so', async () => {
	const { client } = fakeClient({ answer: async () => ({ ok: true, data: { text: 'The fisherman walks along the quay.', name: 'Qwen3-VL', images: 1, imagesSkipped: 0, imagesDropped: 1, lostTags: [] } }) });
	const writer = await asked(client);
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	const html = await renderComponent(PANEL, { writer, text: '', frames: 2 });
	assert.match(html, /data-writer-dropped="1"/);
	assert.ok(textOf(html).includes(t('modals.shot.writer.dropped', { count: 1 })));
});

test('a trip to the prompt library keeps the writing of the shot, its proposal and its undo, and only for that shot', async () => {
	let release;
	const { client, calls } = fakeClient({ answer: (signal) => new Promise((resolve) => (release = resolve)) });
	const writer = writerFor('s1', false, { client: () => client });
	await writer.check();
	writer.open();
	writer.edit('the lantern');
	const pending = writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	parkWriter('s1', writer);
	const back = writerFor('s1', true, { client: () => client });
	assert.equal(back, writer);
	assert.equal(calls.writes[0].signal.aborted, false);
	release({ ok: true, data: { text: 'The fisherman lights his lantern.', name: 'Qwen3-VL', images: 0, imagesSkipped: 0, lostTags: [] } });
	await pending;
	assert.equal(back.state.phase, 'proposed');
	const placed = back.accept('Old.');
	parkWriter('s1', back);
	const again = writerFor('s1', true, { client: () => client });
	assert.equal(again.undo(placed), 'Old.');
	parkWriter('s1', again);
	const fresh = writerFor('s1', false, { client: () => client });
	assert.notEqual(fresh, again);
	assert.equal(fresh.undoable(placed), false);
	parkWriter('s2', fresh);
	assert.notEqual(writerFor('s1', true, { client: () => client }), fresh);
	const source = readFileSync(new URL('../components/modals/ShotEditor.svelte', import.meta.url), 'utf8');
	assert.match(source, /parkWriter\(id, writer\)/);
	assert.match(source, /writerFor\(id, Boolean\(kept\)\)/);
	assert.match(source, /if \(!parking\) writer\.cancel\(\)/);
});

test('leaving a parked writing for good stops it', async () => {
	const { client, calls } = fakeClient({ answer: aborting });
	const writer = writerFor('s3', false, { client: () => client });
	await writer.check();
	writer.open();
	writer.edit('the lantern');
	const pending = writer.write({ projectId: 'p1', shotId: 's3', option: OPTION, doc: {} });
	parkWriter('s3', writer);
	writerFor('s3', false, { client: () => client });
	await pending;
	assert.equal(calls.writes[0].signal.aborted, true);
	assert.equal(writer.state.phase, 'open');
});

test('a proposal that keeps a tag in angle brackets says which one before it is used', async () => {
	const { client } = fakeClient({ answer: async () => ({ ok: true, data: { text: '<Subject 3> waves.', name: 'Qwen3-VL', images: 0, imagesSkipped: 0, imagesDropped: 0, lostTags: [], keptTags: ['<Subject 3>'] } }) });
	const writer = await asked(client);
	await writer.write({ projectId: 'p1', shotId: 's1', option: OPTION, doc: {} });
	const html = await renderComponent(PANEL, { writer, text: '', frames: 0 });
	assert.match(html, /data-writer-kept-tags="(&lt;|<)Subject 3(&gt;|>)"/);
	const shown = textOf(html).replaceAll('&lt;', '<').replaceAll('&gt;', '>');
	assert.ok(shown.includes(t('modals.shot.writer.keptTags', { tags: '<Subject 3>', count: 1 })));
});

async function parkedWriting(shotId) {
	const { client, calls } = fakeClient({ answer: aborting });
	const writer = writerFor(shotId, false, { client: () => client });
	await writer.check();
	writer.open();
	writer.edit('the lantern');
	const pending = writer.write({ projectId: 'p1', shotId, option: OPTION, doc: {} });
	parkWriter(shotId, writer);
	return { writer, calls, pending };
}

test('a parked writing lives while its library is open, and stops when another window opens instead of the shot', async () => {
	ui.modal = null;
	await settle();
	const kept = await parkedWriting('s5');
	ui.modal = { type: 'library', target: { kind: 'shot', id: 's5', returnTo: { type: 'shot', id: 's5', draft: {}, baseline: {} } } };
	await settle();
	assert.equal(kept.calls.writes[0].signal.aborted, false);
	assert.deepEqual(parkedShots(), ['s5']);
	ui.modal = { type: 'export' };
	await settle();
	await kept.pending;
	assert.equal(kept.calls.writes[0].signal.aborted, true);
	assert.deepEqual(parkedShots(), []);
	assert.notEqual(writerFor('s5', true), kept.writer);
	ui.modal = null;
	await settle();
});

test('a parked writing stops when a project loads and when the page goes away', async () => {
	ui.modal = null;
	await settle();
	const { openProject } = await import('./project.svelte.js');
	const { dispose } = await import('./state.svelte.js');
	const loaded = await parkedWriting('s6');
	ui.modal = { type: 'library', target: { kind: 'shot', id: 's6', returnTo: { type: 'shot', id: 's6', draft: {}, baseline: {} } } };
	await settle();
	bindClient({
		async getProject(id) {
			return { ok: true, data: { id, name: 'Other', version: 1, doc: { name: 'Other' }, createdAt: null, updatedAt: null } };
		},
		async saveLastProject() {
			return { ok: true, data: null };
		}
	});
	await openProject('other-project');
	await loaded.pending;
	assert.equal(loaded.calls.writes[0].signal.aborted, true);
	assert.deepEqual(parkedShots(), []);
	const left = await parkedWriting('s7');
	ui.modal = { type: 'library', target: { kind: 'shot', id: 's7', returnTo: { type: 'shot', id: 's7', draft: {}, baseline: {} } } };
	await settle();
	dispose();
	await settle();
	await left.pending;
	assert.equal(left.calls.writes[0].signal.aborted, true);
	assert.deepEqual(parkedShots(), []);
});

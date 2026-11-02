import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

const hooks = `
import { readFile } from 'node:fs/promises';
import { compileModule } from ${JSON.stringify(import.meta.resolve('svelte/compiler'))};
export async function load(url, context, next) {
	if (url.endsWith('.svelte.js')) return { format: 'module', shortCircuit: true, source: compileModule(await readFile(new URL(url), 'utf8'), { generate: 'client', filename: url }).js.code };
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast() {} } } };
globalThis.document = { body: {}, querySelector: () => null };

const { doc, ui, act, replaceDoc, dispose } = await import('./state.svelte.js');
const { IS_MAC, handleKeydown } = await import('./commands.js');
const { emptyDoc } = await import('./starter.js');

after(() => {
	dispose();
	delete globalThis.window;
	delete globalThis.document;
});

function press(key, { shift = false, target = undefined } = {}) {
	let prevented = false;
	handleKeydown({ key: shift ? key.toUpperCase() : key, code: `Key${key.toUpperCase()}`, ctrlKey: !IS_MAC, metaKey: IS_MAC, altKey: false, shiftKey: shift, repeat: false, target, preventDefault: () => (prevented = true) }, null);
	return prevented;
}

function renamed() {
	replaceDoc({ ...emptyDoc((key) => key), name: 'Before' });
	Object.assign(ui, { modal: null, paletteOpen: false, hostModal: false });
	act(() => (doc.name = 'After'));
	assert.ok(press('z'));
	assert.equal(doc.name, 'Before');
}

test('shortcuts flow: Ctrl+Y redoes what Ctrl+Z undid, like Ctrl+Shift+Z', () => {
	renamed();
	assert.ok(press('y'));
	assert.equal(doc.name, 'After');

	renamed();
	assert.ok(press('z', { shift: true }));
	assert.equal(doc.name, 'After');
});

test('shortcuts flow: Ctrl+Y leaves a text field and an open window to the browser', () => {
	renamed();
	assert.equal(press('y', { target: { tagName: 'INPUT' } }), false);
	assert.equal(doc.name, 'Before');
	ui.modal = { type: 'about' };
	assert.equal(press('y'), false);
	assert.equal(doc.name, 'Before');
	ui.modal = null;
	assert.ok(press('y'));
	assert.equal(doc.name, 'After');
});

test('shortcuts flow: Escape closes a take preview first, then the monitor of the Review, then a seam', () => {
	const escape = () => handleKeydown({ key: 'Escape', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, target: undefined, preventDefault() {} }, null);
	Object.assign(ui, { modal: null, paletteOpen: false, hostModal: false, menuOpen: null, preview: { kind: 'result', id: 't1' }, compare: null, reviewMonitor: true, seamCompare: 's2' });
	escape();
	assert.equal(ui.preview, null);
	assert.equal(ui.reviewMonitor, true);
	escape();
	assert.equal(ui.reviewMonitor, false);
	assert.equal(ui.seamCompare, 's2');
	escape();
	assert.equal(ui.seamCompare, null);
});

test('shortcuts flow: Ctrl+Z undoes the drag of a slider that keeps the focus, and stays with a text field', () => {
	replaceDoc({ ...emptyDoc((key) => key), name: 'Before' });
	Object.assign(ui, { modal: null, paletteOpen: false, hostModal: false });
	act(() => (doc.name = 'After'));
	assert.equal(press('z', { target: { tagName: 'INPUT', type: 'text' } }), false);
	assert.equal(doc.name, 'After');
	assert.ok(press('z', { target: { tagName: 'INPUT', type: 'range' } }));
	assert.equal(doc.name, 'Before');
	assert.ok(press('y', { target: { tagName: 'INPUT', type: 'range' } }));
	assert.equal(doc.name, 'After');
});

test('shortcuts flow: with the assistant panel open, Ctrl+Z still undoes on the page, other keys and a real dialog do not', () => {
	const chatOpen = (selector) => (selector.includes('ai-chat-trigger') ? [{}] : []);
	try {
		document.querySelectorAll = chatOpen;
		renamed();
		assert.ok(press('y'));
		assert.equal(doc.name, 'After');
		assert.equal(press('d'), false);
		assert.equal(press('z', { target: { tagName: 'TEXTAREA' } }), false);
		document.querySelectorAll = () => [{}];
		assert.equal(press('z'), false);
		assert.equal(doc.name, 'After');
	} finally {
		delete document.querySelectorAll;
	}
});

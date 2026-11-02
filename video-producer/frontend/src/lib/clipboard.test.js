import { test } from 'node:test';
import assert from 'node:assert/strict';
import { copyText } from './clipboard.js';

function fakeDocument({ copy = true, throws = false, dialog = false } = {}) {
	const log = [];
	const area = {
		style: {},
		attributes: {},
		value: '',
		setAttribute(name, value) {
			this.attributes[name] = value;
		},
		focus() {
			log.push('area focus');
		},
		select() {
			log.push('select');
		},
		setSelectionRange(from, to) {
			log.push(`range ${from}-${to}`);
		},
		remove() {
			log.push('remove');
		}
	};
	const host = { appendChild: (node) => log.push(node === area ? 'append area' : 'append other') };
	const active = {
		focus() {
			log.push('restore focus');
		},
		closest: (selector) => (dialog && selector.includes('dialog') ? host : null)
	};
	const doc = {
		body: { appendChild: (node) => log.push(node === area ? 'append area to body' : 'append other') },
		activeElement: active,
		createElement: (tag) => (tag === 'textarea' ? area : null),
		execCommand(command) {
			log.push(`exec ${command} of ${area.value}`);
			if (throws) throw new Error('blocked');
			return copy;
		}
	};
	return { doc, log, area };
}

test('copyText: the clipboard API when the page has it, nothing else touched', async () => {
	const written = [];
	const { doc, log } = fakeDocument();
	const nav = { clipboard: { writeText: async (text) => written.push(text) } };
	assert.equal(await copyText('un prompt', { nav, doc }), true);
	assert.deepEqual(written, ['un prompt']);
	assert.deepEqual(log, []);
});

test('copyText: without the clipboard API (an http address), a temporary text area and the copy command', async () => {
	const { doc, log, area } = fakeDocument();
	assert.equal(await copyText('un prompt', { nav: {}, doc }), true);
	assert.deepEqual(log, ['append area to body', 'area focus', 'select', 'range 0-9', 'exec copy of un prompt', 'remove', 'restore focus']);
	assert.equal(area.attributes.readonly, '');
	assert.equal(area.attributes['aria-hidden'], 'true');
	assert.equal(area.style.cssText.includes('opacity:0'), true);
});

test('copyText: the text area goes inside an open dialog so a focus trap keeps the selection', async () => {
	const { doc, log } = fakeDocument({ dialog: true });
	assert.equal(await copyText('x', { nav: undefined, doc }), true);
	assert.equal(log[0], 'append area');
});

test('copyText: a clipboard API that refuses falls back to the copy command', async () => {
	const { doc, log } = fakeDocument();
	const nav = {
		clipboard: {
			writeText: async () => {
				throw new Error('NotAllowedError');
			}
		}
	};
	assert.equal(await copyText('texte', { nav, doc }), true);
	assert.ok(log.includes('exec copy of texte'));
});

test('copyText: false when both fail, never a false success', async () => {
	assert.equal(await copyText('x', { nav: {}, doc: fakeDocument({ copy: false }).doc }), false);
	assert.equal(await copyText('x', { nav: {}, doc: fakeDocument({ throws: true }).doc }), false);
	const refusing = { clipboard: { writeText: () => Promise.reject(new Error('denied')) } };
	assert.equal(await copyText('x', { nav: refusing, doc: fakeDocument({ copy: false }).doc }), false);
	assert.equal(await copyText('x', { nav: {}, doc: undefined }), false);
	assert.equal(await copyText('x', { nav: {}, doc: { body: null } }), false);
	const noCommand = fakeDocument().doc;
	noCommand.execCommand = undefined;
	assert.equal(await copyText('x', { nav: {}, doc: noCommand }), false);
});

test('copyText: the text area is removed even when the copy command throws', async () => {
	const { doc, log } = fakeDocument({ throws: true });
	await copyText('x', { nav: {}, doc });
	assert.ok(log.includes('remove'));
	assert.ok(log.includes('restore focus'));
});

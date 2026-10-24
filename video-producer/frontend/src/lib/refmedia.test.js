import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { parse } from 'svelte/compiler';
import { SOUND_SPACE, SOUND_TYPES } from './sound.js';
import { refMediaKind, typesOf } from './refmedia.js';

const source = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');

const CHILDREN = ['fragment', 'nodes', 'consequent', 'alternate', 'body', 'fallback', 'pending', 'then', 'catch'];
const attribute = (node, name) => node.attributes?.find((a) => a.type === 'Attribute' && a.name === name);
const literal = (node, name) => {
	const value = attribute(node, name)?.value;
	return Array.isArray(value) && value.length === 1 && value[0].type === 'Text' ? value[0].data : null;
};
const drags = (node) => Boolean(attribute(node, 'draggable')) && literal(node, 'draggable') !== 'false';
const scrubs = (node) => (['audio', 'video'].includes(node.name) && Boolean(attribute(node, 'controls'))) || (node.name === 'input' && literal(node, 'type') === 'range');

function draggedControls(node, inside = false, found = []) {
	if (Array.isArray(node)) {
		for (const child of node) draggedControls(child, inside, found);
		return found;
	}
	if (!node || typeof node !== 'object') return found;
	const element = node.type === 'RegularElement';
	if (element && inside && scrubs(node)) found.push(node.name);
	for (const key of CHILDREN) if (key in node) draggedControls(node[key], inside || (element && drags(node)), found);
	return found;
}

test('typesOf: the types of each reference family, in their order, none for an unknown family', () => {
	assert.deepEqual(typesOf('identite'), ['Personnage', 'Décor', 'Objet', 'Style']);
	assert.deepEqual(typesOf('decors3d'), ['Capture 3D']);
	assert.deepEqual(typesOf('mouvement'), ['Control video', 'Trajectoire']);
	assert.deepEqual(typesOf(SOUND_SPACE), SOUND_TYPES);
	assert.deepEqual(typesOf('camera'), []);
	assert.deepEqual(typesOf(undefined), []);
});

test('refMediaKind: an image for Identity and 3D Sets, a video for Motion, a sound for Sound, by family and type', () => {
	for (const type of typesOf('identite')) assert.equal(refMediaKind('identite', type), 'image', type);
	assert.equal(refMediaKind('decors3d', 'Capture 3D'), 'image');
	assert.equal(refMediaKind('mouvement', 'Control video'), 'video');
	assert.equal(refMediaKind('mouvement', 'Trajectoire'), 'video');
	for (const type of SOUND_TYPES) assert.equal(refMediaKind(SOUND_SPACE, type), 'audio', type);
});

test('refMediaKind: a type the family does not list takes the media of the family, an unknown family none', () => {
	assert.equal(refMediaKind('mouvement', 'Caméra'), 'video');
	assert.equal(refMediaKind('identite', null), 'image');
	assert.equal(refMediaKind('camera', 'Personnage'), null);
});

test('the server sends a reference as its own media and reads its role from the family: character, setting, motion', () => {
	const director = source('../../../backend/director.py');
	assert.match(director, /ROLES_BY_SPACE = \{"identite": "character", "decors3d": "setting", "mouvement": "motion"\}/);
	assert.match(director, /"define_motion": "\{label\} is the source of the motion of \[Shot 1\]\."/);
	assert.match(source('./scene.svelte.js'), /space: 'decors3d', type: 'Capture 3D', assetId: image\.id/);
});

test('the reference editor offers the types of every family and the media its type takes', () => {
	const references = source('./references.js');
	assert.match(references, /export \{ refMediaKind, typesOf \};/);
	assert.match(references, /const type = typesOf\(space\)\[0\];/);
	const inspector = source('../components/inspector/Inspector.svelte');
	assert.match(inspector, /\{@const refKind = refMediaKind\(item\.space, item\.type\)\}/);
	assert.match(inspector, /\{#each typesOf\(item\.space\) as type \(type\)\}/);
	assert.match(inspector, /\{#if refKind === 'audio'\}/);
	assert.match(inspector, /<MediaPicker kind=\{refKind \?\? 'image'\} title=\{item\.name\} value=\{item\.assetId\}/);
	const picker = source('../components/shots/MediaPicker.svelte');
	assert.match(picker, /doc\.assets\.filter\(\(a\) => a\.kind === kind && a\.src\)/);
	assert.match(picker, /pickMedia\(kind, title, choose\)/);
	assert.match(picker, /pickLocalMedia\(kind, choose\)/);
	const board = source('../components/references/ReferenceBoard.svelte');
	assert.match(board, /\{@const thumb = assetThumb\(a\)\}/);
	assert.match(board, /\{@const kind = refMediaKind\(r\.space, r\.type\)\}/);
});

test('pages: no player or slider sits inside an element that drags, so its cursor follows the pointer instead of the drag', () => {
	const files = ['../VideoProducerPage.svelte', ...readdirSync(new URL('../components', import.meta.url), { recursive: true }).filter((f) => f.endsWith('.svelte')).map((f) => `../components/${f.replaceAll('\\', '/')}`)];
	const caught = Object.fromEntries(files.map((file) => [file, draggedControls(parse(source(file), { modern: true }).fragment)]).filter(([, found]) => found.length));

	assert.deepEqual(caught, {});
	assert.ok(files.length > 50);
	assert.deepEqual(draggedControls(parse('<li draggable="true"><audio controls></audio></li><div draggable="false"><input type="range" /></div>', { modern: true }).fragment), ['audio']);
});

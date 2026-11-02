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

globalThis.window = { __potionui: { confirm: async () => true, notifications: { toast: () => {} } } };

const { doc, dispose } = await import('./state.svelte.js');
const { anchorsOf, takeTimes } = await import('./match.svelte.js');

after(() => {
	dispose();
	delete globalThis.window;
});

test('match: a slowed shot samples the part of its take it shows, and the next shot is matched to the last frame it shows', () => {
	assert.deepEqual(takeTimes({ srcIn: 1, dur: 4 }, { srcDur: 6 }), [1.6, 3, 4.4]);
	assert.deepEqual(takeTimes({ srcIn: 1, dur: 4, speed: 0.5 }, { srcDur: 6 }), [1.3, 2, 2.7]);
	assert.deepEqual(takeTimes({ srcIn: 0, dur: 8, speed: 0.25 }, { srcDur: 6 }), [0.3, 1, 1.7]);
	doc.assets = [
		{ id: 'a1', kind: 'video', name: 'One', src: '/one.mp4', srcDur: 6 },
		{ id: 'a2', kind: 'video', name: 'Two', src: '/two.mp4', srcDur: 6 }
	];
	doc.clips = [
		{ id: 's1', assetId: 'a1', start: 0, dur: 4, srcIn: 1, speed: 0.5, label: 'One' },
		{ id: 's2', assetId: 'a2', start: 4, dur: 2, srcIn: 0, label: 'Two' }
	];
	const previous = anchorsOf(doc.clips[1]).find((anchor) => anchor.kind === 'previous');
	assert.ok(Math.abs(previous.at - 2.96) < 1e-9, `at ${previous.at}`);
});

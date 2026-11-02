import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { readFileSync } from 'node:fs';

const hooks = `
import { readFile } from 'node:fs/promises';
export async function load(url, context, next) {
	if (url.endsWith('.json')) return { format: 'module', shortCircuit: true, source: 'export default ' + (await readFile(new URL(url), 'utf8')) };
	return next(url, context);
}`;
register(`data:text/javascript,${encodeURIComponent(hooks)}`, import.meta.url);

const { FAMILIES, LIMITS, ORDER, SHEET, VIDEO_TRACKS, cardReception, familyOf, layoutOf, mediaKey, projectReception, receptionOf, shotReception, takesReferences, takesSheet, videoCap, videoFrames, videoPieces, videoRegion } = await import('./reception.js');
const { MAX_VREF_TRACKS, VREF_ROLES } = await import('./vrefs.js');
const { PROFILES } = await import('./generation.js');
const { CONDITION, audioBehavior } = await import('./sound.js');
const { effectiveEngine } = await import('./engine.js');

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const pageCopy = read('./reception.json');
const shared = read('../../../backend/reception.json');
const { engines, cases } = read('../../../tests/fixtures/reception_cases.json');
const lengths = read('../../../tests/fixtures/vref_lengths.json');
const round = (value, digits) => Math.round(value * 10 ** digits) / 10 ** digits;
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-6, `${actual} != ${expected}`);

const infoOf = (engine) => {
	const found = Object.values(engines).find((e) => e.preset === engine.preset && (e.model ?? null) === (engine.model ?? null));
	return found ? { id: found.preset, cloud: found.cloud, audioMux: found.audio_mux, profiles: found.profiles } : null;
};
const engineFor = (doc) => (clip) => {
	const engine = effectiveEngine(clip, doc);
	return { ...engine, info: infoOf(engine) };
};
const caseDoc = (name) => structuredClone(cases.find((c) => c.name.startsWith(name)).doc);
const shots = (group) => group.shots.map((shot) => shot.clip?.id ?? shot.id);

test('the page copy of reception.json is identical to the backend one', () => {
	assert.deepEqual(pageCopy, shared);
	assert.deepEqual(LIMITS, shared.limits);
});

test('the table names only engine families the page can tell apart, and a last rule for every engine', () => {
	const families = shared.layouts.flatMap((rule) => rule.families ?? []);
	assert.ok(families.every((family) => FAMILIES.includes(family)));
	assert.deepEqual(Object.keys(shared.layouts.at(-1)), ['layout']);
	assert.equal(familyOf({ id: engines.h3.preset }), 'h3');
	assert.equal(familyOf({ id: engines.cloud.preset, cloud: true }), 'cloud');
	assert.equal(familyOf({ id: engines.wan.preset }), 'other');
	assert.equal(familyOf({ id: engines.ltx.preset }), 'ltx');
	assert.equal(layoutOf('h3', 'Ref2VA'), 'refs');
	assert.equal(layoutOf('ltx', 'Ref2VA'), 'sheet');
	assert.equal(layoutOf('ltx', 'FL2VA'), 'cast');
	assert.equal(layoutOf('h3', 'Hybrid AV'), 'subjects');
	assert.equal(layoutOf('other', 'FL2VA'), 'cast');
});

test('a sound guides the engine exactly in the profiles that send the references themselves', () => {
	for (const profile of PROFILES) {
		for (const preset of [{ audioMux: true }, { audioMux: false }, { cloud: true }]) assert.equal(audioBehavior(preset, profile) === CONDITION, takesReferences(profile), `${profile} ${JSON.stringify(preset)}`);
	}
});

for (const c of cases) {
	test(`shared case: ${c.name}`, () => {
		const doc = c.doc;
		const found = {};
		for (const clip of doc.clips) {
			const shot = shotReception(doc, clip, engineFor(doc)(clip));
			if (shot.state === 'blocked') {
				found[clip.id] = { blocked: true };
				continue;
			}
			const ids = (status) => doc.references.filter((r) => shot.statuses.get(r.id) === status).map((r) => r.id);
			found[clip.id] = { layout: shot.layout, ignoredLayout: shot.ignoredLayout, sent: ids('sent'), trimmed: ids('trimmed'), mixed: ids('mixed'), excluded: ids('excluded'), notCast: ids('not_cast') };
			if (doc.vrefTracks) {
				const slots = (status) => shot.videoTracks.filter((x) => x.status === status).map((x) => x.slot);
				found[clip.id].tracks = Object.fromEntries(['sent', 'trimmed', 'short', 'missing', 'ignored', 'excluded', 'off'].map((status) => [status, slots(status)]));
				found[clip.id].windows = Object.fromEntries(shot.videoTracks.filter((x) => x.window).map((x) => [String(x.slot), x.window.map((v) => round(v, 3))]));
			}
		}
		assert.deepEqual(found, c.expected);
	});
}

test('the table orders the references, bounds the reference video tracks and names the roles and sizes the page knows', () => {
	assert.deepEqual(ORDER, ['own', 'cast', 'tracks', 'shared']);
	assert.equal(VIDEO_TRACKS.max, MAX_VREF_TRACKS);
	assert.deepEqual(Object.keys(VIDEO_TRACKS.roles), VREF_ROLES);
	assert.deepEqual(Object.values(VIDEO_TRACKS.roles), ['under', 'before']);
	assert.ok(VIDEO_TRACKS.sizes.includes(VIDEO_TRACKS.size));
	assert.equal((VIDEO_TRACKS.minFrames - VIDEO_TRACKS.head) % VIDEO_TRACKS.chunk, 0);
	assert.equal(VIDEO_TRACKS.minFrames, 56);
});

test('shared lengths: the frames a track sends for a length, its cap and its region', () => {
	for (const [seconds, frames] of lengths.frames) assert.equal(videoFrames(seconds), frames, `${seconds} s`);
	for (const [cap, seconds] of lengths.caps) close(videoCap(cap), seconds);
	for (const r of lengths.regions) {
		const [a, b] = videoRegion(r.role, r.start, r.seconds, r.cap);
		close(a, r.region[0]);
		close(b, r.region[1]);
	}
});

test('shared lengths: the parts of the items a track sends', () => {
	for (const c of lengths.pieces) {
		const { frames, pieces } = videoPieces(c.items, c.role, c.start, c.seconds, c.cap);
		assert.equal(frames, c.frames, c.name);
		assert.deepEqual(pieces.map((p) => [p.id, round(p.from, 6), round(p.to, 6)]), c.pieces.map((p) => [p.id, p.from, p.to]), c.name);
	}
});

test('shotReception: a track sends nothing to a shot whose engine is not known, and its slots come in slot order', () => {
	const doc = caseDoc('the videos of the shot go first');
	const clip = doc.clips[0];
	assert.deepEqual(shotReception(doc, clip, { preset: 'gone', profile: 'Ref2VA', info: null }).videoTracks.map((x) => [x.slot, x.status, x.window]), [
		[1, 'unknown', null],
		[2, 'unknown', null]
	]);
	assert.deepEqual(shotReception(doc, clip, engineFor(doc)(clip)).videoTracks.map((x) => [x.slot, x.frames]), [
		[1, 56],
		[2, 56]
	]);
});

test('mediaKey: only an asset the server can read has a media', () => {
	assert.equal(mediaKey({ origin: { kind: 'library', itemId: 'x' } }), 'library:x');
	assert.equal(mediaKey({ origin: { kind: 'history', generationId: 'g', fileId: 0 } }), 'history:g:0');
	assert.equal(mediaKey({ origin: { kind: 'history', generationId: 'g' } }), null);
	assert.equal(mediaKey({ src: 'data:image/png;base64,' }), null);
	assert.equal(mediaKey(null), null);
});

test('receptionOf: the shots a reference goes to, grouped by engine, profile and what they get, the exclusions last', () => {
	const doc = caseDoc('a sound is mixed');
	doc.clips[1].referenceOverrides = { exclude: ['g-rain'] };
	const rain = receptionOf(doc.references[0], doc, engineFor(doc));
	assert.deepEqual(
		rain.groups.map((g) => [g.engine?.preset ?? null, g.engine?.profile ?? null, g.status, shots(g)]),
		[
			[engines.ltx.preset, 'FL2VA', 'mixed', ['s1']],
			[engines.h3.preset, 'Ref2VA', 'sent', ['s3']],
			[engines.h3.preset, 'FL2VA', 'mixed', ['s4']],
			[engines.cloud.preset, 'FL2VA', 'ignored', ['s5']],
			[null, null, 'excluded', ['s2']]
		]
	);
	assert.deepEqual(rain.going.map((c) => c.id), ['s1', 's3', 's4', 's5']);
	assert.equal(rain.linked, null);
	const image = receptionOf(doc.references[2], doc, engineFor(doc));
	assert.equal(image.linked.card.id, 'lina');
	assert.equal(image.linked.voice, false);
	assert.deepEqual(receptionOf(doc.references[1], doc, engineFor(doc)).linked, { kind: 'characters', card: doc.bible.characters[0], voice: true });
});

test('receptionOf: a picture of a card goes to the shots that cast the card, whatever its scope, and the shots that do not cast it come last', () => {
	const doc = caseDoc('the cast chooses the pictures');
	const back = receptionOf(doc.references[1], doc, engineFor(doc));
	assert.deepEqual(
		back.groups.map((g) => [g.engine?.preset ?? null, g.engine?.profile ?? null, g.status, shots(g)]),
		[
			[engines.h3.preset, 'Ref2VA', 'sent', ['s1', 's2']],
			[engines.wan.preset, 'FL2VA', 'ignored', ['s4']]
		]
	);
	const cyclist = receptionOf(doc.references[2], doc, engineFor(doc));
	assert.deepEqual(
		cyclist.groups.map((g) => [g.engine?.preset ?? null, g.status, shots(g)]),
		[
			[engines.h3.preset, 'sent', ['s2']],
			[null, 'not_cast', ['s1', 's3', 's4']]
		]
	);
	assert.deepEqual(cyclist.going.map((c) => c.id), ['s2']);
	assert.deepEqual(cyclist.cast.map((c) => c.id), ['s2']);
});

test('receptionOf: a reference of one shot goes to that shot only, and an engine the page does not know says so', () => {
	const doc = caseDoc('Ref2VA sends');
	const own = receptionOf(doc.references[3], doc, engineFor(doc));
	assert.deepEqual(own.shots.map((s) => [s.clip.id, s.status]), [['s2', 'sent']]);
	const unknown = receptionOf(doc.references[0], doc, () => ({ preset: 'gone', model: null, profile: 'FL2VA', info: null }));
	assert.deepEqual(unknown.groups.map((g) => [g.status, shots(g)]), [['unknown', ['s1', 's2']]]);
});

test('projectReception: one line per engine and profile with what its shots get', () => {
	const doc = caseDoc('a sound is mixed');
	const groups = projectReception(doc, engineFor(doc));
	assert.deepEqual(
		groups.map((g) => [g.engine.preset, g.engine.profile, g.references, shots(g), g.counts]),
		[
			[engines.ltx.preset, 'FL2VA', false, ['s1'], { mixed: 1, ignored: 1, not_cast: 1 }],
			[engines.wan.preset, 'FL2VA', false, ['s2'], { ignored: 2, not_cast: 1 }],
			[engines.h3.preset, 'Ref2VA', true, ['s3'], { sent: 3 }],
			[engines.h3.preset, 'FL2VA', false, ['s4'], { mixed: 1, ignored: 1, not_cast: 1 }],
			[engines.cloud.preset, 'FL2VA', false, ['s5'], { ignored: 2, not_cast: 1 }]
		]
	);
	assert.deepEqual(projectReception({ clips: [] }, engineFor(doc)), []);
});

test('cardReception: the shots a card is cast in, grouped by engine and whether its pictures or its voice go', () => {
	const doc = caseDoc('a sound is mixed');
	for (const clip of doc.clips) clip.cast = { characters: clip.id === 's2' ? [] : ['lina'] };
	const lina = doc.bible.characters[0];
	const found = cardReception(doc, 'characters', lina, engineFor(doc));
	assert.deepEqual(found.references, ['g-img', 'g-voice']);
	assert.deepEqual(
		found.groups.map((g) => [g.engine.preset, g.engine.profile, g.received, shots(g)]),
		[
			[engines.ltx.preset, 'FL2VA', false, ['s1']],
			[engines.h3.preset, 'Ref2VA', true, ['s3']],
			[engines.h3.preset, 'FL2VA', false, ['s4']],
			[engines.cloud.preset, 'FL2VA', false, ['s5']]
		]
	);
	assert.deepEqual(cardReception(doc, 'places', { id: 'none', references: [] }, engineFor(doc)), { references: [], shots: [], groups: [] });
});

test('shotReception: tracks of the shot count among its sounds before the global ones', () => {
	const doc = caseDoc('a sound is mixed');
	const clip = doc.clips[2];
	assert.equal(shotReception(doc, clip, engineFor(doc)(clip), 2).statuses.get('g-voice'), 'trimmed');
	assert.equal(shotReception(doc, clip, engineFor(doc)(clip), 1).statuses.get('g-voice'), 'sent');
});

const sheetDoc = () => {
	const picture = (id) => ({ id: `a-${id}`, kind: 'image', origin: { kind: 'library', itemId: `i-${id}` } });
	const reference = (id, asset = `a-${id}`) => ({ id, assetId: asset, scope: { type: 'global' } });
	const ids = ['f1', 'f2', 'f3', 'g1', 'h1', 'k1', 'q1', 'q2'];
	return {
		assets: [...ids.map(picture), { id: 'a-gone', kind: 'image', origin: null }, { id: 'a-voice', kind: 'audio', origin: { kind: 'library', itemId: 'i-voice' } }],
		references: [...ids.map((id) => reference(id)), reference('gone', 'a-gone'), reference('voice', 'a-voice'), reference('loose')],
		bible: {
			characters: [
				{ id: 'c-f', label: 'Fisher', references: ['gone', 'f1', 'f2', 'f3'] },
				{ id: 'c-g', label: 'Girl', references: ['g1'] },
				{ id: 'c-n', label: 'Nobody', references: [] },
				{ id: 'c-h', label: 'Hal', references: ['h1'] },
				{ id: 'c-k', label: 'Kim', references: ['k1'] }
			],
			places: [{ id: 'p-q', label: 'Quay', references: ['q1', 'q2'] }]
		},
		clips: [{ id: 's1', start: 0, dur: 5, cast: { characters: ['c-f', 'c-g', 'c-n', 'c-h', 'c-k'], place: 'p-q' } }]
	};
};

test('shotReception: on LTX-2.5 in Ref2VA the cast goes on one sheet, two pictures per character for three characters, one of the place', () => {
	const doc = sheetDoc();
	const ltx = { id: engines.ltx.preset, cloud: false, audioMux: true, profiles: ['FL2VA', 'Ref2VA'] };
	assert.ok(takesSheet('ltx', 'Ref2VA') && !takesSheet('h3', 'Ref2VA') && !takesSheet('ltx', 'FL2VA'));
	assert.equal(takesReferences('Ref2VA', 'ltx'), false);
	assert.deepEqual([SHEET.characters, SHEET.images, SHEET.size, SHEET.fps], [3, 2, [768, 448], 24]);
	const shot = shotReception(doc, doc.clips[0], { preset: engines.ltx.preset, profile: 'Ref2VA', info: ltx });
	assert.equal(shot.layout, 'sheet');
	assert.deepEqual(Object.fromEntries(shot.statuses), {
		f1: 'sent', f2: 'sent', f3: 'trimmed', gone: 'missing', g1: 'sent', h1: 'sent', k1: 'trimmed', q1: 'sent', q2: 'trimmed', voice: 'mixed', loose: 'ignored'
	});
	const plain = shotReception(doc, doc.clips[0], { preset: engines.ltx.preset, profile: 'FL2VA', info: ltx });
	assert.equal(plain.layout, 'cast');
	assert.ok([...plain.statuses.values()].every((status) => ['ignored', 'mixed'].includes(status)));
});

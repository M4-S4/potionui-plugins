import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DOMAINS, mergeDomains, translate } from '../i18n/core.js';
import { EXCHANGE, MAKERS, baseName, edl, fcpxml, fileOf, labelOf, otio, seqDuration, srt, srtCues } from './exchange.js';

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, '..', '..', '..', 'tests', 'fixtures', 'exports');
const readDomain = (domain) => JSON.parse(readFileSync(join(here, '..', 'i18n', 'en', `${domain}.json`), 'utf-8'));
const dictionaries = { en: mergeDomains(Object.fromEntries(DOMAINS.map((domain) => [domain, readDomain(domain)]))) };
const en = (key, params) => translate(dictionaries, 'en', key, params);
const optionsFor = (doc) => ({ label: labelOf(doc, en('lib.default.clip')) });

function sampleDoc() {
	return {
		name: 'Dawn & <Port>',
		fps: 25,
		resolution: '1080p',
		clips: [
			{ id: 'c1', assetId: 'a1', start: 0, dur: 2, srcIn: 0.5, label: 'Ridge', stage: 'final', take: 't1' },
			{ id: 'c2', assetId: null, start: 2, dur: 1.5, srcIn: 0, label: '', stage: 'todo', take: null },
			{ id: 'c3', assetId: 'a2', start: 3.5, dur: 1, srcIn: 0, label: '', stage: 'draft', take: null }
		],
		audio: [{ id: 'u1', assetId: 'v1', lane: 'A1', start: 0.5, dur: 1.2, srcIn: 0, gain: -3 }],
		titles: [{ id: 'ti1', text: 'Dawn', sub: 'Port', start: 0, dur: 1 }],
		lanes: [{ id: 'A1', name: 'Voices', role: 'Dialogue' }],
		assets: [
			{ id: 'a1', kind: 'video', name: 'Ridge take', src: '/api/media/generations/g1/ridge%20take.mp4?x=1', srcDur: 6, generated: true, quality: 'final', resultId: 't1' },
			{ id: 'a2', kind: 'video', name: 'Hut · wide', src: null, srcDur: null, generated: true, quality: 'draft', resultId: 'r7' },
			{ id: 'v1', kind: 'audio', name: 'Line 1', src: null }
		]
	};
}

test('fileOf: the real base name of a file, the prototype name of an unknown take, null without a file', () => {
	const doc = {
		assets: [
			{ id: 'a1', src: '/api/media/uploads/My%20Clip.mp4?token=x', generated: false, name: 'My clip' },
			{ id: 'a2', src: null, generated: true, quality: 'draft', resultId: 'r9', name: 'Take' },
			{ id: 'a3', src: null, generated: false, name: 'Placeholder' },
			{ id: 'a4', src: '/api/media/generations/g1/take_0001.mp4', generated: true, quality: 'final', resultId: 't1', name: 'Take' }
		]
	};
	const label = labelOf(doc, 'Shot');
	assert.equal(fileOf(doc, { assetId: 'a1' }, label), 'My Clip.mp4');
	assert.equal(fileOf(doc, { assetId: 'a2', label: 'Dawn · wide' }, label), 'Dawn_wide_draft_r9.mov');
	assert.equal(fileOf(doc, { assetId: 'a3' }, label), null);
	assert.equal(fileOf(doc, { assetId: 'a4' }, label), 'take_0001.mp4');
	assert.equal(fileOf(doc, { assetId: null }, label), null);
	assert.equal(baseName('/a/b%ZZ.mp4#t=1'), 'b%ZZ.mp4');
	assert.equal(label({ assetId: 'a3' }), 'Placeholder');
	assert.equal(label({}), 'Shot');
});

test('formats: gaps for shots without a file, escaped names, CRLF edit list, cues in time order', () => {
	const doc = sampleDoc();
	const options = optionsFor(doc);
	assert.equal(seqDuration(doc), 4.5);
	const xml = fcpxml(doc, options);
	assert.match(xml, /<project name="Dawn &amp; &lt;Port&gt;">/);
	assert.match(xml, /<asset id="r2" name="Ridge" start="0s" duration="150\/25s" hasVideo="1" format="r1"><media-rep kind="original-media" src="file:\/\/\/Video%20Producer\/ridge%20take\.mp4"\/><\/asset>/);
	assert.match(xml, /<gap name="Shot" offset="50\/25s" start="0s" duration="38\/25s"\/>/);
	assert.match(xml, /<asset-clip ref="r3" name="Hut · wide" offset="88\/25s" start="0\/25s" duration="25\/25s"\/>/);
	const timeline = JSON.parse(otio(doc, options));
	const [video, voices] = timeline.tracks.children;
	assert.deepEqual(video.children.map((c) => c.OTIO_SCHEMA), ['Clip.2', 'Gap.1', 'Clip.2']);
	assert.equal(video.children[0].media_references.DEFAULT_MEDIA.target_url, 'ridge take.mp4');
	assert.equal(video.children[2].media_references.DEFAULT_MEDIA.target_url, 'Hut_wide_draft_r7.mov');
	assert.deepEqual(voices.children.map((c) => c.OTIO_SCHEMA), ['Gap.1', 'Clip.2']);
	assert.deepEqual(voices.children[1].media_references, { DEFAULT_MEDIA: { OTIO_SCHEMA: 'MissingReference.1' } });
	assert.equal(voices.children[1].active_media_reference_key, 'DEFAULT_MEDIA');
	const list = edl(doc, options);
	assert.ok(list.startsWith('TITLE: DAWN & <PORT>\r\nFCM: NON-DROP FRAME\r\n\r\n'));
	assert.match(list, /002 {2}BL {7}V {5}C {8}00:00:00:00 00:00:01:13 00:00:02:00 00:00:03:13\r\n\* FROM CLIP NAME: Shot\r\n\r\n/);
	assert.match(list, /\* SOURCE FILE: ridge take\.mp4\r\n/);
	assert.deepEqual(srtCues(doc).map((c) => c.text), ['Dawn\nPort']);
	assert.equal(srt(doc), '1\n00:00:00,000 --> 00:00:01,000\nDawn\nPort\n');
	assert.deepEqual(Object.keys(MAKERS), Object.keys(EXCHANGE));
});

test('text the formats cannot hold: control characters out of the XML, line breaks out of the edit list, blank lines out of a cue', () => {
	const doc = sampleDoc();
	const forged = '002  BL       V     C        00:00:00:00 00:00:01:00 00:00:00:00 00:00:01:00';
	doc.name = 'Dawn\u0001\ufffe';
	doc.clips[0].label = `Ridge\r\n${forged}`;
	doc.titles = [{ id: 'ti1', text: 'one\n\n \t\ntwo', sub: 'three\r\n', start: 0, dur: 1 }];
	const options = optionsFor(doc);
	assert.match(fcpxml(doc, options), /<project name="Dawn">/);
	const lines = edl(doc, options).split('\r\n');
	assert.equal(lines.filter((line) => /^\d{3} /.test(line)).length, 3);
	assert.ok(lines.includes(`* FROM CLIP NAME: Ridge${forged}`));
	assert.equal(srt(doc), '1\n00:00:00,000 --> 00:00:01,000\none\ntwo\nthree\n');
});

test('the four formats regenerate the backend golden files byte for byte (media=name)', () => {
	const fixture = JSON.parse(readFileSync(join(fixtures, 'reference-project.json'), 'utf-8'));
	for (const format of Object.keys(EXCHANGE)) {
		const golden = readFileSync(join(fixtures, `reference.${format}`));
		const made = Buffer.from(MAKERS[format](fixture.doc, optionsFor(fixture.doc)), 'utf-8');
		assert.equal(made.toString('utf-8'), golden.toString('utf-8'), `${format} differs from reference.${format}`);
		assert.ok(made.equals(golden), `${format} differs from reference.${format} at the byte level`);
	}
});

test('formats: a slowed shot reads the source its speed covers, with an M2 line, a time warp and a time map', () => {
	const doc = sampleDoc();
	doc.clips = [{ ...doc.clips[0], dur: 4, srcIn: 1, speed: 0.5 }];
	const options = optionsFor(doc);
	const lines = edl(doc, options).split('\r\n');
	assert.equal(lines[3], '001  VP001    V     C        00:00:01:00 00:00:03:00 00:00:00:00 00:00:04:00');
	assert.equal(lines[4], `M2   VP001          ${(doc.fps * 0.5).toFixed(1).padStart(5, '0')}                00:00:01:00`);
	const clip = JSON.parse(otio(doc, options)).tracks.children[0].children[0];
	assert.equal(clip.source_range.duration.value, 2 * doc.fps);
	assert.deepEqual(clip.effects, [{ OTIO_SCHEMA: 'LinearTimeWarp.1', name: '', effect_name: 'LinearTimeWarp', metadata: {}, time_scalar: 0.5 }]);
	assert.match(fcpxml(doc, options), new RegExp(`<timeMap><timept time="${doc.fps}/${doc.fps}s" value="${doc.fps}/${doc.fps}s" interp="linear"/><timept time="${5 * doc.fps}/${doc.fps}s" value="${3 * doc.fps}/${doc.fps}s" interp="linear"/></timeMap></asset-clip>`));
});

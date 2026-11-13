import { laneCode } from './tracks.js';
import { BOX, deliverySize, ratioOf } from './formats.js';
import { sourceSeconds, speedOf } from './cadence.js';
import { cuts, filled, moved, placement, readAt } from './dissolve.js';

const DISSOLVE_NAME = 'Cross Dissolve';
const DISSOLVE_EFFECT = 'FxPlug:4731E73A-8DAC-4113-9A30-AE85B1761265';

export const EXCHANGE = {
	fcpxml: { ext: 'fcpxml', mime: 'application/xml' },
	otio: { ext: 'otio', mime: 'application/json' },
	edl: { ext: 'edl', mime: 'text/plain' },
	srt: { ext: 'srt', mime: 'application/x-subrip' }
};

const XML_FORBIDDEN = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/g;
const esc = (s) => String(s).replace(XML_FORBIDDEN, '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const oneLine = (s) => String(s).replace(/[\r\n]/g, '');
const fold = (text) =>
	String(text)
		.split(/\r\n|\r|\n/)
		.filter((line) => !/^[ \t]*$/.test(line))
		.join('\n');
const assetOf = (doc, id) => (id ? doc.assets?.find((a) => a.id === id) : undefined);

export function seqDuration(doc) {
	const ends = [...doc.clips.map((c) => c.start + c.dur), ...doc.audio.map((c) => c.start + c.dur), ...doc.titles.map((c) => c.start + c.dur)];
	return Math.max(1, ...ends);
}

export function baseName(src) {
	const path = String(src ?? '').split(/[?#]/)[0];
	const last = path.slice(path.lastIndexOf('/') + 1);
	try {
		return decodeURIComponent(last);
	} catch {
		return last;
	}
}

export function fileOf(doc, c, label) {
	const a = assetOf(doc, c.assetId);
	if (!a) return null;
	if (a.src) return baseName(a.src) || null;
	if (a.generated) return `${label(c).replace(/[^\p{L}\p{N}]+/gu, '_')}_${a.quality}_${a.resultId}.mov`;
	return null;
}

function timing(doc) {
	const frames = (sec) => Math.round(sec * doc.fps);
	const count = (n) => `${n}/${doc.fps}s`;
	const rt = (sec) => count(frames(sec));
	const span = (start, dur) => frames(start + dur) - frames(start);
	const tcode = (sec) => {
		const f = frames(sec);
		const p = (n) => String(n).padStart(2, '0');
		const s = Math.floor(f / doc.fps);
		return [p(Math.floor(s / 3600)), p(Math.floor((s % 3600) / 60)), p(s % 60), p(f % doc.fps)].join(':');
	};
	return { frames, count, rt, span, tcode };
}

export function sequenceFrame(doc) {
	const ratio = ratioOf(doc.aspect);
	return deliverySize(ratio === null || ratio < 1 / 4 || ratio > 4 ? BOX : ratio, doc.resolution);
}

const NAMED_RATES = ['24', '25', '30', '50', '60'];

function formatName(doc) {
	const [width, height] = sequenceFrame(doc);
	const [boxWidth, boxHeight] = deliverySize(BOX, doc.resolution);
	return width === boxWidth && height === boxHeight && NAMED_RATES.includes(String(doc.fps)) ? ` name="FFVideoFormat${doc.resolution}${doc.fps}"` : '';
}

export function fcpxml(doc, { label }) {
	const { frames, count, rt, span } = timing(doc);
	const file = (c) => fileOf(doc, c, label);
	const media = doc.clips.filter(file);
	const res = sequenceFrame(doc);
	const assets = media.map(
		(c, i) =>
			`\t\t<asset id="r${i + 2}" name="${esc(label(c))}" start="0s" duration="${rt(assetOf(doc, c.assetId).srcDur ?? c.srcIn + sourceSeconds(c))}" hasVideo="1" format="r1"><media-rep kind="original-media" src="file:///Video%20Producer/${esc(encodeURI(file(c)))}"/></asset>`
	);
	const edits = cuts(doc.clips, frames);
	const places = placement(doc.clips);
	const effect = media.length + 2;
	if (edits.some((cut) => cut?.overlap)) assets.push(`\t\t<effect id="r${effect}" name="${DISSOLVE_NAME}" uid="${DISSOLVE_EFFECT}"/>`);
	const timeMap = (c, source, length) =>
		`<timeMap><timept time="${rt(source)}" value="${rt(source)}" interp="linear"/><timept time="${count(frames(source) + length)}" value="${rt(source + sourceSeconds(c, length / doc.fps))}" interp="linear"/></timeMap>`;
	const spine = doc.clips.flatMap((c, i) => {
		const cut = edits[i];
		const length = cut ? cut.end - cut.start : span(c.start, c.dur);
		const offset = cut ? count(cut.start) : rt(c.start);
		const source = Math.max(readAt(c.srcIn, places[i]?.start ?? c.start, cut ? cut.start : frames(c.start), doc.fps, speedOf(c)), 0);
		const transition = cut?.overlap ? [`\t\t\t\t\t\t<transition name="${DISSOLVE_NAME}" offset="${count(cut.start - cut.head)}" duration="${count(cut.overlap)}"><filter-video ref="r${effect}" name="${DISSOLVE_NAME}"/></transition>`] : [];
		return [
			...transition,
			file(c)
				? `\t\t\t\t\t\t<asset-clip ref="r${media.indexOf(c) + 2}" name="${esc(label(c))}" offset="${offset}" start="${rt(source)}" duration="${count(length)}"${speedOf(c) === 1 ? '/>' : `>${timeMap(c, source, length)}</asset-clip>`}`
				: `\t\t\t\t\t\t<gap name="${esc(label(c))}" offset="${offset}" start="0s" duration="${count(length)}"/>`
		];
	});
	return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
	<resources>
		<format id="r1"${formatName(doc)} frameDuration="1/${doc.fps}s" width="${res[0]}" height="${res[1]}"/>
${assets.join('\n')}
	</resources>
	<library>
		<event name="Video Producer">
			<project name="${esc(doc.name)}">
				<sequence format="r1" duration="${rt(seqDuration(doc))}" tcStart="0s">
					<spine>
${spine.join('\n')}
					</spine>
				</sequence>
			</project>
		</event>
	</library>
</fcpxml>
`;
}

export function otio(doc, { label }) {
	const { frames, span } = timing(doc);
	const rate = doc.fps;
	const file = (c) => fileOf(doc, c, label);
	const range = (start, length) => ({ OTIO_SCHEMA: 'TimeRange.1', start_time: { OTIO_SCHEMA: 'RationalTime.1', rate, value: start }, duration: { OTIO_SCHEMA: 'RationalTime.1', rate, value: length } });
	const reference = (url) => ({ DEFAULT_MEDIA: url ? { OTIO_SCHEMA: 'ExternalReference.1', target_url: url } : { OTIO_SCHEMA: 'MissingReference.1' } });
	const edits = cuts(doc.clips, frames);
	const places = placement(doc.clips);
	const time = (value) => ({ OTIO_SCHEMA: 'RationalTime.1', rate, value });
	const item = (c, source, length) =>
		file(c)
			? {
					OTIO_SCHEMA: 'Clip.2',
					name: label(c),
					source_range: range(frames(source), length),
					media_references: reference(file(c)),
					active_media_reference_key: 'DEFAULT_MEDIA',
					metadata: { video_producer: { stage: c.stage, take: c.take } },
					...(speedOf(c) === 1 ? {} : { effects: [{ OTIO_SCHEMA: 'LinearTimeWarp.1', name: '', effect_name: 'LinearTimeWarp', metadata: {}, time_scalar: speedOf(c) }] })
				}
			: { OTIO_SCHEMA: 'Gap.1', name: label(c), source_range: range(0, length) };
	const video = doc.clips.flatMap((c, i) => {
		const cut = edits[i];
		const length = cut ? cut.end - cut.start : span(c.start, c.dur);
		const source = Math.max(readAt(c.srcIn, places[i]?.start ?? c.start, cut ? cut.start : frames(c.start), doc.fps, speedOf(c)), 0);
		const transition = cut?.overlap ? [{ OTIO_SCHEMA: 'Transition.1', name: DISSOLVE_NAME, metadata: {}, transition_type: 'SMPTE_Dissolve', in_offset: time(cut.head), out_offset: time(cut.overlap - cut.head) }] : [];
		return [...transition, item(c, source, length)];
	});
	const lanes = doc.lanes.map((l) => {
		const items = doc.audio.filter((a) => a.lane === l.id).sort((a, b) => a.start - b.start);
		const children = [];
		let at = 0;
		for (const a of items) {
			if (a.start > at) children.push({ OTIO_SCHEMA: 'Gap.1', source_range: range(0, frames(a.start) - frames(at)) });
			children.push({
				OTIO_SCHEMA: 'Clip.2',
				name: assetOf(doc, a.assetId)?.name,
				source_range: range(frames(a.srcIn), span(a.start, a.dur)),
				media_references: reference(file(a)),
				active_media_reference_key: 'DEFAULT_MEDIA',
				metadata: { video_producer: { role: l.role, gain_db: a.gain } }
			});
			at = a.start + a.dur;
		}
		return { OTIO_SCHEMA: 'Track.1', name: `${laneCode(doc.lanes, l.id)} · ${l.name}`, kind: 'Audio', children };
	});
	return JSON.stringify(
		{ OTIO_SCHEMA: 'Timeline.1', name: doc.name, global_start_time: null, tracks: { OTIO_SCHEMA: 'Stack.1', name: 'tracks', children: [{ OTIO_SCHEMA: 'Track.1', name: 'V1', kind: 'Video', children: video }, ...lanes] } },
		null,
		2
	);
}

export function edl(doc, { label }) {
	const { tcode, frames } = timing(doc);
	const lines = [`TITLE: ${oneLine(doc.name).toUpperCase()}`, 'FCM: NON-DROP FRAME', ''];
	const joins = [...cuts(doc.clips, frames).map((cut) => cut?.overlap ?? 0), 0];
	const places = placement(doc.clips);
	const fills = filled(places);
	const onFrame = (at) => !+(frames(at) / doc.fps - at).toFixed(6);
	const sourceAt = (srcIn, start, at, speed) => Math.max(onFrame(at) ? srcIn + (at - start) * speed : readAt(srcIn, start, frames(at), doc.fps, speed), 0);
	doc.clips.forEach((c, i) => {
		const file = fileOf(doc, c, label);
		const n = String(i + 1).padStart(3, '0');
		const reel = file ? `VP${n}` : 'BL';
		const speed = speedOf(c);
		const recordIn = moved(c, places[i]) ? places[i].start : c.start;
		const recordOut = joins[i + 1] > 0 ? doc.clips[i + 1].start : fills[i] ? places.slice(i + 1).find(Boolean).start : places[i] ? places[i].end : c.start + c.dur;
		const plain = !(joins[i + 1] > 0) && !fills[i] && !moved(c, places[i]);
		const sourceIn = sourceAt(c.srcIn, recordIn, recordIn, speed);
		const sourceOut = speed === 1 ? (frames(sourceIn) + frames(recordOut) - frames(recordIn)) / doc.fps : plain && onFrame(recordOut) ? c.srcIn + c.dur * speed : sourceAt(c.srcIn, recordIn, recordOut, speed);
		let cut = 'C       ';
		if (joins[i] > 0) {
			const before = doc.clips[i - 1];
			const held = sourceAt(before.srcIn, before.start, c.start, speedOf(before));
			const beforeReel = fileOf(doc, before, label) ? `VP${String(i).padStart(3, '0')}` : 'BL';
			lines.push(`${n}  ${beforeReel.padEnd(8)} V     C        ${tcode(held)} ${tcode(held)} ${tcode(c.start)} ${tcode(c.start)}`);
			cut = `D    ${String(joins[i]).padStart(3, '0')}`;
		}
		lines.push(`${n}  ${reel.padEnd(8)} V     ${cut} ${tcode(sourceIn)} ${tcode(sourceOut)} ${tcode(recordIn)} ${tcode(recordOut)}`);
		if (speed !== 1) lines.push(`M2   ${reel.padEnd(8)}       ${(doc.fps * speed).toFixed(1).padStart(5, '0')}                ${tcode(sourceIn)}`);
		if (joins[i] > 0) lines.push(`* FROM CLIP NAME: ${oneLine(label(doc.clips[i - 1]))}`, `* TO CLIP NAME: ${oneLine(label(c))}`);
		else lines.push(`* FROM CLIP NAME: ${oneLine(label(c))}`);
		if (file) lines.push(`* SOURCE FILE: ${oneLine(file)}`);
		lines.push('');
	});
	return lines.join('\r\n');
}

export function srtCues(doc) {
	return doc.titles.map((title) => ({ start: title.start, end: title.start + title.dur, text: [title.text, title.sub].filter(Boolean).join('\n') })).sort((a, b) => a.start - b.start);
}

export function srt(doc) {
	const ts = (sec) => {
		const ms = Math.round(sec * 1000);
		const p = (n, w = 2) => String(n).padStart(w, '0');
		return `${p(Math.floor(ms / 3600000))}:${p(Math.floor((ms % 3600000) / 60000))}:${p(Math.floor((ms % 60000) / 1000))},${p(ms % 1000, 3)}`;
	};
	return srtCues(doc)
		.map((c, i) => `${i + 1}\n${ts(c.start)} --> ${ts(c.end)}\n${fold(c.text)}\n`)
		.join('\n');
}

export const MAKERS = { fcpxml, otio, edl, srt };

export function download(name, data, type = 'text/plain') {
	const blob = data instanceof Blob ? data : new Blob([data], { type: `${type};charset=utf-8` });
	const url = URL.createObjectURL(blob);
	const link = Object.assign(document.createElement('a'), { href: url, download: name });
	document.body.append(link);
	link.click();
	link.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

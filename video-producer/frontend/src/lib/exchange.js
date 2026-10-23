import { laneCode } from './tracks.js';

export const EXCHANGE = {
	fcpxml: { ext: 'fcpxml', mime: 'application/xml' },
	otio: { ext: 'otio', mime: 'application/json' },
	edl: { ext: 'edl', mime: 'text/plain' },
	srt: { ext: 'srt', mime: 'application/x-subrip' }
};

const RESOLUTIONS = { '720p': [1280, 720], '1080p': [1920, 1080], '4K': [3840, 2160] };

const XML_FORBIDDEN = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/g;
const esc = (s) => String(s).replace(XML_FORBIDDEN, '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const oneLine = (s) => String(s).replace(/[\r\n]/g, '');
const fold = (text) =>
	String(text)
		.split(/\r\n|\r|\n/)
		.filter((line) => !/^[ \t]*$/.test(line))
		.join('\n');
const assetOf = (doc, id) => (id ? doc.assets?.find((a) => a.id === id) : undefined);

export function labelOf(doc, fallback) {
	return (c) => c?.label || assetOf(doc, c?.assetId)?.name || fallback;
}

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
	const rt = (sec) => `${frames(sec)}/${doc.fps}s`;
	const tcode = (sec) => {
		const f = frames(sec);
		const p = (n) => String(n).padStart(2, '0');
		const s = Math.floor(f / doc.fps);
		return [p(Math.floor(s / 3600)), p(Math.floor((s % 3600) / 60)), p(s % 60), p(f % doc.fps)].join(':');
	};
	return { frames, rt, tcode };
}

export function fcpxml(doc, { label }) {
	const { rt } = timing(doc);
	const file = (c) => fileOf(doc, c, label);
	const media = doc.clips.filter(file);
	const res = RESOLUTIONS[doc.resolution] ?? RESOLUTIONS['1080p'];
	const assets = media.map(
		(c, i) =>
			`\t\t<asset id="r${i + 2}" name="${esc(label(c))}" start="0s" duration="${rt(assetOf(doc, c.assetId).srcDur ?? c.srcIn + c.dur)}" hasVideo="1" format="r1"><media-rep kind="original-media" src="file:///Video%20Producer/${esc(encodeURI(file(c)))}"/></asset>`
	);
	const spine = doc.clips.map((c) =>
		file(c)
			? `\t\t\t\t\t\t<asset-clip ref="r${media.indexOf(c) + 2}" name="${esc(label(c))}" offset="${rt(c.start)}" start="${rt(c.srcIn)}" duration="${rt(c.dur)}"/>`
			: `\t\t\t\t\t\t<gap name="${esc(label(c))}" offset="${rt(c.start)}" start="0s" duration="${rt(c.dur)}"/>`
	);
	return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
	<resources>
		<format id="r1" name="FFVideoFormat${doc.resolution}${doc.fps}" frameDuration="1/${doc.fps}s" width="${res[0]}" height="${res[1]}"/>
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
	const { frames } = timing(doc);
	const rate = doc.fps;
	const file = (c) => fileOf(doc, c, label);
	const range = (start, dur) => ({ OTIO_SCHEMA: 'TimeRange.1', start_time: { OTIO_SCHEMA: 'RationalTime.1', rate, value: frames(start) }, duration: { OTIO_SCHEMA: 'RationalTime.1', rate, value: frames(dur) } });
	const reference = (url) => ({ DEFAULT_MEDIA: url ? { OTIO_SCHEMA: 'ExternalReference.1', target_url: url } : { OTIO_SCHEMA: 'MissingReference.1' } });
	const video = doc.clips.map((c) =>
		file(c)
			? {
					OTIO_SCHEMA: 'Clip.2',
					name: label(c),
					source_range: range(c.srcIn, c.dur),
					media_references: reference(file(c)),
					active_media_reference_key: 'DEFAULT_MEDIA',
					metadata: { video_producer: { stage: c.stage, take: c.take } }
				}
			: { OTIO_SCHEMA: 'Gap.1', name: label(c), source_range: range(0, c.dur) }
	);
	const lanes = doc.lanes.map((l) => {
		const items = doc.audio.filter((a) => a.lane === l.id).sort((a, b) => a.start - b.start);
		const children = [];
		let at = 0;
		for (const a of items) {
			if (a.start > at) children.push({ OTIO_SCHEMA: 'Gap.1', source_range: range(0, a.start - at) });
			children.push({
				OTIO_SCHEMA: 'Clip.2',
				name: assetOf(doc, a.assetId)?.name,
				source_range: range(a.srcIn, a.dur),
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
	const { tcode } = timing(doc);
	const lines = [`TITLE: ${oneLine(doc.name).toUpperCase()}`, 'FCM: NON-DROP FRAME', ''];
	doc.clips.forEach((c, i) => {
		const file = fileOf(doc, c, label);
		const n = String(i + 1).padStart(3, '0');
		const reel = file ? `VP${n}` : 'BL';
		lines.push(`${n}  ${reel.padEnd(8)} V     C        ${tcode(c.srcIn)} ${tcode(c.srcIn + c.dur)} ${tcode(c.start)} ${tcode(c.start + c.dur)}`);
		lines.push(`* FROM CLIP NAME: ${oneLine(label(c))}`);
		if (file) lines.push(`* SOURCE FILE: ${oneLine(file)}`);
		lines.push('');
	});
	return lines.join('\r\n');
}

export function srtCues(doc, { cue }) {
	const cues = [];
	for (const a of doc.audio) {
		const src = assetOf(doc, a.assetId);
		if (src?.transcript) cues.push({ start: a.start, end: a.start + a.dur, text: src.character ? cue(src.character, src.transcript) : src.transcript });
	}
	for (const title of doc.titles) cues.push({ start: title.start, end: title.start + title.dur, text: [title.text, title.sub].filter(Boolean).join('\n') });
	return cues.sort((a, b) => a.start - b.start);
}

export function srt(doc, options) {
	const ts = (sec) => {
		const ms = Math.round(sec * 1000);
		const p = (n, w = 2) => String(n).padStart(w, '0');
		return `${p(Math.floor(ms / 3600000))}:${p(Math.floor((ms % 3600000) / 60000))}:${p(Math.floor((ms % 60000) / 1000))},${p(ms % 1000, 3)}`;
	};
	return srtCues(doc, options)
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

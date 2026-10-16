import { t } from '../i18n/index.svelte.js';
import { doc, asset, clipLabel, seqDuration } from './state.svelte.js';

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const frames = (sec) => Math.round(sec * doc.fps);
const rt = (sec) => `${frames(sec)}/${doc.fps}s`;

function tcode(sec, sep = ':') {
	const f = frames(sec);
	const p = (n) => String(n).padStart(2, '0');
	const s = Math.floor(f / doc.fps);
	return [p(Math.floor(s / 3600)), p(Math.floor((s % 3600) / 60)), p(s % 60), p(f % doc.fps)].join(sep);
}

const fileOf = (c) => {
	const a = asset(c.assetId);
	if (!a) return null;
	if (a.generated) return `${clipLabel(c).replace(/[^\p{L}\p{N}]+/gu, '_')}_${a.quality}_${a.resultId}.mov`;
	return `${a.name.replace(/[^\p{L}\p{N}]+/gu, '_')}.mov`;
};

export function fcpxml() {
	const media = doc.clips.filter(fileOf);
	const res = { '720p': [1280, 720], '1080p': [1920, 1080], '4K': [3840, 2160] }[doc.resolution] ?? [1920, 1080];
	const assets = media.map(
		(c, i) =>
			`\t\t<asset id="r${i + 2}" name="${esc(clipLabel(c))}" start="0s" duration="${rt(asset(c.assetId).srcDur)}" hasVideo="1" format="r1"><media-rep kind="original-media" src="file:///Video%20Producer/${encodeURI(fileOf(c))}"/></asset>`
	);
	const spine = doc.clips.map((c) =>
		fileOf(c)
			? `\t\t\t\t\t\t<asset-clip ref="r${media.indexOf(c) + 2}" name="${esc(clipLabel(c))}" offset="${rt(c.start)}" start="${rt(c.srcIn)}" duration="${rt(c.dur)}"/>`
			: `\t\t\t\t\t\t<gap name="${esc(clipLabel(c))}" offset="${rt(c.start)}" start="0s" duration="${rt(c.dur)}"/>`
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
				<sequence format="r1" duration="${rt(seqDuration())}" tcStart="0s">
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

export function otio() {
	const rate = doc.fps;
	const range = (start, dur) => ({ OTIO_SCHEMA: 'TimeRange.1', start_time: { OTIO_SCHEMA: 'RationalTime.1', rate, value: frames(start) }, duration: { OTIO_SCHEMA: 'RationalTime.1', rate, value: frames(dur) } });
	const video = doc.clips.map((c) =>
		fileOf(c)
			? {
					OTIO_SCHEMA: 'Clip.2',
					name: clipLabel(c),
					source_range: range(c.srcIn, c.dur),
					media_references: { DEFAULT_MEDIA: { OTIO_SCHEMA: 'ExternalReference.1', target_url: fileOf(c) } },
					active_media_reference_key: 'DEFAULT_MEDIA',
					metadata: { video_producer: { stage: c.stage, take: c.take } }
				}
			: { OTIO_SCHEMA: 'Gap.1', name: clipLabel(c), source_range: range(0, c.dur) }
	);
	const lanes = doc.lanes.map((l) => {
		const items = doc.audio.filter((a) => a.lane === l.id).sort((a, b) => a.start - b.start);
		const children = [];
		let at = 0;
		for (const a of items) {
			if (a.start > at) children.push({ OTIO_SCHEMA: 'Gap.1', source_range: range(0, a.start - at) });
			children.push({ OTIO_SCHEMA: 'Clip.2', name: asset(a.assetId)?.name, source_range: range(a.srcIn, a.dur), metadata: { video_producer: { role: l.role, gain_db: a.gain } } });
			at = a.start + a.dur;
		}
		return { OTIO_SCHEMA: 'Track.1', name: `${l.id} · ${l.name}`, kind: 'Audio', children };
	});
	return JSON.stringify(
		{ OTIO_SCHEMA: 'Timeline.1', name: doc.name, global_start_time: null, tracks: { OTIO_SCHEMA: 'Stack.1', name: 'tracks', children: [{ OTIO_SCHEMA: 'Track.1', name: 'V1', kind: 'Video', children: video }, ...lanes] } },
		null,
		2
	);
}

export function edl() {
	const lines = [`TITLE: ${doc.name.toUpperCase()}`, 'FCM: NON-DROP FRAME', ''];
	doc.clips.forEach((c, i) => {
		const n = String(i + 1).padStart(3, '0');
		const reel = fileOf(c) ? `VP${n}` : 'BL';
		lines.push(`${n}  ${reel.padEnd(8)} V     C        ${tcode(c.srcIn)} ${tcode(c.srcIn + c.dur)} ${tcode(c.start)} ${tcode(c.start + c.dur)}`);
		lines.push(`* FROM CLIP NAME: ${clipLabel(c)}`);
		if (fileOf(c)) lines.push(`* SOURCE FILE: ${fileOf(c)}`);
		lines.push('');
	});
	return lines.join('\r\n');
}

export function srtCues() {
	const cues = [];
	for (const a of doc.audio) {
		const src = asset(a.assetId);
		if (src?.transcript) cues.push({ start: a.start, end: a.start + a.dur, text: src.character ? t('modals.export.cue', { character: src.character, text: src.transcript }) : src.transcript });
	}
	for (const title of doc.titles) cues.push({ start: title.start, end: title.start + title.dur, text: [title.text, title.sub].filter(Boolean).join('\n') });
	return cues.sort((a, b) => a.start - b.start);
}

export function srt() {
	const ts = (sec) => {
		const ms = Math.round(sec * 1000);
		const p = (n, w = 2) => String(n).padStart(w, '0');
		return `${p(Math.floor(ms / 3600000))}:${p(Math.floor((ms % 3600000) / 60000))}:${p(Math.floor((ms % 60000) / 1000))},${p(ms % 1000, 3)}`;
	};
	return srtCues()
		.map((c, i) => `${i + 1}\n${ts(c.start)} --> ${ts(c.end)}\n${c.text}\n`)
		.join('\n');
}

export function download(name, text, type = 'text/plain') {
	const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
	const link = Object.assign(document.createElement('a'), { href: url, download: name });
	document.body.append(link);
	link.click();
	link.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}

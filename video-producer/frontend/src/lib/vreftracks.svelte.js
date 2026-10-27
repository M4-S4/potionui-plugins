import { formatNumber, t } from '../i18n/index.svelte.js';
import { LIMITS, VIDEO_TRACKS, leastSeconds } from './reception.js';
import { ui, doc, act, asset, round, select, toast } from './state.svelte.js';
import { ulid } from './ulid.js';
import { MAX_VREF_TRACKS, videoTracksOf } from './vrefs.js';
import { addVrefItem, addVrefTrack, freeSlot, setTrackFrames, setTrackOff, trackOf, vrefLabel } from './vreftracks.js';

export function trackName(track) {
	if (!track) return '';
	const label = vrefLabel(track.slot);
	return track.name ? `${label} · ${track.name}` : label;
}

export const roleLabel = (role) => (role === 'continuation' ? t('lib.vref.role.continuation') : t('lib.vref.role.motion'));

export const sideText = (role) => (role === 'continuation' ? t('lib.vref.before') : t('lib.vref.under'));

const vsecs = (v) => `${formatNumber(v, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} s`;

export const sentSeconds = (frames) => vsecs(frames / VIDEO_TRACKS.fps);

export function trackVerdict(entry) {
	const side = sideText(entry.track.role);
	if (entry.status === 'sent') return { text: t('lib.vref.verdict.sent', { seconds: sentSeconds(entry.frames), side }), tone: 'text-success', ok: true };
	if (entry.status === 'trimmed') return { text: t('lib.vref.verdict.trimmed', { max: LIMITS.video }), tone: 'text-warning', ok: false };
	if (entry.status === 'short') return { text: t('lib.vref.verdict.short', { seconds: vsecs(leastSeconds()), side }), tone: 'text-warning', ok: false };
	if (entry.status === 'missing') return { text: t('lib.vref.verdict.missing'), tone: 'text-warning', ok: false };
	if (entry.status === 'excluded') return { text: t('lib.vref.verdict.excluded'), tone: 'text-fg-subtle', ok: false };
	if (entry.status === 'off') return { text: t('lib.vref.verdict.off'), tone: 'text-fg-subtle', ok: false };
	if (entry.status === 'blocked') return { text: t('lib.vref.verdict.blocked'), tone: 'text-fg-subtle', ok: false };
	if (entry.status === 'unknown') return { text: t('lib.vref.verdict.unknown'), tone: 'text-fg-subtle', ok: false };
	return { text: t('lib.vref.verdict.ignored'), tone: 'text-fg-subtle', ok: false };
}

export function addTrackItem() {
	const slot = freeSlot(doc);
	if (slot === null) {
		const taken = videoTracksOf(doc).map((track) => vrefLabel(track.slot));
		return {
			label: t('timeline.add.vref'),
			icon: 'film',
			disabled: true,
			hint: t('timeline.vref.full', { max: MAX_VREF_TRACKS, first: taken[0], second: taken[1], third: taken[2] }),
			run: () => {}
		};
	}
	return { label: t('timeline.add.vref'), icon: 'film', badge: vrefLabel(slot), hint: t('timeline.vref.addHint', { max: MAX_VREF_TRACKS }), run: addVideoTrack };
}

export function addVideoTrack() {
	let track = null;
	act(() => (track = addVrefTrack(doc, ulid(), '')));
	if (!track) return toast(t('timeline.vref.fullToast', { max: MAX_VREF_TRACKS }), 'warning');
	select('vtrack', track.id);
	toast(t('timeline.vref.added', { label: vrefLabel(track.slot) }));
	return trackOf(doc, track.id);
}

export function placeOnTrack(trackId, assetId, at) {
	const track = trackOf(doc, trackId);
	const a = asset(assetId);
	if (!track || !a) return null;
	if (a.kind !== 'video') {
		toast(t('timeline.vref.videoOnly'), 'warning');
		return null;
	}
	let item = null;
	act(() => (item = addVrefItem(doc, { id: ulid(), track: track.id, assetId, start: round(Math.max(0, at), 0.04), srcDur: a.srcDur })));
	select('vref', item.id);
	toast(t('timeline.vref.dropped', { name: a.name, label: vrefLabel(track.slot) }));
	return item.start + item.dur;
}

export function setTrackRole(track, role) {
	if (!track || track.role === role) return;
	act(() => (track.role = role));
	toast(t('timeline.vref.roleSet', { label: vrefLabel(track.slot), role: roleLabel(role) }));
}

export function setTrackLength(track, frames) {
	if (!track) return;
	act(() => setTrackFrames(track, frames));
}

export function renameTrack(track, name) {
	if (!track || track.name === name) return;
	act(() => (track.name = name));
}

export function toggleTrack(track) {
	if (!track) return;
	const off = track.off !== true;
	act(() => setTrackOff(track, off));
	toast(off ? t('timeline.vref.disabled', { label: vrefLabel(track.slot) }) : t('timeline.vref.enabled', { label: vrefLabel(track.slot) }));
}

export function openTrackSettings(track, field = null) {
	if (!track) return;
	select('vtrack', track.id);
	ui.inspectorOpen = true;
	ui.vrefField = field ? { id: track.id, field } : null;
}

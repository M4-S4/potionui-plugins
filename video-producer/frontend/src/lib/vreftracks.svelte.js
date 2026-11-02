import { formatNumber, getLocale, t } from '../i18n/index.svelte.js';
import { LIMITS, VIDEO_TRACKS, engineKey, leastSeconds } from './reception.js';
import { ui, doc, act, asset, round, select, toast, newReferenceLane, undo, openDirector, shotNumber } from './state.svelte.js';
import { ulid } from './ulid.js';
import { MAX_VREF_TRACKS, videoTracksOf } from './vrefs.js';
import { addVrefItem, addVrefTrack, freeSlot, itemSpan, sendingChanges, sendings, setTrackFrames, setTrackOff, trackBusy, trackOf, vrefLabel } from './vreftracks.js';
import { engineTitle, shotReceptionFor } from './references.js';
import { ensureTakeAsset, releaseTake } from './production.svelte.js';
import { takeById } from './takes.svelte.js';
import { excludedVrefsOf, releaseShot, setExcludedVrefs } from './shots.js';
import { freeReferenceLane, takeSound } from './sound.js';
import { laneCode } from './tracks.js';

export function trackName(track) {
	if (!track) return '';
	const label = vrefLabel(track.slot);
	return track.name ? `${label} · ${track.name}` : label;
}

export const roleLabel = (role) => (role === 'continuation' ? t('lib.vref.role.continuation') : t('lib.vref.role.motion'));

export const sideText = (role) => (role === 'continuation' ? t('lib.vref.before') : t('lib.vref.under'));

const vsecs = (v) => `${formatNumber(v, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} s`;

export const sentSeconds = (frames) => vsecs(frames / VIDEO_TRACKS.fps);

export const leastText = () => vsecs(leastSeconds());

export function trackVerdict(entry) {
	const side = sideText(entry.track.role);
	if (entry.status === 'sent') return { text: t('lib.vref.verdict.sent', { seconds: sentSeconds(entry.frames), side }), tone: 'text-success', ok: true };
	if (entry.status === 'trimmed') return { text: t('lib.vref.verdict.trimmed', { max: LIMITS.video }), tone: 'text-warning', ok: false };
	if (entry.status === 'short') return { text: t('lib.vref.verdict.short', { seconds: leastText(), side }), tone: 'text-warning', ok: false };
	if (entry.status === 'missing') return { text: t('lib.vref.verdict.missing'), tone: 'text-warning', ok: false };
	if (entry.status === 'excluded') return { text: t('lib.vref.verdict.excluded'), tone: 'text-fg-subtle', ok: false };
	if (entry.status === 'off') return { text: t('lib.vref.verdict.off'), tone: 'text-fg-subtle', ok: false };
	if (entry.status === 'blocked') return { text: t('lib.vref.verdict.blocked'), tone: 'text-fg-subtle', ok: false };
	if (entry.status === 'unknown') return { text: t('lib.vref.verdict.unknown'), tone: 'text-fg-subtle', ok: false };
	return { text: t('lib.vref.verdict.ignored'), tone: 'text-fg-subtle', ok: false };
}

export function shotList(clips) {
	if (clips.length > 3) return t('lib.vref.change.shots', { count: clips.length });
	return new Intl.ListFormat(getLocale(), { type: 'conjunction' }).format(clips.map(shotNumber));
}

export function showTrack(trackId) {
	if (!trackOf(doc, trackId)) return;
	openDirector('references');
	select('vtrack', trackId);
}

export const trackSendings = () => (videoTracksOf(doc).length ? sendings(doc.clips.map(shotReceptionFor)) : new Map());

function stoppedLine(label, group) {
	const shots = shotList(group.clips);
	if (group.status === 'ignored') return t('lib.vref.change.ignored', { label, shots, engine: engineTitle(group.engine) });
	if (group.status === 'trimmed') return t('lib.vref.change.trimmed', { label, shots, max: LIMITS.video });
	if (group.status === 'blocked') return t('lib.vref.change.blocked', { label, shots, engine: engineTitle(group.engine) });
	if (group.status === 'unknown') return t('lib.vref.change.unknown', { label, shots });
	if (group.status === 'short') return t('lib.vref.change.short', { label, shots, seconds: leastText() });
	return t('lib.vref.change.stopped', { label, shots });
}

export function announceSendings(before) {
	if (!before.size && !videoTracksOf(doc).length) return [];
	const changes = sendingChanges(before, doc.clips.map(shotReceptionFor));
	if (!changes.length) return [];
	const lines = [];
	for (const change of changes) {
		const label = vrefLabel(change.track.slot);
		const groups = [];
		for (const x of change.stopped) {
			const key = `${x.status}|${x.status === 'ignored' || x.status === 'blocked' ? engineKey(x.engine) : ''}`;
			let group = groups.find((g) => g.key === key);
			if (!group) groups.push((group = { key, status: x.status, engine: x.engine, clips: [] }));
			group.clips.push(x.clip);
		}
		lines.push(...groups.map((group) => stoppedLine(label, group)));
		if (change.started.length) lines.push(t('lib.vref.change.started', { label, shots: shotList(change.started) }));
	}
	const first = changes[0].track.id;
	toast(lines.join(' '), 'info', { label: t('lib.vref.change.see'), run: () => showTrack(first) }, 6000);
	return changes;
}

export function leaveAside(trackId, clips) {
	const track = trackOf(doc, trackId);
	const left = clips.filter((clip) => !excludedVrefsOf(clip).includes(trackId));
	if (!track || !left.length) return 0;
	act(() => {
		for (const clip of left) setExcludedVrefs(clip, [...excludedVrefsOf(clip), trackId]);
	});
	toast(t('lib.vref.leftAside', { label: vrefLabel(track.slot), shots: shotList(left) }), 'info', { label: t('shell.toast.undo'), run: undo });
	return left.length;
}

export function withSendings(change) {
	const before = trackSendings();
	const result = change();
	announceSendings(before);
	return result;
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

const ready = (take) => take?.status === 'done' && Boolean(take.url);

export const takeClip = (take) => doc.clips.find((clip) => clip.id === take?.shotId) ?? null;

export const isPlaced = (take, clip = takeClip(take)) => Boolean(clip && take && clip.take === take.id);

export function takeSpan(take, clip = takeClip(take)) {
	const start = clip ? clip.start : round(Math.max(0, ui.playhead), 0.04);
	const length = asset(`gen-${take.id}`)?.srcDur ?? take.durationS;
	return [start, start + itemSpan(length)];
}

export function takeChoices(take, clip = takeClip(take)) {
	if (!ready(take)) return null;
	const span = takeSpan(take, clip);
	const shot = clip ? shotNumber(clip) : null;
	const targets = videoTracksOf(doc).map((track) => {
		const busy = trackBusy(doc, track.id, span[0], span[1]);
		return { track, busy, reason: busy ? (shot ? t('lib.vref.take.busy', { label: vrefLabel(track.slot), shot }) : t('lib.vref.take.busyHere', { label: vrefLabel(track.slot) })) : null };
	});
	return { placed: isPlaced(take, clip), span, shot, targets, slot: freeSlot(doc) };
}

export function sendTakeToTrack(take, { trackId = null, move = false, sound = false } = {}) {
	if (!ready(take)) return null;
	const clip = takeClip(take);
	const span = takeSpan(take, clip);
	const target = trackId ? trackOf(doc, trackId) : null;
	if (trackId && !target) return null;
	if (target && trackBusy(doc, target.id, span[0], span[1])) {
		toast(clip ? t('lib.vref.take.busy', { label: vrefLabel(target.slot), shot: shotNumber(clip) }) : t('lib.vref.take.busyHere', { label: vrefLabel(target.slot) }), 'warning');
		return null;
	}
	if (!target && freeSlot(doc) === null) {
		toast(t('timeline.vref.fullToast', { max: MAX_VREF_TRACKS }), 'warning');
		return null;
	}
	const moving = move && isPlaced(take, clip);
	let done = null;
	act(() => {
		const assetId = ensureTakeAsset(take);
		if (!assetId) return;
		const track = target ?? addVrefTrack(doc, ulid(), '');
		const item = addVrefItem(doc, { id: ulid(), track: track.id, assetId, start: span[0], srcDur: span[1] - span[0], fromTake: take.id });
		let lane = null;
		if (sound) {
			lane = freeReferenceLane(doc, span) ?? newReferenceLane();
			doc.audio.push(takeSound({ id: ulid(), assetId, lane: lane.id, start: span[0], dur: item.dur, fromTake: take.id }));
		}
		done = { track, item, lane, released: moving ? releaseShot(clip) : null };
	});
	if (!done) return null;
	if (done.released) releaseTake(done.released);
	select('vref', done.item.id);
	const params = { label: vrefLabel(done.track.slot), variant: take.variant, shot: clip ? shotNumber(clip) : '' };
	const message = moving ? t('lib.vref.take.moved', params) : t('lib.vref.take.copied', params);
	toast(done.lane ? `${message} ${t('lib.vref.take.withSound', { lane: laneCode(doc.lanes, done.lane.id) })}` : message, 'info', { label: t('shell.toast.undo'), run: undo });
	return done;
}

export function dropTakeOnTrack(takeId, trackId) {
	const take = takeById(takeId);
	if (!ready(take)) return null;
	return sendTakeToTrack(take, { trackId, move: isPlaced(take), sound: ui.vrefSound === true });
}

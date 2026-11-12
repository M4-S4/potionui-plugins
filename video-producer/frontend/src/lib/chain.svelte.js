import { formatNumber, t } from '../i18n/index.svelte.js';
import { ui, doc, act, toast, undo, clipLabel, onShotsAdded, secs } from './state.svelte.js';
import { project, getClient, flushSave, projectGone } from './project.svelte.js';
import { onTake, takeStore } from './takes.svelte.js';
import { isRemoved } from './removedtakes.js';
import { engineChoices } from './production.svelte.js';
import { aspectOf, draftResolution, optionFor, presetProfiles } from './generation.js';
import { effectiveEngine } from './engine.js';
import { frameErrorText, placeSeamFrame, previousShot, seamImage } from './seam.js';
import { chainByOf, setShotChainBy, chainOn, chainPlan, chainSource, chainState, chainWaiting, continueFallback, frameAsset, ignoresFirstFrame, placesTakeFrame, resetShotChain, seamChain, setShotChain, shotChained, stillAsset, takeFrameAsset } from './chain.js';
import { FPS, TWELVE_GB_PRESETS, maxPixels, visionTokens } from './encoder.js';
import { chosenSize, parseSize } from './formats.js';
import { optionsOf, presetFields } from './options.js';
import { sentReferences } from './shots.js';
import { VIDEO_TRACKS, leastSeconds } from './reception.js';

export const chainJobs = $state({ shots: [] });

export const chainBusy = (shotId) => chainJobs.shots.includes(shotId);

export function chainOf(clip) {
	const i = clip ? doc.clips.findIndex((c) => c.id === clip.id) : -1;
	return i > 0 ? chainState(doc, i) : null;
}

const assetName = (previous) => t('lib.chain.assetName', { shot: clipLabel(previous) });

async function extract(previous) {
	const saved = await flushSave();
	if (!saved || !project.id) {
		toast(t('lib.seam.saveFirst'), 'error');
		return null;
	}
	const projectId = project.id;
	const result = await getClient().endFrame(projectId, previous.id);
	if (projectId !== project.id) return null;
	if (result.ok) return result.data;
	if (result.error.code === 'project_not_found') projectGone(projectId);
	else toast(frameErrorText(result.error, t), result.error.status === 409 ? 'warning' : 'error');
	return null;
}

async function chainFrame(shotId, auto) {
	const clip = doc.clips.find((c) => c.id === shotId);
	const previous = clip ? previousShot(doc, shotId) : null;
	const source = previous ? chainSource(doc, previous) : null;
	if (!source) {
		if (!auto) toast(t('lib.chain.noMedia', { shot: clipLabel(previous) }), 'warning');
		return;
	}
	if (chainBusy(shotId)) return;
	let asset = source.at === null ? stillAsset(doc, source, assetName(previous)) : null;
	if (!asset) {
		chainJobs.shots.push(shotId);
		try {
			const frame = await extract(previous);
			if (frame) asset = frameAsset(frame.media, frame.source, assetName(previous));
		} finally {
			chainJobs.shots = chainJobs.shots.filter((id) => id !== shotId);
		}
	}
	const target = doc.clips.find((c) => c.id === shotId);
	if (!asset || !target) return;
	if (auto && (seamImage(doc, shotId, 'first') || previousShot(doc, shotId)?.id !== previous.id)) return;
	act(() => placeSeamFrame(doc, target, 'first', asset));
	const names = { shot: clipLabel(target), previous: clipLabel(previous) };
	toast(auto ? t('lib.chain.taken', names) : t('lib.seam.added', names), 'success', { label: t('shell.toast.undo'), run: undo });
}

export const takeEndFrame = (clip) => chainFrame(clip.id, false);

function chainShots(clips) {
	for (const clip of clips) {
		const source = chainPlan(doc, clip);
		if (!source) continue;
		if (source.at !== null) {
			queueMicrotask(() => chainFrame(clip.id, true));
			continue;
		}
		const previous = previousShot(doc, clip.id);
		placeSeamFrame(doc, clip, 'first', stillAsset(doc, source, assetName(previous)));
		toast(t('lib.chain.taken', { shot: clipLabel(clip), previous: clipLabel(previous) }), 'success');
	}
}

onShotsAdded(chainShots);

export function setShotChaining(clip, on) {
	const target = doc.clips.find((c) => c.id === clip?.id);
	const previous = target ? previousShot(doc, target.id) : null;
	if (!previous || shotChained(doc, target) === on) return;
	act(() => setShotChain(doc, target, on));
	const names = { shot: clipLabel(target), previous: clipLabel(previous) };
	toast(on ? t('lib.chain.shotOn', names) : t('lib.chain.shotOff', names), 'info', { label: t('shell.toast.undo'), run: undo });
	if (on && !seamImage(doc, target.id, 'first') && chainSource(doc, previous)) chainFrame(target.id, true);
}

export function chooseShotChainBy(clip, value) {
	const target = doc.clips.find((c) => c.id === clip?.id);
	if (!target || chainByOf(doc, target) === value) return;
	act(() => setShotChainBy(doc, target, value));
}

export const toggleShotChaining = (clip) => setShotChaining(clip, !shotChained(doc, clip));

export function seamChainOf(clip) {
	const i = clip ? doc.clips.findIndex((c) => c.id === clip.id) : -1;
	if (i <= 0) return null;
	const engine = effectiveEngine(doc.clips[i], doc);
	const option = optionFor(engineChoices(), engine);
	const references = engine.profile === 'Ref2VA';
	const modes = option && option.kind !== 'cloud' ? (option.info?.modes ?? []) : [];
	const extendable = engine.profile === 'FL2VA' && TWELVE_GB_PRESETS.includes(option?.preset) && modes.includes('extend');
	const continues = chainByOf(doc, doc.clips[i]) === 'video' && (references || extendable);
	const fallback = continues ? continueFallback(doc, i, { references, tokens: references ? encoderTokens(doc.clips[i], option) : null, maxDuration: option?.info?.limits?.maxDuration ?? null, least: leastSeconds() }) : null;
	const state = seamChain(doc, i, takeStore.list, ignoresFirstFrame(option), continues, references, fallback);
	if (state && !['off', 'waiting'].includes(state.state) && option && !presetProfiles(option.info).includes(engine.profile)) return { ...state, state: 'profileUnsupported', profile: engine.profile, extends: false };
	return state;
}

export function encoderTokens(clip, option) {
	if (!option || !TWELVE_GB_PRESETS.includes(option.preset)) return null;
	const size = parseSize(draftResolution(option.info, ui.me?.settings?.draftResolution, aspectOf(doc.aspect, doc.resolution), chosenSize(doc, option.preset, 'draft')));
	if (!size) return null;
	const field = presetFields(option.info).find((f) => f.name === 'reference_pixel_budget');
	const budget = optionsOf(doc.engine, option.preset).reference_pixel_budget ?? field?.default ?? null;
	const pictures = sentReferences(doc, clip)
		.map((reference) => (doc.assets ?? []).find((a) => a.id === reference.assetId))
		.filter((a) => a?.kind === 'image')
		.map((a) => (a.width > 0 && a.height > 0 ? [a.width, a.height] : null));
	const frames = Math.min(VIDEO_TRACKS.minFrames, Math.floor((clip?.dur ?? 0) * FPS));
	return visionTokens(pictures, [[frames, size]], maxPixels(budget, size));
}

export function waitText(take) {
	if (!chainWaiting(take)) return '';
	const previous = doc.clips.find((c) => c.id === take.chain.previous);
	const shot = previous ? clipLabel(previous) : '—';
	const after = take.chain.after ? takeStore.list.find((x) => x.id === take.chain.after) : null;
	if (after) return t('lib.chain.waitTake', { variant: after.variant, shot });
	return take.chain.video ? t('lib.chain.waitEnd', { shot }) : t('lib.chain.waitFrame', { shot });
}

const MAX_EXTEND_SECONDS = 328 / 24;

export function chainStatusText(state) {
	const previous = clipLabel(state.from);
	if (state.state === 'off') return t('storyboard.chain.off');
	if (state.state === 'profileUnsupported') return t('modals.shot.profileUnsupported', { profile: state.profile });
	if (state.state === 'textOnly') return t('storyboard.chain.textOnly');
	if (state.state === 'waiting') return waitText(state.take);
	if (state.state === 'own') return t('storyboard.chain.own');
	if (state.state === 'stale') return t('storyboard.chain.stale', { previous });
	if (state.state === 'fresh') return t('storyboard.chain.fresh', { previous });
	if (state.state === 'ready') return t('storyboard.chain.ready', { previous });
	if (state.state === 'references') return t('storyboard.chain.references', { previous });
	const seconds = secs(leastSeconds());
	if (state.extends) {
		if (state.state === 'continues') return t('storyboard.chain.extends', { previous });
		if (state.state === 'continueLater') return t('storyboard.chain.extendLater', { previous });
		if (state.state === 'continueStill') return t('storyboard.chain.extendStill', { previous });
		if (state.state === 'continueShort') return t('storyboard.chain.extendShort', { previous, seconds });
		if (state.state === 'continueOwnLast') return t('storyboard.chain.extendOwnLast', { previous });
		if (state.state === 'continueLong') return t('storyboard.chain.extendLong', { previous, seconds: secs(MAX_EXTEND_SECONDS) });
	}
	if (state.state === 'continues') return t('storyboard.chain.continues', { previous });
	if (state.state === 'continueStill') return t('storyboard.chain.continueStill', { previous });
	if (state.state === 'continueLater') return t('storyboard.chain.continueLater', { previous });
	if (state.state === 'continueShort') return t('storyboard.chain.continueShort', { previous, seconds });
	if (state.state === 'continueEncoder') return t('storyboard.chain.continueEncoder', { previous, tokens: formatNumber(state.tokens), limit: formatNumber(state.limit) });
	return t('storyboard.chain.later', { previous });
}

export function shotWaitText(shotId) {
	const take = takeStore.list.find((x) => x.shotId === shotId && chainWaiting(x));
	return take ? waitText(take) : '';
}

export function followProjectChain(clip) {
	const target = doc.clips.find((c) => c.id === clip?.id);
	if (!target || typeof target.firstFromPrevious !== 'boolean') return;
	const before = shotChained(doc, target);
	act(() => resetShotChain(doc, target));
	const previous = previousShot(doc, target.id);
	if (!before && chainOn(doc) && previous && !seamImage(doc, target.id, 'first') && chainSource(doc, previous)) chainFrame(target.id, true);
}

const placed = new Set();

function placeTakeFrame(take, live) {
	if (placed.has(take?.id) || !placesTakeFrame(doc, take, takeStore.list, (id) => isRemoved(doc, id))) return;
	const target = doc.clips.find((c) => c.id === take.shotId);
	const previous = previousShot(doc, take.shotId);
	const asset = takeFrameAsset(doc, take, assetName(previous));
	if (!asset) return;
	placed.add(take.id);
	const apply = () => placeSeamFrame(doc, target, 'first', asset);
	if (!live) return apply();
	act(apply);
	toast(t('lib.chain.batchTaken', { shot: clipLabel(target), previous: clipLabel(previous), variant: take.variant }), 'success', { label: t('shell.toast.undo'), run: undo });
}

onTake(placeTakeFrame);

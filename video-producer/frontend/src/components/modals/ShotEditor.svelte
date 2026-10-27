<script>
	import { tick } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, asset, clipLabel, promptIssues, relayout, secs, toast } from '../../lib/state.svelte.js';
	import { takesOf, engineLabel, engineChoices, engineGroups, currentEngine, soundBehaviorOf, shotDurationLimit, settleRelease } from '../../lib/production.svelte.js';
	import { PROFILES, optionKey, presetProfiles, withProfile } from '../../lib/generation.js';
	import { SEED_MAX, randomSeed, validSeed } from '../../lib/engine.js';
	import { engineTitle, refTypeLabel, shotReceptionIn } from '../../lib/references.js';
	import { TAG_CLASS, typeIcon } from '../../lib/reftags.js';
	import { LIMITS } from '../../lib/reception.js';
	import { citeTrack, citedSlots, vrefLabel, vrefTag } from '../../lib/vreftracks.js';
	import { roleLabel, trackVerdict } from '../../lib/vreftracks.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { SHOT_CAP, applyShotDraft, inputsChanged, overrunsTake, rebaseDraft, shotDraft, shotReferences } from '../../lib/shots.js';
	import { CONDITION, SOUND_ROLE, SOUND_SPACE, SOUND_TYPES, conditionWindow, muxWindow, referenceLanes, trackPortion } from '../../lib/sound.js';
	import { laneTitle } from '../../lib/tracks.js';
	import { ulid } from '../../lib/ulid.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import MediaPicker from '../shots/MediaPicker.svelte';
	import AudioPicker from '../shots/AudioPicker.svelte';
	import SoundNote from '../shots/SoundNote.svelte';
	import CastField from '../shots/CastField.svelte';
	import DialogueField from '../shots/DialogueField.svelte';
	import ComposedPrompt from '../shots/ComposedPrompt.svelte';
	import ReferencePrompt from '../shots/ReferencePrompt.svelte';
	import KeyframeCandidates from '../shots/KeyframeCandidates.svelte';
	import RefTags from '../references/RefTags.svelte';

	let { id, draft: kept = null, baseline: keptBaseline = null, focus = null } = $props();

	const IDENTITY_TYPES = ['Personnage', 'Décor', 'Objet', 'Style'];
	const clip = $derived(doc.clips.find((c) => c.id === id));
	const textId = $props.id();

	function initialBaseline() {
		if (keptBaseline) return $state.snapshot(keptBaseline);
		const c = doc.clips.find((x) => x.id === id);
		return c ? shotDraft(doc, c, doc.engine) : null;
	}

	function initialDraft() {
		return kept ? $state.snapshot(kept) : baseline && structuredClone(baseline);
	}

	const baseline = initialBaseline();
	let draft = $state(initialDraft());
	let adding = $state(null);
	let composed = $state(null);

	const takes = $derived(clip ? takesOf(clip) : []);
	const inherited = $derived(clip ? shotReferences(doc, clip, draft.exclude).inherited : []);
	const sentCount = $derived(draft.own.length + inherited.filter((x) => !x.excluded).length);
	const limit = $derived(clip ? shotDurationLimit({ ...clip, engine: draft.engine }) : { max: SHOT_CAP, by: null, take: null });
	const beyondTake = $derived(clip ? overrunsTake(limit.take, clip.dur, +draft.dur) : false);
	const issues = $derived(clip ? promptIssues({ text: draft.text, start: clip.start, dur: +draft.dur, shotId: clip.id }) : []);
	const changed = $derived(Boolean(baseline) && inputsChanged(baseline, draft));
	const groups = $derived(engineGroups());
	const draftKey = $derived(draft.engine.preset ? optionKey(draft.engine.preset, draft.engine.model ?? null) : '');
	const draftOption = $derived(draftKey ? (engineChoices().find((o) => o.key === draftKey) ?? null) : null);
	const profiles = $derived.by(() => {
		const option = draftKey ? draftOption : currentEngine();
		return option ? presetProfiles(option.info) : [...PROFILES];
	});
	const ownEngine = $derived(Object.keys(draft.engine).length > 0);
	const isSound = (r) => asset(r.assetId)?.kind === 'audio';
	const lanes = $derived(clip ? referenceLanes(doc, clip, draft.excludeLanes) : []);
	const behavior = $derived(clip ? soundBehaviorOf({ ...clip, engine: draft.engine }) : null);
	const soundWindow = $derived(clip ? (behavior === CONDITION ? conditionWindow(doc, { ...clip, dur: +draft.dur }) : muxWindow({ ...clip, dur: +draft.dur })) : [0, 0]);
	const sounding = $derived(lanes.some((x) => !x.excluded) || draft.own.some(isSound) || inherited.some((x) => !x.excluded && isSound(x.reference)));
	const source = $derived.by(() => {
		const copy = $state.snapshot(doc);
		const shot = copy.clips.find((c) => c.id === id);
		if (shot && baseline) applyShotDraft(copy, shot, baseline, $state.snapshot(draft), { makeId: ulid, maxDur: limit.max, engine: copy.engine });
		return copy;
	});

	const REFERENCE_PROFILE = 'Ref2VA';
	const draftShot = $derived(source.clips.find((c) => c.id === id) ?? null);
	const reception = $derived(draftShot ? shotReceptionIn(source, draftShot) : null);
	const vrefRows = $derived(reception?.videoTracks ?? []);
	const ignoredRows = $derived(vrefRows.filter((entry) => entry.status === 'ignored'));
	const ignoredLabels = $derived(ignoredRows.map((entry) => vrefLabel(entry.slot)).join(', '));
	const switchTarget = $derived.by(() => {
		const current = draftKey ? draftOption : currentEngine();
		if (current && presetProfiles(current.info).includes(REFERENCE_PROFILE)) return { option: null, label: withProfile(current.label, REFERENCE_PROFILE) };
		const other = engineChoices().find((o) => presetProfiles(o.info).includes(REFERENCE_PROFILE));
		return other ? { option: other, label: withProfile(other.label, REFERENCE_PROFILE) } : null;
	});

	let textEl = $state(null);
	let caret = null;
	const cited = $derived(citedSlots(draft?.text));

	function cite(slot) {
		const result = citeTrack(draft.text, slot, caret);
		if (!result.added) return;
		draft.text = result.text;
		caret = result.caret;
		tick().then(() => {
			textEl?.focus();
			textEl?.setSelectionRange(result.caret, result.caret);
		});
	}

	function toggleVref(trackId, on) {
		const list = draft.excludeVrefs ?? [];
		draft.excludeVrefs = on ? [...list.filter((x) => x !== trackId), trackId] : list.filter((x) => x !== trackId);
	}

	function switchToReferences() {
		if (!switchTarget) return;
		if (switchTarget.option) pickEngine(switchTarget.option.key);
		setOwn('profile', REFERENCE_PROFILE);
	}

	function pickEngine(key) {
		const { preset, model, backend, ...rest } = draft.engine;
		const option = engineChoices().find((o) => o.key === key);
		draft.engine = option ? { ...rest, preset: option.preset, model: option.model, backend: option.backend } : rest;
	}

	function setOwn(key, value) {
		const { [key]: dropped, ...rest } = draft.engine;
		draft.engine = value ? { ...rest, [key]: value } : rest;
	}

	function setSeed(value) {
		const seed = value === '' ? null : Number(value);
		setOwn('seed', null);
		if (validSeed(seed)) draft.engine = { ...draft.engine, seed };
	}

	function toggleExclude(refId, on) {
		draft.exclude = on ? [...draft.exclude, refId] : draft.exclude.filter((x) => x !== refId);
	}

	function addOwn(assetId) {
		adding = null;
		if (!assetId) return;
		const a = asset(assetId);
		draft.own = [...draft.own, { id: ulid(), name: a?.name || t('lib.default.reference', { type: refTypeLabel(IDENTITY_TYPES[0]) }), space: 'identite', type: IDENTITY_TYPES[0], assetId, role: 'Identité' }];
	}

	function addSound(assetId) {
		adding = null;
		if (!assetId) return;
		const a = asset(assetId);
		draft.own = [...draft.own, { id: ulid(), name: a?.name || t('lib.default.reference', { type: refTypeLabel(SOUND_TYPES[0]) }), space: SOUND_SPACE, type: SOUND_TYPES[0], assetId, role: SOUND_ROLE }];
	}

	function toggleLane(laneId, on) {
		draft.excludeLanes = on ? [...draft.excludeLanes, laneId] : draft.excludeLanes.filter((x) => x !== laneId);
	}

	function removeOwn(refId) {
		draft.own = draft.own.filter((r) => r.id !== refId);
	}

	function saveIt() {
		if (!clip) return (ui.modal = null);
		let released = null;
		let conflicts = 0;
		act(() => {
			const current = $state.snapshot(shotDraft(doc, clip, doc.engine));
			const rebased = rebaseDraft($state.snapshot(baseline), $state.snapshot(draft), current);
			const result = applyShotDraft(doc, clip, current, rebased.draft, { makeId: ulid, maxDur: limit.max, engine: doc.engine });
			conflicts = rebased.conflicts;
			released = result.released;
			if (result.resized) relayout();
		});
		settleRelease(clip, released);
		if (conflicts) toast(t('modals.shot.kept', { count: conflicts }), 'warning');
		ui.modal = null;
	}

	function openLibrary() {
		ui.modal = { type: 'library', target: { kind: 'shot', id, returnTo: { type: 'shot', id, draft: $state.snapshot(draft), baseline } } };
	}
</script>

{#if clip && baseline}
	<Modal title={t('modals.shot.title', { shot: clipLabel(clip) })} subtitle={t('modals.shot.subtitle', { start: secs(clip.start), end: secs(clip.start + clip.dur) })} icon="film" width={860}>
		<div class="grid grid-cols-[1fr_250px] gap-4 p-4">
			<div class="min-w-0 space-y-4">
				{#if takes.length}
					<div class="flex gap-2 rounded-lg border border-line-hover p-2 text-xs text-fg-muted">
						<Icon name="info" class="mt-px h-3.5 w-3.5 shrink-0" />{t('modals.shot.takesNote', { count: takes.length })}
					</div>
				{/if}
				<section class="space-y-1.5">
					<div class="flex items-center justify-between">
						<label for={textId} class="vp-label">{t('modals.prompt.instruction')}</label>
						<button type="button" class="flex min-h-6 items-center gap-1 text-xs text-fg-muted hover:text-fg" onclick={openLibrary}><Icon name="wand" class="h-3.5 w-3.5" />{t('modals.prompt.library')}</button>
					</div>
					<!-- svelte-ignore a11y_autofocus -->
					<textarea id={textId} class="input w-full text-md" rows="5" bind:this={textEl} bind:value={draft.text} onblur={(e) => (caret = e.currentTarget.selectionStart)} autofocus={focus !== 'keyframes'} placeholder={t('modals.prompt.placeholder')}></textarea>
					{#each issues as issue, i (i)}
						{#if issue.level === 'conflict'}
							<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{issue.text}</HostUi>
						{/if}
					{/each}
				</section>

				<section class="space-y-1.5" aria-labelledby="{textId}-cast">
					<span id="{textId}-cast" class="vp-section-title">{t('modals.shot.cast')}</span>
					<CastField cast={draft.cast} text={draft.text} onchange={(cast) => (draft.cast = cast)} />
				</section>

				<section class="space-y-1.5" aria-labelledby="{textId}-dialogue">
					<span id="{textId}-dialogue" class="vp-section-title">{t('modals.shot.dialogue.title')}</span>
					<DialogueField lines={draft.dialogue ?? []} cast={draft.cast} seconds={+draft.dur} onchange={(lines) => (draft.dialogue = lines)} />
				</section>

				<section class="space-y-1.5" aria-labelledby="{textId}-reference">
					<span id="{textId}-reference" class="vp-section-title">{t('modals.shot.reference.title')}</span>
					<ReferencePrompt reference={composed?.reference ?? null} value={draft.referencePrompt ?? null} onchange={(value) => (draft.referencePrompt = value)} />
					<ComposedPrompt {source} shotId={id} bind:current={composed} />
				</section>

				<section class="space-y-2" aria-labelledby="{textId}-refs">
					<div class="flex items-baseline justify-between gap-2">
						<span id="{textId}-refs" class="vp-section-title">{t('modals.shot.references')}</span>
						<span class="text-xs text-fg-subtle">{t('modals.shot.referencesSent', { count: sentCount })}</span>
					</div>
					<div class="space-y-1">
						<div class="text-xs font-medium text-fg-muted">{t('modals.shot.inherited')}</div>
						{#if inherited.length}
							<ul class="divide-y divide-line rounded-lg border border-line-strong">
								{#each inherited as { reference: r, excluded } (r.id)}
									{@const thumb = r.assetId ? assetThumb(asset(r.assetId)) : null}
									<li class="flex items-center gap-2 px-2 py-1.5 text-xs {excluded ? 'opacity-60' : ''}">
										{#if thumb}<img src={thumb} alt="" class="h-7 w-12 shrink-0 rounded object-cover" />{:else}<span class="flex h-7 w-12 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name={typeIcon(r)} class="h-3.5 w-3.5 text-fg-muted" /></span>{/if}
										<span class="min-w-0 flex-1 space-y-0.5">
											<span class="block truncate text-fg {excluded ? 'line-through' : ''}">{r.name}</span>
											<RefTags reference={r} />
											{#if !r.assetId || (isSound(r) && asset(r.assetId)?.srcDur)}<span class="block truncate text-fg-subtle">{r.assetId ? secs(asset(r.assetId).srcDur) : t('modals.shot.noMedia')}</span>{/if}
											{#if isSound(r) && asset(r.assetId)?.src && !excluded}
												<!-- svelte-ignore a11y_media_has_caption -->
												<audio class="mt-1 h-7 w-full" controls preload="metadata" src={asset(r.assetId).src} aria-label={t('modals.shot.listen', { name: r.name })}></audio>
											{/if}
										</span>
										<label class="flex shrink-0 items-center gap-1.5 text-fg-muted">
											<input type="checkbox" checked={excluded} onchange={(e) => toggleExclude(r.id, e.currentTarget.checked)} aria-label={t('modals.shot.excludeLabel', { name: r.name })} />
											{t('modals.shot.exclude')}
										</label>
									</li>
								{/each}
							</ul>
						{:else}
							<p class="text-xs text-fg-subtle">{t('modals.shot.noInherited')}</p>
						{/if}
					</div>
					<div class="space-y-1">
						<div class="flex items-center justify-between gap-2">
							<span class="text-xs font-medium text-fg-muted">{t('modals.shot.own')}</span>
							<span class="flex items-center gap-1">
								<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => (adding = adding === 'image' ? null : 'image') }}>{t('modals.shot.addReference')}</HostUi>
								<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => (adding = adding === 'sound' ? null : 'sound') }}>{t('modals.shot.addSound')}</HostUi>
							</span>
						</div>
						{#if adding === 'image'}
							<MediaPicker title={t('modals.shot.newReference')} onpick={addOwn} removable={false} compact />
						{:else if adding === 'sound'}
							<AudioPicker title={t('modals.shot.newSound')} onpick={addSound} removable={false} />
						{/if}
						{#if draft.own.length}
							<ul class="divide-y divide-line rounded-lg border border-line-strong">
								{#each draft.own as r (r.id)}
									{@const thumb = r.assetId ? assetThumb(asset(r.assetId)) : null}
									<li class="space-y-1 px-2 py-1.5 text-xs">
										<div class="flex items-center gap-2">
											{#if thumb}<img src={thumb} alt="" class="h-7 w-12 shrink-0 rounded object-cover" />{:else}<span class="flex h-7 w-12 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name={typeIcon(r)} class="h-3.5 w-3.5 text-fg-muted" /></span>{/if}
											<input class="input vp-dense min-w-0 flex-1" bind:value={r.name} aria-label={t('modals.shot.referenceName')} />
											{#if r.space === 'identite' || r.space === SOUND_SPACE}
												<select class="vp-popup shrink-0" bind:value={r.type} aria-label={t('modals.shot.referenceType', { name: r.name })}>
													{#each r.space === SOUND_SPACE ? SOUND_TYPES : IDENTITY_TYPES as type (type)}<option value={type}>{refTypeLabel(type)}</option>{/each}
												</select>
											{/if}
											<HostUi name="IconButton" props={{ icon: 'trash', label: t('modals.shot.removeReference', { name: r.name }), tooltip: t('modals.shot.removeReferenceTip'), size: 'xs', onclick: () => removeOwn(r.id) }} />
										</div>
										<RefTags reference={{ ...r, scope: { type: 'shot', shotId: clip.id } }} class="pl-14" />
										{#if isSound(r) && asset(r.assetId)?.src}
											<div class="flex items-center gap-2 pl-14">
												<!-- svelte-ignore a11y_media_has_caption -->
												<audio class="h-7 min-w-0 flex-1" controls preload="metadata" src={asset(r.assetId).src} aria-label={t('modals.shot.listen', { name: r.name })}></audio>
												{#if asset(r.assetId).srcDur}<span class="vp-tc shrink-0 text-fg-subtle">{secs(asset(r.assetId).srcDur)}</span>{/if}
											</div>
										{/if}
									</li>
								{/each}
							</ul>
						{:else if !adding}
							<p class="text-xs text-fg-subtle">{t('modals.shot.noOwn')}</p>
						{/if}
					</div>
					<div class="space-y-1">
						<div class="text-xs font-medium text-fg-muted">{t('modals.shot.tracks')}</div>
						{#if lanes.length}
							<ul class="divide-y divide-line rounded-lg border border-line-strong">
								{#each lanes as { lane, excluded } (lane.id)}
									{@const portion = trackPortion(doc, lane.id, soundWindow)}
									<li class="flex items-center gap-2 px-2 py-1.5 text-xs {excluded ? 'opacity-60' : ''}">
										<span class="flex h-7 w-12 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name="wave" class="h-3.5 w-3.5 text-fg-muted" /></span>
										<span class="min-w-0 flex-1">
											<span class="block truncate text-fg {excluded ? 'line-through' : ''}">{laneTitle(doc.lanes, lane)}</span>
											<span class="block truncate text-fg-subtle">{portion.length ? t('modals.shot.trackPortion', { count: portion.length, start: secs(soundWindow[0]), end: secs(soundWindow[1]) }) : t('modals.shot.trackSilent', { start: secs(soundWindow[0]), end: secs(soundWindow[1]) })}</span>
										</span>
										<label class="flex shrink-0 items-center gap-1.5 text-fg-muted">
											<input type="checkbox" checked={excluded} onchange={(e) => toggleLane(lane.id, e.currentTarget.checked)} aria-label={t('modals.shot.excludeLabel', { name: laneTitle(doc.lanes, lane) })} />
											{t('modals.shot.exclude')}
										</label>
									</li>
								{/each}
							</ul>
						{:else}
							<p class="text-xs text-fg-subtle">{t('modals.shot.noTracks')}</p>
						{/if}
					</div>
					{#if vrefRows.length}
						<div class="space-y-1" data-vref-section>
							<div class="text-xs font-medium text-fg-muted">{t('modals.shot.vref.title')}</div>
							<ul class="divide-y divide-line rounded-lg border border-line-strong">
								{#each vrefRows as entry (entry.track.id)}
									{@const verdict = trackVerdict(entry)}
									{@const excluded = (draft.excludeVrefs ?? []).includes(entry.track.id)}
									{@const sentAs = (composed?.videoTracks ?? []).find((x) => x.slot === entry.slot)?.label ?? null}
									<li class="flex items-center gap-2 px-2 py-1.5 text-xs {excluded || entry.status === 'off' ? 'opacity-60' : ''}" data-vref-row={entry.slot}>
										<span class="flex h-7 w-12 shrink-0 items-center justify-center"><span class="{TAG_CLASS} vp-tc {verdict.ok ? 'border-success text-success' : 'line-through'}">{vrefLabel(entry.slot)}</span></span>
										<span class="min-w-0 flex-1">
											<span class="block truncate text-fg">{entry.track.name ? `${entry.track.name} · ${roleLabel(entry.track.role)}` : roleLabel(entry.track.role)}</span>
											<span class="block truncate {verdict.tone}">{verdict.text}</span>
										</span>
										{#if cited.includes(entry.slot)}
											<span class="vp-tc shrink-0 text-fg-subtle" data-vref-cited={entry.slot}>{sentAs ? t('modals.shot.vref.citedAs', { tag: vrefTag(entry.slot), label: sentAs }) : t('modals.shot.vref.cited', { tag: vrefTag(entry.slot) })}</span>
										{:else}
											<HostUi name="Tooltip" props={{ text: t('modals.shot.vref.citeTip', { tag: vrefTag(entry.slot) }) }}>
												<button type="button" class="h-6 shrink-0 rounded px-1.5 text-xs font-medium text-fg-muted hover:bg-surface-2 hover:text-fg" data-vref-cite={entry.slot} onclick={() => cite(entry.slot)}>{t('modals.shot.vref.cite')}</button>
											</HostUi>
										{/if}
										<label class="flex shrink-0 items-center gap-1.5 text-fg-muted">
											<input type="checkbox" checked={excluded} disabled={entry.status === 'off'} onchange={(e) => toggleVref(entry.track.id, e.currentTarget.checked)} aria-label={t('modals.shot.excludeLabel', { name: vrefLabel(entry.slot) })} />
											{t('modals.shot.exclude')}
										</label>
									</li>
								{/each}
							</ul>
							{#if ignoredRows.length}
								<div class="flex gap-2 rounded-lg border border-line-hover p-2 text-xs text-fg-muted" data-vref-ignored>
									<Icon name="info" class="mt-px h-3.5 w-3.5 shrink-0" />
									<span class="min-w-0 space-y-1">
										<span class="block">{t('modals.shot.vref.ignored', { engine: engineTitle(reception.engine), labels: ignoredLabels, count: ignoredRows.length })}</span>
										<span class="flex flex-wrap gap-x-3">
											{#if switchTarget}<button type="button" class="vp-link-hit text-left underline decoration-line-hover underline-offset-2 hover:text-fg" onclick={switchToReferences}>{t('modals.shot.vref.switch', { engine: switchTarget.label })}</button>{/if}
											<button type="button" class="vp-link-hit text-left underline decoration-line-hover underline-offset-2 hover:text-fg" onclick={() => ignoredRows.forEach((entry) => toggleVref(entry.track.id, true))}>{t('modals.shot.vref.leave', { labels: ignoredLabels, count: ignoredRows.length })}</button>
										</span>
									</span>
								</div>
							{/if}
						</div>
					{/if}
					{#if reception?.counts}
						<p class="text-xs text-fg-subtle" data-media-counts>{t('modals.shot.vref.counts', { videos: reception.counts.video, images: reception.counts.image, sounds: reception.counts.audio, maxVideos: LIMITS.video, maxImages: LIMITS.image, maxSounds: LIMITS.audio })}</p>
					{/if}
					{#if sounding && behavior}<SoundNote {behavior} />{/if}
				</section>
				<KeyframeCandidates {clip} {draft} focus={focus === 'keyframes'} onaccept={(role, assetId) => (draft[role] = assetId)} />
			</div>

			<div class="space-y-4">
				<section class="space-y-1.5">
					<label class="block space-y-1">
						<span class="vp-label">{t('modals.prompt.duration')}</span>
						<input class="input vp-dense vp-tc w-full" type="number" step="0.04" min="0.4" max={limit.max} bind:value={draft.dur} />
					</label>
					{#if limit.by === 'source'}<p class="text-xs text-fg-subtle">{t('modals.shot.durationMax', { max: secs(limit.max) })}</p>{/if}
					{#if limit.by === 'engine'}<p class="text-xs text-fg-subtle">{t('modals.shot.durationEngine', { max: secs(limit.max) })}</p>{/if}
					{#if beyondTake}<p class="text-xs text-warning">{t('modals.shot.durationBeyondTake', { take: secs(limit.take) })}</p>{/if}
				</section>
				<section class="space-y-1.5">
					<div class="vp-section-title">{t('inspector.section.frames')}</div>
					<div class="grid grid-cols-2 gap-2">
						<MediaPicker title={t('inspector.frames.first')} value={draft.first} onpick={(v) => (draft.first = v)} />
						<MediaPicker title={t('inspector.frames.last')} value={draft.last} onpick={(v) => (draft.last = v)} />
					</div>
				</section>
				<section class="space-y-1.5">
					<div class="vp-section-title">{t('generation.drafts.label')}</div>
					<DraftsField value={draft.drafts} onchange={(n) => (draft.drafts = n)} label={false} />
					<p class="text-xs text-fg-subtle">{t('modals.shot.draftsHint')}</p>
				</section>
				<section class="space-y-2" data-slot="engine" aria-labelledby="{textId}-engine">
					<div class="flex items-center justify-between gap-2">
						<span id="{textId}-engine" class="vp-section-title">{t('modals.shot.engine')}</span>
						{#if ownEngine}
							<button type="button" class="vp-link-hit text-xs text-fg-muted underline decoration-line-hover underline-offset-2 hover:text-fg" onclick={() => (draft.engine = {})}>{t('modals.shot.engineReset')}</button>
						{/if}
					</div>
					<label class="block space-y-1">
						<span class="vp-label">{t('modals.shot.engineChoice')}</span>
						<select class="vp-popup w-full" value={draftKey} onchange={(e) => pickEngine(e.currentTarget.value)}>
							<option value="">{t('modals.shot.asProject', { value: engineLabel() })}</option>
							{#if draftKey && !draftOption}<option value={draftKey}>{t('generation.engine.unavailable')}</option>{/if}
							{#each groups as g (g.label)}
								<optgroup label={g.label}>
									{#each g.options as o (o.key)}<option value={o.key}>{o.label}</option>{/each}
								</optgroup>
							{/each}
						</select>
					</label>
					<label class="block space-y-1">
						<span class="vp-label">{t('modals.shot.profile')}</span>
						<select class="vp-popup w-full" value={draft.engine.profile ?? ''} onchange={(e) => setOwn('profile', e.currentTarget.value)}>
							<option value="">{t('modals.shot.asProject', { value: doc.direction.mode })}</option>
							{#each PROFILES as m (m)}<option value={m} disabled={!profiles.includes(m)}>{m}</option>{/each}
						</select>
					</label>
					{#if draft.engine.profile && !profiles.includes(draft.engine.profile)}<p class="text-xs text-warning">{t('modals.shot.profileUnsupported', { profile: draft.engine.profile })}</p>{/if}
					<label class="block space-y-1">
						<span class="vp-label">{t('modals.shot.quality')}</span>
						<select class="vp-popup w-full" value={draft.engine.quality ?? ''} onchange={(e) => setOwn('quality', e.currentTarget.value)}>
							<option value="">{t('modals.shot.asOrder')}</option>
							<option value="draft">{t('lib.stage.draft')}</option>
							<option value="final">{t('lib.stage.final')}</option>
						</select>
					</label>
					<div class="space-y-1">
						<label class="vp-label block" for="{textId}-seed">{t('modals.shot.seed')}</label>
						<div class="flex gap-1">
							<input id="{textId}-seed" class="input vp-dense vp-tc min-w-0 flex-1" type="number" min="0" max={SEED_MAX} step="1" placeholder={t('modals.shot.seedRandom')} value={draft.engine.seed ?? ''} oninput={(e) => setSeed(e.currentTarget.value)} />
							<HostUi name="IconButton" props={{ icon: 'refresh', label: t('modals.shot.seedPick'), tooltip: t('modals.shot.seedPick'), size: 'sm', onclick: () => (draft.engine = { ...draft.engine, seed: randomSeed() }) }} />
						</div>
						<p class="text-xs text-fg-subtle">{t('modals.shot.seedHint')}</p>
					</div>
				</section>
			</div>
		</div>
		{#snippet footer()}
			{#if takes.length && changed}<span class="mr-auto flex items-center gap-1.5 text-xs text-warning"><Icon name="alert" class="h-3.5 w-3.5" />{t('modals.shot.staleWarning')}</span>{/if}
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: () => (ui.modal = null) }}>{t('modals.prompt.cancel')}</HostUi>
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', onclick: saveIt }}>{t('modals.prompt.save')}</HostUi>
		{/snippet}
	</Modal>
{/if}

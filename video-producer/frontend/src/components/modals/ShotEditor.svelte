<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, asset, clipLabel, globalPrompt, promptIssues, relayout, secs, sourceLength } from '../../lib/state.svelte.js';
	import { takesOf, engineLabel } from '../../lib/production.svelte.js';
	import { families, refTypeLabel } from '../../lib/references.js';
	import { assetThumb } from '../../lib/media.js';
	import { applyShotDraft, inputsChanged, shotDraft, shotReferences } from '../../lib/shots.js';
	import { ulid } from '../../lib/ulid.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import ImagePicker from '../shots/ImagePicker.svelte';

	let { id, draft: kept = null, baseline: keptBaseline = null } = $props();

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
	let adding = $state(false);

	const takes = $derived(clip ? takesOf(clip) : []);
	const family = (space) => families.find((f) => f.id === space) ?? null;
	const inherited = $derived(clip ? shotReferences(doc, clip, draft.exclude).inherited : []);
	const sentCount = $derived(draft.own.length + inherited.filter((x) => !x.excluded).length);
	const maxDur = $derived(clip ? sourceLength(clip) - clip.srcIn : 60);
	const issues = $derived(clip ? promptIssues({ text: draft.text, start: clip.start, dur: +draft.dur, shotId: clip.id }) : []);
	const changed = $derived(Boolean(baseline) && inputsChanged(baseline, draft));

	function toggleExclude(refId, on) {
		draft.exclude = on ? [...draft.exclude, refId] : draft.exclude.filter((x) => x !== refId);
	}

	function addOwn(assetId) {
		adding = false;
		if (!assetId) return;
		const a = asset(assetId);
		draft.own = [...draft.own, { id: ulid(), name: a?.name || t('lib.default.reference', { type: refTypeLabel(IDENTITY_TYPES[0]) }), space: 'identite', type: IDENTITY_TYPES[0], assetId, role: 'Identité' }];
	}

	function removeOwn(refId) {
		draft.own = draft.own.filter((r) => r.id !== refId);
	}

	function saveIt() {
		if (!clip) return (ui.modal = null);
		act(() => {
			const { resized } = applyShotDraft(doc, clip, baseline, $state.snapshot(draft), { makeId: ulid, maxDur, engine: doc.engine });
			if (resized) relayout();
		});
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
					<textarea id={textId} class="input w-full text-md" rows="5" bind:value={draft.text} autofocus placeholder={t('modals.prompt.placeholder')}></textarea>
					{#each issues as issue, i (i)}
						{#if issue.level === 'conflict'}
							<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{issue.text}</HostUi>
						{/if}
					{/each}
					<details class="rounded-lg border border-line-strong p-2.5 text-xs">
						<summary class="-mb-1 -mt-1 min-h-6 cursor-pointer py-1 font-medium text-fg-muted">{t('modals.prompt.global')}</summary>
						<p class="mt-1.5 leading-5 text-fg-subtle">{globalPrompt()}</p>
					</details>
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
									{@const f = family(r.space)}
									{@const thumb = r.assetId ? assetThumb(asset(r.assetId)) : null}
									<li class="flex items-center gap-2 px-2 py-1.5 text-xs {excluded ? 'opacity-60' : ''}">
										{#if thumb}<img src={thumb} alt="" class="h-7 w-12 shrink-0 rounded object-cover" />{:else}<span class="flex h-7 w-12 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name={f?.icon ?? 'bookmark'} class="h-3.5 w-3.5 text-fg-muted" /></span>{/if}
										<span class="min-w-0 flex-1">
											<span class="block truncate text-fg {excluded ? 'line-through' : ''}">{r.name}</span>
											<span class="block truncate text-fg-subtle">{f?.label ?? r.space} · {refTypeLabel(r.type)}{r.assetId ? '' : ` · ${t('modals.shot.noMedia')}`}</span>
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
							<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => (adding = !adding) }}>{t('modals.shot.addReference')}</HostUi>
						</div>
						{#if adding}
							<ImagePicker title={t('modals.shot.newReference')} onpick={addOwn} removable={false} compact />
						{/if}
						{#if draft.own.length}
							<ul class="divide-y divide-line rounded-lg border border-line-strong">
								{#each draft.own as r (r.id)}
									{@const f = family(r.space)}
									{@const thumb = r.assetId ? assetThumb(asset(r.assetId)) : null}
									<li class="flex items-center gap-2 px-2 py-1.5 text-xs">
										{#if thumb}<img src={thumb} alt="" class="h-7 w-12 shrink-0 rounded object-cover" />{:else}<span class="flex h-7 w-12 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name={f?.icon ?? 'bookmark'} class="h-3.5 w-3.5 text-fg-muted" /></span>{/if}
										<input class="input vp-dense min-w-0 flex-1" bind:value={r.name} aria-label={t('modals.shot.referenceName')} />
										{#if r.space === 'identite'}
											<select class="vp-popup shrink-0" bind:value={r.type} aria-label={t('modals.shot.referenceType', { name: r.name })}>
												{#each IDENTITY_TYPES as type (type)}<option value={type}>{refTypeLabel(type)}</option>{/each}
											</select>
										{:else}
											<span class="shrink-0 text-fg-subtle">{f?.label ?? r.space} · {refTypeLabel(r.type)}</span>
										{/if}
										<HostUi name="IconButton" props={{ icon: 'trash', label: t('modals.shot.removeReference', { name: r.name }), tooltip: t('modals.shot.removeReferenceTip'), size: 'xs', onclick: () => removeOwn(r.id) }} />
									</li>
								{/each}
							</ul>
						{:else if !adding}
							<p class="text-xs text-fg-subtle">{t('modals.shot.noOwn')}</p>
						{/if}
					</div>
				</section>
			</div>

			<div class="space-y-4">
				<section class="space-y-1.5">
					<label class="block space-y-1">
						<span class="vp-label">{t('modals.prompt.duration')}</span>
						<input class="input vp-dense vp-tc w-full" type="number" step="0.04" min="0.4" max={maxDur} bind:value={draft.dur} />
					</label>
					{#if clip.assetId && asset(clip.assetId)?.srcDur}<p class="text-xs text-fg-subtle">{t('modals.shot.durationMax', { max: secs(maxDur) })}</p>{/if}
				</section>
				<section class="space-y-1.5">
					<div class="vp-section-title">{t('inspector.section.frames')}</div>
					<div class="grid grid-cols-2 gap-2">
						<ImagePicker title={t('inspector.frames.first')} value={draft.first} onpick={(v) => (draft.first = v)} />
						<ImagePicker title={t('inspector.frames.last')} value={draft.last} onpick={(v) => (draft.last = v)} />
					</div>
				</section>
				<section class="space-y-1.5">
					<div class="vp-section-title">{t('generation.drafts.label')}</div>
					<DraftsField value={draft.drafts} onchange={(n) => (draft.drafts = n)} label={false} />
					<p class="text-xs text-fg-subtle">{t('modals.shot.draftsHint')}</p>
				</section>
				<section class="space-y-1.5" data-slot="engine">
					<div class="vp-section-title">{t('modals.shot.engine')}</div>
					<div class="rounded-lg border border-line-strong p-2 text-xs text-fg-muted">
						<div class="truncate text-fg">{engineLabel()}</div>
						<div>{t('modals.shot.engineProject', { profile: doc.direction.mode })}</div>
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

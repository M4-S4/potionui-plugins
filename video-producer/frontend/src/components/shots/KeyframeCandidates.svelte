<script>
	import { tick, untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t, formatDuration, formatNumber } from '../../i18n/index.svelte.js';
	import { doc, ui, asset, clipLabel } from '../../lib/state.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { FAILURE_CODES, optionFor } from '../../lib/generation.js';
	import { effectiveEngine } from '../../lib/engine.js';
	import { engineChoices, engineLabel } from '../../lib/production.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import { DEFAULT_CANDIDATES, MAX_CANDIDATES, MIN_CANDIDATES, NOTE_CODES, PRESET_STATES, acceptedRoles, blocked, chosenOption, draftPictures, inFlight, presetAbsent, requestBody, usable } from '../../lib/keyframes.js';
	import { keyframeState, keyframeChoices, keyframeChoice, chooseKeyframeOption, openKeyframes, scheduleKeyframeEstimate, startCandidates, acceptCandidate, toggleRejected, retryCandidate, cancelCandidate, deleteCandidate } from '../../lib/keyframes.svelte.js';
	import { MAKE, RETRIEVE, draftChained, frameNotes, retrieveChoices, retrieves } from '../../lib/shotimages.js';
	import { neighborsOf, retrieveImages, shotImages } from '../../lib/shotimages.svelte.js';
	import { PICTURE_ICONS, TAG_CLASS } from '../../lib/reftags.js';
	import Icon from '../Icon.svelte';

	let { clip, draft, onaccept, focus = false } = $props();

	const id = $props.id();
	let open = $state(false);
	let choice = $state('first');
	let count = $state(DEFAULT_CANDIDATES);
	let shown = false;
	let focused = false;
	let root = $state(null);

	const making = $derived(!retrieves(choice));
	const options = $derived(keyframeChoices());
	const stored = $derived(keyframeChoice());
	const absent = $derived(presetAbsent(options, stored));
	const option = $derived(absent ? null : chosenOption(options, stored));
	const runnable = $derived(option && !option.disabled ? option : null);
	const target = $derived(runnable ?? (absent ? { key: '', preset: stored.preset, model: stored.model, maxImages: null } : null));
	const pictures = $derived(draftPictures(doc, clip, draft, choice));
	const limit = $derived(runnable?.maxImages ?? pictures.length);
	const body = $derived(making && target ? requestBody({ option: target, role: choice, count, prompt: draft.text, pictures }) : null);
	const estimate = $derived(keyframeState.estimate);
	const candidates = $derived(keyframeState.list.filter((take) => take.shotId === clip.id));
	const flying = $derived(candidates.filter(inFlight).length);
	const ready = $derived(Boolean(runnable) && pictures.length > 0 && !blocked(estimate) && !keyframeState.starting && !keyframeState.estimating);
	const sources = $derived(neighborsOf(clip, draft));
	const retrieveOptions = $derived(retrieveChoices(sources));
	const picked = $derived(retrieveOptions.find((o) => o.id === choice) ?? null);
	const engine = $derived(effectiveEngine({ ...clip, engine: draft.engine }, doc));
	const engineOption = $derived(optionFor(engineChoices(), engine));
	const linked = $derived(draftChained(doc, draft) && sources.previous.state !== 'none' && sources.previous.state !== 'empty');
	const notes = $derived(frameNotes({ option: engineOption, profile: engine.profile, choice, hasStart: Boolean(draft.first), chained: linked }));
	const usableOptions = $derived(options.filter((o) => !o.disabled));
	const groups = $derived.by(() => {
		const list = [];
		for (const o of usableOptions) {
			const label = o.group ?? t('keyframes.local');
			let group = list.find((g) => g.label === label);
			if (!group) list.push((group = { label, options: [] }));
			group.options.push(o);
		}
		const off = options.filter((o) => o.disabled);
		if (off.length) list.push({ label: t('keyframes.unavailable'), options: off });
		return list;
	});

	$effect(() => {
		const shotId = clip.id;
		return untrack(() => openKeyframes(shotId));
	});

	$effect(() => {
		if (shown || !candidates.length) return;
		shown = true;
		open = true;
	});

	$effect(() => {
		if (open && body) scheduleKeyframeEstimate(body);
	});

	$effect(() => {
		if (!focus || !root || focused) return;
		focused = true;
		open = true;
		tick().then(() => root?.scrollIntoView({ block: 'start' }));
	});

	const roleText = (value) => (value === 'last' ? t('keyframes.role.last') : t('keyframes.role.first'));
	const retrieveText = (side) => (side === 'previous' ? t('keyframes.retrieve.previous') : side === 'next' ? t('keyframes.retrieve.next') : t('keyframes.retrieve.neighbors'));
	const choiceText = (value) => (value === 'both' ? t('keyframes.role.both') : retrieves(value) ? retrieveText(value) : roleText(value));

	function optionLabel(o) {
		if (o.disabled) return t('keyframes.optionOff', { name: o.label, reason: t(`keyframes.reason.${o.reason}`) });
		return o.mode === 'img2img' ? t('keyframes.optionOne', { name: o.label }) : o.label;
	}

	function unusableText(o) {
		return t(`keyframes.unusable.${o.reason}`, { fields: (o.missing ?? []).join(', ') || '—' });
	}

	function sourceReason(source) {
		const shot = source.shot ? clipLabel(source.shot) : '';
		if (source.state === 'none') return source.side === 'previous' ? t('keyframes.retrieve.reason.first') : t('keyframes.retrieve.reason.last');
		if (source.state === 'empty') return t('keyframes.retrieve.reason.empty', { shot });
		if (source.state === 'pending' && source.side === 'next') return t('keyframes.retrieve.reason.pendingNext', { shot });
		return '';
	}

	function choiceReason(o) {
		if (o.enabled) return '';
		return o.sources.map(sourceReason).filter(Boolean).join(' ');
	}

	function sourceText(source) {
		const shot = clipLabel(source.shot);
		if (source.side === 'previous') return t(`keyframes.retrieve.previousState.${source.state}`, { shot });
		if (source.state === 'ready' && source.image) return t('keyframes.retrieve.nextState.start', { shot });
		return t(`keyframes.retrieve.nextState.${source.state}`, { shot });
	}

	function sourceThumb(source) {
		if (source.image) return assetThumb(source.image);
		return source.source ? assetThumb(asset(source.source.assetId)) : null;
	}

	function noteText(note) {
		const data = note.data ?? {};
		if (note.code === 'preset_missing') return t(`keyframes.state.${PRESET_STATES.includes(data.state) ? data.state : 'unknown'}`);
		if (note.code === 'preset_unusable') return option?.disabled ? unusableText(option) : t('keyframes.note.preset_unusable');
		if (note.code === 'missing_models') return t('keyframes.note.missing_models', { fields: (data.fields ?? []).join(', ') });
		if (note.code === 'references_trimmed') return t('keyframes.note.references_trimmed', { sent: data.sent ?? limit, found: data.found ?? pictures.length });
		if (note.code === 'aspect_mismatch') return t('keyframes.note.aspect_mismatch', { size: String(data.size ?? '—').replace('x', '×'), aspect: data.aspect ?? doc.aspect });
		if (note.code === 'quota_exceeded') return t('keyframes.note.quota_exceeded', { need: formatNumber(data.needed_minutes ?? 0, { maximumFractionDigits: 1 }), remaining: formatNumber(data.remaining ?? 0, { maximumFractionDigits: 1 }) });
		if (note.code === 'reference_unavailable') return t('keyframes.note.reference_unavailable', { name: asset(data.asset_id)?.name ?? data.asset_id ?? '—' });
		return NOTE_CODES.includes(note.code) ? t(`keyframes.note.${note.code}`) : note.message;
	}

	const summary = $derived.by(() => {
		if (!estimate) return [];
		const lines = [];
		const { time, vram, quota, cost } = estimate;
		lines.push(time.seconds !== null ? t('keyframes.estimate.time', { duration: formatDuration(time.seconds), each: formatDuration(time.perCandidate), count: time.samples }) : t('keyframes.estimate.timeUnknown'));
		const memory = { gb: formatNumber(vram.estimateGb ?? 0, { maximumFractionDigits: 1 }), free: formatNumber(vram.freeGb ?? 0, { maximumFractionDigits: 1 }) };
		if (!runnable?.cloud && vram.estimateGb !== null) lines.push(vram.streams ? t('keyframes.estimate.memoryStream', memory) : t('keyframes.estimate.memory', memory));
		if (quota.applies) lines.push(quota.exempt ? t('keyframes.estimate.quotaExempt') : t('keyframes.estimate.quota', { need: formatNumber(quota.neededMinutes, { maximumFractionDigits: 1 }) }));
		else lines.push(t('keyframes.estimate.cloud'));
		if (cost) lines.push(cost.known && cost.totalUsd !== null ? t('keyframes.estimate.cost', { cost: `$${cost.totalUsd}` }) : t('keyframes.estimate.costUnknown'));
		return lines;
	});

	function thumbOf(picture) {
		const a = asset(picture.assetId);
		return a ? assetThumb(a) : null;
	}

	function stateText(take) {
		if (take.status === 'queued') return t('keyframes.card.queued');
		if (take.status === 'running') return t('keyframes.card.running', { percent: Math.round(Math.min(100, Math.max(0, take.progress ?? 0))) });
		if (take.status === 'failed' && take.errorCode === 'no_output') return t('keyframes.card.noOutput');
		if (take.status === 'failed') return FAILURE_CODES.includes(take.errorCode) ? t(`generation.failed.${take.errorCode}`, { id: take.generationId ?? '—' }) : take.errorMessage || t('keyframes.card.failed');
		if (take.status === 'cancelled') return t('keyframes.card.cancelled');
		return '';
	}

	function accept(take, which) {
		acceptCandidate(take, which, onaccept);
	}

	const makeLabel = $derived(choice === 'both' ? t('keyframes.makeBoth', { count }) : t('keyframes.make', { count, role: roleText(choice).toLowerCase() }));
	const linkOnly = $derived(choice === 'previous' && sources.previous.state === 'pending');
	const turnsChainOn = $derived(Boolean(picked?.enabled) && (choice === 'previous' || choice === 'neighbors') && !draftChained(doc, draft));
</script>

<section class="space-y-2" aria-labelledby="{id}-title" data-shot-images bind:this={root}>
	<div class="flex items-center justify-between gap-2">
		<!-- svelte-ignore a11y_autofocus -->
		<button type="button" class="flex min-h-6 items-center gap-1.5 text-left" aria-expanded={open} aria-controls="{id}-body" autofocus={focus} onclick={() => (open = !open)}>
			<Icon name={open ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5 text-fg-muted" />
			<span id="{id}-title" class="vp-section-title">{t('keyframes.title')}</span>
		</button>
		{#if flying}<span class="flex items-center gap-1 text-xs text-signal"><span class="h-1.5 w-1.5 rounded-full bg-signal"></span>{t('keyframes.flying', { count: flying })}</span>{/if}
	</div>
	{#if open}
		<div id="{id}-body" class="space-y-2.5 rounded-lg border border-line-strong p-2.5">
			<p class="text-xs leading-5 text-fg-subtle">{t('keyframes.hint')}</p>
			<div class="space-y-1">
				<span class="vp-label block">{t('keyframes.roleLabel')}</span>
				{#each [['make', MAKE, t('keyframes.makeGroup')], ['retrieve', RETRIEVE, t('keyframes.retrieveGroup')]] as [group, values, label] (group)}
					<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
						<span class="w-36 shrink-0 text-xs text-fg-subtle">{label}</span>
						<div class="flex rounded-md border border-line-strong p-0.5" role="group" aria-label={label} data-image-choices={group}>
							{#each values as value (value)}
								{@const off = group === 'retrieve' && !retrieveOptions.find((o) => o.id === value)?.enabled && !retrieveOptions.find((o) => o.id === value)?.done}
								<button
									type="button"
									class="h-6 rounded px-2 text-xs disabled:cursor-default {choice === value ? 'bg-surface-3 font-medium text-fg' : 'text-fg-muted hover:text-fg'} {off ? 'opacity-50' : ''}"
									aria-pressed={choice === value}
									disabled={off}
									title={off ? choiceReason(retrieveOptions.find((o) => o.id === value)) : null}
									data-image-choice={value}
									onclick={() => (choice = value)}>{choiceText(value)}</button
								>
							{/each}
						</div>
					</div>
				{/each}
				{#each retrieveOptions.filter((o) => o.id !== 'neighbors' && !o.enabled && !o.done) as o (o.id)}
					<p class="text-xs text-fg-subtle" data-retrieve-reason={o.id}>{retrieveText(o.id)} · {choiceReason(o)}</p>
				{/each}
			</div>
			{#each notes as note (note)}
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{t(`keyframes.frameNote.${note}`, { engine: engineOption?.label ?? engineLabel() })}</HostUi>
			{/each}
			{#if !making && picked}
				<div class="space-y-1.5" data-retrieve-preview>
					{#each picked.sources as s (s.side)}
						{@const thumb = sourceThumb(s)}
						<div class="flex items-center gap-2 rounded-md border border-line-strong p-1.5 text-xs">
							<span class="block h-9 w-16 shrink-0 overflow-hidden rounded bg-surface-3">{#if thumb}<img src={thumb} alt="" class="h-full w-full object-cover" />{:else}<span class="flex h-full items-center justify-center text-fg-subtle"><Icon name={s.side === 'previous' ? 'film' : 'image'} class="h-3.5 w-3.5" /></span>{/if}</span>
							<span class="min-w-0 flex-1 {s.state === 'stale' ? 'text-warning' : 'text-fg-muted'}">{s.shot ? sourceText(s) : sourceReason(s)}</span>
						</div>
					{/each}
					{#if turnsChainOn}<p class="text-xs text-fg-subtle">{t('keyframes.retrieve.chainOn')}</p>{/if}
					<div class="flex justify-end">
						<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: linkOnly ? 'clock' : 'download', disabled: !picked.enabled || picked.done || shotImages.busy, loading: shotImages.busy, onclick: () => retrieveImages(clip, draft, choice) }}>{linkOnly ? t('keyframes.retrieve.link') : t('keyframes.retrieve.action')}</HostUi>
					</div>
				</div>
			{:else if !options.length && !absent}
				<HostUi name="Alert" props={{ variant: 'info', density: 'compact', icon: true }}>{ui.isAdmin ? t('keyframes.empty.admin') : t('keyframes.empty.user')}</HostUi>
			{:else}
				<div class="grid grid-cols-[1fr_auto] items-end gap-2">
					<label class="block min-w-0 space-y-1">
						<span class="vp-label">{t('keyframes.model')}</span>
						<select class="vp-popup w-full" value={option?.key ?? ''} onchange={(e) => chooseKeyframeOption(e.currentTarget.value)} data-image-model>
							{#if absent}<option value="">{t('keyframes.modelUnavailable')}</option>{/if}
							{#each groups as g (g.label)}
								<optgroup label={g.label}>
									{#each g.options as o (o.key)}<option value={o.key} disabled={o.disabled}>{optionLabel(o)}</option>{/each}
								</optgroup>
							{/each}
						</select>
					</label>
					<label class="block space-y-1">
						<span class="vp-label">{choice === 'both' ? t('keyframes.countEach') : t('keyframes.count')}</span>
						<select class="vp-popup" bind:value={count}>
							{#each Array.from({ length: MAX_CANDIDATES - MIN_CANDIDATES + 1 }, (_, i) => MIN_CANDIDATES + i) as n (n)}<option value={n}>{n}</option>{/each}
						</select>
					</label>
				</div>
				{#if absent}
					<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{t('keyframes.absent')}</HostUi>
				{:else if option?.disabled}
					<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{unusableText(option)}</HostUi>
				{/if}
				<div class="space-y-1">
					<div class="text-xs font-medium text-fg-muted">{t('keyframes.pictures')}</div>
					{#if pictures.length}
						<ul class="flex flex-wrap gap-1.5" aria-label={t('keyframes.pictures')}>
							{#each pictures as p, i (p.assetId)}
								{@const thumb = thumbOf(p)}
								{@const left = i >= limit}
								<li class="w-24 text-2xs {left ? 'opacity-50' : ''}" title={left ? t('keyframes.leftOut', { max: limit }) : p.name}>
									<span class="relative block overflow-hidden rounded border border-line-strong">
										{#if thumb}<img src={thumb} alt="" class="aspect-video w-full object-cover" />{:else}<span class="flex aspect-video w-full items-center justify-center bg-surface-3"><Icon name="image" class="h-3.5 w-3.5 text-fg-muted" /></span>{/if}
										<span class="absolute left-0.5 top-0.5 rounded bg-black/60 px-1 font-semibold text-white">{i + 1}</span>
									</span>
									<span class="mt-0.5 {TAG_CLASS}" data-picture-role={p.role}><Icon name={PICTURE_ICONS[p.role]} class="h-3 w-3 shrink-0" /><span class="truncate">{p.role === 'frame' && choice === 'both' ? t('keyframes.pictureFrameEnd') : t(`keyframes.pictureRole.${p.role}`)}</span></span>
									<span class="block truncate text-fg-subtle {left ? 'line-through' : ''}">{p.name || asset(p.assetId)?.name || '—'}</span>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="text-xs text-fg-subtle">{t('keyframes.picturesNone')}</p>
					{/if}
				</div>
				{#if keyframeState.error}
					<p class="text-xs text-danger">{t('keyframes.estimate.failed')}</p>
				{:else if estimate && runnable}
					<div class="space-y-1 text-xs">
						<p class="text-fg-muted">{summary.join(' · ')}</p>
						{#each estimate.blocks as note, i (i)}
							<p class="flex gap-1.5 text-danger"><Icon name="alert" class="mt-0.5 h-3.5 w-3.5 shrink-0" />{noteText(note)}</p>
						{/each}
						{#each estimate.warnings.filter((w) => w.code !== 'time_unknown') as note, i (i)}
							<p class="flex gap-1.5 text-warning"><Icon name="info" class="mt-0.5 h-3.5 w-3.5 shrink-0" />{noteText(note)}</p>
						{/each}
					</div>
				{:else if keyframeState.estimating}
					<p class="text-xs text-fg-subtle">{t('keyframes.estimate.loading')}</p>
				{/if}
				<div class="flex justify-end">
					<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'sparkles', disabled: !ready, loading: keyframeState.starting, onclick: () => body && startCandidates(body) }}>{makeLabel}</HostUi>
				</div>
			{/if}
			{#if candidates.length}
				<ul class="grid grid-cols-2 gap-2" aria-label={t('keyframes.gallery')}>
					{#each candidates as take (take.id)}
						{@const roles = acceptedRoles(take, draft)}
						{@const done = usable(take)}
						<li class="overflow-hidden rounded-lg border {roles.length ? 'border-signal ring-1 ring-signal' : 'border-line-strong'} {take.label === 'rejected' ? 'opacity-60' : ''}">
							<div class="relative bg-surface-3">
								{#if done}
									<a href={take.url} target="_blank" rel="noopener" aria-label={t('keyframes.card.open', { variant: take.variant })}>
										<img src={take.thumbUrl ?? take.url} alt="" class="aspect-video w-full object-contain" />
									</a>
								{:else}
									<span class="flex aspect-video w-full flex-col items-center justify-center gap-1 px-2 text-center text-xs {take.status === 'failed' ? 'text-danger' : 'text-fg-muted'}">
										{#if take.status === 'running'}<HostUi name="Spinner" props={{ size: 'sm' }} />{:else}<Icon name={take.status === 'failed' ? 'alert' : take.status === 'cancelled' ? 'x' : 'history'} class="h-4 w-4" />{/if}
										<span class="line-clamp-3">{stateText(take)}</span>
									</span>
								{/if}
								<span class="absolute left-1 top-1 rounded bg-black/60 px-1 text-xs font-semibold text-white">{take.variant}</span>
								{#if take.frameRole}<span class="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-2xs text-white" data-frame-role={take.frameRole}>{take.frameRole === 'last' ? t('keyframes.card.forLast') : t('keyframes.card.forFirst')}</span>{/if}
								{#if roles.length}<span class="absolute right-1 top-1 rounded bg-signal px-1 text-2xs font-medium text-white">{roles.map(roleText).join(' · ')}</span>{/if}
							</div>
							<div class="flex flex-wrap items-center gap-0.5 border-t border-line p-0.5">
								{#if done}
									<HostUi name="Button" props={{ variant: roles.includes('first') ? 'secondary' : 'ghost', size: 'xs', onclick: () => accept(take, 'first') }}>{t('keyframes.card.useFirst')}</HostUi>
									<HostUi name="Button" props={{ variant: roles.includes('last') ? 'secondary' : 'ghost', size: 'xs', onclick: () => accept(take, 'last') }}>{t('keyframes.card.useLast')}</HostUi>
								{:else if inFlight(take)}
									<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => cancelCandidate(take) }}>{t('keyframes.card.cancel')}</HostUi>
								{:else}
									<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'refresh', onclick: () => retryCandidate(take) }}>{t('keyframes.card.retry')}</HostUi>
								{/if}
								<span class="ml-auto flex items-center gap-0.5">
									{#if done}
										<HostUi name="IconButton" props={{ icon: hostIconName('thumb-down'), label: take.label === 'rejected' ? t('keyframes.card.restore', { variant: take.variant }) : t('keyframes.card.reject', { variant: take.variant }), tooltip: take.label === 'rejected' ? t('keyframes.card.restoreTip') : t('keyframes.card.rejectTip'), size: 'xs', class: 'vp-toggle', ariaPressed: take.label === 'rejected', onclick: () => toggleRejected(take) }} />
									{/if}
									<HostUi name="IconButton" props={{ icon: 'trash', label: t('keyframes.card.delete', { variant: take.variant }), tooltip: t('keyframes.card.deleteTip'), size: 'xs', onclick: () => deleteCandidate(take) }} />
								</span>
							</div>
						</li>
					{/each}
				</ul>
			{:else if keyframeState.loaded && making && (options.length || absent)}
				<p class="text-xs text-fg-subtle">{t('keyframes.none')}</p>
			{/if}
		</div>
	{/if}
</section>

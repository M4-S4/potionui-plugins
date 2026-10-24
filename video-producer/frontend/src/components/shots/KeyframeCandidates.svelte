<script>
	import { untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t, formatDuration, formatNumber } from '../../i18n/index.svelte.js';
	import { doc, ui, asset } from '../../lib/state.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { FAILURE_CODES } from '../../lib/generation.js';
	import { hostIconName } from '../../lib/icons.js';
	import { DEFAULT_CANDIDATES, MAX_CANDIDATES, MIN_CANDIDATES, NOTE_CODES, PRESET_STATES, ROLES, acceptedRoles, blocked, chosenOption, draftPictures, inFlight, presetAbsent, requestBody, usable } from '../../lib/keyframes.js';
	import { keyframeState, keyframeChoices, keyframeChoice, chooseKeyframeOption, openKeyframes, scheduleKeyframeEstimate, startCandidates, acceptCandidate, toggleRejected, retryCandidate, cancelCandidate, deleteCandidate } from '../../lib/keyframes.svelte.js';
	import Icon from '../Icon.svelte';

	let { clip, draft, onaccept } = $props();

	const id = $props.id();
	let open = $state(false);
	let role = $state('first');
	let count = $state(DEFAULT_CANDIDATES);
	let shown = false;

	const options = $derived(keyframeChoices());
	const stored = $derived(keyframeChoice());
	const absent = $derived(presetAbsent(options, stored));
	const option = $derived(absent ? null : chosenOption(options, stored));
	const target = $derived(option ?? (absent ? { key: '', preset: stored.preset, model: stored.model, maxImages: null } : null));
	const pictures = $derived(draftPictures(doc, clip, draft, role));
	const limit = $derived(option?.maxImages ?? pictures.length);
	const body = $derived(target ? requestBody({ option: target, role, count, prompt: draft.text, pictures }) : null);
	const estimate = $derived(keyframeState.estimate);
	const candidates = $derived(keyframeState.list.filter((take) => take.shotId === clip.id));
	const flying = $derived(candidates.filter(inFlight).length);
	const ready = $derived(Boolean(option) && pictures.length > 0 && !blocked(estimate) && !keyframeState.starting && !keyframeState.estimating);
	const groups = $derived.by(() => {
		const list = [];
		for (const o of options) {
			const label = o.group ?? t('keyframes.local');
			let group = list.find((g) => g.label === label);
			if (!group) list.push((group = { label, options: [] }));
			group.options.push(o);
		}
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

	const roleText = (value) => (value === 'last' ? t('keyframes.role.last') : t('keyframes.role.first'));

	function noteText(note) {
		const data = note.data ?? {};
		if (note.code === 'preset_missing') return t(`keyframes.state.${PRESET_STATES.includes(data.state) ? data.state : 'unknown'}`);
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
		if (!option?.cloud && vram.estimateGb !== null) lines.push(vram.streams ? t('keyframes.estimate.memoryStream', memory) : t('keyframes.estimate.memory', memory));
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
</script>

<section class="space-y-2" aria-labelledby="{id}-title">
	<div class="flex items-center justify-between gap-2">
		<button type="button" class="flex min-h-6 items-center gap-1.5 text-left" aria-expanded={open} aria-controls="{id}-body" onclick={() => (open = !open)}>
			<Icon name={open ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5 text-fg-muted" />
			<span id="{id}-title" class="vp-section-title">{t('keyframes.title')}</span>
		</button>
		{#if flying}<span class="flex items-center gap-1 text-xs text-signal"><span class="h-1.5 w-1.5 rounded-full bg-signal"></span>{t('keyframes.flying', { count: flying })}</span>{/if}
	</div>
	{#if open}
		<div id="{id}-body" class="space-y-2.5 rounded-lg border border-line-strong p-2.5">
			<p class="text-xs leading-5 text-fg-subtle">{t('keyframes.hint')}</p>
			{#if !options.length && !absent}
				<HostUi name="Alert" props={{ variant: 'info', density: 'compact', icon: true }}>{ui.isAdmin ? t('keyframes.empty.admin') : t('keyframes.empty.user')}</HostUi>
			{:else}
				<div class="grid grid-cols-[1fr_auto_auto] items-end gap-2">
					<label class="block min-w-0 space-y-1">
						<span class="vp-label">{t('keyframes.model')}</span>
						<select class="vp-popup w-full" value={target?.key ?? ''} onchange={(e) => chooseKeyframeOption(e.currentTarget.value)}>
							{#if absent}<option value="">{t('keyframes.modelUnavailable')}</option>{/if}
							{#each groups as g (g.label)}
								<optgroup label={g.label}>
									{#each g.options as o (o.key)}<option value={o.key}>{o.label}</option>{/each}
								</optgroup>
							{/each}
						</select>
					</label>
					<div class="space-y-1">
						<span class="vp-label block">{t('keyframes.roleLabel')}</span>
						<div class="flex rounded-md border border-line-strong p-0.5" role="group" aria-label={t('keyframes.roleLabel')}>
							{#each ROLES as r (r)}
								<button type="button" class="h-6 rounded px-2 text-xs {role === r ? 'bg-surface-3 font-medium text-fg' : 'text-fg-muted hover:text-fg'}" aria-pressed={role === r} onclick={() => (role = r)}>{roleText(r)}</button>
							{/each}
						</div>
					</div>
					<label class="block space-y-1">
						<span class="vp-label">{t('keyframes.count')}</span>
						<select class="vp-popup" bind:value={count}>
							{#each Array.from({ length: MAX_CANDIDATES - MIN_CANDIDATES + 1 }, (_, i) => MIN_CANDIDATES + i) as n (n)}<option value={n}>{n}</option>{/each}
						</select>
					</label>
				</div>
				{#if absent}
					<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{t('keyframes.absent')}</HostUi>
				{/if}
				<div class="space-y-1">
					<div class="text-xs font-medium text-fg-muted">{t('keyframes.pictures')}</div>
					{#if pictures.length}
						<ul class="flex flex-wrap gap-1.5" aria-label={t('keyframes.pictures')}>
							{#each pictures as p, i (p.assetId)}
								{@const thumb = thumbOf(p)}
								{@const left = i >= limit}
								<li class="w-20 text-2xs {left ? 'opacity-50' : ''}" title={left ? t('keyframes.leftOut', { max: limit }) : p.name}>
									<span class="relative block overflow-hidden rounded border border-line-strong">
										{#if thumb}<img src={thumb} alt="" class="aspect-video w-full object-cover" />{:else}<span class="flex aspect-video w-full items-center justify-center bg-surface-3"><Icon name="image" class="h-3.5 w-3.5 text-fg-muted" /></span>{/if}
										<span class="absolute left-0.5 top-0.5 rounded bg-black/60 px-1 font-semibold text-white">{i + 1}</span>
									</span>
									<span class="block truncate text-fg-muted">{t(`keyframes.pictureRole.${p.role}`)}</span>
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
				{:else if estimate}
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
					<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'sparkles', disabled: !ready, loading: keyframeState.starting, onclick: () => body && startCandidates(body) }}>{t('keyframes.make', { count, role: roleText(role).toLowerCase() })}</HostUi>
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
			{:else if keyframeState.loaded && (options.length || absent)}
				<p class="text-xs text-fg-subtle">{t('keyframes.none')}</p>
			{/if}
		</div>
	{/if}
</section>

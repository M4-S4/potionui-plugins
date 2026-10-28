<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, asset, select, clipLabel } from '../../lib/state.svelte.js';
	import { refTypeLabel, shotReceptionFor, engineTitle, receptionVerdict, refMediaKind, setSent, addShotReference } from '../../lib/references.js';
	import { LIMITS, takesReferences } from '../../lib/reception.js';
	import { isGlobal, shotReferences } from '../../lib/shots.js';
	import { assetThumb, clipThumb } from '../../lib/media.js';
	import { typeIcon } from '../../lib/reftags.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let { clip } = $props();

	const shot = $derived(shotReceptionFor(clip));
	const lists = $derived(shotReferences(doc, clip));
	const borrowed = $derived(lists.cast.filter((x) => !isGlobal(x.reference)));
	const engine = $derived(engineTitle(shot.engine));
	const number = $derived(String(doc.clips.indexOf(clip) + 1).padStart(2, '0'));
	const thumb = $derived(clipThumb(clip));
	const notice = $derived.by(() => {
		if (shot.state === 'unknown') return { text: t('panels.director.refs.shotUnknown'), tone: 'text-fg-muted' };
		if (shot.state === 'blocked') return { text: t('panels.director.refs.shotBlocked', { engine, profile: shot.engine.profile }), tone: 'text-warning' };
		if (takesReferences(shot.engine.profile)) return { text: t('panels.director.refs.shotMedia', { engine, image: LIMITS.image, video: LIMITS.video, audio: LIMITS.audio }), tone: 'text-fg-muted' };
		return { text: t('panels.director.refs.shotNoMedia', { engine }), tone: 'text-fg-muted' };
	});
	const kindOf = (r) => asset(r.assetId)?.kind ?? refMediaKind(r.space, r.type) ?? 'image';
	const flagged = (r) => ['trimmed', 'missing'].includes(shot.statuses.get(r.id));
</script>

<div class="space-y-4 p-3" data-reference-shot={clip.id}>
	<div class="flex items-center gap-2.5">
		{#if thumb}
			<img src={thumb} alt="" class="h-10 w-16 shrink-0 rounded-md object-cover" />
		{:else}
			<span class="flex h-10 w-16 shrink-0 items-center justify-center rounded-md bg-surface-3 text-fg-muted"><Icon name="film" class="h-4 w-4" /></span>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="truncate text-sm font-medium">{number} · {clipLabel(clip)}</div>
			<div class="truncate text-xs text-fg-subtle" title={engine}>{engine}</div>
		</div>
	</div>

	<p class="flex items-start gap-1.5 rounded-lg border border-line-strong p-2 text-xs {notice.tone}" data-reference-notice={shot.state}>
		<Icon name="info" class="mt-px h-3.5 w-3.5 shrink-0" />
		<span class="min-w-0">{notice.text}</span>
	</p>
	{#if shot.overridden}<p class="text-xs text-fg-subtle">{t('panels.director.refs.ownWords', { count: 1, shots: number })}</p>{/if}
	{#if shot.ignoredLayout}<p class="text-xs text-warning" data-reference-lost>{t('panels.director.refs.lostWords', { count: 1, shots: number })}</p>{/if}

	<section class="space-y-1.5" data-reference-globals>
		<div class="vp-section-title">{t('panels.director.refs.globals', { count: lists.inherited.length })}</div>
		{#each lists.inherited as x (x.reference.id)}
			{@const r = x.reference}
			{@const small = assetThumb(asset(r.assetId))}
			<div class="flex min-h-7 items-center gap-2" data-reference-row={r.id}>
				<span class="flex h-6 w-10 shrink-0 items-center justify-center overflow-hidden rounded bg-surface-3 text-fg-muted">{#if small}<img src={small} alt="" class="h-full w-full object-cover" />{:else}<Icon name={typeIcon(r)} class="h-3 w-3" />{/if}</span>
				<button type="button" class="min-w-0 flex-1 truncate text-left text-xs {x.excluded || x.notCast ? 'text-fg-subtle line-through' : 'text-fg-muted hover:text-fg'}" onclick={() => select('reference', r.id)}>{r.name || refTypeLabel(r.type)}</button>
				{#if !x.excluded && x.notCast}<span class="shrink-0 text-2xs text-fg-subtle" data-reference-not-cast>{t('panels.director.refs.notCast')}</span>{/if}
				{#if !x.excluded && flagged(r)}<span class="shrink-0 text-2xs text-warning">{receptionVerdict(shot.statuses.get(r.id), kindOf(r)).text}</span>{/if}
				<span class="inline-flex shrink-0 overflow-hidden rounded border border-line-strong text-2xs" role="group" aria-label={t('panels.director.refs.sendsLabel', { name: r.name || refTypeLabel(r.type), shot: number })}>
					<button type="button" class="px-1.5 py-0.5 {x.excluded ? 'text-fg-subtle hover:text-fg' : 'bg-surface-3 text-fg'}" aria-pressed={!x.excluded} onclick={() => setSent(clip, r.id, true)}>{t('panels.director.refs.sends')}</button>
					<button type="button" class="px-1.5 py-0.5 {x.excluded ? 'bg-surface-3 text-fg' : 'text-fg-subtle hover:text-fg'}" aria-pressed={x.excluded} onclick={() => setSent(clip, r.id, false)}>{t('panels.director.refs.excluded')}</button>
				</span>
			</div>
		{:else}
			<p class="text-xs text-fg-subtle">{t('panels.director.refs.noGlobals')}</p>
		{/each}
	</section>

	{#if borrowed.length}
		<section class="space-y-1.5" data-reference-cast>
			<div class="vp-section-title">{t('panels.director.refs.fromCast', { count: borrowed.length })}</div>
			{#each borrowed as x (x.reference.id)}
				{@const r = x.reference}
				{@const small = assetThumb(asset(r.assetId))}
				<div class="flex min-h-7 items-center gap-2" data-reference-row={r.id}>
					<span class="flex h-6 w-10 shrink-0 items-center justify-center overflow-hidden rounded bg-surface-3 text-fg-muted">{#if small}<img src={small} alt="" class="h-full w-full object-cover" />{:else}<Icon name={typeIcon(r)} class="h-3 w-3" />{/if}</span>
					<button type="button" class="min-w-0 flex-1 truncate text-left text-xs {x.excluded ? 'text-fg-subtle line-through' : 'text-fg-muted hover:text-fg'}" onclick={() => select('reference', r.id)}>{r.name || refTypeLabel(r.type)}</button>
					{#if !x.excluded && flagged(r)}<span class="shrink-0 text-2xs text-warning">{receptionVerdict(shot.statuses.get(r.id), kindOf(r)).text}</span>{/if}
					<span class="inline-flex shrink-0 overflow-hidden rounded border border-line-strong text-2xs" role="group" aria-label={t('panels.director.refs.sendsLabel', { name: r.name || refTypeLabel(r.type), shot: number })}>
						<button type="button" class="px-1.5 py-0.5 {x.excluded ? 'text-fg-subtle hover:text-fg' : 'bg-surface-3 text-fg'}" aria-pressed={!x.excluded} onclick={() => setSent(clip, r.id, true)}>{t('panels.director.refs.sends')}</button>
						<button type="button" class="px-1.5 py-0.5 {x.excluded ? 'bg-surface-3 text-fg' : 'text-fg-subtle hover:text-fg'}" aria-pressed={x.excluded} onclick={() => setSent(clip, r.id, false)}>{t('panels.director.refs.excluded')}</button>
					</span>
				</div>
			{/each}
		</section>
	{/if}

	<section class="space-y-1.5" data-reference-owns>
		<div class="vp-section-title">{t('panels.director.refs.owns', { shot: number, count: lists.own.length })}</div>
		{#each lists.own as r (r.id)}
			{@const small = assetThumb(asset(r.assetId))}
			<div class="flex min-h-7 items-center gap-2" data-reference-row={r.id}>
				<span class="flex h-6 w-10 shrink-0 items-center justify-center overflow-hidden rounded bg-surface-3 text-fg-muted">{#if small}<img src={small} alt="" class="h-full w-full object-cover" />{:else}<Icon name={typeIcon(r)} class="h-3 w-3" />{/if}</span>
				<button type="button" class="min-w-0 flex-1 truncate text-left text-xs text-fg-muted hover:text-fg" onclick={() => select('reference', r.id)}>{r.name || refTypeLabel(r.type)}</button>
				{#if flagged(r)}<span class="shrink-0 text-2xs text-warning">{receptionVerdict(shot.statuses.get(r.id), kindOf(r)).text}</span>{/if}
				<span class="shrink-0 text-2xs text-fg-subtle">{t('panels.director.refs.own')}</span>
			</div>
		{/each}
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('plus'), onclick: () => addShotReference(clip) }}>{t('panels.director.refs.addTo', { shot: number })}</HostUi>
	</section>
</div>

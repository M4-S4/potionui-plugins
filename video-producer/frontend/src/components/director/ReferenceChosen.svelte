<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, act, asset, clipLabel, shotNumber } from '../../lib/state.svelte.js';
	import { families, refMediaKind, refRoleLabel, refTypeLabel, typesOf, reception, receptionVerdict, engineTitle, setReferenceShot, linkReferenceCard, startImage } from '../../lib/references.js';
	import { engineOptionLabel } from '../../lib/production.svelte.js';
	import { isGlobal } from '../../lib/shots.js';
	import { SPACES, cardsOf, labelOf } from '../../lib/bible.js';
	import { isPictureReference } from '../../lib/keyframes.js';
	import { showInReview } from '../../lib/band.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { typeIcon, REFERENCE_ROLES } from '../../lib/reftags.js';
	import { hostIconName } from '../../lib/icons.js';
	import MediaPicker from '../shots/MediaPicker.svelte';
	import AudioPicker from '../shots/AudioPicker.svelte';
	import ReceptionList from './ReceptionList.svelte';
	import Icon from '../Icon.svelte';

	let { reference } = $props();

	let editing = $state(null);
	let previewing = $state(false);
	let pending = $state(false);

	const found = $derived(reception(reference));
	const media = $derived(reference.assetId ? asset(reference.assetId) : null);
	const thumb = $derived(assetThumb(media));
	const kind = $derived(media?.kind ?? refMediaKind(reference.space, reference.type) ?? 'image');
	const family = $derived(families.find((f) => f.id === reference.space) ?? null);
	const cardKind = $derived(found.linked && !found.linked.voice ? found.linked.kind : (Object.keys(SPACES).find((k) => SPACES[k] === reference.space) ?? null));
	const cards = $derived(cardKind ? cardsOf(doc, cardKind).filter((c) => labelOf(c)) : []);
	const cardId = $derived(cardKind ? (cardsOf(doc, cardKind).find((c) => (c.references ?? []).includes(reference.id))?.id ?? '') : '');
	const open = $derived(editing ?? !reference.assetId);
	const scope = $derived(!isGlobal(reference) || pending ? 'shot' : 'global');
	const scopes = $derived([
		{ id: 'global', label: t('inspector.scope.global') },
		{ id: 'shot', label: t('inspector.scope.shot') }
	]);
	const rows = $derived(
		found.groups.map((g) => ({
			key: g.key,
			status: g.status,
			title: g.status === 'excluded' ? t('panels.director.refs.excludedBy') : g.status === 'not_cast' ? t('panels.director.refs.notCastBy') : engineTitle(g.engine),
			shots: g.shots.map((shot) => shot.clip),
			...receptionVerdict(g.status, kind, g.engine?.profile)
		}))
	);
	const blind = $derived(kind === 'audio' ? [] : [...new Set(found.groups.filter((g) => g.status === 'ignored').map((g) => g.engine.label ?? engineOptionLabel(g.engine.preset, g.engine.model)))]);
	const worded = $derived(found.shots.filter((shot) => shot.status === 'sent' || found.cast.includes(shot.clip)));
	const ownWords = $derived(worded.filter((shot) => shot.overridden).map((shot) => shot.clip));
	const lostWords = $derived(worded.filter((shot) => shot.ignoredLayout).map((shot) => shot.clip));
	const linked = $derived(found.linked);
	const startable = $derived(isPictureReference(reference) && media?.kind === 'image');
	const nums = (clips) => clips.map(shotNumber).join(', ');
	const shotName = (c) => `${shotNumber(c)} · ${clipLabel(c)}`;

	function pickScope(id) {
		if (id === 'global') {
			pending = false;
			setReferenceShot(reference, null);
		} else if (isGlobal(reference)) pending = true;
	}

	function pickShot(id) {
		if (!id) return;
		pending = false;
		setReferenceShot(reference, id);
	}

	function startFrom(e) {
		startImage(doc.clips.find((c) => c.id === e.currentTarget.value));
		e.currentTarget.value = '';
	}
</script>

<div class="space-y-4 p-3" data-reference-chosen={reference.id}>
	<div class="flex items-center gap-2.5">
		{#if thumb}
			<img src={thumb} alt="" class="h-10 w-16 shrink-0 rounded-md object-cover" />
		{:else}
			<span class="flex h-10 w-16 shrink-0 items-center justify-center rounded-md bg-surface-3 text-fg-muted"><Icon name={typeIcon(reference)} class="h-4 w-4" /></span>
		{/if}
		<div class="min-w-0 flex-1">
			<div class="truncate text-sm font-medium">{reference.name || refTypeLabel(reference.type)}</div>
			<div class="truncate text-xs text-fg-subtle">{[family?.short, refTypeLabel(reference.type)].filter(Boolean).join(' · ')}</div>
		</div>
		<HostUi name="IconButton" props={{ icon: hostIconName('pencil'), label: t('panels.director.refs.edit'), tooltip: t('panels.director.refs.edit'), size: 'sm', class: 'vp-h7', onclick: () => (editing = !open) }} />
	</div>

	{#if previewing && media?.src}
		<div class="overflow-hidden rounded-lg border border-line bg-surface-3" data-reference-preview>
			{#if media.kind === 'video'}
				<video src={media.src} class="max-h-64 w-full" controls muted preload="metadata"></video>
			{:else if media.kind === 'audio'}
				<!-- svelte-ignore a11y_media_has_caption -->
				<audio src={media.src} class="w-full" controls preload="metadata"></audio>
			{:else}
				<img src={media.src} alt="" class="max-h-64 w-full object-contain" />
			{/if}
		</div>
	{/if}

	{#if open}
		<section class="space-y-2" data-reference-edit>
			<label class="block space-y-1">
				<span class="text-xs text-fg-muted">{t('inspector.field.name')}</span>
				<input class="input vp-dense w-full" value={reference.name} onchange={(e) => act(() => (reference.name = e.currentTarget.value))} />
			</label>
			<label class="flex items-center gap-2">
				<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.type')}</span>
				<select class="input vp-dense min-w-0 flex-1" value={reference.type} onchange={(e) => act(() => (reference.type = e.currentTarget.value))}>
					{#each typesOf(reference.space) as type (type)}<option value={type}>{refTypeLabel(type)}</option>{/each}
				</select>
			</label>
			{#if kind === 'audio'}
				<div class="space-y-1">
					<span class="text-xs text-fg-muted">{t('inspector.reference.sound')}</span>
					<AudioPicker title={reference.name} value={reference.assetId} onpick={(id) => act(() => (reference.assetId = id))} />
				</div>
			{:else}
				<div class="space-y-1">
					<span class="text-xs text-fg-muted">{kind === 'video' ? t('inspector.reference.video') : t('inspector.reference.image')}</span>
					<MediaPicker {kind} title={reference.name} value={reference.assetId} onpick={(id) => act(() => (reference.assetId = id))} />
				</div>
				<label class="flex items-center gap-2">
					<span class="w-24 shrink-0 text-xs text-fg-muted">{t('inspector.field.role')}</span>
					<select class="input vp-dense min-w-0 flex-1" value={reference.role} onchange={(e) => act(() => (reference.role = e.currentTarget.value))}>
						{#each REFERENCE_ROLES as r (r)}<option value={r}>{refRoleLabel(r)}</option>{/each}
					</select>
				</label>
			{/if}
			{#if reference.file}<div class="text-xs text-fg-subtle">{t('inspector.reference.file', { file: reference.file })}</div>{/if}
		</section>
	{/if}

	<dl class="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 text-xs">
		<dt class="text-fg-subtle">{t('inspector.field.scope')}</dt>
		<dd class="min-w-0"><HostUi name="SegmentedControl" props={{ items: scopes, selected: scope, variant: 'toggle', fullWidth: true, ariaLabel: t('inspector.field.scope'), onSelect: pickScope }} /></dd>
		{#if scope === 'shot'}
			<dt class="text-fg-subtle">{t('inspector.field.shot')}</dt>
			<dd class="min-w-0">
				<select class="vp-popup w-full" value={isGlobal(reference) ? '' : reference.scope.shotId} onchange={(e) => pickShot(e.currentTarget.value)} aria-label={t('inspector.field.shot')} data-reference-shot-pick>
					{#if isGlobal(reference)}<option value="" disabled>{t('panels.director.refs.pickShot')}</option>{/if}
					{#each doc.clips as c (c.id)}<option value={c.id}>{shotName(c)}</option>{/each}
				</select>
			</dd>
		{/if}
		{#if cardKind}
			<dt class="text-fg-subtle">{t('panels.director.refs.card')}</dt>
			<dd class="min-w-0">
				<select class="vp-popup w-full" value={cardId} onchange={(e) => linkReferenceCard(reference, cardKind, e.currentTarget.value || null)} aria-label={t('panels.director.refs.card')}>
					<option value="">{t('panels.director.refs.noCard')}</option>
					{#each cards as c (c.id)}<option value={c.id}>{labelOf(c)}</option>{/each}
				</select>
			</dd>
		{:else if linked?.voice}
			<dt class="text-fg-subtle">{t('panels.director.refs.card')}</dt>
			<dd class="min-w-0 truncate text-fg-muted">{t('panels.director.refs.voiceOf', { name: labelOf(linked.card) })}</dd>
		{/if}
	</dl>
	{#if pending && isGlobal(reference)}<p class="text-xs text-fg-subtle">{t('panels.director.refs.pickShotHint')}</p>{/if}

	<section class="space-y-2" data-reference-reception>
		<div class="vp-section-title">{t('panels.director.refs.received')}</div>
		{#if rows.length}
			<ReceptionList {rows} label={t('panels.director.refs.received')} />
		{:else if !doc.clips.length}
			<p class="text-xs text-fg-subtle">{t('panels.director.refs.noShots')}</p>
		{/if}
		{#if linked && !linked.voice}
			<p class="text-xs text-fg-muted">{found.cast.length ? t('panels.director.refs.cardText', { name: labelOf(linked.card), count: found.cast.length }) : t('panels.director.refs.cardNone', { name: labelOf(linked.card) })}</p>
		{/if}
		{#if blind.length}
			<p class="text-xs text-fg-subtle">{startable ? t('panels.director.refs.blindStart', { count: blind.length, engines: blind.join(', ') }) : t('panels.director.refs.blind', { count: blind.length, engines: blind.join(', ') })}</p>
		{/if}
		{#if ownWords.length}<p class="text-xs text-fg-subtle">{t('panels.director.refs.ownWords', { count: ownWords.length, shots: nums(ownWords) })}</p>{/if}
		{#if lostWords.length}<p class="text-xs text-warning" data-reference-lost>{t('panels.director.refs.lostWords', { count: lostWords.length, shots: nums(lostWords) })}</p>{/if}
	</section>

	<section class="space-y-2">
		<div class="vp-section-title">{found.going.length ? t('panels.director.refs.going', { count: found.going.length }) : t('panels.director.refs.goingNone')}</div>
		{#if found.going.length}
			<div class="flex flex-wrap gap-1" data-reference-going>
				{#each found.going as c (c.id)}
					<button type="button" class="vp-tc rounded border border-line-strong px-1.5 py-0.5 text-xs text-fg-muted transition-colors hover:border-signal hover:text-fg" title={t('panels.director.refs.goingTip', { shot: shotName(c) })} onclick={() => showInReview(c)}>{shotNumber(c)}</button>
				{/each}
			</div>
		{/if}
	</section>

	{#if startable || media?.src}
		<section class="space-y-2">
			<div class="vp-section-title">{t('panels.director.refs.actions')}</div>
			<div class="flex flex-wrap items-center gap-2">
				{#if startable && !isGlobal(reference)}
					{@const target = doc.clips.find((c) => c.id === reference.scope.shotId)}
					{#if target}
						<HostUi name="Tooltip" props={{ text: t('panels.director.refs.startImageTip', { shot: shotName(target) }), wrapperClass: 'inline-flex' }}>
							<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('image'), onclick: () => startImage(target) }}>{t('panels.director.refs.startImage')}</HostUi>
						</HostUi>
					{/if}
				{:else if startable && found.going.length}
					<select class="vp-popup w-full" value="" onchange={startFrom} aria-label={t('panels.director.refs.startImage')} data-reference-start>
						<option value="" disabled>{t('panels.director.refs.startImageFor')}</option>
						{#each found.going as c (c.id)}<option value={c.id}>{shotName(c)}</option>{/each}
					</select>
				{/if}
				{#if media?.src}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: hostIconName('eye'), onclick: () => (previewing = !previewing) }}>{previewing ? t('panels.director.refs.hidePreview') : t('panels.director.refs.preview')}</HostUi>
				{/if}
			</div>
		</section>
	{/if}
</div>

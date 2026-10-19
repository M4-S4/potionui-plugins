<script>
	import { untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, asset, clipAt, clipLabel, secs } from '../../lib/state.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { pickImage } from '../../lib/importer.js';
	import { createSceneFromImage } from '../../lib/scene.svelte.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';

	const clip = $derived(ui.selection?.kind === 'clip' ? (doc.clips.find((c) => c.id === ui.selection.id) ?? clipAt(ui.playhead)) : clipAt(ui.playhead));
	const video = $derived(asset(clip?.assetId)?.kind === 'video' ? asset(clip.assetId) : null);
	const at = $derived(clip ? Math.max(0, (clip.srcIn ?? 0) + Math.min(clip.dur, Math.max(0, ui.playhead - clip.start))) : 0);
	const images = $derived(doc.assets.filter((a) => a.kind === 'image' && a.src));

	let source = $state(untrack(() => (video ? 'shot' : images.length ? 'project' : 'library')));
	let picked = $state(untrack(() => images[0]?.id ?? null));
	let name = $state('');
	let sending = $state(false);

	const sources = $derived([
		{ id: 'shot', label: t('modals.sceneNew.fromShot') },
		{ id: 'project', label: t('modals.sceneNew.fromProject') },
		{ id: 'library', label: t('modals.sceneNew.fromLibrary') }
	]);
	const chosen = $derived(source === 'shot' ? (video ? { assetId: video.id, time: at } : null) : picked && asset(picked) ? { assetId: picked, time: null } : null);
	const fallbackName = $derived(source === 'shot' ? (clip ? t('modals.sceneNew.shotName', { shot: clipLabel(clip), time: secs(at) }) : '') : (asset(picked)?.name ?? ''));

	const close = () => (ui.modal = null);

	function fromLibrary() {
		pickImage(t('modals.sceneNew.pickTitle'), (id) => {
			picked = id;
			source = 'project';
		});
	}

	async function create() {
		if (!chosen || sending) return;
		sending = true;
		close();
		await createSceneFromImage({ ...chosen, name: name.trim() || fallbackName });
	}
</script>

<Modal title={t('modals.sceneNew.title')} subtitle={t('modals.sceneNew.subtitle')} icon="cube" width={560}>
	<div class="space-y-3 p-4">
		<HostUi name="SegmentedControl" props={{ items: sources, selected: source, variant: 'toggle', fullWidth: true, ariaLabel: t('modals.sceneNew.source'), onSelect: (id) => (source = id) }} />
		{#if source === 'shot'}
			{#if video}
				<div class="flex items-center gap-3 rounded-lg border border-line-strong p-2.5">
					{#if assetThumb(video)}<img src={assetThumb(video)} alt="" class="aspect-video w-28 shrink-0 rounded object-cover" />{/if}
					<div class="min-w-0 text-sm">
						<div class="truncate font-medium">{clipLabel(clip)}</div>
						<div class="text-xs text-fg-muted">{t('modals.sceneNew.frameAt', { time: secs(at) })}</div>
					</div>
				</div>
				<p class="text-xs text-fg-subtle">{t('modals.sceneNew.shotHint')}</p>
			{:else}
				<p class="rounded-lg border border-dashed border-line-hover p-3 text-sm text-fg-muted">{t('modals.sceneNew.noVideo')}</p>
			{/if}
		{:else if source === 'project'}
			{#if images.length}
				<div class="grid grid-cols-4 gap-1.5" role="radiogroup" aria-label={t('modals.sceneNew.fromProject')}>
					{#each images as a (a.id)}
						<HostUi name="Tooltip" props={{ text: a.name, wrapperClass: 'block' }}>
							<button type="button" role="radio" aria-checked={picked === a.id} class="block w-full overflow-hidden rounded border {picked === a.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong'}" onclick={() => (picked = a.id)}>
								<img src={assetThumb(a)} alt={a.name} class="aspect-video w-full object-cover" />
							</button>
						</HostUi>
					{/each}
				</div>
			{:else}
				<p class="rounded-lg border border-dashed border-line-hover p-3 text-sm text-fg-muted">{t('modals.sceneNew.noImage')}</p>
			{/if}
		{:else}
			<div class="flex flex-col items-start gap-2 rounded-lg border border-dashed border-line-hover p-3">
				<p class="text-sm text-fg-muted">{t('modals.sceneNew.libraryHint')}</p>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'image', onclick: fromLibrary }}>{t('modals.sceneNew.pick')}</HostUi>
			</div>
		{/if}
		<label class="block space-y-1">
			<span class="vp-label">{t('modals.sceneNew.name')}</span>
			<input class="input vp-dense" bind:value={name} placeholder={fallbackName || t('scene.default.name')} />
		</label>
		<p class="flex gap-1.5 text-xs text-fg-subtle"><Icon name="info" class="mt-px h-3.5 w-3.5 shrink-0" />{t('modals.sceneNew.note')}</p>
	</div>
	{#snippet footer()}
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: close }}>{t('modals.sceneNew.cancel')}</HostUi>
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'cube', disabled: !chosen || sending, onclick: create }}>{t('modals.sceneNew.create')}</HostUi>
	{/snippet}
</Modal>

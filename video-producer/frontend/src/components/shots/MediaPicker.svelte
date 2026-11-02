<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, asset } from '../../lib/state.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { libraryAvailable, pickMedia, pickLocalMedia } from '../../lib/importer.js';
	import Icon from '../Icon.svelte';

	let { value = null, title, onpick, removable = true, compact = false, kind = 'image' } = $props();

	let open = $state(false);
	const video = $derived(kind === 'video');
	const current = $derived(value ? asset(value) : null);
	const thumb = $derived(current ? assetThumb(current) : null);
	const choices = $derived(doc.assets.filter((a) => a.kind === kind && a.src));

	function choose(id) {
		open = false;
		onpick(id);
	}
</script>

<div class="space-y-1.5">
	<button
		type="button"
		class="block w-full overflow-hidden rounded-md border text-left transition-colors {open ? 'border-signal' : 'border-line-strong hover:border-line-hover'}"
		aria-expanded={open}
		aria-label={video ? t('modals.shot.pickVideo', { slot: title }) : t('modals.shot.pickImage', { slot: title })}
		onclick={() => (open = !open)}
	>
		{#if thumb}
			<img src={thumb} alt="" class="aspect-video w-full object-cover" />
		{:else}
			<span class="flex aspect-video w-full flex-col items-center justify-center gap-1 bg-surface-3 text-2xs text-fg-subtle"><Icon name={video ? 'film' : 'image'} class="h-4 w-4" />{video ? t('modals.shot.noVideo') : t('modals.shot.noImage')}</span>
		{/if}
		{#if !compact}<span class="block truncate px-1.5 py-0.5 text-2xs text-fg-muted">{title}{current ? ` · ${current.name}` : ''}</span>{/if}
	</button>
	{#if open}
		<div class="space-y-1.5 rounded-md border border-line-strong bg-surface-2/60 p-1.5">
			{#if choices.length}
				<ul class="grid max-h-36 grid-cols-3 gap-1 overflow-auto" aria-label={video ? t('modals.shot.projectVideos') : t('modals.shot.projectImages')}>
					{#each choices as a (a.id)}
						{@const preview = assetThumb(a)}
						<li>
							<button type="button" class="block w-full overflow-hidden rounded border {a.id === value ? 'border-signal ring-1 ring-signal' : 'border-transparent hover:border-line-hover'}" title={a.name} aria-label={a.name} aria-pressed={a.id === value} onclick={() => choose(a.id)}>
								{#if preview}
									<img src={preview} alt="" class="aspect-video w-full object-cover" />
								{:else}
									<span class="flex aspect-video w-full items-center justify-center bg-surface-3"><Icon name={video ? 'film' : 'image'} class="h-3.5 w-3.5 text-fg-muted" /></span>
								{/if}
							</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="text-xs text-fg-subtle">{video ? t('modals.shot.noProjectVideo') : t('modals.shot.noProjectImage')}</p>
			{/if}
			<div class="flex flex-wrap gap-1">
				{#if libraryAvailable()}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'folder', onclick: () => pickMedia(kind, title, choose) }}>{t('panels.media.import')}</HostUi>
				{/if}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'upload', onclick: () => pickLocalMedia(kind, choose) }}>{t('panels.media.importLocal')}</HostUi>
				{#if removable && value}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'x', class: 'ml-auto', onclick: () => choose(null) }}>{t('modals.shot.removeImage')}</HostUi>
				{/if}
			</div>
		</div>
	{/if}
</div>

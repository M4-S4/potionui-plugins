<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, asset } from '../../lib/state.svelte.js';
	import { assetThumb } from '../../lib/media.js';
	import { libraryAvailable, pickImage, pickLocalImage } from '../../lib/importer.js';
	import Icon from '../Icon.svelte';

	let { value = null, title, onpick, removable = true, compact = false } = $props();

	let open = $state(false);
	const current = $derived(value ? asset(value) : null);
	const thumb = $derived(current ? assetThumb(current) : null);
	const images = $derived(doc.assets.filter((a) => a.kind === 'image' && a.src));

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
		aria-label={t('modals.shot.pickImage', { slot: title })}
		onclick={() => (open = !open)}
	>
		{#if thumb}
			<img src={thumb} alt="" class="aspect-video w-full object-cover" />
		{:else}
			<span class="flex aspect-video w-full flex-col items-center justify-center gap-1 bg-surface-3 text-2xs text-fg-subtle"><Icon name="image" class="h-4 w-4" />{t('modals.shot.noImage')}</span>
		{/if}
		{#if !compact}<span class="block truncate px-1.5 py-0.5 text-2xs text-fg-muted">{title}{current ? ` · ${current.name}` : ''}</span>{/if}
	</button>
	{#if open}
		<div class="space-y-1.5 rounded-md border border-line-strong bg-surface-2/60 p-1.5">
			{#if images.length}
				<ul class="grid max-h-36 grid-cols-3 gap-1 overflow-auto" aria-label={t('modals.shot.projectImages')}>
					{#each images as a (a.id)}
						<li>
							<button type="button" class="block w-full overflow-hidden rounded border {a.id === value ? 'border-signal ring-1 ring-signal' : 'border-transparent hover:border-line-hover'}" title={a.name} aria-label={a.name} aria-pressed={a.id === value} onclick={() => choose(a.id)}>
								<img src={assetThumb(a)} alt="" class="aspect-video w-full object-cover" />
							</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="text-xs text-fg-subtle">{t('modals.shot.noProjectImage')}</p>
			{/if}
			<div class="flex flex-wrap gap-1">
				{#if libraryAvailable()}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'folder', onclick: () => pickImage(title, choose) }}>{t('panels.media.import')}</HostUi>
				{/if}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'upload', onclick: () => pickLocalImage(choose) }}>{t('panels.media.importLocal')}</HostUi>
				{#if removable && value}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'x', class: 'ml-auto', onclick: () => choose(null) }}>{t('modals.shot.removeImage')}</HostUi>
				{/if}
			</div>
		</div>
	{/if}
</div>

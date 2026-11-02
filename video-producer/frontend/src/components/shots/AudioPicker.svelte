<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, asset, secs } from '../../lib/state.svelte.js';
	import { libraryAvailable, pickMedia, pickLocalMedia } from '../../lib/importer.js';
	import Icon from '../Icon.svelte';

	let { value = null, title, onpick, removable = true } = $props();

	let open = $state(false);
	const current = $derived(value ? asset(value) : null);
	const sounds = $derived(doc.assets.filter((a) => a.kind === 'audio' && a.src));

	function choose(id) {
		open = false;
		onpick(id);
	}
</script>

<div class="space-y-1.5">
	<button
		type="button"
		class="flex min-h-9 w-full items-center gap-2 rounded-md border px-2 text-left text-xs transition-colors {open ? 'border-signal' : 'border-line-strong hover:border-line-hover'}"
		aria-expanded={open}
		aria-label={t('modals.shot.pickSound', { slot: title })}
		onclick={() => (open = !open)}
	>
		<Icon name="wave" class="h-4 w-4 shrink-0 text-fg-muted" />
		<span class="min-w-0 flex-1 truncate {current ? 'text-fg' : 'text-fg-subtle'}">{current ? current.name : t('modals.shot.noSound')}</span>
		{#if current?.srcDur}<span class="vp-tc shrink-0 text-fg-subtle">{secs(current.srcDur)}</span>{/if}
	</button>
	{#if open}
		<div class="space-y-1.5 rounded-md border border-line-strong bg-surface-2/60 p-1.5">
			{#if sounds.length}
				<ul class="max-h-36 space-y-0.5 overflow-auto" aria-label={t('modals.shot.projectSounds')}>
					{#each sounds as a (a.id)}
						<li>
							<button type="button" class="flex min-h-7 w-full items-center gap-2 rounded border px-1.5 text-left text-xs {a.id === value ? 'border-signal ring-1 ring-signal' : 'border-transparent hover:border-line-hover'}" aria-pressed={a.id === value} onclick={() => choose(a.id)}>
								<Icon name="music" class="h-3.5 w-3.5 shrink-0 text-fg-muted" />
								<span class="min-w-0 flex-1 truncate">{a.name}</span>
								{#if a.srcDur}<span class="vp-tc shrink-0 text-fg-subtle">{secs(a.srcDur)}</span>{/if}
							</button>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="text-xs text-fg-subtle">{t('modals.shot.noProjectSound')}</p>
			{/if}
			<div class="flex flex-wrap gap-1">
				{#if libraryAvailable()}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'folder', onclick: () => pickMedia('audio', title, choose) }}>{t('panels.media.import')}</HostUi>
				{/if}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'upload', onclick: () => pickLocalMedia('audio', choose) }}>{t('panels.media.importLocal')}</HostUi>
				{#if removable && value}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'x', class: 'ml-auto', onclick: () => choose(null) }}>{t('modals.shot.removeSound')}</HostUi>
				{/if}
			</div>
		</div>
	{/if}
	{#if current?.src}
		<!-- svelte-ignore a11y_media_has_caption -->
		<audio class="h-8 w-full" controls preload="metadata" src={current.src} aria-label={t('modals.shot.listen', { name: current.name })}></audio>
	{/if}
</div>

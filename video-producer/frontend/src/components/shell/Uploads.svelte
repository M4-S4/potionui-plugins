<script>
	import { fly } from 'svelte/transition';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { overlayLayer } from '../../lib/host.js';
	import { uploads, cancelUpload } from '../../lib/uploads.svelte.js';
	import Icon from '../Icon.svelte';

	const icon = { image: 'image', video: 'film', audio: 'music' };
	const active = $derived(uploads.items.filter((x) => x.status === 'waiting' || x.status === 'uploading').length);

	function state(item) {
		if (item.status === 'waiting') return t('project.upload.waiting');
		if (item.status === 'done') return t('project.upload.done');
		if (item.status === 'cancelled') return t('project.upload.cancelled');
		if (item.status === 'failed') return t('project.upload.failedShort');
		return t('project.upload.percent', { value: formatNumber(Math.round(item.progress)) });
	}
</script>

{#if uploads.items.length}
	<section class="vp-uploads" use:overlayLayer={'toast'} aria-label={t('project.upload.title')} transition:fly={{ y: 8, duration: ms(180) }}>
		<header class="flex items-center gap-2 border-b border-line px-3 py-2 text-xs font-semibold">
			<Icon name="upload" class="h-3.5 w-3.5 text-fg-muted" />
			<span class="flex-1">{active ? t('project.upload.active', { count: active }) : t('project.upload.title')}</span>
		</header>
		<ul class="max-h-60 overflow-auto py-1" aria-live="polite">
			{#each uploads.items as item (item.id)}
				<li class="flex items-center gap-2 px-3 py-1.5 text-xs">
					<Icon name={icon[item.kind] ?? 'upload'} class="h-3.5 w-3.5 shrink-0 text-fg-muted" />
					<div class="min-w-0 flex-1">
						<div class="flex items-center gap-2">
							<span class="min-w-0 flex-1 truncate text-fg" title={item.name}>{item.name}</span>
							<span class="vp-tc shrink-0 {item.status === 'failed' ? 'text-danger' : item.status === 'done' ? 'text-success' : 'text-fg-subtle'}">{state(item)}</span>
						</div>
						<div class="mt-1 h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('project.upload.progress', { name: item.name })} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(item.progress)}>
							<div class="h-full rounded-full transition-[width] duration-150 {item.status === 'failed' ? 'bg-danger' : 'bg-signal'}" style:width="{item.status === 'failed' ? 100 : item.progress}%"></div>
						</div>
					</div>
					{#if item.status === 'waiting' || item.status === 'uploading'}
						<button type="button" class="vp-upload-x" onclick={() => cancelUpload(item.id)} aria-label={t('project.upload.cancel', { name: item.name })} title={t('project.upload.cancel', { name: item.name })}><Icon name="x" class="h-3.5 w-3.5" /></button>
					{/if}
				</li>
			{/each}
		</ul>
	</section>
{/if}

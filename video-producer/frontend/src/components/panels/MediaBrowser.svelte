<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, addFrame, secs } from '../../lib/state.svelte.js';
	import { audioRoleLabel } from '../../lib/catalog.js';
	import { assetThumb } from '../../lib/media.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import { mountHostSlot } from '../../lib/host.js';
	import { addToTimeline, importFiles, openImport, openLocalImport } from '../../lib/importer.js';
	import { deleteAsset } from '../../lib/assets.svelte.js';
	import { fileDrop } from '../../lib/filedrop.js';
	import { LOCAL_KINDS } from '../../lib/upload.js';
	import { activateOnKey } from '../../lib/keyboard.js';
	import PanelHeader from './PanelHeader.svelte';
	import Icon from '../Icon.svelte';

	const collections = ['all', 'image', 'video', 'audio', 'generated'];
	let picked = $state(null);
	let dropping = $state(null);
	const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
	const media = $derived(doc.assets);
	const categoryOf = (a) => (a.kind === 'audio' ? 'audio' : a.generated ? 'generated' : a.kind === 'image' ? 'image' : 'video');
	const inCollection = (a, c) => c === 'all' || categoryOf(a) === c;
	const list = $derived(media.filter((a) => inCollection(a, ui.mediaCollection) && (!ui.mediaQuery || norm(a.name).includes(norm(ui.mediaQuery)))));
	const cur = $derived(doc.assets.find((a) => a.id === picked) ?? null);
	const originLabel = (a) => (a.origin?.kind === 'library' ? t('project.origin.library') : t('project.origin.history'));

	function collectionLabel(c) {
		if (c === 'all') return t('panels.media.collection.all');
		if (c === 'image') return t('panels.media.collection.images');
		if (c === 'video') return t('panels.media.collection.videos');
		if (c === 'audio') return t('panels.media.collection.audio');
		return t('panels.media.collection.generated');
	}

	function kindLabel(kind) {
		if (kind === 'video') return t('panels.media.kind.video');
		if (kind === 'image') return t('panels.media.kind.image');
		return t('panels.media.kind.audio');
	}

	function clearFilters() {
		ui.mediaQuery = '';
		ui.mediaCollection = 'all';
	}

	const emptyProps = $derived({
		compact: true,
		icon: 'search',
		title: t('panels.media.empty'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'xs', onclick: clearFilters, children: t('panels.media.clearFilters') }) }
	});
	const noneProps = $derived({
		compact: true,
		icon: 'image',
		title: t('panels.media.none'),
		description: t('panels.media.noneHint'),
		actions: { slot: importButtons }
	});

	function importButtons(el) {
		const row = el.appendChild(document.createElement('div'));
		row.className = 'flex flex-wrap justify-center gap-1.5';
		const mounted = [
			mountHostSlot(row.appendChild(document.createElement('div')), 'Button', { variant: 'secondary', size: 'xs', icon: 'folder', onclick: () => openImport(), children: t('panels.media.import') }),
			mountHostSlot(row.appendChild(document.createElement('div')), 'Button', { variant: 'secondary', size: 'xs', icon: 'upload', onclick: () => openLocalImport(), children: t('panels.media.importLocal') })
		];
		return () => {
			for (const unmount of mounted) unmount();
			row.remove();
		};
	}
</script>

<div class="relative flex min-h-0 flex-1 flex-col" use:fileDrop={{ kinds: LOCAL_KINDS.media, hover: (v) => (dropping = v), drop: (files) => importFiles(files, LOCAL_KINDS.media) }}>
	<PanelHeader icon="image" title={t('panels.media.title')} subtitle={t('panels.media.count', { count: media.length })}>
		<HostUi
			name="IconButton"
			props={{ icon: 'folder', label: t('panels.media.import'), size: 'sm', class: 'vp-h7', tooltip: t('panels.media.importTip'), kbd: commandById('import')?.key, onclick: () => openImport() }}
		/>
		<HostUi
			name="IconButton"
			props={{ icon: 'upload', label: t('panels.media.importLocal'), size: 'sm', class: 'vp-h7', tooltip: t('panels.media.importLocalTip'), kbd: commandById('import-local')?.key, onclick: () => openLocalImport() }}
		/>
	</PanelHeader>

	<div class="flex flex-col gap-2 px-3 pb-2 pt-3">
		<div class="relative">
			<Icon name="search" class="pointer-events-none absolute left-2 top-1.5 h-4 w-4 text-fg-subtle" />
			<input class="input vp-dense !pl-7" placeholder={t('panels.media.search')} bind:value={ui.mediaQuery} aria-label={t('panels.media.search')} />
		</div>
		<div class="flex flex-wrap gap-1" role="tablist" aria-label={t('panels.media.collections')}>
			{#each collections as c (c)}
				<button type="button" role="tab" aria-selected={ui.mediaCollection === c} class="vp-pill" onclick={() => (ui.mediaCollection = c)}>{collectionLabel(c)}</button>
			{/each}
		</div>
	</div>

	<div class="min-h-0 flex-1 overflow-auto px-3">
		{#if list.length}
			<ul class="grid grid-cols-2 gap-2 pb-3">
				{#each list as a (a.id)}
					{@const thumb = assetThumb(a)}
					<li>
						<div
							role="button"
							tabindex="0"
							class="group w-full overflow-hidden rounded-lg border text-left {picked === a.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}"
							draggable="true"
							ondragstart={(e) => e.dataTransfer.setData('text/x-asset', a.id)}
							onclick={() => (picked = a.id)}
							onkeydown={(e) => activateOnKey(e, () => (picked = a.id))}
							ondblclick={() => (ui.preview = { kind: 'asset', id: a.id })}
							title={t('panels.media.dragHint')}
						>
							<div class="relative aspect-video bg-surface-3">
								{#if thumb}
									<img src={thumb} alt="" class="h-full w-full object-cover" draggable="false" />
								{:else}
									<div class="flex h-full items-center justify-center text-fg-muted"><Icon name={a.kind !== 'audio' ? 'film' : a.role === 'Dialogue' ? 'mic' : 'music'} class="h-6 w-6" /></div>
								{/if}
								{#if a.srcDur !== null}<span class="vp-tc absolute bottom-1 right-1 rounded-sm bg-black/60 px-1 text-2xs text-white">{secs(a.srcDur)}</span>{/if}
								<span class="absolute right-1 top-1 rounded-md bg-black/60 text-white opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100">
									<HostUi name="IconButton" props={{ icon: 'trash', label: t('panels.media.deleteNamed', { name: a.name }), size: 'xs', tooltip: t('panels.media.deleteTip'), onclick: (e) => (e.stopPropagation(), deleteAsset(a.id)) }} />
								</span>
								{#if a.generated}
									<span class="absolute left-1 top-1 flex items-center gap-1 rounded-sm bg-black/60 px-1 text-2xs text-white"><span class="h-1.5 w-1.5 rounded-full {a.quality === 'final' ? 'bg-success-solid' : 'bg-signal-solid'}"></span>{a.quality === 'final' ? t('lib.stage.final') : t('lib.stage.draft')}</span>
								{:else if a.origin}
									<span class="absolute left-1 top-1 rounded-sm bg-black/60 px-1 text-2xs text-white">{originLabel(a)}</span>
								{/if}
							</div>
							<div class="truncate px-1.5 py-1 text-xs text-fg">{a.name}</div>
						</div>
					</li>
				{/each}
			</ul>
		{:else}
			<div class="pb-3">
				<HostUi name="EmptyState" props={media.length ? emptyProps : noneProps} />
			</div>
		{/if}
	</div>

	{#if cur}
		<div class="flex shrink-0 flex-col gap-2 border-t border-line p-3">
			<div class="flex items-center gap-2">
				<span class="truncate text-sm font-medium">{cur.name}</span>
				<span class="ml-auto shrink-0"><HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{kindLabel(cur.kind)}</HostUi></span>
				<HostUi name="IconButton" props={{ icon: 'trash', label: t('panels.media.delete'), size: 'xs', tooltip: t('panels.media.deleteTip'), onclick: () => deleteAsset(cur.id) }} />
			</div>
			<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
				{#if cur.srcDur !== null}
					<dt class="text-fg-subtle">{t('panels.media.duration')}</dt>
					<dd class="vp-tc text-fg-muted">{secs(cur.srcDur)}</dd>
				{/if}
				{#if cur.res}
					<dt class="text-fg-subtle">{t('panels.media.format')}</dt>
					<dd class="text-fg-muted">{cur.fps ? t('panels.media.formatFps', { res: cur.res, fps: cur.fps }) : cur.res}</dd>
				{/if}
				<dt class="text-fg-subtle">{t('panels.media.collection')}</dt>
				<dd class="text-fg-muted">{cur.role ? t('panels.media.collectionRole', { collection: collectionLabel(categoryOf(cur)), role: audioRoleLabel(cur.role) }) : collectionLabel(categoryOf(cur))}</dd>
				{#if cur.origin}
					<dt class="text-fg-subtle">{t('project.origin.label')}</dt>
					<dd class="text-fg-muted">{originLabel(cur)}</dd>
				{/if}
			</dl>
			<div class="flex gap-1.5">
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('eye'), class: 'flex-1', onclick: () => (ui.preview = { kind: 'asset', id: cur.id }) }}>{t('panels.media.preview')}</HostUi>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'plus', class: 'flex-1', onclick: () => addToTimeline(cur.id) }}>{t('panels.media.toCut')}</HostUi>
			</div>
			{#if cur.kind !== 'audio'}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'image', class: 'w-full', onclick: () => addFrame(cur.id) }}>{t('panels.media.useAsFrame')}</HostUi>
			{/if}
		</div>
	{/if}

	{#if dropping}
		<div class="vp-dropzone" class:vp-dropzone-refused={dropping === 'reject'} role="status">
			<Icon name={dropping === 'reject' ? 'alert' : 'upload'} class="h-6 w-6" />
			<span>{dropping === 'reject' ? t('project.upload.dropRefused') : t('project.upload.dropMedia')}</span>
		</div>
	{/if}
</div>

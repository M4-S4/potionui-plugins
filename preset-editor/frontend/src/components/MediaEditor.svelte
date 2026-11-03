<script>
	import ActionButton from './ActionButton.svelte';
	import Icon from './Icon.svelte';
	import Pill from './Pill.svelte';
	import { deleteMedia, listMedia, updateMedia, uploadMedia } from '../lib/client.js';
	import { MEDIA_ACCEPT, formatBytes, galleryBody, galleryRows, isVideo, moveItem, rowsChanged } from '../lib/media.js';
	import { authMedia, confirm, toast } from '../lib/dom.js';

	let { api, draftId, modes = [], focus = '', onChange, onDirty } = $props();

	let phase = $state('loading');
	let error = $state('');
	let listing = $state.raw({ cover: null, gallery: [], files: [] });
	let rows = $state([]);
	let busy = $state('');
	let caption = $state('');
	let mode = $state('');
	let coverInput = $state();
	let galleryInput = $state();
	let revision = $state(0);

	const files = $derived(Array.isArray(listing.files) ? listing.files : []);
	const byPath = $derived(new Map(files.map((file) => [file.path, file])));
	const coverFile = $derived(listing.cover ? byPath.get(listing.cover) ?? { path: listing.cover, size: 0, roles: ['cover'], missing: true } : null);
	const loose = $derived(files.filter((file) => file.roles.length === 0));
	const styles = $derived(files.filter((file) => file.roles.includes('style')));
	const galleryDirty = $derived(rowsChanged(rows, listing.gallery));

	$effect(() => {
		onDirty?.(galleryDirty);
	});

	$effect(() => {
		draftId;
		load();
	});

	function adopt(data) {
		revision += 1;
		listing = data;
		rows = galleryRows(data.gallery);
	}

	async function load() {
		phase = 'loading';
		error = '';
		const result = await listMedia(api, draftId);
		if (!result.ok) {
			error = result.error.message;
			phase = 'error';
			return;
		}
		adopt(result.data);
		phase = 'ready';
	}

	function changed(data) {
		adopt(data.media);
		onChange?.(data);
	}

	async function upload(role, fileList) {
		const picked = Array.from(fileList ?? []);
		if (!picked.length) return;
		busy = role;
		let last = null;
		let count = 0;
		for (const file of picked) {
			const result = await uploadMedia(api, draftId, file, { role, caption: caption.trim(), mode });
			if (!result.ok) {
				toast('error', `${file.name}: ${result.error.message}`);
				continue;
			}
			last = result.data;
			count += 1;
		}
		busy = '';
		if (!last) return;
		changed(last);
		caption = '';
		toast('success', role === 'cover' ? 'Cover uploaded' : `${count} file${count > 1 ? 's' : ''} added to the gallery`);
	}

	async function declare(body, label, marker) {
		busy = marker;
		const result = await updateMedia(api, draftId, body);
		busy = '';
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		changed(result.data);
		if (label) toast('success', label);
	}

	async function remove(path) {
		const ok = await confirm({ title: `Delete ${path}?`, message: 'The file leaves the draft and its media entries go with it.', variant: 'danger' });
		if (!ok) return;
		busy = 'delete';
		const result = await deleteMedia(api, draftId, path);
		busy = '';
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		changed(result.data);
	}

	function pick(input, event) {
		upload(input, event.currentTarget.files);
		event.currentTarget.value = '';
	}

	function addToGallery(path) {
		rows = [...rows, ...galleryRows([{ src: path }])];
	}
</script>

{#snippet thumb(path, size)}
	{#if isVideo(path)}
		<video class="{size} flex-shrink-0 rounded bg-surface-3 object-cover" use:authMedia={{ api, draftId, path, stamp: revision }} muted playsinline preload="metadata"></video>
	{:else}
		<img class="{size} flex-shrink-0 rounded bg-surface-3 object-cover" use:authMedia={{ api, draftId, path, stamp: revision }} alt={path} />
	{/if}
{/snippet}

{#snippet fileLine(file)}
	<span class="truncate font-mono text-fg" title={file.path}>{file.path}</span>
	<span class="text-fg-subtle">{formatBytes(file.size)}</span>
	{#if file.over_budget}<Pill tone="warning" title="Larger than the budget the core linter allows for a preset media file">over budget</Pill>{/if}
	{#if file.missing}<Pill tone="danger">file missing</Pill>{/if}
{/snippet}

<div class="space-y-4 rounded-lg border border-line bg-surface-1 px-3 py-3 text-xs">
	<div class="flex flex-wrap items-center gap-2">
		<span class="font-mono text-fg">public/</span>
		<span class="text-fg-subtle">{files.length} media file{files.length === 1 ? '' : 's'}</span>
		{#if galleryDirty}<Pill tone="warning">gallery unsaved</Pill>{/if}
		<span class="flex-1"></span>
		<ActionButton variant="ghost" icon="refresh" disabled={!!busy} onclick={load}>Reload</ActionButton>
	</div>

	{#if phase === 'loading'}
		<p class="py-6 text-center text-fg-subtle">Loading…</p>
	{:else if phase === 'error'}
		<p class="py-6 text-center text-danger">{error}</p>
	{:else}
		<section class="space-y-2">
			<h4 class="font-semibold text-fg">Cover</h4>
			{#if coverFile}
				<div class="flex flex-wrap items-center gap-3 rounded border px-2 py-2 {coverFile.path === focus ? 'border-accent' : 'border-line'}">
					{#if !coverFile.missing}{@render thumb(coverFile.path, 'h-24 w-36')}{/if}
					<div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">{@render fileLine(coverFile)}</div>
					<ActionButton variant="ghost" disabled={!!busy} title="Keep the file, drop it from media.cover" onclick={() => declare({ cover: null }, 'Cover cleared', 'cover')}>Unset</ActionButton>
					{#if !coverFile.missing}<ActionButton variant="ghost" icon="trash" disabled={!!busy} onclick={() => remove(coverFile.path)}>Delete</ActionButton>{/if}
				</div>
			{:else}
				<p class="text-fg-subtle">No cover yet. The catalogue card shows it; images are downscaled to 1024 px WebP, videos are kept as they are.</p>
			{/if}
			<input type="file" class="hidden" accept={MEDIA_ACCEPT} bind:this={coverInput} onchange={(event) => pick('cover', event)} />
			<ActionButton icon="plus" loading={busy === 'cover'} disabled={!!busy} onclick={() => coverInput?.click()}>{coverFile ? 'Replace the cover' : 'Upload a cover'}</ActionButton>
		</section>

		<section class="space-y-2">
			<h4 class="font-semibold text-fg">Gallery <span class="font-normal text-fg-subtle">({rows.length})</span></h4>
			{#if rows.length}
				<ul class="space-y-2">
					{#each rows as row, index (row.src)}
						<li class="flex flex-wrap items-start gap-3 rounded border px-2 py-2 {row.src === focus ? 'border-accent' : 'border-line'}">
							{#if byPath.has(row.src)}{@render thumb(row.src, 'h-20 w-28')}{/if}
							<div class="min-w-0 flex-1 space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									{@render fileLine(byPath.get(row.src) ?? { path: row.src, size: 0, roles: ['gallery'], missing: true })}
								</div>
								<div class="gallery-row grid grid-cols-1 gap-1">
									<input type="text" class="input w-full" placeholder="Caption" bind:value={row.caption} aria-label="Caption" />
									<select class="input w-full" bind:value={row.mode} aria-label="Mode">
										<option value="">any mode</option>
										{#each modes as item (item)}
											<option value={item}>{item}</option>
										{/each}
									</select>
									<input type="text" class="input w-full font-mono" placeholder="seed" bind:value={row.seed} aria-label="Seed" />
								</div>
								<textarea class="input w-full resize-y font-mono" rows="2" placeholder="Prompt used for this example (optional)" bind:value={row.prompt} aria-label="Prompt"></textarea>
							</div>
							<div class="flex flex-col gap-1">
								<button type="button" class="rounded p-0.5 text-fg-subtle hover:text-fg disabled:opacity-40" title="Move up" disabled={index === 0 || !!busy} onclick={() => (rows = moveItem(rows, index, index - 1))}><Icon name="chevron-down" class="h-3.5 w-3.5 rotate-180" /></button>
								<button type="button" class="rounded p-0.5 text-fg-subtle hover:text-fg disabled:opacity-40" title="Move down" disabled={index === rows.length - 1 || !!busy} onclick={() => (rows = moveItem(rows, index, index + 1))}><Icon name="chevron-down" class="h-3.5 w-3.5" /></button>
								<button type="button" class="rounded p-0.5 text-fg-subtle hover:text-danger" title="Remove from the gallery (keeps the file)" disabled={!!busy} onclick={() => (rows = rows.filter((_, i) => i !== index))}><Icon name="close" class="h-3.5 w-3.5" /></button>
							</div>
						</li>
					{/each}
				</ul>
			{:else}
				<p class="text-fg-subtle">No example yet. Gallery items show on the preset page with their caption, mode and seed.</p>
			{/if}
			<div class="flex flex-wrap items-center gap-2">
				<ActionButton variant="primary" icon="check" loading={busy === 'gallery-save'} disabled={!galleryDirty || !!busy} onclick={() => declare({ gallery: galleryBody(rows) }, 'Gallery saved', 'gallery-save')}>Save gallery</ActionButton>
				{#if galleryDirty}<ActionButton variant="ghost" disabled={!!busy} onclick={() => (rows = galleryRows(listing.gallery))}>Revert</ActionButton>{/if}
			</div>
			<div class="flex flex-wrap items-end gap-2 rounded border border-dashed border-line px-2 py-2">
				<label class="caption-field block flex-1">
					<span class="mb-0.5 block text-fg-muted">Caption for the new files</span>
					<input type="text" class="input w-full" bind:value={caption} />
				</label>
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Mode</span>
					<select class="input" bind:value={mode}>
						<option value="">any mode</option>
						{#each modes as item (item)}
							<option value={item}>{item}</option>
						{/each}
					</select>
				</label>
				<input type="file" class="hidden" multiple accept={MEDIA_ACCEPT} bind:this={galleryInput} onchange={(event) => pick('gallery', event)} />
				<ActionButton icon="plus" loading={busy === 'gallery'} disabled={!!busy} onclick={() => galleryInput?.click()}>Upload examples</ActionButton>
			</div>
		</section>

		{#if loose.length}
			<section class="space-y-2">
				<h4 class="font-semibold text-fg">Other files under public/ <span class="font-normal text-fg-subtle">(not declared in preset.yml)</span></h4>
				<ul class="space-y-1">
					{#each loose as file (file.path)}
						<li class="flex flex-wrap items-center gap-3 rounded border px-2 py-1 {file.path === focus ? 'border-accent' : 'border-line'}">
							{@render thumb(file.path, 'h-12 w-16')}
							<div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">{@render fileLine(file)}</div>
							<ActionButton variant="ghost" loading={busy === `cover:${file.path}`} disabled={!!busy} onclick={() => declare({ cover: file.path }, 'Cover set', `cover:${file.path}`)}>Use as cover</ActionButton>
							<ActionButton variant="ghost" disabled={!!busy || rows.some((row) => row.src === file.path)} onclick={() => addToGallery(file.path)}>Add to gallery</ActionButton>
							<ActionButton variant="ghost" icon="trash" disabled={!!busy} onclick={() => remove(file.path)}>Delete</ActionButton>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		{#if styles.length}
			<details class="rounded border border-line bg-surface-2/40">
				<summary class="cursor-pointer px-2 py-1 font-semibold text-fg">Style previews <span class="font-normal text-fg-subtle">({styles.length} under public/styles/, referenced by styles.yml)</span></summary>
				<ul class="space-y-1 px-2 py-2">
					{#each styles as file (file.path)}
						<li class="flex flex-wrap items-center gap-3 rounded border px-2 py-1 {file.path === focus ? 'border-accent' : 'border-line'}">
							{@render thumb(file.path, 'h-10 w-14')}
							<div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">{@render fileLine(file)}</div>
							<ActionButton variant="ghost" icon="trash" disabled={!!busy} onclick={() => remove(file.path)}>Delete</ActionButton>
						</li>
					{/each}
				</ul>
			</details>
		{/if}

		<p class="text-fg-subtle">Accepted: {MEDIA_ACCEPT.replaceAll(',', ' ')}. Uploads are capped at 20 MB; the core linter has its own budget per file. Paths under public/ can also be referenced from description.md and as examples in a form.yml.</p>
	{/if}
</div>

<style>
	.caption-field { min-width: 10rem; }
	@media (min-width: 640px) {
		.gallery-row { grid-template-columns: minmax(0, 1fr) 8rem 6rem; }
	}
</style>

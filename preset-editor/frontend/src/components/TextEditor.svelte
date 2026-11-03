<script>
	import ActionButton from './ActionButton.svelte';
	import Pill from './Pill.svelte';
	import { deleteFile, readFile, writeFile } from '../lib/client.js';
	import { fileKind, insertAt, lineCount, snippetsFor } from '../lib/files.js';
	import { authImages, confirm, toast } from '../lib/dom.js';
	import { renderMarkdown, safeHref } from '../lib/markdown.js';
	import { parseYaml } from '../lib/yaml.js';

	let { api, draftId, path, sharedFiles = [], onSaved, onDeleted, onDirty } = $props();

	let phase = $state('loading');
	let content = $state('');
	let loaded = $state('');
	let etag = $state('');
	let error = $state('');
	let saving = $state(false);
	let conflict = $state.raw(null);
	let snippetId = $state('');
	let sharedChoice = $state('resolutions/sdxl.yml');
	let textarea = $state();
	let gutter = $state();
	let preview = $state(false);

	const kind = $derived(fileKind(path));
	const dirty = $derived(content !== loaded);
	const lines = $derived(lineCount(content));
	const snippets = $derived(snippetsFor(kind));
	const yamlCheck = $derived(path.endsWith('.yml') || path.endsWith('.yaml') ? parseYaml(content) : { ok: true });
	const isMarkdown = $derived(path.endsWith('.md'));
	const rendered = $derived(isMarkdown && preview ? renderMarkdown(content, { resolveImage: (src) => (src.startsWith('public/') ? { media: src } : safeHref(src)) }) : '');

	$effect(() => {
		onDirty?.(dirty);
	});

	$effect(() => {
		path;
		load();
	});

	async function load() {
		phase = 'loading';
		conflict = null;
		error = '';
		const result = await readFile(api, draftId, path);
		if (!result.ok) {
			error = result.error.message;
			phase = 'error';
			return;
		}
		content = result.data.content;
		loaded = result.data.content;
		etag = result.data.etag;
		phase = 'ready';
	}

	async function save(overrideEtag = null) {
		if (saving) return;
		saving = true;
		conflict = null;
		const result = await writeFile(api, draftId, path, content, overrideEtag ?? etag);
		saving = false;
		if (!result.ok) {
			if (result.error.status === 412 || result.error.status === 428) {
				conflict = { etag: result.error.etag ?? null, content: typeof result.error.content === 'string' ? result.error.content : null };
				return;
			}
			toast('error', result.error.message);
			return;
		}
		etag = result.data.etag;
		loaded = content;
		onSaved?.(result.data);
		toast('success', `${path} saved`);
	}

	function takeTheirs() {
		if (conflict?.content !== null && conflict?.content !== undefined) {
			content = conflict.content;
			loaded = conflict.content;
		}
		if (conflict?.etag) etag = conflict.etag;
		conflict = null;
	}

	function keepMine() {
		save(conflict?.etag ?? null);
	}

	function onKeydown(event) {
		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
			event.preventDefault();
			if (dirty) save();
		} else if (event.key === 'Tab' && !event.shiftKey) {
			event.preventDefault();
			insert('  ', false);
		}
	}

	function insert(snippet, asBlock = true) {
		const position = textarea?.selectionStart ?? content.length;
		const result = asBlock ? insertAt(content, position, snippet) : { text: content.slice(0, position) + snippet + content.slice(position), cursor: position + snippet.length };
		content = result.text;
		queueMicrotask(() => {
			textarea?.focus();
			textarea?.setSelectionRange(result.cursor, result.cursor);
		});
	}

	function insertSnippet() {
		const snippet = snippets.find((item) => item.id === snippetId);
		if (!snippet) return;
		insert(snippet.build(sharedChoice));
	}

	function syncScroll() {
		if (gutter && textarea) gutter.scrollTop = textarea.scrollTop;
	}

	async function remove() {
		const ok = await confirm({ title: `Delete ${path}?`, message: 'The file leaves the draft; publishing writes the draft as it is.', variant: 'danger' });
		if (!ok) return;
		const result = await deleteFile(api, draftId, path);
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		onDeleted?.(result.data);
	}
</script>

<div class="editor-frame flex h-full flex-col rounded-lg border border-line bg-surface-1">
	<div class="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
		<span class="truncate font-mono text-xs text-fg" title={path}>{path}</span>
		{#if dirty}<Pill tone="warning">unsaved</Pill>{/if}
		{#if !yamlCheck.ok}<Pill tone="danger" title={yamlCheck.error.message}>YAML error line {yamlCheck.error.line ?? '?'}</Pill>{/if}
		<span class="text-2xs text-fg-subtle">{lines} line{lines > 1 ? 's' : ''}</span>
		<span class="flex-1"></span>
		{#if snippets.length}
			<select class="input text-xs" bind:value={snippetId} aria-label="Fragment to insert">
				<option value="">Insert…</option>
				{#each snippets as snippet (snippet.id)}
					<option value={snippet.id}>{snippet.label}</option>
				{/each}
			</select>
			{#if snippetId === 'shared-options'}
				<select class="input text-xs" bind:value={sharedChoice} aria-label="Shared options file">
					{#each sharedFiles as file (file)}
						<option value={file}>{file}</option>
					{/each}
				</select>
			{/if}
			<ActionButton variant="ghost" disabled={!snippetId} onclick={insertSnippet}>Insert</ActionButton>
		{/if}
		{#if isMarkdown}
			<ActionButton variant={preview ? 'secondary' : 'ghost'} icon="document" title={preview ? 'Back to the text' : 'Preview the Markdown'} onclick={() => (preview = !preview)}>{preview ? 'Edit' : 'Preview'}</ActionButton>
		{/if}
		<ActionButton variant="primary" icon="check" loading={saving} disabled={!dirty || phase !== 'ready'} title="Save (Ctrl+S)" onclick={() => save()}>Save</ActionButton>
		{#if path !== 'preset.yml'}
			<ActionButton variant="ghost" icon="trash" title="Delete this file" onclick={remove}>Delete</ActionButton>
		{/if}
	</div>

	{#if conflict}
		<div class="flex flex-wrap items-center gap-2 border-b border-warning/40 bg-warning/10 px-3 py-2 text-xs text-fg" role="alert">
			<span>This file changed on the server since you opened it.</span>
			<ActionButton onclick={takeTheirs}>Load the server version</ActionButton>
			<ActionButton variant="danger" onclick={keepMine}>Overwrite with mine</ActionButton>
		</div>
	{/if}

	{#if phase === 'loading'}
		<p class="px-3 py-6 text-center text-xs text-fg-subtle">Loading…</p>
	{:else if phase === 'error'}
		<p class="px-3 py-6 text-center text-xs text-danger">{error}</p>
	{:else if isMarkdown && preview}
		<div class="markdown editor-body flex-1 overflow-auto px-4 py-3 text-sm text-fg" use:authImages={{ api, draftId, html: rendered }}>{@html rendered}</div>
	{:else}
		<div class="flex min-h-0 flex-1 font-mono text-xs leading-5">
			<div bind:this={gutter} class="w-10 flex-shrink-0 select-none overflow-hidden border-r border-line bg-surface-2 py-2 text-right text-fg-subtle" aria-hidden="true">
				{#each Array.from({ length: lines }, (_, i) => i + 1) as line (line)}
					<div class="pr-2">{line}</div>
				{/each}
			</div>
			<textarea
				bind:this={textarea}
				bind:value={content}
				class="editor-body flex-1 resize-y bg-transparent px-3 py-2 text-fg outline-none"
				spellcheck="false"
				wrap="off"
				aria-label="File content"
				onkeydown={onKeydown}
				onscroll={syncScroll}
			></textarea>
		</div>
	{/if}
</div>

<style>
	.markdown :global(h1) { font-size: 1.25rem; font-weight: 600; margin: 0.75rem 0 0.5rem; }
	.markdown :global(h2) { font-size: 1.1rem; font-weight: 600; margin: 0.75rem 0 0.4rem; }
	.markdown :global(h3), .markdown :global(h4), .markdown :global(h5), .markdown :global(h6) { font-size: 1rem; font-weight: 600; margin: 0.6rem 0 0.3rem; }
	.markdown :global(p), .markdown :global(ul), .markdown :global(ol), .markdown :global(blockquote), .markdown :global(pre) { margin: 0 0 0.6rem; }
	.markdown :global(ul) { list-style: disc; padding-left: 1.25rem; }
	.markdown :global(ol) { list-style: decimal; padding-left: 1.25rem; }
	.markdown :global(code) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85em; background: rgb(127 127 127 / 0.15); border-radius: 0.25rem; padding: 0 0.25rem; }
	.markdown :global(pre) { background: rgb(127 127 127 / 0.15); border-radius: 0.375rem; padding: 0.5rem 0.75rem; overflow: auto; }
	.markdown :global(pre code) { background: none; padding: 0; }
	.markdown :global(blockquote) { border-left: 3px solid currentColor; opacity: 0.8; padding-left: 0.75rem; }
	.markdown :global(a) { text-decoration: underline; }
	.markdown :global(img) { max-width: 100%; border-radius: 0.375rem; }
	.markdown :global(hr) { border: 0; border-top: 1px solid currentColor; opacity: 0.3; margin: 0.75rem 0; }
	.editor-frame { min-height: 24rem; }
	.editor-body { min-height: 22rem; }
</style>

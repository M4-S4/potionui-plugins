<script>
	import { onMount } from 'svelte';
	import ActionButton from './ActionButton.svelte';
	import FileTree from './FileTree.svelte';
	import FormBuilder from './FormBuilder.svelte';
	import Icon from './Icon.svelte';
	import LintPanel from './LintPanel.svelte';
	import ManifestEditor from './ManifestEditor.svelte';
	import MediaEditor from './MediaEditor.svelte';
	import Pill from './Pill.svelte';
	import PipelineBuilder from './PipelineBuilder.svelte';
	import PreviewPanel from './PreviewPanel.svelte';
	import TextEditor from './TextEditor.svelte';
	import { adminPresetUrl } from '../lib/catalog.js';
	import { addMode, deleteDraft, exportDraftUrl, fieldTypes, getDraft, lintDraft, pipesReference, publishDraft, removeMode, sharedReference } from '../lib/client.js';
	import { MODE_RE, canPublish, describeSource, formatTimestamp } from '../lib/drafts.js';
	import { fileKind, isEditable, isMedia, modeOf } from '../lib/files.js';
	import { confirm, toast } from '../lib/dom.js';

	let { api, draft, onChange, onBack, onPublished, onDiscarded } = $props();

	const VIEWS = [
		{ id: 'form', label: 'Fields' },
		{ id: 'media', label: 'Media' },
		{ id: 'yaml', label: 'YAML' }
	];

	let selected = $state('preset.yml');
	let manifestView = $state('form');
	let fileView = $state('builder');
	let types = $state.raw([]);
	let pipes = $state.raw([]);
	let busy = $state('');
	let install = $state(true);
	let published = $state.raw(null);
	let failure = $state.raw(null);
	let sharedFiles = $state.raw([]);
	let newMode = $state('');
	let dirty = $state(false);

	const files = $derived(Array.isArray(draft.files) ? draft.files : []);
	const modes = $derived([...new Set(files.map((file) => modeOf(file.path)).filter(Boolean))]);
	const mediaFiles = $derived(files.filter((file) => isMedia(file.path)));
	const selectedKind = $derived(selected ? fileKind(selected) : '');
	const buildable = $derived(selectedKind === 'form' || selectedKind === 'tab' || selectedKind === 'pipeline');
	const ready = $derived(canPublish(draft.last_lint) && !busy && !dirty);
	const modeProblem = $derived(newMode && !MODE_RE.test(newMode.trim()) ? 'lowercase letters, digits and _' : modes.includes(newMode.trim()) ? 'already there' : '');

	onMount(async () => {
		const [shared, fields, reference] = await Promise.all([sharedReference(api), fieldTypes(api), pipesReference(api)]);
		if (shared.ok) sharedFiles = shared.data.files ?? [];
		if (fields.ok && Array.isArray(fields.data)) types = fields.data;
		if (reference.ok && Array.isArray(reference.data?.pipes)) pipes = reference.data.pipes;
	});

	$effect(() => {
		if (selected && !files.some((file) => file.path === selected)) selected = files.find((file) => isEditable(file.path))?.path ?? '';
	});

	function updated(partial) {
		onChange?.({ ...draft, ...partial, last_lint: partial.lint ? { ...partial.lint, at: new Date().toISOString() } : draft.last_lint });
	}

	async function refresh() {
		const result = await getDraft(api, draft.draft_id);
		if (result.ok) onChange?.(result.data);
	}

	async function leaveEdits() {
		if (!dirty) return true;
		const ok = await confirm({ title: 'Discard unsaved changes?', message: 'The open editor has changes that are not saved yet.', variant: 'danger' });
		if (ok) dirty = false;
		return ok;
	}

	async function select(path) {
		if (path === selected) return;
		if (!(await leaveEdits())) return;
		selected = path;
	}

	async function showView(id) {
		if (id === manifestView) return;
		if (!(await leaveEdits())) return;
		manifestView = id;
	}

	async function showFileView(id) {
		if (id === fileView) return;
		if (!(await leaveEdits())) return;
		fileView = id;
	}

	async function openMedia() {
		if (selected === 'preset.yml' && manifestView === 'media') return;
		if (!(await leaveEdits())) return;
		selected = 'preset.yml';
		manifestView = 'media';
	}

	async function lint() {
		busy = 'lint';
		failure = null;
		const result = await lintDraft(api, draft.draft_id);
		if (!result.ok) toast('error', result.error.message);
		else await refresh();
		busy = '';
	}

	async function publish() {
		busy = 'publish';
		failure = null;
		published = null;
		const result = await publishDraft(api, draft.draft_id, { install });
		if (!result.ok) {
			failure = result.error;
			if (result.error.lint) updated({ lint: result.error.lint });
			toast('error', result.error.message);
		} else {
			published = result.data;
			onChange?.(result.data.draft);
			onPublished?.(result.data);
			toast('success', `${result.data.preset.name} is published${result.data.installed ? ' and installed' : ''}`);
		}
		busy = '';
	}

	async function discard() {
		const ok = await confirm({ title: `Discard the draft of ${draft.name}?`, message: 'The draft folder is deleted. A published preset stays where it is.', variant: 'danger' });
		if (!ok) return;
		busy = 'discard';
		const result = await deleteDraft(api, draft.draft_id);
		busy = '';
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		toast('info', 'Draft discarded');
		onDiscarded?.(draft);
	}

	async function createMode() {
		const mode = newMode.trim();
		if (!mode || modeProblem) return;
		busy = 'mode';
		const result = await addMode(api, draft.draft_id, { mode });
		busy = '';
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		newMode = '';
		updated({ files: result.data.files, lint: result.data.lint });
		selected = `modes/${mode}/form.yml`;
	}

	async function dropMode(mode) {
		const ok = await confirm({ title: `Remove the mode ${mode}?`, message: 'Its folder leaves the draft and the mode is removed from preset.yml.', variant: 'danger' });
		if (!ok) return;
		busy = 'mode';
		const result = await removeMode(api, draft.draft_id, mode);
		busy = '';
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		updated({ files: result.data.files, lint: result.data.lint });
	}
</script>

<div class="space-y-4">
	<div class="flex flex-wrap items-center gap-2">
		<ActionButton variant="ghost" icon="arrow-left" onclick={onBack}>All presets</ActionButton>
		<h2 class="min-w-0 flex-1 truncate text-base font-semibold text-fg">{draft.name}</h2>
		{#if draft.published_at}
			<Pill tone="success"><Icon name="check" class="h-3 w-3" />published {formatTimestamp(draft.published_at)}</Pill>
		{:else}
			<Pill tone="neutral">draft</Pill>
		{/if}
	</div>

	<p class="text-xs text-fg-subtle">
		{describeSource(draft.source)} · id <span class="font-mono text-fg-muted">{draft.preset_id}</span> · published to
		<span class="font-mono text-fg-muted">content/presets/local/{draft.target_dir}</span> · {files.length} file{files.length === 1 ? '' : 's'}
	</p>

	<div class="grid grid-cols-1 gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
		<aside class="space-y-3">
			<div class="rounded-lg border border-line bg-surface-1 px-3 py-2">
				<h3 class="mb-1 text-xs font-semibold text-fg">Files</h3>
				<FileTree {files} {selected} onSelect={select} />
			</div>
			<div class="rounded-lg border border-line bg-surface-1 px-3 py-2">
				<h3 class="mb-1 text-xs font-semibold text-fg">Modes</h3>
				<ul class="space-y-1 text-xs">
					{#each modes as mode (mode)}
						<li class="flex items-center gap-1">
							<span class="flex-1 font-mono text-fg">{mode}</span>
							<button type="button" class="rounded p-0.5 text-fg-subtle hover:text-danger" title="Remove the mode {mode}" disabled={!!busy || modes.length < 2} onclick={() => dropMode(mode)}>
								<Icon name="trash" class="h-3.5 w-3.5" />
							</button>
						</li>
					{/each}
				</ul>
				<form class="mt-2 flex items-center gap-1" onsubmit={(event) => { event.preventDefault(); createMode(); }}>
					<input type="text" class="input min-w-0 flex-1 font-mono text-xs" placeholder="new mode" bind:value={newMode} aria-label="New mode name" />
					<ActionButton type="submit" icon="plus" loading={busy === 'mode'} disabled={!newMode.trim() || !!modeProblem || !!busy} title={modeProblem || 'Add a mode from the skeleton'}>Add</ActionButton>
				</form>
			</div>
			<div class="rounded-lg border border-line bg-surface-1 px-3 py-2">
				<h3 class="mb-1 text-xs font-semibold text-fg">Media</h3>
				<p class="text-xs text-fg-subtle">{mediaFiles.length} file{mediaFiles.length === 1 ? '' : 's'} under public/</p>
				<ActionButton class="mt-1" icon="folder" onclick={openMedia}>Cover and gallery</ActionButton>
			</div>
		</aside>
		<div class="min-w-0">
			{#if selected === 'preset.yml'}
				<div class="mb-2 inline-flex rounded border border-line bg-surface-2 p-0.5 text-xs" role="tablist" aria-label="preset.yml views">
					{#each VIEWS as view (view.id)}
						<button type="button" role="tab" aria-selected={manifestView === view.id} class="rounded px-2.5 py-0.5 transition-colors {manifestView === view.id ? 'bg-surface-1 text-fg shadow-sm' : 'text-fg-muted hover:text-fg'}" onclick={() => showView(view.id)}>{view.label}</button>
					{/each}
				</div>
				{#if manifestView === 'form'}
					<ManifestEditor {api} draftId={draft.draft_id} onDirty={(value) => (dirty = value)} onSaved={(data) => updated({ lint: data.lint })} onOpenYaml={() => showView('yaml')} />
				{:else if manifestView === 'media'}
					<MediaEditor {api} draftId={draft.draft_id} {modes} onDirty={(value) => (dirty = value)} onChange={(data) => updated({ files: data.files, lint: data.lint })} />
				{:else}
					<TextEditor {api} draftId={draft.draft_id} path="preset.yml" {sharedFiles} onDirty={(value) => (dirty = value)} onSaved={(data) => updated({ lint: data.lint })} />
				{/if}
			{:else if selected && isMedia(selected)}
				<MediaEditor {api} draftId={draft.draft_id} {modes} focus={selected} onDirty={(value) => (dirty = value)} onChange={(data) => updated({ files: data.files, lint: data.lint })} />
			{:else if selected && buildable}
				<div class="mb-2 inline-flex rounded border border-line bg-surface-2 p-0.5 text-xs" role="tablist" aria-label="{selectedKind} views">
					{#each [{ id: 'builder', label: 'Builder' }, { id: 'yaml', label: 'YAML' }] as view (view.id)}
						<button type="button" role="tab" aria-selected={fileView === view.id} class="rounded px-2.5 py-0.5 transition-colors {fileView === view.id ? 'bg-surface-1 text-fg shadow-sm' : 'text-fg-muted hover:text-fg'}" onclick={() => showFileView(view.id)}>{view.label}</button>
					{/each}
				</div>
				{#key selected}
					{#if fileView === 'builder' && selectedKind === 'pipeline'}
						<PipelineBuilder {api} draftId={draft.draft_id} path={selected} reference={pipes} onDirty={(value) => (dirty = value)} onSaved={(data) => updated({ lint: data.lint })} onOpenYaml={() => showFileView('yaml')} />
					{:else if fileView === 'builder'}
						<FormBuilder {api} draftId={draft.draft_id} path={selected} {types} {sharedFiles} {mediaFiles} onDirty={(value) => (dirty = value)} onSaved={(data) => updated({ lint: data.lint })} onOpenYaml={() => showFileView('yaml')} onOpenFile={select} onFilesChanged={refresh} />
					{:else}
						<TextEditor {api} draftId={draft.draft_id} path={selected} {sharedFiles} onDirty={(value) => (dirty = value)} onSaved={(data) => updated({ lint: data.lint })} onDeleted={(data) => updated({ files: data.files, lint: data.lint })} />
					{/if}
				{/key}
			{:else if selected}
				{#key selected}
					<TextEditor {api} draftId={draft.draft_id} path={selected} {sharedFiles} onDirty={(value) => (dirty = value)} onSaved={(data) => updated({ lint: data.lint })} onDeleted={(data) => updated({ files: data.files, lint: data.lint })} />
				{/key}
			{:else}
				<p class="rounded-lg border border-line bg-surface-1 px-4 py-8 text-center text-sm text-fg-subtle">Pick a file to edit.</p>
			{/if}
		</div>
	</div>

	<LintPanel lint={draft.last_lint} />

	{#if failure && !failure.lint}
		<div class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
			<p>{failure.message}</p>
			{#if failure.errors?.length}
				<ul class="mt-2 list-disc space-y-1 pl-5 text-xs">
					{#each failure.errors as item, index (index)}
						<li>{item}</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}

	{#if published}
		<div class="rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-fg" role="status">
			<p class="font-medium">{published.preset.name} is in the catalogue{published.installed ? ' and installed on this instance' : ''}.</p>
			<p class="mt-1 text-xs text-fg-muted">
				{#if published.archived}The previous version is kept in the history ({published.archived}).{:else}First publication of this preset.{/if}
			</p>
			<p class="mt-2 flex flex-wrap gap-3 text-xs">
				<a class="inline-flex items-center gap-1 text-accent hover:underline" href={adminPresetUrl(published.preset_id)}><Icon name="external-link" class="h-3.5 w-3.5" />View in Admin → Presets</a>
				<a class="inline-flex items-center gap-1 text-accent hover:underline" href="/generate"><Icon name="external-link" class="h-3.5 w-3.5" />Open Generate</a>
			</p>
		</div>
	{/if}

	<div class="flex flex-wrap items-center gap-2">
		<ActionButton icon="refresh" loading={busy === 'lint'} disabled={!!busy} onclick={lint}>Lint again</ActionButton>
		<label class="flex items-center gap-1.5 text-xs text-fg-muted">
			<input type="checkbox" bind:checked={install} disabled={!!busy} />
			Install on this instance
		</label>
		<ActionButton variant="primary" icon="publish" loading={busy === 'publish'} disabled={!ready} title={dirty ? 'Save the open editor first' : canPublish(draft.last_lint) ? 'Write the preset into content/presets/local' : 'Fix the lint errors first'} onclick={publish}>Publish</ActionButton>
		<a class="inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium text-fg-muted transition-colors hover:bg-surface-3/50 hover:text-fg" href={exportDraftUrl(draft.draft_id)} download title="Download the draft folder as a zip archive"><Icon name="folder" class="h-3.5 w-3.5" />Download zip</a>
		<span class="flex-1"></span>
		<ActionButton variant="ghost" icon="trash" loading={busy === 'discard'} disabled={!!busy} onclick={discard}>Discard draft</ActionButton>
	</div>

	<PreviewPanel {api} presetId={draft.preset_id} {modes} publishedAt={draft.published_at} />
</div>

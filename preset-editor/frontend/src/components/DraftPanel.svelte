<script>
	import ActionButton from './ActionButton.svelte';
	import Icon from './Icon.svelte';
	import LintPanel from './LintPanel.svelte';
	import Pill from './Pill.svelte';
	import { adminPresetUrl } from '../lib/catalog.js';
	import { deleteDraft, getDraft, lintDraft, publishDraft } from '../lib/client.js';
	import { canPublish, describeSource, formatTimestamp } from '../lib/drafts.js';
	import { confirm, toast } from '../lib/dom.js';

	let { api, draft, onChange, onBack, onPublished, onDiscarded } = $props();

	let busy = $state('');
	let install = $state(true);
	let published = $state.raw(null);
	let failure = $state.raw(null);

	const ready = $derived(canPublish(draft.last_lint) && !busy);

	async function refresh() {
		const result = await getDraft(api, draft.draft_id);
		if (result.ok) onChange?.(result.data);
		return result;
	}

	async function lint() {
		busy = 'lint';
		failure = null;
		const result = await lintDraft(api, draft.draft_id);
		if (!result.ok) {
			failure = result.error;
			toast('error', result.error.message);
		} else {
			await refresh();
		}
		busy = '';
	}

	async function publish() {
		busy = 'publish';
		failure = null;
		published = null;
		const result = await publishDraft(api, draft.draft_id, { install });
		if (!result.ok) {
			failure = result.error;
			if (result.error.lint) onChange?.({ ...draft, last_lint: { ...result.error.lint, at: new Date().toISOString() } });
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
		const ok = await confirm({
			title: `Discard the draft of ${draft.name}?`,
			message: 'The draft folder is deleted. A published preset stays where it is.',
			variant: 'danger'
		});
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

	<dl class="grid grid-cols-1 gap-x-6 gap-y-2 rounded-lg border border-line bg-surface-1 px-4 py-3 text-xs sm:grid-cols-2">
		<div><dt class="text-fg-subtle">Origin</dt><dd class="text-fg">{describeSource(draft.source)}</dd></div>
		<div><dt class="text-fg-subtle">Preset id</dt><dd class="font-mono text-fg">{draft.preset_id}</dd></div>
		<div><dt class="text-fg-subtle">Published to</dt><dd class="font-mono text-fg">content/presets/local/{draft.target_dir}</dd></div>
		<div><dt class="text-fg-subtle">Files</dt><dd class="text-fg">{draft.files?.length ?? 0} file{(draft.files?.length ?? 0) === 1 ? '' : 's'} · updated {formatTimestamp(draft.updated_at)}</dd></div>
	</dl>

	{#if draft.files?.length}
		<details class="rounded-lg border border-line bg-surface-1">
			<summary class="cursor-pointer px-4 py-2 text-xs font-medium text-fg-muted">Files in the draft</summary>
			<ul class="border-t border-line px-4 py-2 font-mono text-xs text-fg-muted">
				{#each draft.files as file (file.path)}
					<li class="flex justify-between gap-4"><span class="truncate">{file.path}</span><span class="text-fg-subtle">{file.size} B</span></li>
				{/each}
			</ul>
		</details>
	{/if}

	<LintPanel lint={draft.last_lint} />

	{#if failure && !failure.lint}
		<div class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">{failure.message}</div>
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
		<ActionButton variant="primary" icon="publish" loading={busy === 'publish'} disabled={!ready} title={canPublish(draft.last_lint) ? 'Write the preset into content/presets/local' : 'Fix the lint errors first'} onclick={publish}>Publish</ActionButton>
		<span class="flex-1"></span>
		<ActionButton variant="ghost" icon="trash" loading={busy === 'discard'} disabled={!!busy} onclick={discard}>Discard draft</ActionButton>
	</div>
</div>

<script>
	import ActionButton from './ActionButton.svelte';
	import Pill from './Pill.svelte';
	import { readFile, writeFile } from '../lib/client.js';
	import { CATEGORIES, ENGINES } from '../lib/drafts.js';
	import { SECTION_HINTS, SECTION_KEYS, applyManifestForm, fieldProblems, formSnapshot, manifestForm, sectionProblems } from '../lib/manifest.js';
	import { confirm, toast } from '../lib/dom.js';
	import { hasComments } from '../lib/yaml.js';

	let { api, draftId, onSaved, onDirty, onOpenYaml } = $props();

	let phase = $state('loading');
	let error = $state('');
	let source = $state('');
	let etag = $state('');
	let form = $state.raw(null);
	let fields = $state({ name: '', version: '', category: '', engine: '', driver: '', tags: '' });
	let sections = $state({});
	let loaded = $state('');
	let saving = $state(false);
	let conflict = $state.raw(null);

	const snapshot = $derived(JSON.stringify({ fields, sections }));
	const dirty = $derived(phase === 'ready' && snapshot !== loaded);
	const problems = $derived(phase === 'ready' ? { ...fieldProblems(fields), ...sectionProblems(sections) } : {});
	const problemCount = $derived(Object.keys(problems).length);
	const commented = $derived(hasComments(source));
	const engineChoices = $derived([...new Set([...ENGINES, fields.engine.trim()].filter(Boolean))]);

	$effect(() => {
		onDirty?.(dirty);
	});

	$effect(() => {
		draftId;
		load();
	});

	function adopt(text, nextEtag) {
		source = text;
		etag = nextEtag;
		const parsed = manifestForm(text);
		if (!parsed.ok) {
			form = null;
			error = `preset.yml cannot be edited as a form: ${parsed.error.message}${parsed.error.line ? ` (line ${parsed.error.line})` : ''}`;
			phase = 'invalid';
			return;
		}
		form = parsed;
		fields = { ...parsed.fields };
		sections = { ...parsed.sections };
		loaded = formSnapshot(parsed);
		phase = 'ready';
	}

	async function load() {
		phase = 'loading';
		conflict = null;
		error = '';
		const result = await readFile(api, draftId, 'preset.yml');
		if (!result.ok) {
			error = result.error.message;
			phase = 'error';
			return;
		}
		adopt(result.data.content, result.data.etag);
	}

	async function save(overrideEtag = null) {
		if (saving || problemCount) return;
		const built = applyManifestForm(source, { fields, sections }, form);
		if (!built.ok) {
			toast('error', 'Fix the highlighted fields first');
			return;
		}
		if (!built.changed.length) {
			loaded = snapshot;
			return;
		}
		if (built.lostComments.length && overrideEtag === null) {
			const plural = built.lostComments.length > 1 ? 's' : '';
			const ok = await confirm({
				title: 'Rewrite these sections?',
				message: `Saving ${built.changed.join(', ')} from the form drops ${built.lostComments.length} comment line${plural} (line${plural} ${built.lostComments.join(', ')}). The YAML view keeps every comment.`,
				variant: 'warning'
			});
			if (!ok) return;
		}
		saving = true;
		conflict = null;
		const result = await writeFile(api, draftId, 'preset.yml', built.text, overrideEtag ?? etag);
		saving = false;
		if (!result.ok) {
			if (result.error.status === 412 || result.error.status === 428) {
				conflict = { etag: result.error.etag ?? null, content: typeof result.error.content === 'string' ? result.error.content : null };
				return;
			}
			toast('error', result.error.message);
			return;
		}
		adopt(built.text, result.data.etag);
		onSaved?.(result.data);
		toast('success', 'preset.yml saved');
	}

	function takeTheirs() {
		if (conflict?.content !== null && conflict?.content !== undefined) adopt(conflict.content, conflict.etag ?? etag);
		else load();
		conflict = null;
	}

	function keepMine() {
		save(conflict?.etag ?? etag);
	}

	function onKeydown(event) {
		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
			event.preventDefault();
			if (dirty) save();
		}
	}

	function rowsFor(key) {
		return Math.min(16, Math.max(3, (sections[key] ?? '').split('\n').length + 1));
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="flex min-h-[24rem] flex-col rounded-lg border border-line bg-surface-1" onkeydown={onKeydown}>
	<div class="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
		<span class="font-mono text-xs text-fg">preset.yml</span>
		{#if dirty}<Pill tone="warning">unsaved</Pill>{/if}
		{#if problemCount}<Pill tone="danger">{problemCount} problem{problemCount > 1 ? 's' : ''}</Pill>{/if}
		<span class="flex-1"></span>
		<ActionButton variant="ghost" icon="edit" title="Edit the raw YAML" onclick={onOpenYaml}>YAML</ActionButton>
		<ActionButton variant="primary" icon="check" loading={saving} disabled={!dirty || !!problemCount || phase !== 'ready'} title="Save (Ctrl+S)" onclick={() => save()}>Save</ActionButton>
	</div>

	{#if conflict}
		<div class="flex flex-wrap items-center gap-2 border-b border-warning/40 bg-warning/10 px-3 py-2 text-xs text-fg" role="alert">
			<span>preset.yml changed on the server since you opened it.</span>
			<ActionButton onclick={takeTheirs}>Load the server version</ActionButton>
			<ActionButton variant="danger" onclick={keepMine}>Overwrite with mine</ActionButton>
		</div>
	{/if}

	{#if phase === 'loading'}
		<p class="px-3 py-6 text-center text-xs text-fg-subtle">Loading…</p>
	{:else if phase === 'error'}
		<p class="px-3 py-6 text-center text-xs text-danger">{error}</p>
	{:else if phase === 'invalid'}
		<div class="space-y-2 px-3 py-6 text-center text-xs">
			<p class="text-danger">{error}</p>
			<ActionButton icon="edit" onclick={onOpenYaml}>Open the YAML</ActionButton>
		</div>
	{:else}
		<div class="space-y-4 px-3 py-3 text-xs">
			<div class="flex flex-wrap gap-x-5 gap-y-1 text-fg-subtle">
				<span>id <span class="font-mono text-fg-muted">{form.readOnly.id}</span></span>
				<span>schema <span class="font-mono text-fg-muted">{form.readOnly.schema}</span></span>
				<span>modes <span class="font-mono text-fg-muted">{form.modes.join(', ') || '—'}</span> (sidebar)</span>
				<span>media (Media tab)</span>
			</div>

			{#if commented}
				<p class="rounded border border-info/25 bg-info/10 px-2 py-1 text-info">preset.yml has comments. Saving from the form keeps those outside the sections you change and asks before dropping any.</p>
			{/if}

			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Name</span>
					<input type="text" class="input w-full" bind:value={fields.name} />
					{#if problems.name}<span class="text-danger">{problems.name}</span>{/if}
				</label>
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Version</span>
					<input type="text" class="input w-full font-mono" bind:value={fields.version} placeholder="1.0.0" />
					{#if problems.version}<span class="text-danger">{problems.version}</span>{/if}
				</label>
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Category</span>
					<select class="input w-full" bind:value={fields.category}>
						{#if !CATEGORIES.includes(fields.category)}<option value={fields.category}>{fields.category || '—'}</option>{/if}
						{#each CATEGORIES as category (category)}
							<option value={category}>{category}</option>
						{/each}
					</select>
					{#if problems.category}<span class="text-danger">{problems.category}</span>{/if}
				</label>
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Engine</span>
					<input type="text" class="input w-full font-mono" list="preset-editor-engines" bind:value={fields.engine} />
					<datalist id="preset-editor-engines">
						{#each engineChoices as engine (engine)}
							<option value={engine}></option>
						{/each}
					</datalist>
					{#if problems.engine}<span class="text-danger">{problems.engine}</span>{/if}
				</label>
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Driver</span>
					<input type="text" class="input w-full font-mono" bind:value={fields.driver} placeholder={fields.engine.trim() === 'cloud' ? 'cloud.openrouter' : 'optional'} />
					{#if problems.driver}<span class="text-danger">{problems.driver}</span>{/if}
				</label>
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Tags (comma-separated)</span>
					<input type="text" class="input w-full" bind:value={fields.tags} placeholder="sdxl, photo" />
				</label>
			</div>

			<div class="space-y-2">
				<h4 class="font-semibold text-fg">Advanced sections, as YAML</h4>
				{#each SECTION_KEYS as key (key)}
					<details class="rounded border border-line bg-surface-2/40" open={!!sections[key]}>
						<summary class="flex cursor-pointer flex-wrap items-center gap-2 px-2 py-1">
							<span class="font-mono text-fg">{key}</span>
							<span class="text-fg-subtle">{SECTION_HINTS[key]}</span>
							<span class="flex-1"></span>
							{#if problems[key]}<Pill tone="danger">{problems[key]}</Pill>{:else if (sections[key] ?? '').trim()}<Pill tone="accent">set</Pill>{/if}
						</summary>
						<textarea class="w-full resize-y border-t border-line bg-transparent px-2 py-1 font-mono text-xs text-fg outline-none" rows={rowsFor(key)} spellcheck="false" aria-label="{key} as YAML" bind:value={sections[key]}></textarea>
					</details>
				{/each}
			</div>

			{#if form.unknownKeys.length}
				<p class="text-fg-subtle">Kept as they are (unknown to this form): <span class="font-mono">{form.unknownKeys.join(', ')}</span></p>
			{/if}
		</div>
	{/if}
</div>

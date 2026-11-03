<script>
	import ActionButton from './ActionButton.svelte';
	import Icon from './Icon.svelte';
	import Pill from './Pill.svelte';
	import { readFile, writeFile } from '../lib/client.js';
	import { confirm, toast } from '../lib/dom.js';
	import { modeOf } from '../lib/files.js';
	import { PIPE_KEYS, insertPipe, isTemplated, movePipe, newPipe, parsePipelineDocument, pipeRef, pipeTitle, pipelineProblems, referenceMap, removePipe, serializePipelineDocument, sourcesBefore, startChain, toPipe } from '../lib/pipelineModel.js';
	import { commentLines, dumpYaml, parseYaml } from '../lib/yaml.js';

	let { api, draftId, path, reference = [], onDirty, onSaved, onOpenYaml } = $props();

	let phase = $state('loading');
	let error = $state('');
	let source = $state('');
	let etag = $state('');
	let doc = $state(null);
	let loaded = $state('');
	let selectedId = $state('');
	let saving = $state(false);
	let conflict = $state.raw(null);
	let newName = $state('');
	let family = $state('sdxl');
	let seenId = $state('');
	let extraText = $state('');
	let extraError = $state('');

	const mode = $derived(modeOf(path));
	const refs = $derived(referenceMap(reference));
	const names = $derived([...refs.keys()].sort());
	const snapshot = $derived(doc ? serializePipelineDocument(doc) : '');
	const dirty = $derived(phase === 'ready' && snapshot !== loaded);
	const report = $derived(doc ? pipelineProblems(doc, reference) : { byPipe: new Map(), count: 0 });
	const blocked = $derived(report.count + (extraError ? 1 : 0));
	const selected = $derived(doc ? doc.pipes.find((pipe) => pipe.id === selectedId) ?? null : null);
	const index = $derived(doc && selected ? doc.pipes.indexOf(selected) : -1);
	const known = $derived(selected ? refs.get(String(selected.attrs.name ?? '')) ?? null : null);
	const specs = $derived(known?.configuration ?? []);
	const specNames = $derived(specs.map((spec) => spec.name));
	const configuration = $derived(selected && selected.attrs.configuration && typeof selected.attrs.configuration === 'object' && !Array.isArray(selected.attrs.configuration) ? selected.attrs.configuration : {});
	const extraKeys = $derived(Object.keys(configuration).filter((key) => !specNames.includes(key)));
	const inputs = $derived(selected && Array.isArray(selected.attrs.input) ? selected.attrs.input : []);
	const sources = $derived(doc && selected ? sourcesBefore(doc, selected.id) : []);
	const comments = $derived(commentLines(source).length);
	const problems = $derived(selected ? report.byPipe.get(selected.id) ?? [] : []);
	const enabledMode = $derived(!selected || selected.attrs.enabled === undefined || selected.attrs.enabled === true ? 'true' : selected.attrs.enabled === false ? 'false' : 'expression');

	$effect(() => {
		onDirty?.(dirty);
	});

	$effect(() => {
		path;
		load();
	});

	$effect(() => {
		if (!selected || selected.id === seenId) return;
		seenId = selected.id;
		extraText = extraKeys.length ? dumpYaml(Object.fromEntries(extraKeys.map((key) => [key, configuration[key]])), { lineWidth: -1 }).trimEnd() : '';
		extraError = '';
	});

	function adopt(text, nextEtag) {
		source = text;
		etag = nextEtag;
		const parsed = parsePipelineDocument(text);
		if (!parsed.ok) {
			doc = null;
			error = `${path} cannot be edited as a list: ${parsed.error.message}${parsed.error.line ? ` (line ${parsed.error.line})` : ''}`;
			phase = 'invalid';
			return;
		}
		doc = parsed;
		loaded = serializePipelineDocument(parsed);
		if (!parsed.pipes.some((pipe) => pipe.id === selectedId)) selectedId = parsed.pipes[0]?.id ?? '';
		phase = 'ready';
	}

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
		adopt(result.data.content, result.data.etag);
	}

	async function save(overrideEtag = null) {
		if (saving || blocked || !doc) return;
		const text = serializePipelineDocument(doc);
		if (comments && overrideEtag === null) {
			const ok = await confirm({ title: `Rewrite ${path}?`, message: `The builder writes the whole file: its ${comments} comment line${comments > 1 ? 's' : ''} and the original formatting go away. The YAML view keeps them.`, variant: 'warning' });
			if (!ok) return;
		}
		saving = true;
		conflict = null;
		const result = await writeFile(api, draftId, path, text, overrideEtag ?? etag);
		saving = false;
		if (!result.ok) {
			if (result.error.status === 412 || result.error.status === 428) {
				conflict = { etag: result.error.etag ?? null, content: typeof result.error.content === 'string' ? result.error.content : null };
				return;
			}
			toast('error', result.error.message);
			return;
		}
		source = text;
		etag = result.data.etag;
		loaded = snapshot;
		onSaved?.(result.data);
		toast('success', `${path} saved`);
	}

	function takeTheirs() {
		if (conflict?.content !== null && conflict?.content !== undefined) adopt(conflict.content, conflict.etag ?? etag);
		else load();
		conflict = null;
	}

	function keepMine() {
		save(conflict?.etag ?? etag);
	}

	function set(key, value) {
		if (!selected) return;
		const next = { ...selected.attrs };
		if (value === undefined || value === null || value === '') delete next[key];
		else next[key] = value;
		selected.attrs = next;
	}

	function setConfig(key, value) {
		const next = { ...configuration };
		if (value === undefined || value === null || value === '') delete next[key];
		else next[key] = value;
		set('configuration', Object.keys(next).length ? next : undefined);
	}

	function specValue(spec) {
		const value = configuration[spec.name];
		if (value === undefined || value === null) return '';
		if (typeof value === 'string') return value;
		return dumpYaml(value, { lineWidth: -1 }).trimEnd();
	}

	function commitSpec(spec, text) {
		const trimmed = String(text ?? '').trim();
		if (!trimmed) {
			setConfig(spec.name, undefined);
			return;
		}
		if (isTemplated(trimmed) || spec.param_type === 'str') {
			setConfig(spec.name, text);
			return;
		}
		const parsed = parseYaml(trimmed);
		setConfig(spec.name, parsed.ok ? parsed.data : text);
	}

	function commitExtra() {
		extraError = '';
		const parsed = parseYaml(extraText);
		if (!parsed.ok || (parsed.data !== null && (typeof parsed.data !== 'object' || Array.isArray(parsed.data)))) {
			extraError = parsed.ok ? 'a mapping' : parsed.error.message;
			return;
		}
		const next = { ...configuration };
		for (const key of extraKeys) delete next[key];
		Object.assign(next, parsed.data ?? {});
		set('configuration', Object.keys(next).length ? next : undefined);
	}

	function setEnabled(value) {
		if (value === 'true') set('enabled', true);
		else if (value === 'false') set('enabled', false);
		else set('enabled', typeof selected.attrs.enabled === 'string' ? selected.attrs.enabled : '{{ form.enabled }}');
	}

	function setInput(row, part, value) {
		const next = inputs.map((entry, position) => (position === row ? [...entry] : entry));
		next[row][part] = value;
		set('input', next);
	}

	function addInput() {
		set('input', [...inputs, ['', sources[sources.length - 1]?.ref ?? '', '']]);
	}

	function dropInput(row) {
		const next = inputs.filter((_, position) => position !== row);
		set('input', next.length ? next : undefined);
	}

	function outputsOf(sourceRef) {
		const found = sources.find((item) => item.ref === sourceRef);
		return found ? (refs.get(found.name)?.outputs ?? []).map((item) => item.name) : [];
	}

	function add() {
		const name = newName.trim();
		if (!name || !doc) return;
		const pipe = newPipe(name, reference);
		insertPipe(doc, pipe, index >= 0 ? index + 1 : null);
		selectedId = pipe.id;
		newName = '';
	}

	function duplicate() {
		if (!selected) return;
		const copy = toPipe({ ...selected.attrs, id: `${pipeRef(selected)}_2` });
		insertPipe(doc, copy, index + 1);
		selectedId = copy.id;
	}

	function remove() {
		if (!selected) return;
		removePipe(doc, selected.id);
		selectedId = doc.pipes[Math.min(index, doc.pipes.length - 1)]?.id ?? '';
	}

	async function useChain(kind) {
		if (!doc) return;
		if (doc.pipes.length) {
			const ok = await confirm({ title: 'Replace the pipeline?', message: `The ${doc.pipes.length} pipe${doc.pipes.length > 1 ? 's' : ''} of this file are replaced by the ${kind} chain.`, variant: 'danger' });
			if (!ok) return;
		}
		doc.pipes = startChain(kind, { family: family.trim() || 'sdxl' });
		selectedId = doc.pipes[0]?.id ?? '';
	}

	function onKeydown(event) {
		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
			event.preventDefault();
			if (dirty) save();
		}
	}

	function errorsOf(pipe) {
		return (report.byPipe.get(pipe.id) ?? []).filter((item) => item.level !== 'warning').length;
	}

	function rows(text) {
		return Math.min(12, Math.max(2, String(text ?? '').split('\n').length + 1));
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="editor-frame flex flex-col rounded-lg border border-line bg-surface-1" onkeydown={onKeydown}>
	<div class="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
		<span class="truncate font-mono text-xs text-fg" title={path}>{path}</span>
		<Pill tone="info">pipeline{mode ? ` · ${mode}` : ''}</Pill>
		{#if dirty}<Pill tone="warning">unsaved</Pill>{/if}
		{#if blocked}<Pill tone="danger">{blocked} problem{blocked > 1 ? 's' : ''}</Pill>{/if}
		<span class="flex-1"></span>
		<ActionButton variant="ghost" icon="edit" title="Edit the raw YAML" onclick={onOpenYaml}>YAML</ActionButton>
		<ActionButton variant="primary" icon="check" loading={saving} disabled={!dirty || !!blocked || phase !== 'ready'} title="Save (Ctrl+S)" onclick={() => save()}>Save</ActionButton>
	</div>

	{#if conflict}
		<div class="flex flex-wrap items-center gap-2 border-b border-warning/40 bg-warning/10 px-3 py-2 text-xs text-fg" role="alert">
			<span>{path} changed on the server since you opened it.</span>
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
		<div class="builder-grid grid grid-cols-1 gap-3 px-3 py-3">
			<aside class="space-y-3 text-xs">
				<div class="rounded border border-line bg-surface-2/40 px-2 py-2">
					<ol class="space-y-0.5">
						{#each doc.pipes as pipe, position (pipe.id)}
							<li>
								<button type="button" class="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left transition-colors {pipe.id === selectedId ? 'bg-accent/10 text-accent' : 'text-fg hover:bg-surface-3/60'}" onclick={() => (selectedId = pipe.id)}>
									<span class="w-4 text-right text-fg-subtle">{position + 1}</span>
									<span class="truncate font-mono {pipe.attrs.enabled === false ? 'line-through opacity-60' : ''}">{pipeTitle(pipe)}</span>
									{#if typeof pipe.attrs.enabled === 'string'}<Pill tone="info" title={pipe.attrs.enabled}>when</Pill>{/if}
									{#if errorsOf(pipe)}<Pill tone="danger">{errorsOf(pipe)}</Pill>{/if}
								</button>
							</li>
						{/each}
					</ol>
					{#if !doc.pipes.length}<p class="px-1 py-1 text-fg-subtle">No pipe yet.</p>{/if}
				</div>
				<div class="space-y-1 rounded border border-line bg-surface-2/40 px-2 py-2">
					<span class="block text-fg-muted">Add a pipe {selected ? 'after the selected one' : 'at the end'}</span>
					<form class="flex items-center gap-1" onsubmit={(event) => { event.preventDefault(); add(); }}>
						<input type="text" class="input min-w-0 flex-1 font-mono" list="preset-editor-pipe-names" bind:value={newName} aria-label="Pipe name" />
						<datalist id="preset-editor-pipe-names">
							{#each names as name (name)}
								<option value={name}></option>
							{/each}
						</datalist>
						<ActionButton type="submit" icon="plus" disabled={!newName.trim()}>Add</ActionButton>
					</form>
					<span class="block pt-1 text-fg-muted">Start from a chain</span>
					<div class="flex flex-wrap items-center gap-1">
						<input type="text" class="input w-24 font-mono" bind:value={family} aria-label="Model family" title="Family of the native loader and generator pipes" />
						<ActionButton onclick={() => useChain('native')}>Native</ActionButton>
						<ActionButton onclick={() => useChain('cloud')}>Cloud</ActionButton>
					</div>
				</div>
				{#if selected}
					<div class="flex flex-wrap gap-1">
						<ActionButton title="Move up" disabled={index <= 0} onclick={() => movePipe(doc, selected.id, -1)}>↑</ActionButton>
						<ActionButton title="Move down" disabled={index >= doc.pipes.length - 1} onclick={() => movePipe(doc, selected.id, 1)}>↓</ActionButton>
						<ActionButton icon="copy" onclick={duplicate}>Duplicate</ActionButton>
						<ActionButton variant="ghost" icon="trash" onclick={remove}>Remove</ActionButton>
					</div>
				{/if}
			</aside>
			<div class="min-w-0 space-y-3 text-xs">
				{#if selected}
					{#if problems.length}
						<ul class="space-y-0.5 rounded border border-danger/40 bg-danger/10 px-2 py-1 text-danger">
							{#each problems as problem, position (position)}
								<li class={problem.level === 'warning' ? 'text-warning' : ''}><span class="font-mono">{problem.key}</span>: {problem.message}</li>
							{/each}
						</ul>
					{/if}
					<div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
						<label class="block">
							<span class="mb-0.5 block text-fg-muted">Pipe</span>
							<input type="text" class="input w-full font-mono" list="preset-editor-pipe-names" value={selected.attrs.name ?? ''} onchange={(event) => set('name', event.currentTarget.value.trim())} />
						</label>
						<label class="block">
							<span class="mb-0.5 block text-fg-muted">Id <span class="text-fg-subtle">(needed when a name appears twice)</span></span>
							<input type="text" class="input w-full font-mono" value={selected.attrs.id ?? ''} onchange={(event) => set('id', event.currentTarget.value.trim())} />
						</label>
						<label class="block">
							<span class="mb-0.5 block text-fg-muted">Enabled</span>
							<select class="input w-full" value={enabledMode} onchange={(event) => setEnabled(event.currentTarget.value)}>
								<option value="true">yes</option>
								<option value="false">no</option>
								<option value="expression">when an expression is true</option>
							</select>
						</label>
						{#if enabledMode === 'expression'}
							<label class="block col-span-full">
								<span class="mb-0.5 block text-fg-muted">Expression</span>
								<input type="text" class="input w-full font-mono" value={selected.attrs.enabled} onchange={(event) => set('enabled', event.currentTarget.value)} />
							</label>
						{/if}
					</div>
					{#if known?.description}<p class="text-fg-subtle">{known.description}</p>{/if}

					<div class="space-y-1">
						<h4 class="font-semibold text-fg">Inputs <span class="font-normal text-fg-subtle">· [this pipe's input, source pipe, its output]</span></h4>
						{#each inputs as entry, row (row)}
							<div class="input-row grid grid-cols-1 items-center gap-1">
								<input type="text" class="input w-full font-mono" list="preset-editor-pipe-inputs" value={Array.isArray(entry) ? entry[0] ?? '' : ''} placeholder="input" onchange={(event) => setInput(row, 0, event.currentTarget.value.trim())} />
								<input type="text" class="input w-full font-mono" list="preset-editor-pipe-sources" value={Array.isArray(entry) ? entry[1] ?? '' : ''} placeholder="source pipe" onchange={(event) => setInput(row, 1, event.currentTarget.value.trim())} />
								<input type="text" class="input w-full font-mono" list="preset-editor-pipe-outputs-{row}" value={Array.isArray(entry) ? entry[2] ?? '' : ''} placeholder="output" onchange={(event) => setInput(row, 2, event.currentTarget.value.trim())} />
								<datalist id="preset-editor-pipe-outputs-{row}">
									{#each outputsOf(Array.isArray(entry) ? entry[1] : '') as output (output)}
										<option value={output}></option>
									{/each}
								</datalist>
								<button type="button" class="rounded p-0.5 text-fg-subtle hover:text-danger" title="Remove this input" onclick={() => dropInput(row)}><Icon name="close" class="h-3.5 w-3.5" /></button>
							</div>
						{/each}
						<datalist id="preset-editor-pipe-inputs">
							{#each known?.inputs ?? [] as item (item.name)}
								<option value={item.name}>{item.io_type}{item.required ? ', required' : ''}</option>
							{/each}
						</datalist>
						<datalist id="preset-editor-pipe-sources">
							{#each sources as item (item.ref)}
								<option value={item.ref}>{item.name}</option>
							{/each}
						</datalist>
						<ActionButton icon="plus" onclick={addInput}>Add an input</ActionButton>
					</div>

					<div class="space-y-2">
						<h4 class="font-semibold text-fg">Configuration {#if known}<span class="font-normal text-fg-subtle">· {specs.length} declared key{specs.length === 1 ? '' : 's'}; values may be Jinja expressions</span>{:else}<span class="font-normal text-fg-subtle">· unknown pipe, keys as YAML below</span>{/if}</h4>
						{#if specs.length}
							<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
								{#each specs as spec (spec.name)}
									<label class="block {spec.param_type === 'dict' || spec.param_type === 'list' ? 'sm:col-span-2' : ''}">
										<span class="mb-0.5 block text-fg-muted" title={spec.description ?? ''}><span class="font-mono text-fg">{spec.name}</span> <span class="text-fg-subtle">{spec.param_type}{spec.required ? ', required' : ''}{spec.choices ? `: ${spec.choices.join(' | ')}` : ''}</span></span>
										{#if spec.param_type === 'dict' || spec.param_type === 'list'}
											<textarea class="input w-full resize-y font-mono" rows={rows(specValue(spec))} value={specValue(spec)} onblur={(event) => commitSpec(spec, event.currentTarget.value)} spellcheck="false"></textarea>
										{:else}
											<input type="text" class="input w-full font-mono" value={specValue(spec)} placeholder={spec.default === null || spec.default === undefined ? '' : String(spec.default)} onchange={(event) => commitSpec(spec, event.currentTarget.value)} />
										{/if}
									</label>
								{/each}
							</div>
						{/if}
						<label class="block">
							<span class="mb-0.5 block text-fg-muted">Other configuration keys <span class="text-fg-subtle">(YAML mapping)</span></span>
							<textarea class="input w-full resize-y font-mono" rows={rows(extraText)} bind:value={extraText} onblur={commitExtra} spellcheck="false"></textarea>
							{#if extraError}<span class="text-danger">{extraError}</span>{/if}
						</label>
						{#if Object.keys(selected.attrs).some((key) => !PIPE_KEYS.includes(key))}
							<p class="text-danger">Keys the core refuses: <span class="font-mono">{Object.keys(selected.attrs).filter((key) => !PIPE_KEYS.includes(key)).join(', ')}</span> (fix them in the YAML view).</p>
						{/if}
					</div>
				{:else}
					<p class="text-fg-muted">Pick a pipe on the left, add one, or start from a chain. Pipes run in the order of the list: a pipe reads only from pipes declared before it.</p>
				{/if}
				<p class="text-fg-subtle">The builder rewrites the whole file when saving; comments and the original formatting go away (the YAML view keeps them).</p>
			</div>
		</div>
	{/if}
</div>

<style>
	.editor-frame { min-height: 24rem; }
	@media (min-width: 640px) {
		.input-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr) auto; }
	}
	@media (min-width: 1024px) {
		.builder-grid { grid-template-columns: 18rem minmax(0, 1fr); }
	}
</style>

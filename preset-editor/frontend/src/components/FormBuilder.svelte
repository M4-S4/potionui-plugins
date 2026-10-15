<script>
	import { dndzone } from 'svelte-dnd-action';
	import ActionButton from './ActionButton.svelte';
	import FieldInspector from './FieldInspector.svelte';
	import Icon from './Icon.svelte';
	import Pill from './Pill.svelte';
	import { readFile, writeFile } from '../lib/client.js';
	import { confirm, toast } from '../lib/dom.js';
	import { modeOf } from '../lib/files.js';
	import { FORM_META_KEYS, cloneNode, externalChildrenPath, fieldNames, findNode, insertNode, isContainerType, metaProblems, moveNode, newField, newTabReference, nodeTitle, parseFormDocument, removeNode, serializeFormDocument } from '../lib/formModel.js';
	import { treeProblems } from '../lib/formSchema.js';
	import { commentLines, parseYaml } from '../lib/yaml.js';

	let { api, draftId, path, types = [], sharedFiles = [], mediaFiles = [], onDirty, onSaved, onOpenYaml, onOpenFile, onFilesChanged } = $props();

	const META_FIELDS = [
		['label', 'Label', 'text'],
		['mode_label', 'Mode label', 'text'],
		['mode_icon', 'Mode icon', 'text'],
		['short_description', 'Short description', 'text'],
		['description', 'Description (markdown)', 'textarea']
	];

	let phase = $state('loading');
	let error = $state('');
	let source = $state('');
	let etag = $state('');
	let doc = $state(null);
	let loaded = $state('');
	let selectedId = $state('');
	let saving = $state(false);
	let conflict = $state.raw(null);
	let paletteType = $state('string');
	let tabSlug = $state('');
	let variantName = $state('');
	let negativeError = $state('');
	let view = $state('field');

	const kind = $derived(path.endsWith('form.yml') ? 'form' : 'tab');
	const mode = $derived(modeOf(path));
	const variant = $derived(/\/variants\/([^/]+)\/form\.yml$/.exec(path)?.[1] ?? null);
	const typeNames = $derived(types.map((item) => item.type));
	const configKeys = $derived(Object.fromEntries(types.filter((item) => Array.isArray(item.configuration_schema) && item.configuration_schema.length).map((item) => [item.type, item.configuration_schema.map((spec) => spec.name)])));
	const snapshot = $derived(doc ? serializeFormDocument(doc) : '');
	const dirty = $derived(phase === 'ready' && snapshot !== loaded);
	const report = $derived(doc ? treeProblems(doc.fields, { types: typeNames, kind, configKeys }) : { byNode: new Map(), general: [], count: 0 });
	const metaIssues = $derived(doc ? metaProblems(doc.meta) : {});
	const blocked = $derived(report.count + Object.keys(metaIssues).length + (negativeError ? 1 : 0));
	const found = $derived(doc ? findNode(doc.fields, selectedId) : null);
	const selected = $derived(found?.node ?? null);
	const comments = $derived(commentLines(source).length);
	const palette = $derived([...types].sort((a, b) => Number(b.container) - Number(a.container) || a.type.localeCompare(b.type)));
	const examples = $derived(mediaFiles.filter((file) => /\.(jpg|jpeg|png|webp|gif|mp4|webm)$/i.test(file.path) && !file.path.startsWith('public/styles/')).map((file) => file.path));

	$effect(() => {
		onDirty?.(dirty);
	});

	$effect(() => {
		path;
		load();
	});

	function adopt(text, nextEtag) {
		source = text;
		etag = nextEtag;
		const parsed = parseFormDocument(text, { kind });
		if (!parsed.ok) {
			doc = null;
			error = `${path} cannot be edited as a tree: ${parsed.error.message}${parsed.error.line ? ` (line ${parsed.error.line})` : ''}`;
			phase = 'invalid';
			return;
		}
		doc = parsed;
		loaded = serializeFormDocument(parsed);
		if (!findNode(parsed.fields, selectedId)) selectedId = parsed.fields[0]?.id ?? '';
		view = selectedId ? 'field' : 'form';
		negativeError = '';
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
		const text = serializeFormDocument(doc);
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

	function replaceChildren(parentId, items) {
		if (!doc) return;
		if (!parentId) doc.fields = items;
		else {
			const target = findNode(doc.fields, parentId);
			if (target) target.node.children = items;
		}
	}

	function suggestName(type) {
		const taken = new Set(fieldNames(doc.fields));
		let index = 1;
		while (taken.has(`${type}_${index}`)) index += 1;
		return `${type}_${index}`;
	}

	function addField(where) {
		if (!doc) return;
		const type = paletteType.trim();
		if (!type) return;
		const container = isContainerType(type);
		const node = newField(type, { name: container || ['header', 'section', 'alert', 'markdown'].includes(type) ? '' : suggestName(type) });
		if (where === 'inside' && selected) insertNode(doc.fields, node, { parentId: selected.id });
		else if (where === 'after' && found) insertNode(doc.fields, node, { parentId: found.parent?.id ?? null, index: found.index + 1 });
		else insertNode(doc.fields, node);
		selectedId = node.id;
		view = 'field';
	}

	function duplicate() {
		if (!found) return;
		const copy = cloneNode(found.node);
		insertNode(doc.fields, copy, { parentId: found.parent?.id ?? null, index: found.index + 1 });
		selectedId = copy.id;
	}

	async function remove() {
		if (!found) return;
		const children = Array.isArray(found.node.children) ? found.node.children.length : 0;
		if (children) {
			const ok = await confirm({ title: `Remove ${nodeTitle(found.node)}?`, message: `Its ${children} child field${children > 1 ? 's' : ''} go with it.`, variant: 'danger' });
			if (!ok) return;
		}
		const parentId = found.parent?.id ?? null;
		const index = found.index;
		removeNode(doc.fields, found.node.id);
		const siblings = parentId ? findNode(doc.fields, parentId)?.node.children ?? [] : doc.fields;
		selectedId = siblings[Math.min(index, siblings.length - 1)]?.id ?? parentId ?? '';
		if (!selectedId) view = 'form';
	}

	function shift(delta) {
		if (!found) return;
		moveNode(doc.fields, found.node.id, { parentId: found.parent?.id ?? null, index: found.index + delta });
	}

	function outdent() {
		if (!found?.parent) return;
		const grand = findNode(doc.fields, found.parent.id);
		moveNode(doc.fields, found.node.id, { parentId: grand?.parent?.id ?? null, index: (grand?.index ?? 0) + 1 });
	}

	function updateSelected(attrs, children) {
		if (!found) return;
		found.node.attrs = attrs;
		if (children !== undefined) found.node.children = children;
	}

	async function addTab() {
		const slug = tabSlug.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
		if (!slug || !mode) return;
		const label = tabSlug.trim().replace(/[-_]+/g, ' ').replace(/^\w/, (char) => char.toUpperCase());
		const node = newTabReference(mode, slug, label);
		const parentId = selected && selected.attrs.type === 'tabs' ? selected.id : found?.parent?.attrs.type === 'tabs' ? found.parent.id : null;
		if (parentId) insertNode(doc.fields, node, { parentId });
		else {
			const tabs = newField('tabs');
			tabs.children = [node];
			insertNode(doc.fields, tabs);
		}
		const tabPath = `modes/${mode}/tabs/${slug}.yml`;
		const existing = await readFile(api, draftId, tabPath);
		if (!existing.ok && existing.error.status === 404) {
			const written = await writeFile(api, draftId, tabPath, 'fields: []\n', null);
			if (written.ok) onFilesChanged?.();
			else toast('error', written.error.message);
		}
		tabSlug = '';
		selectedId = node.id;
		view = 'field';
	}

	async function saveVariant() {
		const name = variantName.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
		if (!name || !mode || !doc) return;
		const target = `modes/${mode}/variants/${name}/form.yml`;
		const text = serializeFormDocument({ ...doc, meta: { ...doc.meta, name, default: undefined } });
		const result = await writeFile(api, draftId, target, text, null);
		if (!result.ok) {
			toast('error', result.error.status === 428 ? `${target} exists already` : result.error.message);
			return;
		}
		variantName = '';
		toast('success', `Variant ${name} created`);
		await onFilesChanged?.();
		onOpenFile?.(target);
	}

	function setMeta(key, value) {
		if (!doc) return;
		doc.meta[key] = value === '' ? undefined : value;
	}

	function toggleExample(file, checked) {
		const current = Array.isArray(doc.meta.examples) ? doc.meta.examples : [];
		doc.meta.examples = checked ? [...current.filter((item) => item !== file), file] : current.filter((item) => item !== file);
		if (!doc.meta.examples.length) doc.meta.examples = undefined;
	}

	function commitNegative(text) {
		negativeError = '';
		const parsed = parseYaml(text);
		if (!parsed.ok) negativeError = parsed.error.message;
		doc.raw.negative_prompt = text;
	}

	function onKeydown(event) {
		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
			event.preventDefault();
			if (dirty) save();
		}
	}

	function problemCount(node) {
		return (report.byNode.get(node.id) ?? []).filter((item) => item.level !== 'warning').length;
	}
</script>

{#snippet tree(nodes, parentId, depth)}
	<ul class="min-h-[1.25rem] space-y-0.5" use:dndzone={{ items: nodes, flipDurationMs: 120, type: 'fields', dropTargetStyle: {}, dropTargetClasses: ['bg-accent/10'] }} onconsider={(event) => replaceChildren(parentId, event.detail.items)} onfinalize={(event) => replaceChildren(parentId, event.detail.items)}>
		{#each nodes as node (node.id)}
			<li>
				<button type="button" class="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-xs transition-colors {node.id === selectedId ? 'bg-accent/15 text-accent' : 'text-fg hover:bg-surface-3/60'}" style="padding-left: {depth * 12 + 4}px" onclick={() => { selectedId = node.id; view = 'field'; }}>
					<Icon name={Array.isArray(node.children) ? 'folder' : typeof node.children === 'string' ? 'external-link' : 'document'} class="h-3.5 w-3.5 flex-shrink-0 opacity-70" />
					<span class="truncate">{nodeTitle(node)}</span>
					{#if problemCount(node)}<Pill tone="danger">{problemCount(node)}</Pill>{/if}
					{#if typeof node.children === 'string'}<Pill tone="info">{externalChildrenPath(node)?.path.split('/').pop()}</Pill>{/if}
				</button>
				{#if Array.isArray(node.children)}
					{@render tree(node.children, node.id, depth + 1)}
				{/if}
			</li>
		{/each}
	</ul>
{/snippet}

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="flex min-h-[24rem] flex-col rounded-lg border border-line bg-surface-1" onkeydown={onKeydown}>
	<div class="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
		<span class="truncate font-mono text-xs text-fg" title={path}>{path}</span>
		<Pill tone="info">{kind === 'form' ? (variant ? `variant ${variant}` : 'default form') : 'tab'}</Pill>
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
		{#if report.general.length}
			<ul class="border-b border-danger/40 bg-danger/10 px-3 py-1 text-xs text-danger">
				{#each report.general as problem, index (index)}
					<li>{problem.message}</li>
				{/each}
			</ul>
		{/if}
		<div class="grid grid-cols-1 gap-3 px-3 py-3 lg:grid-cols-[18rem_minmax(0,1fr)]">
			<aside class="space-y-3">
				<div class="rounded border border-line bg-surface-2/40 px-2 py-2">
					<button type="button" class="mb-1 flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-xs font-semibold {view === 'form' ? 'bg-accent/15 text-accent' : 'text-fg hover:bg-surface-3/60'}" onclick={() => (view = 'form')}>
						<Icon name="document" class="h-3.5 w-3.5" />{kind === 'form' ? 'Form settings' : 'Tab file'}
					</button>
					{@render tree(doc.fields, null, 0)}
					{#if !doc.fields.length}<p class="px-1 py-1 text-xs text-fg-subtle">No field yet.</p>{/if}
				</div>
				<div class="space-y-1 rounded border border-line bg-surface-2/40 px-2 py-2 text-xs">
					<span class="block text-fg-muted">Add a field</span>
					<div class="flex items-center gap-1">
						<input type="text" class="input min-w-0 flex-1 font-mono" list="preset-editor-palette" bind:value={paletteType} aria-label="Field type to add" />
						<datalist id="preset-editor-palette">
							{#each palette as item (item.type)}
								<option value={item.type}>{item.container ? 'container' : item.component}</option>
							{/each}
						</datalist>
					</div>
					<div class="flex flex-wrap gap-1">
						<ActionButton icon="plus" disabled={!paletteType.trim() || !selected} title="After the selected field" onclick={() => addField('after')}>After</ActionButton>
						<ActionButton icon="plus" disabled={!paletteType.trim() || !selected || !Array.isArray(selected.children)} title="Inside the selected container" onclick={() => addField('inside')}>Inside</ActionButton>
						<ActionButton icon="plus" disabled={!paletteType.trim()} title="At the end of this file" onclick={() => addField('end')}>End</ActionButton>
					</div>
					{#if kind === 'form' && mode}
						<span class="block pt-1 text-fg-muted">Add a tab backed by a file</span>
						<form class="flex items-center gap-1" onsubmit={(event) => { event.preventDefault(); addTab(); }}>
							<input type="text" class="input min-w-0 flex-1 font-mono" placeholder="advanced" bind:value={tabSlug} aria-label="New tab name" />
							<ActionButton type="submit" icon="plus" disabled={!tabSlug.trim()} title="Creates modes/{mode}/tabs/<name>.yml when missing">Tab</ActionButton>
						</form>
					{/if}
				</div>
				{#if selected}
					<div class="flex flex-wrap gap-1 text-xs">
						<ActionButton icon="chevron-down" title="Move up" disabled={!found || found.index === 0} onclick={() => shift(-1)}><span class="sr-only">Up</span>↑</ActionButton>
						<ActionButton icon="chevron-down" title="Move down" disabled={!found || found.index >= found.siblings.length - 1} onclick={() => shift(1)}><span class="sr-only">Down</span>↓</ActionButton>
						<ActionButton title="Move out of its container" disabled={!found?.parent} onclick={outdent}>Outdent</ActionButton>
						<ActionButton icon="copy" onclick={duplicate}>Duplicate</ActionButton>
						<ActionButton variant="ghost" icon="trash" onclick={remove}>Remove</ActionButton>
					</div>
				{/if}
			</aside>
			<div class="min-w-0">
				{#if view === 'field' && selected}
					<FieldInspector node={selected} {types} problems={report.byNode.get(selected.id) ?? []} {sharedFiles} onChange={updateSelected} {onOpenFile} />
				{:else}
					<div class="space-y-3 text-xs">
						{#if kind === 'form'}
							<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
								<label class="block">
									<span class="mb-0.5 block text-fg-muted">Form name <span class="text-fg-subtle">(what a request's form_name selects)</span></span>
									<input type="text" class="input w-full font-mono" value={doc.meta.name ?? ''} onchange={(event) => setMeta('name', event.currentTarget.value.trim())} />
									{#if metaIssues.name}<span class="text-danger">{metaIssues.name}</span>{/if}
								</label>
								<label class="block">
									<span class="mb-0.5 block text-fg-muted">Order</span>
									<input type="number" class="input w-full font-mono" value={doc.meta.order ?? ''} onchange={(event) => setMeta('order', event.currentTarget.value === '' ? '' : Number(event.currentTarget.value))} />
									{#if metaIssues.order}<span class="text-danger">{metaIssues.order}</span>{/if}
								</label>
								{#each META_FIELDS as [key, label, control] (key)}
									<label class="block {control === 'textarea' ? 'sm:col-span-2' : ''}">
										<span class="mb-0.5 block text-fg-muted">{label}</span>
										{#if control === 'textarea'}
											<textarea class="input w-full resize-y" rows="3" value={doc.meta[key] ?? ''} onchange={(event) => setMeta(key, event.currentTarget.value)}></textarea>
										{:else}
											<input type="text" class="input w-full" value={doc.meta[key] ?? ''} onchange={(event) => setMeta(key, event.currentTarget.value)} />
										{/if}
									</label>
								{/each}
								<label class="flex items-center gap-1.5 text-fg-muted">
									<input type="checkbox" checked={doc.meta.default === true} onchange={(event) => setMeta('default', event.currentTarget.checked ? true : '')} />
									Default variant of the mode
								</label>
							</div>
							<div class="space-y-1">
								<span class="block text-fg-muted">Examples <span class="text-fg-subtle">(media of the draft shown in the variant picker)</span></span>
								{#if examples.length}
									<div class="flex flex-wrap gap-2">
										{#each examples as file (file)}
											<label class="flex items-center gap-1 rounded border border-line px-1.5 py-0.5 font-mono text-fg">
												<input type="checkbox" checked={Array.isArray(doc.meta.examples) && doc.meta.examples.includes(file)} onchange={(event) => toggleExample(file, event.currentTarget.checked)} />
												{file.replace(/^public\//, '')}
											</label>
										{/each}
									</div>
								{:else}
									<p class="text-fg-subtle">Upload media in the Media view of preset.yml first.</p>
								{/if}
								{#if metaIssues.examples}<span class="text-danger">{metaIssues.examples}</span>{/if}
							</div>
							<label class="block">
								<span class="mb-0.5 block text-fg-muted">negative_prompt <span class="text-fg-subtle">(YAML, e.g. <span class="font-mono">applies_when: true</span>)</span></span>
								<textarea class="input w-full resize-y font-mono" rows="2" value={doc.raw.negative_prompt ?? ''} onblur={(event) => commitNegative(event.currentTarget.value)} spellcheck="false"></textarea>
								{#if negativeError}<span class="text-danger">{negativeError}</span>{/if}
							</label>
							{#if Object.keys(doc.unknown).length}
								<p class="text-fg-subtle">Kept as they are (unknown to this builder): <span class="font-mono">{Object.keys(doc.unknown).join(', ')}</span></p>
							{/if}
							{#if mode}
								<div class="space-y-1 rounded border border-dashed border-line px-2 py-2">
									<span class="block text-fg-muted">Save this form as a new variant of {mode}</span>
									<form class="flex items-center gap-1" onsubmit={(event) => { event.preventDefault(); saveVariant(); }}>
										<input type="text" class="input min-w-0 flex-1 font-mono" placeholder="quick" bind:value={variantName} aria-label="Variant name" />
										<ActionButton type="submit" icon="copy" disabled={!variantName.trim()} title="Writes modes/{mode}/variants/<name>/form.yml from the current tree">Create variant</ActionButton>
									</form>
								</div>
							{/if}
						{:else}
							<p class="text-fg-muted">A tab file holds a <span class="font-mono">fields:</span> list that a <span class="font-mono">tab</span> of form.yml loads through <span class="font-mono">children: "{'{{'} paths.preset {'}}'}/{path}"</span>. Pick a field on the left, or add one.</p>
							{#if Object.keys(doc.unknown).length}
								<p class="text-fg-subtle">Kept as they are: <span class="font-mono">{Object.keys(doc.unknown).join(', ')}</span></p>
							{/if}
						{/if}
						<p class="text-fg-subtle">The builder rewrites the whole file when saving; comments and the original formatting go away (the YAML view keeps them). Every attribute the builder does not show is kept under Advanced attributes.</p>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

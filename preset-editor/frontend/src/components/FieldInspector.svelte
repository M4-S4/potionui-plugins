<script>
	import Pill from './Pill.svelte';
	import { FIELD_RAW_KEYS, externalChildrenPath, isContainerType, withIncludeVars } from '../lib/formModel.js';
	import { ANCHORABLE_TYPES, AUDIENCES, BOOL_TYPES, INTEGER_TYPES, NUMERIC_TYPES, SAVE_INTO, STRING_TYPES, isIncludeVar } from '../lib/formSchema.js';
	import { dumpYaml, parseYaml } from '../lib/yaml.js';

	let { node, types = [], formulaGroups = null, allowVars = false, problems = [], sharedFiles = [], onChange, onOpenFile } = $props();

	const PLAIN_KEYS = ['name', 'label', 'description', 'ai_hint', 'formula'];
	const FLAG_KEYS = ['required', 'visible', 'interactive', 'full_width'];

	let rawText = $state('');
	let rawError = $state('');
	let configText = $state('');
	let configError = $state('');
	let defaultText = $state('');
	let defaultError = $state('');
	let optionsText = $state('');
	let optionsError = $state('');
	let varsText = $state('');
	let varsError = $state('');
	let seenId = $state('');

	const attrs = $derived(node?.attrs ?? {});
	const type = $derived(String(attrs.type ?? ''));
	const manifest = $derived(types.find((item) => item.type === type) ?? null);
	const specs = $derived(manifest?.configuration_schema ?? []);
	const specNames = $derived(specs.map((spec) => spec.name));
	const configuration = $derived(attrs.configuration && typeof attrs.configuration === 'object' && !Array.isArray(attrs.configuration) ? attrs.configuration : {});
	const extraConfigKeys = $derived(Object.keys(configuration).filter((key) => !specNames.includes(key) && key !== 'options'));
	const rawKeys = $derived(Object.keys(attrs).filter((key) => FIELD_RAW_KEYS.includes(key) || !['type', 'anchor', ...PLAIN_KEYS, ...FLAG_KEYS, 'default', 'audience', 'width', 'save_into', 'configuration', 'children'].includes(key)));
	const showAnchor = $derived(ANCHORABLE_TYPES.includes(type) || (attrs.anchor !== undefined && attrs.anchor !== null));
	const defaultKind = $derived(BOOL_TYPES.includes(type) ? 'boolean' : NUMERIC_TYPES.includes(type) || INTEGER_TYPES.includes(type) ? 'number' : STRING_TYPES.includes(type) || type === 'select' ? 'text' : 'yaml');
	const hasOptionsSpec = $derived(specNames.includes('options'));
	const external = $derived(node ? externalChildrenPath(node) : null);
	const problemsByKey = $derived(problems.reduce((map, item) => ({ ...map, [item.key]: [...(map[item.key] ?? []), item] }), {}));

	$effect(() => {
		if (!node || node.id === seenId) return;
		seenId = node.id;
		rawText = rawKeys.length ? dumpYaml(Object.fromEntries(rawKeys.map((key) => [key, attrs[key]])), { lineWidth: -1 }).trimEnd() : '';
		rawError = '';
		configText = extraConfigKeys.length ? dumpYaml(Object.fromEntries(extraConfigKeys.map((key) => [key, configuration[key]])), { lineWidth: -1 }).trimEnd() : '';
		configError = '';
		defaultText = attrs.default === undefined || attrs.default === null ? '' : defaultKind === 'yaml' ? dumpYaml(attrs.default, { lineWidth: -1 }).trimEnd() : String(attrs.default);
		defaultError = '';
		optionsText = Array.isArray(configuration.options) ? dumpYaml(configuration.options, { lineWidth: -1 }).trimEnd() : '';
		optionsError = '';
		varsText = external?.vars ? dumpYaml(external.vars, { lineWidth: -1 }).trimEnd() : '';
		varsError = '';
	});

	function set(key, value) {
		const next = { ...attrs };
		if (value === undefined || value === null || value === '') delete next[key];
		else next[key] = value;
		onChange?.(next);
	}

	function setConfig(key, value) {
		const next = { ...configuration };
		if (value === undefined || value === null || value === '') delete next[key];
		else next[key] = value;
		set('configuration', Object.keys(next).length ? next : undefined);
	}

	function setType(value) {
		const next = { ...attrs, type: value };
		const container = isContainerType(value);
		if (container && !Array.isArray(node.children) && !external) onChange?.(next, []);
		else if (!container && Array.isArray(node.children) && node.children.length === 0) onChange?.(next, null);
		else onChange?.(next);
	}

	function commitVars() {
		varsError = '';
		const text = varsText.trim();
		const parsed = text ? parseYaml(text) : { ok: true, data: null };
		if (!parsed.ok) {
			varsError = parsed.error.message;
			return;
		}
		const vars = parsed.data;
		if (vars !== null && (typeof vars !== 'object' || Array.isArray(vars) || Object.values(vars).some((value) => value === null || typeof value === 'object'))) {
			varsError = 'a mapping of names to plain values';
			return;
		}
		onChange?.({ ...attrs }, withIncludeVars(node.children, vars));
	}

	function flagValue(key) {
		const value = attrs[key];
		return value === true ? 'true' : value === false ? 'false' : '';
	}

	function setFlag(key, value) {
		set(key, value === 'true' ? true : value === 'false' ? false : undefined);
	}

	function commitDefault() {
		defaultError = '';
		const text = defaultText.trim();
		if (!text) {
			set('default', undefined);
			return;
		}
		if (allowVars && isIncludeVar(text)) set('default', text);
		else if (defaultKind === 'boolean') set('default', text === 'true');
		else if (defaultKind === 'number') {
			const number = Number(text);
			if (Number.isNaN(number)) {
				defaultError = 'a number';
				return;
			}
			set('default', number);
		} else if (defaultKind === 'text') set('default', defaultText);
		else {
			const parsed = parseYaml(text);
			if (!parsed.ok) {
				defaultError = parsed.error.message;
				return;
			}
			set('default', parsed.data);
		}
	}

	function commitSpec(spec, text) {
		const trimmed = String(text ?? '').trim();
		if (!trimmed) {
			setConfig(spec.name, undefined);
			return;
		}
		if (spec.param_type === 'int' || spec.param_type === 'float') {
			const number = Number(trimmed);
			if (!Number.isNaN(number)) setConfig(spec.name, number);
			return;
		}
		if (spec.param_type === 'str') {
			setConfig(spec.name, text);
			return;
		}
		const parsed = parseYaml(trimmed);
		if (parsed.ok) setConfig(spec.name, parsed.data);
	}

	function specValue(spec) {
		const value = configuration[spec.name];
		if (value === undefined || value === null) return '';
		if (spec.param_type === 'list' || spec.param_type === 'dict') return dumpYaml(value, { lineWidth: -1 }).trimEnd();
		return String(value);
	}

	function commitOptions() {
		optionsError = '';
		if (!optionsText.trim()) {
			setConfig('options', undefined);
			return;
		}
		const parsed = parseYaml(optionsText);
		if (!parsed.ok || !Array.isArray(parsed.data)) {
			optionsError = parsed.ok ? 'a list of { label, value } entries' : parsed.error.message;
			return;
		}
		setConfig('options', parsed.data);
	}

	function commitExtraConfig() {
		configError = '';
		const parsed = parseYaml(configText);
		if (!parsed.ok || (parsed.data !== null && (typeof parsed.data !== 'object' || Array.isArray(parsed.data)))) {
			configError = parsed.ok ? 'a mapping' : parsed.error.message;
			return;
		}
		const next = { ...configuration };
		for (const key of extraConfigKeys) delete next[key];
		Object.assign(next, parsed.data ?? {});
		set('configuration', Object.keys(next).length ? next : undefined);
	}

	function commitRaw() {
		rawError = '';
		const parsed = parseYaml(rawText);
		if (!parsed.ok || (parsed.data !== null && (typeof parsed.data !== 'object' || Array.isArray(parsed.data)))) {
			rawError = parsed.ok ? 'a mapping of attributes' : parsed.error.message;
			return;
		}
		const next = { ...attrs };
		for (const key of rawKeys) delete next[key];
		Object.assign(next, parsed.data ?? {});
		onChange?.(next);
	}

	function insertShared(file) {
		if (!file) return;
		const entry = { path: `{{ paths._shared }}/${file}` };
		const files = Array.isArray(configuration.files) ? [...configuration.files, entry] : [entry];
		setConfig('files', files);
	}

	function rows(text) {
		return Math.min(14, Math.max(2, String(text ?? '').split('\n').length + 1));
	}
</script>

{#if node}
	<div class="space-y-3 text-xs">
		{#if problems.length}
			<ul class="space-y-0.5 rounded border border-danger/40 bg-danger/10 px-2 py-1 text-danger">
				{#each problems as problem, index (index)}
					<li class={problem.level === 'warning' ? 'text-warning' : ''}><span class="font-mono">{problem.key}</span>: {problem.message}</li>
				{/each}
			</ul>
		{/if}

		<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Type</span>
				<input type="text" class="input w-full font-mono" list="preset-editor-field-types" value={type} onchange={(event) => setType(event.currentTarget.value.trim())} />
				<datalist id="preset-editor-field-types">
					{#each types as item (item.type)}
						<option value={item.type}>{item.container ? 'container' : item.component}</option>
					{/each}
				</datalist>
			</label>
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Name <span class="text-fg-subtle">(the key in form.*)</span></span>
				<input type="text" class="input w-full font-mono" value={attrs.name ?? ''} onchange={(event) => set('name', event.currentTarget.value.trim())} />
			</label>
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Label</span>
				<input type="text" class="input w-full" value={attrs.label ?? ''} onchange={(event) => set('label', event.currentTarget.value)} />
			</label>
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Formula group</span>
				<input type="text" class="input w-full font-mono" list="preset-editor-formula-groups" value={attrs.formula === false ? 'false' : attrs.formula ?? ''} onchange={(event) => set('formula', event.currentTarget.value.trim() === 'false' ? false : event.currentTarget.value.trim())} />
				<datalist id="preset-editor-formula-groups">
					{#each formulaGroups ?? [] as group (group)}
						<option value={group}></option>
					{/each}
				</datalist>
			</label>
			{#if showAnchor}
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">Anchor <span class="text-fg-subtle">(where plugin extensions add fields)</span></span>
					<input type="text" class="input w-full font-mono" placeholder="generation" value={attrs.anchor ?? ''} onchange={(event) => set('anchor', event.currentTarget.value.trim())} />
				</label>
			{/if}
			<label class="block sm:col-span-2">
				<span class="mb-0.5 block text-fg-muted">Description</span>
				<input type="text" class="input w-full" value={attrs.description ?? ''} onchange={(event) => set('description', event.currentTarget.value)} />
			</label>
			<label class="block sm:col-span-2">
				<span class="mb-0.5 block text-fg-muted">AI hint</span>
				<textarea class="input w-full resize-y" rows="2" value={attrs.ai_hint ?? ''} onchange={(event) => set('ai_hint', event.currentTarget.value)}></textarea>
			</label>
		</div>

		<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
			<label class="block sm:col-span-2">
				<span class="mb-0.5 block text-fg-muted">Default <span class="text-fg-subtle">({defaultKind === 'yaml' ? 'YAML' : defaultKind})</span></span>
				{#if defaultKind === 'boolean'}
					<select class="input w-full" value={attrs.default === true ? 'true' : attrs.default === false ? 'false' : ''} onchange={(event) => { defaultText = event.currentTarget.value; commitDefault(); }}>
						<option value="">unset</option>
						<option value="true">true</option>
						<option value="false">false</option>
					</select>
				{:else if defaultKind === 'yaml'}
					<textarea class="input w-full resize-y font-mono" rows={rows(defaultText)} bind:value={defaultText} onblur={commitDefault}></textarea>
				{:else}
					<input type="text" class="input w-full font-mono" bind:value={defaultText} onblur={commitDefault} />
				{/if}
				{#if defaultError}<span class="text-danger">{defaultError}</span>{/if}
			</label>
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Audience</span>
				<select class="input w-full" value={attrs.audience ?? ''} onchange={(event) => set('audience', event.currentTarget.value)}>
					<option value="">simple (default)</option>
					{#each AUDIENCES as audience (audience)}
						<option value={audience}>{audience}</option>
					{/each}
				</select>
			</label>
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Width <span class="text-fg-subtle">(row share)</span></span>
				<input type="text" class="input w-full font-mono" placeholder="2 or 3/5" value={attrs.width ?? ''} onchange={(event) => { const value = event.currentTarget.value.trim(); set('width', value === '' ? undefined : /^\d+(?:\.\d+)?$/.test(value) ? Number(value) : value); }} />
			</label>
			{#each FLAG_KEYS as key (key)}
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">{key.replace('_', ' ')}</span>
					<select class="input w-full" value={flagValue(key)} onchange={(event) => setFlag(key, event.currentTarget.value)}>
						<option value="">unset</option>
						<option value="true">true</option>
						<option value="false">false</option>
					</select>
				</label>
			{/each}
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Save into</span>
				<select class="input w-full" value={attrs.save_into ?? ''} onchange={(event) => set('save_into', event.currentTarget.value)}>
					<option value="">no</option>
					{#each SAVE_INTO as target (target)}
						<option value={target}>{target}</option>
					{/each}
				</select>
			</label>
		</div>

		{#if external}
			<div class="flex flex-wrap items-center gap-2 rounded border border-line bg-surface-2/40 px-2 py-1">
				<span class="text-fg-muted">Children loaded from</span>
				<span class="font-mono text-fg">{external.file}</span>
				{#if external.scope === 'preset'}
					<button type="button" class="text-accent hover:underline" onclick={() => onOpenFile?.(external.path)}>Open {external.path.split('/').pop()}</button>
				{:else if external.scope === 'shared'}
					<Pill tone="info">shared tree</Pill>
				{/if}
				<label class="block w-full">
					<span class="mb-0.5 block text-fg-muted">vars <span class="text-fg-subtle">(YAML mapping of plain values, filled into the {'{{'} vars.name {'}}'} placeholders of the file; empty for a plain include)</span></span>
					<textarea class="input w-full resize-y font-mono" rows={rows(varsText)} bind:value={varsText} onblur={commitVars} spellcheck="false"></textarea>
					{#if varsError}<span class="text-danger">{varsError}</span>{/if}
				</label>
			</div>
		{/if}

		<div class="space-y-2">
			<h4 class="font-semibold text-fg">Configuration {#if manifest}<span class="font-normal text-fg-subtle">· {specs.length} declared key{specs.length === 1 ? '' : 's'} for {type}</span>{:else if type}<span class="font-normal text-fg-subtle">· no declared keys for {type}</span>{/if}</h4>
			{#if hasOptionsSpec}
				<label class="block">
					<span class="mb-0.5 block text-fg-muted">options <span class="text-fg-subtle">— one entry per line as YAML, e.g. <span class="font-mono">- {'{'} label: "Fast", value: "fast" {'}'}</span></span></span>
					<textarea class="input w-full resize-y font-mono" rows={rows(optionsText)} bind:value={optionsText} onblur={commitOptions} spellcheck="false"></textarea>
					{#if optionsError}<span class="text-danger">{optionsError}</span>{/if}
				</label>
				{#if sharedFiles.length}
					<label class="block">
						<span class="mb-0.5 block text-fg-muted">Add a shared options file to <span class="font-mono">files</span></span>
						<select class="input w-full" onchange={(event) => { insertShared(event.currentTarget.value); event.currentTarget.value = ''; }}>
							<option value="">choose…</option>
							{#each sharedFiles as file (file)}
								<option value={file}>{file}</option>
							{/each}
						</select>
					</label>
				{/if}
			{/if}
			{#if specs.length}
				<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
					{#each specs.filter((spec) => spec.name !== 'options') as spec (spec.name)}
						<label class="block {spec.param_type === 'list' || spec.param_type === 'dict' ? 'sm:col-span-2' : ''}">
							<span class="mb-0.5 block text-fg-muted" title={spec.description ?? ''}><span class="font-mono text-fg">{spec.name}</span> <span class="text-fg-subtle">{spec.param_type}{spec.required ? ', required' : ''}</span></span>
							{#if spec.param_type === 'bool'}
								<select class="input w-full" value={configuration[spec.name] === true ? 'true' : configuration[spec.name] === false ? 'false' : ''} onchange={(event) => setConfig(spec.name, event.currentTarget.value === '' ? undefined : event.currentTarget.value === 'true')}>
									<option value="">unset{spec.default === true || spec.default === false ? ` (${spec.default})` : ''}</option>
									<option value="true">true</option>
									<option value="false">false</option>
								</select>
							{:else if Array.isArray(spec.choices) && spec.choices.length}
								<select class="input w-full font-mono" value={configuration[spec.name] ?? ''} onchange={(event) => setConfig(spec.name, event.currentTarget.value)}>
									<option value="">unset{spec.default ? ` (${spec.default})` : ''}</option>
									{#each spec.choices as choice (choice)}
										<option value={choice}>{choice}</option>
									{/each}
								</select>
							{:else if spec.param_type === 'list' || spec.param_type === 'dict'}
								<textarea class="input w-full resize-y font-mono" rows={rows(specValue(spec))} value={specValue(spec)} placeholder={spec.example ? dumpYaml(spec.example, { lineWidth: -1 }).trimEnd() : ''} onblur={(event) => commitSpec(spec, event.currentTarget.value)} spellcheck="false"></textarea>
							{:else}
								<input type="text" class="input w-full font-mono" value={specValue(spec)} placeholder={spec.default === null || spec.default === undefined ? (spec.example ?? '') : String(spec.default)} onchange={(event) => commitSpec(spec, event.currentTarget.value)} />
							{/if}
						</label>
					{/each}
				</div>
			{/if}
			<label class="block">
				<span class="mb-0.5 block text-fg-muted">Other configuration keys <span class="text-fg-subtle">(YAML mapping; the linter warns on keys the type does not declare)</span></span>
				<textarea class="input w-full resize-y font-mono" rows={rows(configText)} bind:value={configText} onblur={commitExtraConfig} spellcheck="false"></textarea>
				{#if configError}<span class="text-danger">{configError}</span>{/if}
			</label>
		</div>

		<details class="rounded border border-line bg-surface-2/40" open={rawKeys.length > 0}>
			<summary class="cursor-pointer px-2 py-1 font-semibold text-fg">Advanced attributes <span class="font-normal text-fg-subtle">({FIELD_RAW_KEYS.join(', ')} … as YAML)</span></summary>
			<div class="px-2 pb-2">
				<textarea class="input w-full resize-y font-mono" rows={rows(rawText)} bind:value={rawText} onblur={commitRaw} spellcheck="false" placeholder={'when: "{{ form.mode == \'fast\' }}"\nreactions: []'}></textarea>
				{#if rawError}<span class="text-danger">{rawError}</span>{/if}
			</div>
		</details>
	</div>
{/if}

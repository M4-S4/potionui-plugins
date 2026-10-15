<script>
	import HostUi from '../../../../../sdk/HostUi.svelte';
	import ActionButton from './ActionButton.svelte';
	import Pill from './Pill.svelte';
	import { renderPipes } from '../lib/client.js';
	import { dumpYaml } from '../lib/yaml.js';

	let { api, presetId, modes = [], publishedAt = null } = $props();

	let mode = $state(modes[0] ?? '');
	let open = $state(false);
	let formData = $state.raw({});
	let rendering = $state(false);
	let rendered = $state.raw(null);
	let renderError = $state('');

	$effect(() => {
		if (!modes.includes(mode)) mode = modes[0] ?? '';
	});

	$effect(() => {
		mode;
		publishedAt;
		rendered = null;
		renderError = '';
	});

	async function render() {
		rendering = true;
		renderError = '';
		const result = await renderPipes(api, presetId, mode, formData);
		rendering = false;
		if (!result.ok) {
			rendered = null;
			renderError = result.error.message;
			return;
		}
		rendered = result.data;
	}

	function configurationOf(node) {
		const configuration = node?.configuration;
		return configuration && typeof configuration === 'object' && Object.keys(configuration).length ? dumpYaml(configuration, { lineWidth: -1 }).trimEnd() : '';
	}
</script>

<section class="rounded-lg border border-line bg-surface-1">
	<header class="flex flex-wrap items-center gap-2 px-4 py-2.5">
		<h3 class="text-sm font-semibold text-fg">Form preview</h3>
		<span class="text-xs text-fg-subtle">of the published version{publishedAt ? '' : ' (publish first)'}</span>
		<span class="flex-1"></span>
		{#if publishedAt && modes.length}
			<select class="input text-xs" bind:value={mode} aria-label="Mode to preview">
				{#each modes as item (item)}
					<option value={item}>{item}</option>
				{/each}
			</select>
			<button type="button" class="rounded px-2 py-0.5 text-xs text-fg-muted hover:bg-surface-3/60 hover:text-fg" onclick={() => (open = !open)}>{open ? 'Hide' : 'Show'}</button>
		{/if}
	</header>
	{#if open && publishedAt && mode}
		<div class="border-t border-line px-4 py-3">
			{#key `${presetId}:${mode}:${publishedAt}`}
				<HostUi name="DynamicForm" props={{ presetId, mode, audience: 'advanced', initialData: {}, onFormDataChange: (data) => (formData = data && typeof data === 'object' ? { ...data } : {}) }} />
			{/key}
		</div>
		<div class="space-y-2 border-t border-line px-4 py-3 text-xs">
			<div class="flex flex-wrap items-center gap-2">
				<ActionButton icon="publish" loading={rendering} onclick={render} title="POST /api/presets/{presetId}/pipes with the values of the form above">Render the pipeline with these values</ActionButton>
				{#if rendered}
					<span class="text-fg-subtle">{rendered.debug_info?.enabled_pipes ?? rendered.nodes?.length ?? 0} enabled pipe{(rendered.debug_info?.enabled_pipes ?? 0) === 1 ? '' : 's'} of {rendered.nodes?.length ?? 0}{rendered.debug_info?.missing_pipes ? `, ${rendered.debug_info.missing_pipes} not installed` : ''}</span>
				{/if}
			</div>
			{#if renderError}
				<p class="rounded border border-danger/40 bg-danger/10 px-2 py-1 text-danger" role="alert">{renderError}. PotionUI renders the pipeline the way a generation would, so every form value the pipeline reads (models included) must be filled in above; the server log has the template error.</p>
			{/if}
			{#if rendered}
				<ol class="space-y-1">
					{#each rendered.nodes ?? [] as node, index (node.id ?? index)}
						<li class="rounded border border-line bg-surface-2/40 px-2 py-1">
							<div class="flex flex-wrap items-center gap-2">
								<span class="text-fg-subtle">{index + 1}</span>
								<span class="font-mono text-fg">{node.name}{node.id && node.id !== node.name ? ` (${node.id})` : ''}</span>
								{#if !node.enabled}<Pill tone="neutral">disabled</Pill>{/if}
								{#if node.status === 'not_found'}<Pill tone="danger">not installed</Pill>{/if}
							</div>
							{#if configurationOf(node)}
								<pre class="mt-1 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-2xs text-fg-muted">{configurationOf(node)}</pre>
							{/if}
						</li>
					{/each}
				</ol>
			{/if}
		</div>
	{/if}
</section>

<script>
	import HostUi from '../../../../../sdk/HostUi.svelte';
	import {
		CATEGORIES,
		CLOUD_MODES,
		ENGINES,
		blankFormProblems,
		blankModes,
		blankRequestBody,
		copyFormProblems,
		copyRequestBody,
		initialBlankForm,
		initialCopyForm,
		targetDirOf
	} from '../lib/drafts.js';
	import { familySpec } from '../lib/families.js';

	let { sources = [], families = [], pipes = null, initial = null, kind: initialKind = 'copy', withPublishNow = false, onChange = () => {} } = $props();

	const uid = $props.id();
	let kind = $state(initialKind);
	let copy = $state(initial ?? initialCopyForm(null));
	let blank = $state({ ...initialBlankForm(), name: initial?.name ?? '', model_dir: initial?.model_dir ?? '' });
	let publishNow = $state(false);

	const sourceIds = $derived(sources.map((entry) => entry.id));
	const copyProblems = $derived(copyFormProblems(copy, { sourceIds }));
	const blankProblems = $derived(blankFormProblems(blank));
	const family = $derived(blank.engine === 'native' && blank.family && pipes ? familySpec(pipes, blank.family) : null);
	const target = $derived(kind === 'copy' ? targetDirOf(copy) : targetDirOf(blank));
	const usableFamilies = $derived(families.filter((item) => item.generator_name));

	$effect(() => {
		const problems = kind === 'copy' ? copyProblems : blankProblems;
		const body = kind === 'copy' ? copyRequestBody(copy) : blankRequestBody(blank, family);
		onChange({ kind, body: Object.keys(problems).length ? null : body, problems: { ...problems }, publishNow });
	});

	function pickSource(event) {
		const source = sources.find((entry) => entry.id === event.currentTarget.value) ?? null;
		copy = { ...initialCopyForm(source), name: copy.name || initialCopyForm(source).name };
	}

	function toggleCloudMode(mode) {
		blank.cloudModes = blank.cloudModes.includes(mode) ? blank.cloudModes.filter((item) => item !== mode) : [...blank.cloudModes, mode];
	}
</script>

<div class="space-y-3">
	<div class="flex gap-1 rounded-md bg-surface-2 p-0.5" role="tablist">
		<button type="button" role="tab" aria-selected={kind === 'copy'} class="flex-1 rounded px-3 py-1 text-xs font-medium transition-colors {kind === 'copy' ? 'bg-surface-1 text-fg shadow-sm' : 'text-fg-muted hover:text-fg'}" onclick={() => (kind = 'copy')}>Copy of a preset</button>
		<button type="button" role="tab" aria-selected={kind === 'blank'} class="flex-1 rounded px-3 py-1 text-xs font-medium transition-colors {kind === 'blank' ? 'bg-surface-1 text-fg shadow-sm' : 'text-fg-muted hover:text-fg'}" onclick={() => (kind = 'blank')}>Blank skeleton</button>
	</div>

	{#if kind === 'copy'}
		<HostUi name="DetailField" props={{ label: 'Preset to copy', id: `${uid}-from`, wide: true, error: copyProblems.from_id || null }}>
			<select id="{uid}-from" class="input w-full text-sm" value={copy.from_id} onchange={pickSource} data-autofocus>
				{#if !copy.from_id}
					<option value="" disabled>Choose a preset…</option>
				{/if}
				{#each sources as entry (entry.id)}
					<option value={entry.id}>{entry.name} · {entry.kind}{entry.path ? ` · ${entry.path}` : ''}</option>
				{/each}
			</select>
		</HostUi>
		<HostUi name="DetailField" props={{ label: 'Name', id: `${uid}-name`, wide: true, error: copyProblems.name || null }}>
			<input id="{uid}-name" type="text" class="input w-full text-sm" autocomplete="off" bind:value={copy.name} />
		</HostUi>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
			<HostUi name="DetailField" props={{ label: 'Model folder', id: `${uid}-model`, wide: true, error: copyProblems.model_dir || null }}>
				<input id="{uid}-model" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" bind:value={copy.model_dir} />
			</HostUi>
			<HostUi name="DetailField" props={{ label: 'Variant folder (optional)', id: `${uid}-variant`, wide: true, error: copyProblems.variant_dir || null }}>
				<input id="{uid}-variant" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" bind:value={copy.variant_dir} />
			</HostUi>
		</div>
		<HostUi name="DetailField" props={{ label: 'Preset id (optional)', id: `${uid}-id`, wide: true, error: copyProblems.preset_id || null, help: 'Leave empty for a generated id, like the presets PotionUI ships' }}>
			<input id="{uid}-id" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" placeholder="generated" bind:value={copy.preset_id} />
		</HostUi>
	{:else}
		<HostUi name="DetailField" props={{ label: 'Name', id: `${uid}-bname`, wide: true, error: blankProblems.name || null }}>
			<input id="{uid}-bname" type="text" class="input w-full text-sm" autocomplete="off" bind:value={blank.name} data-autofocus />
		</HostUi>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
			<HostUi name="DetailField" props={{ label: 'Model folder', id: `${uid}-bmodel`, wide: true, error: blankProblems.model_dir || null }}>
				<input id="{uid}-bmodel" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" bind:value={blank.model_dir} />
			</HostUi>
			<HostUi name="DetailField" props={{ label: 'Variant folder (optional)', id: `${uid}-bvariant`, wide: true, error: blankProblems.variant_dir || null }}>
				<input id="{uid}-bvariant" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" bind:value={blank.variant_dir} />
			</HostUi>
		</div>
		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
			<HostUi name="DetailField" props={{ label: 'Engine', id: `${uid}-engine`, wide: true, error: blankProblems.engine || null }}>
				<select id="{uid}-engine" class="input w-full text-sm" bind:value={blank.engine}>
					{#each ENGINES as engine (engine)}
						<option value={engine}>{engine}</option>
					{/each}
				</select>
			</HostUi>
			<HostUi name="DetailField" props={{ label: 'Category', id: `${uid}-category`, wide: true, error: blankProblems.category || null, help: 'Empty: image, or the category of the first cloud mode' }}>
				<select id="{uid}-category" class="input w-full text-sm" bind:value={blank.category}>
					<option value="">(automatic)</option>
					{#each CATEGORIES as category (category)}
						<option value={category}>{category}</option>
					{/each}
				</select>
			</HostUi>
		</div>
		{#if blank.engine === 'cloud'}
			<HostUi name="DetailField" props={{ label: 'Driver', id: `${uid}-driver`, wide: true, error: blankProblems.driver || null, help: 'The cloud provider plugin, e.g. cloud.openrouter' }}>
				<input id="{uid}-driver" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" placeholder="cloud.openrouter" bind:value={blank.driver} />
			</HostUi>
			<HostUi name="DetailField" props={{ label: 'Modes', id: `${uid}-cmodes`, wide: true, error: blankProblems.modes || null }}>
				<div id="{uid}-cmodes" class="flex flex-wrap gap-3">
					{#each CLOUD_MODES as mode (mode)}
						<label class="flex items-center gap-1.5 text-xs text-fg">
							<input type="checkbox" checked={blank.cloudModes.includes(mode)} onchange={() => toggleCloudMode(mode)} />
							{mode}
						</label>
					{/each}
				</div>
			</HostUi>
		{:else}
			<HostUi name="DetailField" props={{ label: 'Modes', id: `${uid}-modes`, wide: true, error: blankProblems.modes || null, help: 'Separated by commas, e.g. txt2img, img2img' }}>
				<input id="{uid}-modes" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" bind:value={blank.modes} />
			</HostUi>
			{#if blank.engine === 'native'}
				<HostUi name="DetailField" props={{ label: 'Model family (optional)', id: `${uid}-family`, wide: true, help: usableFamilies.length ? 'Wires the standard native chain to this family of pipes' : pipes ? 'No model_loader pipe with a generator on this instance' : 'Loading the pipe catalogue…' }}>
					<select id="{uid}-family" class="input w-full text-sm" bind:value={blank.family} disabled={!usableFamilies.length}>
						<option value="">Placeholder pipeline (gallery only)</option>
						{#each usableFamilies as item (item.family)}
							<option value={item.family}>{item.family} · {item.generator_name}</option>
						{/each}
					</select>
				</HostUi>
			{/if}
		{/if}
		<HostUi name="DetailField" props={{ label: 'Preset id (optional)', id: `${uid}-bid`, wide: true, error: blankProblems.preset_id || null }}>
			<input id="{uid}-bid" type="text" class="input w-full font-mono text-sm" autocomplete="off" spellcheck="false" placeholder="generated" bind:value={blank.preset_id} />
		</HostUi>
	{/if}

	{#if withPublishNow}
		<label class="flex items-center gap-1.5 text-xs text-fg-muted">
			<input type="checkbox" bind:checked={publishNow} />
			Publish right away and stay here (no editing)
		</label>
	{/if}

	<p class="text-xs text-fg-subtle">
		Published to <span class="font-mono text-fg-muted">content/presets/local/{target || '…'}</span>
		{#if kind === 'blank'}· modes <span class="font-mono text-fg-muted">{blankModes(blank).join(', ') || '…'}</span>{/if}
	</p>
</div>

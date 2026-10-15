<script>
	import HostUi from '../../../../../sdk/HostUi.svelte';
	import { copyFormProblems, initialCopyForm, targetDirOf } from '../lib/drafts.js';

	let { sources = [], initial = null, onChange = () => {} } = $props();

	const uid = $props.id();
	let form = $state(initial ?? initialCopyForm(null));

	const sourceIds = $derived(sources.map((entry) => entry.id));
	const problems = $derived(copyFormProblems(form, { sourceIds }));
	const target = $derived(targetDirOf(form));

	$effect(() => {
		onChange({ form: { ...form }, problems: { ...problems } });
	});

	function pickSource(event) {
		const source = sources.find((entry) => entry.id === event.currentTarget.value) ?? null;
		form = { ...initialCopyForm(source), name: form.name || initialCopyForm(source).name };
	}
</script>

<div class="space-y-3">
	<HostUi name="DetailField" props={{ label: 'Preset to copy', id: `${uid}-from`, wide: true, error: problems.from_id || null }}>
		<select id="{uid}-from" class="input w-full text-sm" value={form.from_id} onchange={pickSource} data-autofocus>
			{#if !form.from_id}
				<option value="" disabled>Choose a preset…</option>
			{/if}
			{#each sources as entry (entry.id)}
				<option value={entry.id}>{entry.name} · {entry.kind}{entry.path ? ` · ${entry.path}` : ''}</option>
			{/each}
		</select>
	</HostUi>

	<HostUi name="DetailField" props={{ label: 'Name', id: `${uid}-name`, wide: true, error: problems.name || null }}>
		<input id="{uid}-name" type="text" class="input w-full text-sm {problems.name ? 'border-danger' : ''}" autocomplete="off" bind:value={form.name} aria-invalid={problems.name ? 'true' : undefined} />
	</HostUi>

	<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
		<HostUi name="DetailField" props={{ label: 'Model folder', id: `${uid}-model`, wide: true, error: problems.model_dir || null }}>
			<input id="{uid}-model" type="text" class="input w-full font-mono text-sm {problems.model_dir ? 'border-danger' : ''}" autocomplete="off" spellcheck="false" bind:value={form.model_dir} aria-invalid={problems.model_dir ? 'true' : undefined} />
		</HostUi>
		<HostUi name="DetailField" props={{ label: 'Variant folder (optional)', id: `${uid}-variant`, wide: true, error: problems.variant_dir || null }}>
			<input id="{uid}-variant" type="text" class="input w-full font-mono text-sm {problems.variant_dir ? 'border-danger' : ''}" autocomplete="off" spellcheck="false" bind:value={form.variant_dir} aria-invalid={problems.variant_dir ? 'true' : undefined} />
		</HostUi>
	</div>

	<HostUi name="DetailField" props={{ label: 'Preset id (optional)', id: `${uid}-id`, wide: true, error: problems.preset_id || null, help: 'Leave empty for a generated id, like the presets PotionUI ships' }}>
		<input id="{uid}-id" type="text" class="input w-full font-mono text-sm {problems.preset_id ? 'border-danger' : ''}" autocomplete="off" spellcheck="false" placeholder="generated" bind:value={form.preset_id} aria-invalid={problems.preset_id ? 'true' : undefined} />
	</HostUi>

	<p class="text-xs text-fg-subtle">
		Published to <span class="font-mono text-fg-muted">content/presets/local/{target || '…'}</span>
	</p>
</div>

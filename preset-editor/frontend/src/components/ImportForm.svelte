<script>
	import { MAX_NAME_LENGTH, PRESET_ID_RE, SEGMENT_RE } from '../lib/drafts.js';

	let { onChange } = $props();

	let file = $state(null);
	let modelDir = $state('');
	let variantDir = $state('');
	let name = $state('');
	let presetId = $state('');

	const problems = $derived.by(() => {
		const found = {};
		if (!file) found.file = 'choose a zip archive';
		else if (!/\.zip$/i.test(file.name)) found.file = 'a .zip file';
		if (!modelDir.trim()) found.modelDir = 'required';
		else if (!SEGMENT_RE.test(modelDir.trim())) found.modelDir = 'letters, digits, ., _ and -';
		if (variantDir.trim() && !SEGMENT_RE.test(variantDir.trim())) found.variantDir = 'letters, digits, ., _ and -';
		if (name.trim().length > MAX_NAME_LENGTH) found.name = `at most ${MAX_NAME_LENGTH} characters`;
		if (presetId.trim() && !PRESET_ID_RE.test(presetId.trim())) found.presetId = '3 to 64 letters, digits, _ or -';
		return found;
	});

	$effect(() => {
		let body = null;
		if (!Object.keys(problems).length) {
			body = new FormData();
			body.append('file', file, file.name);
			body.append('model_dir', modelDir.trim());
			if (variantDir.trim()) body.append('variant_dir', variantDir.trim());
			if (name.trim()) body.append('name', name.trim());
			if (presetId.trim()) body.append('preset_id', presetId.trim());
		}
		onChange?.({ body, problems });
	});
</script>

<div class="space-y-3 text-xs">
	<p class="text-fg-muted">A zip of a preset folder: <span class="font-mono">preset.yml</span> at its root (or inside a single folder), then <span class="font-mono">modes/</span>, <span class="font-mono">public/</span> and the other files. The archive is unpacked into a new draft and linted; publishing it later checks that its id is free.</p>
	<label class="block">
		<span class="mb-0.5 block text-fg-muted">Archive</span>
		<input type="file" class="input w-full" accept=".zip,application/zip" onchange={(event) => (file = event.currentTarget.files?.[0] ?? null)} />
		{#if problems.file}<span class="text-danger">{problems.file}</span>{/if}
	</label>
	<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
		<label class="block">
			<span class="mb-0.5 block text-fg-muted">Model folder <span class="text-fg-subtle">(content/presets/local/…)</span></span>
			<input type="text" class="input w-full font-mono" bind:value={modelDir} placeholder="MyModel" />
			{#if problems.modelDir}<span class="text-danger">{problems.modelDir}</span>{/if}
		</label>
		<label class="block">
			<span class="mb-0.5 block text-fg-muted">Variant folder <span class="text-fg-subtle">(optional)</span></span>
			<input type="text" class="input w-full font-mono" bind:value={variantDir} placeholder="custom" />
			{#if problems.variantDir}<span class="text-danger">{problems.variantDir}</span>{/if}
		</label>
		<label class="block">
			<span class="mb-0.5 block text-fg-muted">Name <span class="text-fg-subtle">(optional, replaces the archive's)</span></span>
			<input type="text" class="input w-full" bind:value={name} />
			{#if problems.name}<span class="text-danger">{problems.name}</span>{/if}
		</label>
		<label class="block">
			<span class="mb-0.5 block text-fg-muted">Preset id <span class="text-fg-subtle">(optional, replaces the archive's)</span></span>
			<input type="text" class="input w-full font-mono" bind:value={presetId} />
			{#if problems.presetId}<span class="text-danger">{problems.presetId}</span>{/if}
		</label>
	</div>
</div>

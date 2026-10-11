<script>
	import { onMount } from 'svelte';
	// Host wrapper from the PotionUI plugin SDK: resolves only when the plugin sits at
	// content/plugins/<tree>/model-browser (scripts/build-plugins.ps1 mirrors it there).
	import HostUi from '../../../../sdk/HostUi.svelte';
	import { fetchHealth, healthLabel } from './lib/client.js';

	// `api` and `setHeaderHidden` come from the host's plugin page (see index.js).
	let { api, setHeaderHidden } = $props();

	const sections = [{ id: 'civitai', label: 'CivitAI' }];

	let section = $state('civitai');
	let q = $state('');
	// Result of the /health call; null while it is running.
	let health = $state(null);

	const statusText = $derived(healthLabel(health));
	const failed = $derived(health !== null && !health.ok);

	onMount(() => {
		// LibraryPage draws its own header (title and search), so hide the host's header row.
		setHeaderHidden?.(true);

		let cancelled = false;
		fetchHealth(api).then((result) => {
			if (!cancelled) health = result;
		});
		return () => {
			cancelled = true;
		};
	});
</script>

<HostUi
	name="LibraryPage"
	props={{
		title: 'Model Browser',
		titleLabel: 'Model Browser',
		persistKey: 'model-browser:page',
		sections,
		section,
		onSelectSection: (id) => {
			section = id;
		},
		count: 0,
		q,
		onQueryChange: (value) => {
			q = value;
		},
		searchPlaceholder: 'Search models'
	}}
>
	<div class="space-y-4 p-4 sm:p-6">
		<p class="text-md font-medium text-fg">Model Browser — phase 0</p>

		<p
			class="inline-flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm {failed ? 'text-danger' : 'text-fg-muted'}"
			role="status"
		>
			<span
				class="h-2 w-2 flex-shrink-0 rounded-full {health === null ? 'bg-fg-subtle' : health.ok ? 'bg-success' : 'bg-danger'}"
				aria-hidden="true"
			></span>
			{statusText}
		</p>

		{#if q}
			<p class="text-sm text-fg-subtle">Search text: {q}</p>
		{/if}
	</div>
</HostUi>

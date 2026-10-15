<script>
	import { onMount } from 'svelte';
	import HostUi from '../../../../sdk/HostUi.svelte';
	import LocalPresetMenu from './components/LocalPresetMenu.svelte';
	import { localPresets, normalizeCatalog } from './lib/catalog.js';
	import { listCatalog } from './lib/client.js';
	import { standaloneApi } from './lib/hostApi.js';

	const PAGE_ROUTE = '/plugins/preset-editor';
	const NEW_PRESET_URL = `${PAGE_ROUTE}?new=1`;

	let phase = $state('loading');
	let error = $state('');
	let entries = $state.raw([]);

	onMount(load);

	async function load() {
		phase = 'loading';
		const result = await listCatalog(standaloneApi());
		if (!result.ok) {
			error = result.error.message;
			phase = 'error';
			return;
		}
		entries = localPresets(normalizeCatalog(result.data));
		phase = 'ready';
	}
</script>

<div class="flex items-center gap-2">
	<HostUi
		name="Button"
		props={{
			variant: 'secondary',
			size: 'sm',
			icon: 'plus',
			href: NEW_PRESET_URL,
			title: 'Create a preset with the Preset Editor'
		}}
	>
		New Preset
	</HostUi>
	<LocalPresetMenu {entries} {phase} {error} pageRoute={PAGE_ROUTE} />
</div>

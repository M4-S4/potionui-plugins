<script>
	import { onMount } from 'svelte';
	import HostUi from '../../../../sdk/HostUi.svelte';
	import { isAdmin, pageIntent } from './lib/access.js';
	import { getMe } from './lib/client.js';

	let { api, user } = $props();

	const INTENT_TITLES = {
		new: 'New preset',
		draft: 'Draft',
		preset: 'Edit a local preset',
		list: 'Preset Editor'
	};

	let phase = $state(isAdmin(user) ? 'loading' : 'forbidden');
	let error = $state.raw(null);
	let me = $state.raw(null);

	const intent = pageIntent(typeof location === 'undefined' ? '' : location.search);
	const title = $derived(INTENT_TITLES[intent.kind]);
	const description = $derived(
		intent.id
			? `${intent.kind === 'draft' ? 'Draft' : 'Preset'} ${intent.id}. The editor arrives with the next phases.`
			: 'Drafts, the file editor and publishing arrive with the next phases.'
	);

	onMount(() => {
		if (phase !== 'forbidden') boot();
	});

	async function boot() {
		const result = await getMe(api);
		if (!result.ok) {
			error = result.error;
			phase = result.error.status === 401 || result.error.status === 403 ? 'forbidden' : 'error';
			return;
		}
		me = result.data;
		phase = 'ready';
	}
</script>

<HostUi name="PageContainer" props={{ width: 'md' }}>
	{#if phase === 'forbidden'}
		<HostUi
			name="EmptyState"
			props={{
				icon: 'shield',
				title: 'Reserved for administrators',
				description: 'The Preset Editor creates and publishes presets for the whole instance.'
			}}
		/>
	{:else if phase === 'error'}
		<HostUi
			name="EmptyState"
			props={{
				icon: 'shield',
				tone: 'danger',
				title: 'The Preset Editor could not start',
				description: error?.message ?? 'Request failed'
			}}
		/>
	{:else if phase === 'loading'}
		<div class="flex items-center justify-center py-14">
			<HostUi name="Spinner" props={{ size: 'lg' }} />
		</div>
	{:else}
		<HostUi name="EmptyState" props={{ icon: 'edit', title, description }} />
		<p class="mt-3 text-center text-xs text-fg-subtle">Preset Editor {me?.version} · signed in as administrator</p>
	{/if}
</HostUi>

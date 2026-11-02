<script>
	import { ui, directorView } from '../../lib/state.svelte.js';
	import Inspector from '../inspector/Inspector.svelte';
	import ReviewAside from '../director/ReviewAside.svelte';
	import DirectionAside from '../director/DirectionAside.svelte';
	import BibleAside from '../director/BibleAside.svelte';
	import ReferenceAside from '../director/ReferenceAside.svelte';

	const view = $derived(ui.workspace === 'director' ? directorView() : null);
</script>

{#if view === 'review'}
	<ReviewAside />
{:else if view === 'direction'}
	<DirectionAside />
{:else if view === 'bible'}
	<BibleAside />
{:else if view === 'references'}
	<ReferenceAside />
{:else}
	<Inspector />
{/if}

<script>
	import { directorView } from '../../lib/state.svelte.js';
	import ReviewView from './ReviewView.svelte';
	import DirectionView from './DirectionView.svelte';
	import BibleView from './BibleView.svelte';
	import ReferenceBoard from '../references/ReferenceBoard.svelte';

	const view = $derived(directorView());
</script>

{#if view === 'direction'}
	<DirectionView />
{:else if view === 'bible'}
	<BibleView />
{:else if view === 'references'}
	<ReferenceBoard />
{:else}
	<ReviewView />
{/if}

<script>
	// The "Requests" toolbar button, for users who may ask for models or decide on requests, with a
	// count: for those who decide, the open requests they may act on (`/me.requests.open_count`);
	// for the others, their own open requests. It opens RequestsPanel. The count is read again
	// after each change: the page calls `refreshCount()` once a request is sent, the panel after
	// each list it reads (every 15 s while open, and after each answer).
	import { onMount } from 'svelte';
	import Icon from './Icon.svelte';
	import RequestsPanel from './RequestsPanel.svelte';
	import { canDecide, fetchBadgeCount, initialBadgeCount } from '../lib/requests.js';

	let { api, me, sourceLabel = (id) => id } = $props();

	// The approvers' count comes with `/me`; the others' needs one call (onMount).
	const startingCount = () => initialBadgeCount(me);
	let count = $state(startingCount());
	let open = $state(false);
	let button = $state();

	let seq = 0;
	let destroyed = false;

	const decide = $derived(canDecide(me));
	const countText = $derived(decide ? `${count} waiting for a decision` : `${count} still open`);

	onMount(() => {
		if (count === null) refreshCount();
		return () => {
			destroyed = true;
		};
	});

	/** Open the drawer as a click on the button does (the page does it for `?tab=requests`). */
	export function openPanel() {
		open = true;
	}

	/** Read the count again (after a request is sent, approved, rejected or cancelled). */
	export async function refreshCount() {
		const mine = ++seq;
		const next = await fetchBadgeCount(api, me);
		if (mine !== seq || destroyed) return;
		if (next !== null) count = next;
	}
</script>

<!-- The app's `.input` is full width: the wrapper sizes it, as LibraryFilterBar does. -->
<div class="relative flex-shrink-0">
	<button
		bind:this={button}
		type="button"
		class="input flex h-8 items-center gap-1.5 whitespace-nowrap text-xs font-medium"
		aria-haspopup="dialog"
		aria-expanded={open}
		onclick={() => (open = true)}
	>
		<Icon name="inbox" class="h-3.5 w-3.5 text-fg-subtle" />
		<span>Requests</span>
		{#if count > 0}
			<span class="rounded-full bg-signal/10 px-1.5 font-mono text-2xs tabular-nums text-signal" title={countText} aria-hidden="true">{count}</span>
			<span class="sr-only">({countText})</span>
		{/if}
	</button>
</div>

{#if open}
	<RequestsPanel {api} {me} {count} {sourceLabel} opener={button} onClose={() => (open = false)} onChanged={refreshCount} />
{/if}

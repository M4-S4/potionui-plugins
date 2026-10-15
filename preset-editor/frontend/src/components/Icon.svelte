<script>
	let { name, class: className = 'h-4 w-4', strokeWidth = 2 } = $props();

	const PATHS = {
		plus: ['M12 4v16m8-8H4'],
		edit: ['M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z'],
		copy: ['M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z'],
		trash: ['M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16'],
		history: ['M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'],
		restore: ['M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6'],
		publish: ['M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12'],
		check: ['M5 13l4 4L19 7'],
		'check-circle': ['M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z'],
		warning: ['M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'],
		info: ['M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'],
		'external-link': ['M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14'],
		close: ['M6 18L18 6M6 6l12 12'],
		'chevron-down': ['M19 9l-7 7-7-7'],
		'arrow-left': ['M10 19l-7-7m0 0l7-7m-7 7h18'],
		refresh: ['M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15'],
		document: ['M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'],
		folder: ['M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z'],
		search: ['M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z'],
		shield: ['M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z']
	};

	const paths = $derived(PATHS[name] ?? []);
</script>

{#if paths.length}
	<svg class={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
		{#each paths as d (d)}
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width={strokeWidth} {d} />
		{/each}
	</svg>
{/if}

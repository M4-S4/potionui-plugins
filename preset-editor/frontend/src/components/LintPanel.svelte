<script>
	import Icon from './Icon.svelte';
	import Pill from './Pill.svelte';
	import { formatTimestamp, lintSummary } from '../lib/drafts.js';

	let { lint = null } = $props();

	const summary = $derived(lintSummary(lint));
</script>

<section class="rounded-lg border border-line bg-surface-1">
	<header class="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
		<h3 class="text-sm font-semibold text-fg">Lint</h3>
		{#if !lint}
			<Pill tone="neutral">not run yet</Pill>
		{:else if summary.clean}
			<Pill tone="success"><Icon name="check" class="h-3 w-3" />no error</Pill>
		{:else}
			<Pill tone="danger">{summary.errors.length} error{summary.errors.length > 1 ? 's' : ''}</Pill>
		{/if}
		{#if summary.warnings.length}
			<Pill tone="warning">{summary.warnings.length} warning{summary.warnings.length > 1 ? 's' : ''}</Pill>
		{/if}
		{#if summary.at}
			<span class="ml-auto text-2xs text-fg-subtle">{formatTimestamp(summary.at)}</span>
		{/if}
	</header>
	{#if summary.files.length}
		<ul class="divide-y divide-line">
			{#each summary.files as group (group.file)}
				<li class="px-4 py-2">
					<p class="font-mono text-xs text-fg-muted">{group.file}</p>
					<ul class="mt-1 space-y-1">
						{#each group.issues as issue, index (index)}
							<li class="flex items-start gap-2 text-xs">
								<Icon name={issue.level === 'error' ? 'close' : issue.level === 'warning' ? 'warning' : 'info'} class="mt-0.5 h-3.5 w-3.5 flex-shrink-0 {issue.level === 'error' ? 'text-danger' : issue.level === 'warning' ? 'text-warning' : 'text-info'}" />
								<span class="break-words text-fg">{issue.message}</span>
							</li>
						{/each}
					</ul>
				</li>
			{/each}
		</ul>
	{:else if lint}
		<p class="px-4 py-3 text-xs text-fg-subtle">The linter found nothing to report.</p>
	{/if}
</section>

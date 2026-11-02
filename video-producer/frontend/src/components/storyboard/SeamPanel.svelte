<script>
	import { t } from '../../i18n/index.svelte.js';
	import { doc, clipLabel } from '../../lib/state.svelte.js';
	import { seam } from '../../lib/continuity.svelte.js';
	import { openSeam } from '../../lib/band.svelte.js';
	import ChainSwitch from '../shots/ChainSwitch.svelte';
	import SeamFix from './SeamFix.svelte';
	import Icon from '../Icon.svelte';
	import { shotNumberAt } from '../../lib/shots.js';

	let { clip, title = true, compare = true } = $props();

	const index = $derived(doc.clips.findIndex((c) => c.id === clip?.id));
	const sm = $derived(index > 0 ? seam(index) : null);
	const firstFix = $derived(sm ? sm.issues.findIndex((x) => x.fix) : -1);
</script>

{#if sm}
	<div class="flex w-full flex-col gap-2.5" data-seam-panel={clip.id}>
		{#if title}
			<div class="flex items-center gap-2 text-xs">
				<span class="font-semibold text-fg">{t('storyboard.band.seamTitle', { n: shotNumberAt(index - 1), m: shotNumberAt(index) })}</span>
				<span class="min-w-0 flex-1 truncate text-fg-subtle">{clipLabel(sm.from)} → {clipLabel(sm.to)}</span>
			</div>
		{/if}
		<ul class="flex flex-col gap-1.5 text-xs">
			{#each sm.issues as issue, n (n)}
				<li class="flex items-start gap-2" data-seam-issue={issue.kind}>
					<Icon name="alert" class="mt-px h-3.5 w-3.5 shrink-0 text-warning" />
					<div class="min-w-0 flex-1">
						<span class="block text-fg-muted">{issue.text}{#if issue.kind === 'identity'}<span class="mt-0.5 block text-2xs text-fg-subtle" data-look-hint>{t('lib.continuity.lookHint')}</span>{/if}</span>
						{#if !issue.fix || n === firstFix}<div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1"><SeamFix {clip} {issue} /></div>{/if}
					</div>
				</li>
			{:else}
				<li class="flex items-center gap-2 text-fg-muted"><Icon name="check" class="h-3.5 w-3.5 text-success" />{sm.measured ? t('panels.story.continuityOk') : t('panels.story.continuityNone')}</li>
			{/each}
		</ul>
		<div class="border-t border-line pt-2"><ChainSwitch {clip} /></div>
		{#if compare}
			<button type="button" class="vp-link-hit self-start text-xs text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => openSeam(clip)}>{t('storyboard.band.seamCompare')}</button>
		{/if}
	</div>
{/if}

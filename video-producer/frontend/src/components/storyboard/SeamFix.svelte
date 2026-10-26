<script>
	import { t } from '../../i18n/index.svelte.js';
	import { matchToPrevious } from '../../lib/continuity.svelte.js';
	import { compareSeamTakes } from '../../lib/band.svelte.js';
	import SeamAction from '../takes/SeamAction.svelte';

	let { clip, issue } = $props();

	const link = 'vp-link-hit shrink-0 text-left text-fg underline decoration-signal underline-offset-2 hover:decoration-2';

	function run(event, action) {
		event.stopPropagation();
		action(clip);
	}
</script>

{#if issue.fix}
	<button type="button" class={link} data-seam-fix="color" onclick={(e) => run(e, matchToPrevious)}>{t('panels.story.matchColor')}</button>
{:else if issue.kind === 'identity'}
	<button type="button" class={link} data-seam-fix="identity" onclick={(e) => run(e, compareSeamTakes)}>{t('storyboard.seam.compareTakes')}</button>
{:else if issue.kind.startsWith('chain_')}
	<span class="shrink-0" data-seam-fix="chain"><SeamAction {clip} /></span>
{/if}

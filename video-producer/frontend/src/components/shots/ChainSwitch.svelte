<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { chainStatusText, followProjectChain, seamChainOf, setShotChaining } from '../../lib/chain.svelte.js';

	let { clip } = $props();

	const chain = $derived(seamChainOf(clip));
	const id = $derived(`vp-chain-${clip?.id}`);
	const tone = $derived(chain?.state === 'textOnly' || chain?.state === 'stale' ? 'text-warning' : 'text-fg-subtle');
</script>

{#if chain}
	<div class="space-y-1" data-chain-switch={chain.state}>
		<div class="flex min-h-6 items-center justify-between gap-2 text-xs text-fg-muted">
			<label for={id}>{t('storyboard.chain.label')}</label>
			<HostUi name="Switch" props={{ id, checked: chain.state !== 'off', size: 'lg', label: t('storyboard.chain.label'), onchange: (v) => setShotChaining(clip, Boolean(v)) }} />
		</div>
		<p class="text-xs {tone}">{chainStatusText(chain)}</p>
		<p class="flex flex-wrap items-center gap-x-2 text-2xs text-fg-subtle">
			<span>{chain.own ? t('storyboard.chain.fromShot') : t('storyboard.chain.fromProject')}</span>
			{#if chain.own}<button type="button" class="vp-link-hit text-fg-muted underline decoration-line-hover underline-offset-2 hover:text-fg" onclick={() => followProjectChain(clip)}>{t('storyboard.chain.followProject')}</button>{/if}
		</p>
	</div>
{/if}

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { chainStatusText, chooseShotChainBy, followProjectChain, seamChainOf, setShotChaining } from '../../lib/chain.svelte.js';
	import { chainByOf } from '../../lib/chain.js';
	import { doc } from '../../lib/state.svelte.js';

	let { clip } = $props();

	const chain = $derived(seamChainOf(clip));
	const id = $derived(`vp-chain-${clip?.id}`);
	const choosable = $derived(Boolean(chain) && !['off', 'textOnly'].includes(chain.state));
	const by = $derived(chainByOf(doc, clip));
	const choices = $derived([
		{ id: 'frame', label: t('shell.properties.chainByFrame') },
		{ id: 'video', label: t('shell.properties.chainByVideo') }
	]);
	const tone = $derived(['textOnly', 'stale', 'continueStill', 'continueShort', 'continueOwnLast', 'continueLong', 'continueEncoder'].includes(chain?.state) ? 'text-warning' : 'text-fg-subtle');
</script>

{#if chain}
	<div class="space-y-1" data-chain-switch={chain.state}>
		<div class="flex min-h-6 items-center justify-between gap-2 text-xs text-fg-muted">
			<label for={id}>{t('storyboard.chain.label')}</label>
			<HostUi name="Switch" props={{ id, checked: chain.state !== 'off', size: 'lg', label: t('storyboard.chain.label'), onchange: (v) => setShotChaining(clip, Boolean(v)) }} />
		</div>
		<p class="flex flex-wrap items-center gap-x-2 text-2xs text-fg-subtle" data-chain-source={chain.own ? 'shot' : 'project'}>
			<span>{chain.own ? t('storyboard.chain.fromShot') : t('storyboard.chain.fromProject')}</span>
			{#if chain.own}<button type="button" class="vp-link-hit text-fg-muted underline decoration-line-hover underline-offset-2 hover:text-fg" onclick={() => followProjectChain(clip)}>{t('storyboard.chain.followProject')}</button>{/if}
		</p>
		<p class="text-xs {tone}">{chainStatusText(chain)}</p>
		{#if choosable}
			<div class="flex min-h-6 items-center justify-between gap-2 text-xs text-fg-muted" data-chain-by={by}>
				<span>{t('shell.properties.chainBy')}</span>
				<HostUi name="SegmentedControl" props={{ items: choices, selected: by, onSelect: (v) => chooseShotChainBy(clip, v), ariaLabel: t('shell.properties.chainBy'), variant: 'toggle' }} />
			</div>
		{/if}
	</div>
{/if}

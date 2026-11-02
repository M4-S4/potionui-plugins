<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { clipLabel } from '../../lib/state.svelte.js';
	import { chainStatusText, seamChainOf, toggleShotChaining } from '../../lib/chain.svelte.js';
	import Icon from '../Icon.svelte';

	let { clip, small = false } = $props();

	const chain = $derived(seamChainOf(clip));
	const on = $derived(Boolean(chain) && chain.state !== 'off');
	const dot = $derived(chain?.state === 'textOnly' || chain?.state === 'stale' ? 'bg-warning-solid' : chain?.state === 'waiting' ? 'bg-signal' : null);
	const label = $derived(chain ? (on ? t('storyboard.chain.chipOn', { previous: clipLabel(chain.from) }) : t('storyboard.chain.chipOff', { previous: clipLabel(chain.from) })) : '');

	function toggle(event) {
		event.stopPropagation();
		toggleShotChaining(clip);
	}
</script>

{#if chain}
	<HostUi name="Tooltip" props={{ text: `${label} · ${chainStatusText(chain)}`, wrapperClass: 'inline-flex' }}>
		<button
			type="button"
			class="flex items-center gap-1 bg-black/60 text-white backdrop-blur-sm hover:bg-black/80 {small ? 'h-4 rounded px-1' : 'h-[22px] rounded-md px-1.5'} {on ? '' : 'opacity-60'}"
			aria-pressed={on}
			aria-label={label}
			data-chain-chip={chain.state}
			onpointerdown={(e) => e.stopPropagation()}
			ondblclick={(e) => e.stopPropagation()}
			onclick={toggle}
		>
			<Icon name={on ? 'link' : 'unlink'} class={small ? 'h-3 w-3' : 'h-3.5 w-3.5'} />
			{#if dot}<span class="h-1.5 w-1.5 rounded-full {dot}"></span>{/if}
		</button>
	</HostUi>
{/if}

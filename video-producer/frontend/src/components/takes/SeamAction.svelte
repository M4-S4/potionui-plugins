<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { seamOffer, useSeamFrame } from '../../lib/seam.svelte.js';
	import { clipLabel } from '../../lib/state.svelte.js';
	import { hostIconName } from '../../lib/icons.js';

	let { clip, variant = 'link' } = $props();

	const offer = $derived(seamOffer(clip));
	const action = $derived(offer?.stale ? t('lib.chain.refresh') : t('lib.seam.use'));
	const label = $derived(offer?.busy ? t('lib.seam.working') : action);
	const tip = $derived(!offer?.ready ? (offer?.reason ?? '') : offer.stale ? t('lib.chain.refreshTip', { shot: clipLabel(offer.previous) }) : t('lib.seam.useTip'));

	function run(event) {
		event?.stopPropagation?.();
		useSeamFrame(clip);
	}
</script>

{#if offer}
	{#if variant === 'icon'}
		<HostUi name="IconButton" props={{ icon: hostIconName('image'), label: action, tooltip: offer.ready ? action : tip, size: 'sm', class: 'vp-h7 text-warning', disabled: !offer.ready || offer.busy, onclick: run }} />
	{:else if variant === 'button'}
		<HostUi name="Tooltip" props={{ text: tip, wrapperClass: 'flex w-full' }}>
			<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('image'), class: 'w-full', disabled: !offer.ready || offer.busy, onclick: run }}>{label}</HostUi>
		</HostUi>
	{:else}
		<HostUi name="Tooltip" props={{ text: tip, wrapperClass: 'inline-flex' }}>
			<button
				type="button"
				class="vp-link-hit text-left text-fg underline decoration-signal underline-offset-2 hover:decoration-2 disabled:cursor-default disabled:opacity-50"
				disabled={!offer.ready || offer.busy}
				onclick={run}>{label}</button
			>
		</HostUi>
	{/if}
{/if}

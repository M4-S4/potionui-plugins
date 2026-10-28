<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc } from '../../lib/state.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { passProgress } from '../../lib/finalpass.js';
	import { openFinalPass } from '../../lib/finalpass.svelte.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let { variant = 'ghost', room = null, short = false } = $props();

	const pass = $derived(passProgress(doc.clips, takeStore.list));
	const tip = $derived.by(() => {
		if (pass.running) return t('generation.finalPass.tipRunning', { done: pass.done, total: pass.generated, count: pass.running });
		if (pass.complete) return t('generation.finalPass.tipComplete', { total: pass.generated });
		if (pass.missing) return t('generation.finalPass.tipMissing', { done: pass.done, total: pass.generated, count: pass.missing });
		return t('generation.finalPass.tipReady', { done: pass.done, total: pass.generated });
	});
	const GAP = 12;
	let hidden = $state(false);
	let width = $state(0);
	let shown = 0;

	$effect(() => {
		if (width) shown = width;
	});

	$effect(() => {
		if (!room) return;
		const fit = () => {
			const items = [...room.children];
			const content = items.reduce((sum, el) => sum + el.offsetWidth, 0) + GAP * Math.max(0, items.length - 1);
			hidden = content > room.clientWidth - (hidden ? shown + GAP : 0) + 1;
		};
		const resized = new ResizeObserver(fit);
		const changed = new MutationObserver(fit);
		resized.observe(room);
		changed.observe(room, { childList: true, subtree: true, characterData: true });
		return () => {
			resized.disconnect();
			changed.disconnect();
		};
	});
</script>

{#if pass.generated && !hidden}
	<HostUi name="Tooltip" props={{ text: tip, kbd: commandById('final-pass')?.key, wrapperClass: 'inline-flex shrink-0' }}>
		{#if variant === 'ghost'}
			<button type="button" class="flex h-7 shrink-0 items-center gap-1.5 whitespace-nowrap rounded px-2 text-xs font-medium text-fg-muted hover:bg-surface-2 hover:text-fg" aria-label={tip} bind:offsetWidth={width} onclick={openFinalPass}>
				{#if pass.running}<HostUi name="Spinner" props={{ size: 'sm' }} />{:else}<Icon name={pass.complete ? 'check' : 'arrow-up'} class="h-3.5 w-3.5 {pass.complete ? 'text-success' : ''}" />{/if}
				{#if !short}{t('generation.finalPass.button')}{/if}
				<span class="vp-tc {pass.complete ? 'text-success' : 'text-fg'}">{t('generation.finalPass.count', { done: pass.done, total: pass.generated })}</span>
			</button>
		{:else}
			<HostUi name="Button" props={{ variant, size: 'sm', icon: hostIconName('arrow-up'), onclick: openFinalPass }}>{t('generation.finalPass.button')} · {t('generation.finalPass.count', { done: pass.done, total: pass.generated })}</HostUi>
		{/if}
	</HostUi>
{/if}

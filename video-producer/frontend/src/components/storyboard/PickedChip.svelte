<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { clearPicked, pickedClips } from '../../lib/state.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	const count = $derived(pickedClips().length);
</script>

{#if count}
	<span class="flex h-7 min-w-0 items-center gap-1 rounded-full pl-2.5 pr-0.5 text-xs font-medium text-signal" style:background="rgb(var(--signal) / 0.12)" title={t('storyboard.pick.count', { count })} data-picked-chip={count}>
		<Icon name="check" class="h-3.5 w-3.5 shrink-0" /><span class="truncate" aria-label={t('storyboard.pick.count', { count })}>{t('storyboard.pick.chip', { count })}</span>
		<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('storyboard.pick.clear'), tooltip: t('storyboard.pick.clearTip', { key: t('commands.kbd.escape') }), size: 'xs', onclick: clearPicked }} />
	</span>
{/if}

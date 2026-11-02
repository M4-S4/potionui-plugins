<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, directorView } from '../../lib/state.svelte.js';
	import { commandById } from '../../lib/commands.js';
	import { VIEWS, VIEW_ICONS } from '../../lib/director.js';
	import Icon from '../Icon.svelte';

	const current = $derived(directorView());
</script>

{#if !ui.sidebarOpen}
	<div class="vp-seg shrink-0" role="group" aria-label={t('panels.director.views')}>
		{#each VIEWS as id (id)}
			<HostUi name="Tooltip" props={{ text: commandById(`view-${id}`)?.label, kbd: commandById(`view-${id}`)?.key, wrapperClass: 'inline-flex h-full' }}>
				<button type="button" aria-pressed={current === id} aria-label={commandById(`view-${id}`)?.label} onclick={() => (ui.directorView = id)}><Icon name={VIEW_ICONS[id]} class="h-3.5 w-3.5" /></button>
			</HostUi>
		{/each}
	</div>
{/if}

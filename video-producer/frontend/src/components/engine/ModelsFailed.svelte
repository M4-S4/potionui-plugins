<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';

	let { onretry } = $props();
</script>

<div class="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-warning" data-models-failed>
	<span>{t('modals.engine.modelsFailed')}</span>
	<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: onretry }}>{t('modals.engine.modelsRetry')}</HostUi>
</div>

<script>
	import { t } from '../../i18n/index.svelte.js';
	import { ui } from '../../lib/state.svelte.js';
	import Icon from '../Icon.svelte';
</script>

<div class="vp-seg shrink-0" role="group" aria-label={t('storyboard.view.group')}>
	<button type="button" aria-pressed={ui.storyView === 'grid'} onclick={() => (ui.storyView = 'grid')}><Icon name="grid" class="mr-1 inline h-3 w-3" />{t('storyboard.view.grid')}</button>
	<button type="button" aria-pressed={ui.storyView === 'band'} onclick={() => (ui.storyView = 'band')}><Icon name="film" class="mr-1 inline h-3 w-3" />{t('storyboard.view.band')}</button>
</div>

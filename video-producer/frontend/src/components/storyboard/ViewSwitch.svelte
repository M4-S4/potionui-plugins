<script>
	import { t } from '../../i18n/index.svelte.js';
	import { ui } from '../../lib/state.svelte.js';
	import Icon from '../Icon.svelte';

	let { short = false } = $props();
</script>

<div class="vp-seg shrink-0" role="group" aria-label={t('storyboard.view.group')}>
	<button type="button" aria-pressed={ui.storyView === 'grid'} title={short ? t('storyboard.view.grid') : null} onclick={() => (ui.storyView = 'grid')}><Icon name="grid" class="{short ? '' : 'mr-1'} inline h-3 w-3" /><span class={short ? 'sr-only' : ''}>{t('storyboard.view.grid')}</span></button>
	<button type="button" aria-pressed={ui.storyView === 'band'} title={short ? t('storyboard.view.band') : null} onclick={() => (ui.storyView = 'band')}><Icon name="film" class="{short ? '' : 'mr-1'} inline h-3 w-3" /><span class={short ? 'sr-only' : ''}>{t('storyboard.view.band')}</span></button>
</div>

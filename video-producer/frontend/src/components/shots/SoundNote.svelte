<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { CONDITION, MUX } from '../../lib/sound.js';
	import Icon from '../Icon.svelte';

	let { behavior, compact = false } = $props();

	const text = $derived(behavior === CONDITION ? t('generation.sound.condition') : behavior === MUX ? t('generation.sound.mux') : t('generation.sound.ignored'));
	const tone = $derived(behavior === CONDITION ? 'text-success' : behavior === MUX ? 'text-fg-muted' : 'text-warning');
</script>

{#if compact}
	<HostUi name="Tooltip" props={{ text, wrapperClass: 'inline-flex' }}>
		<span class="inline-flex items-center {tone}" role="img" aria-label={text}><Icon name="wave" class="h-3.5 w-3.5" /></span>
	</HostUi>
{:else}
	<p class="flex items-start gap-1.5 text-xs {tone}"><Icon name="wave" class="mt-px h-3.5 w-3.5 shrink-0" />{text}</p>
{/if}

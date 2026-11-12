<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { writerCode } from '../../lib/promptwriter.js';
	import Icon from '../Icon.svelte';

	let { writer, engine = true, saved = true } = $props();

	const status = $derived(writer.status);
	const reason = $derived.by(() => {
		if (!engine) return t('modals.shot.composedNone');
		if (!saved) return t('modals.shot.composedUnsaved');
		if (!status) return writer.checking ? t('modals.shot.writer.checking') : '';
		if (status.available) return '';
		const code = writerCode({ code: status.code });
		return code ? t(`modals.shot.writer.error.${code}`) : status.message || t('modals.shot.writer.error.no_llm');
	});
	const off = $derived(!status?.available || !engine || !saved);
	const tip = $derived(off ? reason || t('modals.shot.writer.checking') : t('modals.shot.writer.tip', { name: status.name ?? '' }));

	function click() {
		if (off) return;
		writer.open();
	}
</script>

<HostUi name="Tooltip" props={{ text: tip }}>
	<button type="button" class="flex min-h-6 items-center gap-1 text-xs {off ? 'cursor-default text-fg-subtle' : 'text-fg-muted hover:text-fg'}" aria-disabled={off} aria-expanded={writer.state.phase !== 'closed'} data-write-prompt={off ? 'off' : 'on'} onclick={click}><Icon name="sparkles" class="h-3.5 w-3.5" />{t('modals.shot.writer.button')}</button>
</HostUi>

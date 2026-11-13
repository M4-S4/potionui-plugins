<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { commandById } from '../../lib/commands.js';
	import { kitsAvailable, openImport, openKitImport, openLocalImport } from '../../lib/importer.js';

	let { kind = 'media' } = $props();
	const key = (id) => (kind === 'media' ? commandById(id)?.key : undefined);
</script>

<HostUi name="IconButton" props={{ icon: 'folder', label: t('panels.media.import'), size: 'sm', class: 'vp-h7', tooltip: t('panels.media.importTip'), kbd: key('import'), onclick: () => openImport(kind) }} />
{#if kitsAvailable()}
	<HostUi name="IconButton" props={{ icon: 'layers', label: t('panels.media.importKit'), size: 'sm', class: 'vp-h7', tooltip: t('panels.media.importKitTip'), onclick: () => openKitImport(kind) }} />
{/if}
<HostUi name="IconButton" props={{ icon: 'upload', label: t('panels.media.importLocal'), size: 'sm', class: 'vp-h7', tooltip: t('panels.media.importLocalTip'), kbd: key('import-local'), onclick: () => openLocalImport(kind) }} />

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui } from '../../lib/state.svelte.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ZOOM, zoomIn, zoomOut } from '../../lib/timeline.js';

	let { onfit } = $props();

	const key = (id) => commandById(id)?.key || undefined;
</script>

<HostUi name="IconButton" props={{ icon: hostIconName('magnet'), label: t('timeline.snapping'), size: 'sm', class: 'vp-h7 vp-toggle', ariaPressed: ui.snapping, kbd: key('snap'), onclick: () => (ui.snapping = !ui.snapping) }} />
<HostUi name="IconButton" props={{ icon: 'minus', label: t('timeline.zoomOut'), size: 'sm', class: 'vp-h7', kbd: key('zoom-out'), onclick: zoomOut }} />
<input class="vp-slider w-24" type="range" min={ZOOM.min} max={ZOOM.max} bind:value={ui.pxPerSec} aria-label={t('timeline.zoom')} />
<HostUi name="IconButton" props={{ icon: 'plus', label: t('timeline.zoomIn'), size: 'sm', class: 'vp-h7', kbd: key('zoom-in'), onclick: zoomIn }} />
<HostUi name="Tooltip" props={{ text: t('timeline.fitTip') }}>
	<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: onfit }}>{t('timeline.fit')}</HostUi>
</HostUi>

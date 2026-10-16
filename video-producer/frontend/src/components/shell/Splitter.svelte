<script>
	import { t } from '../../i18n/index.svelte.js';
	import { ui, clamp, bottomKey } from '../../lib/state.svelte.js';
	import { drag, cancelDrag } from '../../lib/timeline.js';

	const limit = (h) => clamp(h, 160, window.innerHeight - 330);

	function down(e) {
		const k = bottomKey();
		const h0 = ui[k];
		drag(e, { undoable: false, onMove: (dx, dy) => (ui[k] = limit(h0 - dy)) });
	}

	function key(e) {
		const k = bottomKey();
		if (e.key === 'ArrowUp') ui[k] = limit(ui[k] + 20);
		if (e.key === 'ArrowDown') ui[k] = limit(ui[k] - 20);
	}

	$effect(() => cancelDrag);
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
	class="vp-splitter"
	role="separator"
	aria-orientation="horizontal"
	aria-label={t('shell.layout.splitter')}
	aria-valuenow={ui[bottomKey()]}
	tabindex="0"
	onpointerdown={down}
	onkeydown={key}
>
	<div class="vp-splitter-grip"></div>
</div>

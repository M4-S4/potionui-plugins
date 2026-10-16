<script>
	import { formatNumber } from '../../i18n/index.svelte.js';
	import { checkpoint } from '../../lib/state.svelte.js';

	let { label, value, min = 0, max = 100, step = 1, unit = '', onchange, format = null } = $props();
	const id = $props.id();
	const shown = $derived(format ? format(value) : `${formatNumber(Number.isInteger(step) ? Math.round(value) : +value, { minimumFractionDigits: Number.isInteger(step) ? 0 : 1, maximumFractionDigits: Number.isInteger(step) ? 0 : 1 })}${unit}`);
</script>

<div>
	<div class="flex items-center justify-between">
		<label for={id} class="text-xs text-fg-muted">{label}</label>
		<span class="vp-tc text-xs text-fg">{shown}</span>
	</div>
	<input {id} class="vp-slider" type="range" {min} {max} {step} {value} onpointerdown={() => checkpoint()} onkeydown={() => checkpoint()} oninput={(e) => onchange(+e.currentTarget.value)} />
</div>

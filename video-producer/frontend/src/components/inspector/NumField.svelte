<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber } from '../../i18n/index.svelte.js';
	import { checkpoint } from '../../lib/state.svelte.js';

	let { label, value, min = -Infinity, max = Infinity, step = 0.1, unit = '', onchange, disabled = false, hint = '', undoable = true } = $props();
	const id = $props.id();
	const digits = $derived(Number.isInteger(step) ? 0 : step < 0.1 ? 2 : 1);

	function fmt(v) {
		return formatNumber(digits ? +v : Math.round(v), { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false });
	}

	function commit(e) {
		const raw = String(e.currentTarget.value).replace(/\s/g, '').replace(',', '.').replace('−', '-');
		const v = Math.min(max, Math.max(min, parseFloat(raw)));
		if (Number.isFinite(v) && v !== value) {
			if (undoable) checkpoint();
			onchange(v);
		}
		e.currentTarget.value = fmt(value);
	}
</script>

<div class="flex items-center gap-2">
	{#if hint}
		<HostUi name="Tooltip" props={{ text: hint, wrapperClass: 'w-24 shrink-0' }}>
			<label for={id} class="block w-24 text-xs text-fg-muted">{label}</label>
		</HostUi>
	{:else}
		<label for={id} class="w-24 shrink-0 text-xs text-fg-muted">{label}</label>
	{/if}
	<div class="relative flex-1">
		<input {id} class="input vp-dense vp-numfield w-full" type="text" inputmode="decimal" value={fmt(value)} {disabled} onchange={commit} onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
		{#if unit}<span class="pointer-events-none absolute right-2 top-1.5 text-xs text-fg-subtle">{unit}</span>{/if}
	</div>
</div>

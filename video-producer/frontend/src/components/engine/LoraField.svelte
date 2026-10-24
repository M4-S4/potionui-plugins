<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import { loraName } from '../../lib/options.js';

	let { id, row, models = null, onchange } = $props();

	const limits = $derived(row.field.limits ?? {});
	const rows = $derived(Array.isArray(row.value) ? row.value : []);
	const list = $derived(models?.list ?? []);
	const most = $derived(Number.isInteger(limits.max_items) ? limits.max_items : 32);
	const strengthStep = $derived(Number.isFinite(limits.strength_step) && limits.strength_step > 0 ? limits.strength_step : 0.05);
	const names = $derived(rows.map((r) => loraName(r.model, list).name).join(', '));

	function strengthOf(raw) {
		let value = Number(String(raw).replace(',', '.'));
		if (!Number.isFinite(value)) return null;
		if (Number.isFinite(limits.strength_min)) value = Math.max(limits.strength_min, value);
		if (Number.isFinite(limits.strength_max)) value = Math.min(limits.strength_max, value);
		return Number((Math.round(value / strengthStep) * strengthStep).toFixed(4));
	}

	function customize() {
		onchange(rows.map((r) => ({ model: loraName(r.model, list).entry?.ref, strength: r.strength ?? limits.strength_default ?? 1 })).filter((r) => r.model));
	}

	function setRow(index, patch) {
		onchange(rows.map((r, k) => (k === index ? { ...r, ...patch } : r)));
	}

	function setStrength(index, raw) {
		const strength = strengthOf(raw);
		if (strength !== null) setRow(index, { strength });
	}

	function add() {
		if (!list.length || rows.length >= most) return;
		onchange([...rows, { model: list[0].ref, strength: Number.isFinite(limits.strength_default) ? limits.strength_default : 1 }]);
	}

	function remove(index) {
		onchange(rows.filter((_, k) => k !== index));
	}
</script>

{#if row.set}
	<ul class="space-y-1.5">
		{#each rows as r, index (index)}
			<li class="flex items-center gap-1.5">
				<select id={index === 0 ? id : undefined} class="vp-popup min-w-0 flex-1" value={r.model} aria-label={t('modals.engine.lora.pick')} onchange={(e) => setRow(index, { model: e.currentTarget.value })}>
					{#if !loraName(r.model, list).entry}<option value={r.model}>{models?.loading ? t('modals.engine.modelsLoading') : loraName(r.model, list).name}</option>{/if}
					{#each list as m (m.id)}<option value={m.ref}>{m.name}</option>{/each}
				</select>
				<input class="input vp-dense vp-tc w-16" type="text" inputmode="decimal" value={formatNumber(r.strength, { maximumFractionDigits: 3, useGrouping: false })} aria-label={t('modals.engine.lora.strength')} onchange={(e) => setStrength(index, e.currentTarget.value)} />
				<HostUi name="IconButton" props={{ icon: hostIconName('trash'), label: t('modals.engine.lora.remove'), tooltip: t('modals.engine.lora.remove'), size: 'sm', onclick: () => remove(index) }} />
			</li>
		{:else}
			<li class="text-xs text-fg-subtle">{t('modals.engine.lora.none')}</li>
		{/each}
	</ul>
	<div class="mt-1.5">
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', disabled: !list.length || rows.length >= most, onclick: add }}>{t('modals.engine.lora.add')}</HostUi>
	</div>
{:else}
	<div class="flex min-h-7 flex-wrap items-center gap-x-2 gap-y-1">
		<span class="min-w-0 text-xs text-fg-muted">{rows.length ? t('modals.engine.lora.presetDefault', { names }) : t('modals.engine.lora.none')}</span>
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', disabled: models?.loading === true, onclick: customize }}>{t('modals.engine.lora.customize')}</HostUi>
	</div>
	{#if models?.failed}<p class="mt-0.5 text-xs text-warning">{t('modals.engine.modelsFailed')}</p>{/if}
{/if}

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { randomSeed } from '../../lib/engine.js';
	import { hostIconName } from '../../lib/icons.js';
	import { CHOICE_TYPES, FLAG_TYPES, LORA_TYPE, MODEL_TYPE, NUMBER_TYPES, SEED_MAX, SEED_TYPE, TEXT_TYPES, clampNumber, fieldTitle, integral, modelTypeOf } from '../../lib/options.js';
	import LoraField from './LoraField.svelte';

	let { row, main = null, models = null, onchange, need = () => {} } = $props();
	const id = $props.id();

	const field = $derived(row.field);
	const kind = $derived(field.type);
	const limits = $derived(field.limits ?? {});
	const title = $derived(fieldTitle(field));
	const ranged = $derived(NUMBER_TYPES.includes(kind) && Number.isFinite(limits.min) && Number.isFinite(limits.max));
	const digits = $derived(integral(field) ? 0 : Number.isFinite(limits.step) && limits.step > 0 ? Math.min(3, Math.max(1, Math.ceil(-Math.log10(limits.step)))) : 2);
	const only = $derived(main && !field.modes.includes(main) ? field.modes[0] : null);
	const known = $derived((field.options ?? []).some((o) => o.value === row.value));
	const listed = $derived((models?.list ?? []).some((m) => m.ref === row.value));
	const recommended = $derived(field.recommended?.length ? t('modals.engine.recommendedFile', { file: field.recommended[0] }) : t('modals.engine.recommended'));

	$effect(() => {
		const type = kind === MODEL_TYPE || kind === LORA_TYPE ? modelTypeOf(field) : null;
		if (type) need(type);
	});

	function onlyText(mode) {
		if (mode === 'refs') return t('modals.engine.only.refs');
		if (mode === 'img2video') return t('modals.engine.only.img2video');
		if (mode === 'txt2video') return t('modals.engine.only.txt2video');
		return t('modals.engine.only.mode', { mode });
	}

	function number(value) {
		return Number.isFinite(Number(value)) ? formatNumber(Number(value), { maximumFractionDigits: digits, useGrouping: false }) : '';
	}

	function described(value) {
		if (CHOICE_TYPES.includes(kind)) return (field.options ?? []).find((o) => o.value === value)?.label ?? (value || '—');
		if (FLAG_TYPES.includes(kind)) return value === true ? t('modals.engine.on') : t('modals.engine.off');
		if (kind === SEED_TYPE) return value === -1 || value === null || value === undefined ? t('modals.engine.seedRandom') : String(value);
		if (NUMBER_TYPES.includes(kind)) return number(value) || '—';
		if (kind === MODEL_TYPE) return recommended;
		if (kind === LORA_TYPE) return Array.isArray(value) && value.length ? t('modals.engine.lora.count', { count: value.length }) : t('modals.engine.lora.none');
		return value ? String(value) : t('modals.engine.blank');
	}

	function commitNumber(input) {
		const value = clampNumber(field, String(input.value).replace(',', '.'));
		if (value !== null) onchange(value);
		if (input.type === 'text') input.value = number(value ?? row.value);
	}

	function commitSeed(raw) {
		if (raw === '') return onchange(-1);
		const value = Number(raw);
		if (Number.isInteger(value) && value >= -1 && value <= SEED_MAX) onchange(value);
	}
</script>

<div class="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)_1.75rem] items-start gap-x-3 py-1.5" class:pl-4={Boolean(field.gate)} data-option={field.name}>
	<label for={id} class="min-w-0 pt-1.5 text-xs text-fg-muted">
		<span class="block truncate">{title}</span>
		{#if only}<span class="mt-0.5 inline-flex rounded-sm bg-surface-3 px-1 text-2xs text-fg-muted">{onlyText(only)}</span>{/if}
	</label>
	<div class="min-w-0">
		{#if CHOICE_TYPES.includes(kind)}
			<select {id} class="vp-popup w-full" value={row.value ?? ''} disabled={row.disabled} onchange={(e) => onchange(e.currentTarget.value)}>
				{#if !known}<option value={row.value ?? ''} disabled>{row.value || '—'}</option>{/if}
				{#each field.options as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
			</select>
		{:else if NUMBER_TYPES.includes(kind)}
			<div class="flex items-center gap-2">
				{#if ranged}
					<input class="vp-slider min-w-0 flex-1" type="range" min={limits.min} max={limits.max} step={limits.step ?? 'any'} value={row.value ?? limits.min} disabled={row.disabled} aria-label={title} oninput={(e) => commitNumber(e.currentTarget)} />
				{/if}
				<input {id} class="input vp-dense vp-tc {ranged ? 'w-20' : 'w-28'}" type="text" inputmode="decimal" value={number(row.value)} disabled={row.disabled} onchange={(e) => commitNumber(e.currentTarget)} onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
			</div>
		{:else if kind === SEED_TYPE}
			<div class="flex gap-1">
				<input {id} class="input vp-dense vp-tc min-w-0 flex-1" type="number" min="-1" max={SEED_MAX} step="1" placeholder={t('modals.engine.seedRandom')} value={row.value === -1 || row.value === null ? '' : row.value} onchange={(e) => commitSeed(e.currentTarget.value)} />
				<HostUi name="IconButton" props={{ icon: 'refresh', label: t('modals.engine.seedPick'), tooltip: t('modals.engine.seedPick'), size: 'sm', onclick: () => onchange(randomSeed()) }} />
			</div>
		{:else if FLAG_TYPES.includes(kind)}
			<div class="flex min-h-7 items-center">
				<HostUi name="Switch" props={{ id, checked: row.value === true, size: 'lg', label: title, disabled: row.disabled, onchange: (v) => onchange(Boolean(v)) }} />
			</div>
		{:else if TEXT_TYPES.includes(kind)}
			<input {id} class="input vp-dense w-full" type="text" maxlength={limits.max_length ?? 2000} value={row.value ?? ''} disabled={row.disabled} onchange={(e) => onchange(e.currentTarget.value)} />
		{:else if kind === MODEL_TYPE}
			<select {id} class="vp-popup w-full" value={row.set ? row.value : ''} disabled={row.disabled} onchange={(e) => onchange(e.currentTarget.value || undefined)}>
				<option value="">{recommended}</option>
				{#if row.set && !listed}<option value={row.value}>{models?.loading ? t('modals.engine.modelsLoading') : row.value}</option>{/if}
				{#each models?.list ?? [] as m (m.id)}<option value={m.ref}>{m.name}</option>{/each}
			</select>
			{#if models?.failed}<p class="mt-0.5 text-xs text-warning">{t('modals.engine.modelsFailed')}</p>{/if}
		{:else if kind === LORA_TYPE}
			<LoraField {id} {row} {models} {onchange} />
		{/if}
		{#if row.set}<p class="mt-0.5 text-xs text-fg-subtle">{t('modals.engine.default', { value: described(row.base) })}</p>{/if}
	</div>
	<div class="pt-0.5">
		{#if row.set}<HostUi name="IconButton" props={{ icon: hostIconName('undo'), label: t('modals.engine.reset'), tooltip: t('modals.engine.reset'), size: 'sm', onclick: () => onchange(undefined) }} />{/if}
	</div>
</div>

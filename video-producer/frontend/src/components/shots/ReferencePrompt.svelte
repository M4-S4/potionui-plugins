<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { LAYOUTS, acknowledged, replacement, withPart } from '../../lib/refprompt.js';
	import { hostIconName } from '../../lib/icons.js';

	let { reference, value, onchange } = $props();

	const names = $derived(reference ? LAYOUTS[reference.layout] : []);
	const editing = $derived(Boolean(value && reference && value.layout === reference.layout));
	const foreign = $derived(Boolean(value && reference && value.layout !== reference.layout));
	const empty = $derived(names.every((name) => !(reference?.composed[name] ?? '').trim()));
	const stale = $derived(editing && reference.overridden && reference.changed);

	function partLabel(name) {
		if (name === 'subject_definitions') return t('modals.shot.reference.part.subjects');
		if (name === 'retention_analysis') return t('modals.shot.reference.part.retention');
		if (name === 'citations') return t('modals.shot.reference.part.citations');
		return t('modals.shot.reference.part.cast');
	}

	function hint(layout) {
		if (layout === 'refs') return t('modals.shot.reference.hint.refs');
		if (layout === 'subjects') return t('modals.shot.reference.hint.subjects');
		return t('modals.shot.reference.hint.cast');
	}
</script>

{#if !reference}
	<p class="text-xs text-fg-subtle">{value ? t('modals.shot.reference.replacedWaiting') : t('modals.shot.reference.waiting')}</p>
{:else}
	<div class="space-y-2 rounded-lg border border-line-strong p-2.5 text-xs">
		<p class="text-fg-subtle">{hint(reference.layout)}</p>
		{#if foreign}
			<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{t('modals.shot.reference.ignored')}</HostUi>
			<div class="flex flex-wrap gap-1">
				<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => onchange(replacement(reference)) }}>{t('modals.shot.reference.again')}</HostUi>
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => onchange(null) }}>{t('modals.shot.reference.revert')}</HostUi>
			</div>
		{:else if editing}
			<p class="text-fg-muted">{t('modals.shot.reference.replaced')}</p>
			{#each names as name (name)}
				<label class="block space-y-1">
					<span class="vp-label">{partLabel(name)}</span>
					<textarea class="input w-full text-xs" rows={name === 'citations' ? 2 : 4} value={value.parts[name] ?? ''} oninput={(e) => onchange(withPart(value, name, e.currentTarget.value))}></textarea>
				</label>
			{/each}
			{#if stale}
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{t('modals.shot.reference.changed')}</HostUi>
				<details>
					<summary class="min-h-6 cursor-pointer py-1 text-fg-muted">{t('modals.shot.reference.composedNow')}</summary>
					{#each names as name (name)}
						<div class="mt-1">
							<div class="vp-label">{partLabel(name)}</div>
							<p class="whitespace-pre-wrap leading-5 text-fg-subtle">{reference.composed[name] || '—'}</p>
						</div>
					{/each}
				</details>
			{/if}
			<div class="flex flex-wrap gap-1">
				{#if stale}<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => onchange(acknowledged(value, reference)) }}>{t('modals.shot.reference.keep')}</HostUi>{/if}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => onchange(null) }}>{t('modals.shot.reference.revert')}</HostUi>
			</div>
		{:else}
			{#if empty}
				<p class="text-fg-subtle">{t('modals.shot.reference.empty')}</p>
			{:else}
				{#each names as name (name)}
					{#if reference.composed[name]}
						<div>
							<div class="vp-label">{partLabel(name)}</div>
							<p class="max-h-32 overflow-auto whitespace-pre-wrap leading-5 text-fg-muted">{reference.composed[name]}</p>
						</div>
					{/if}
				{/each}
			{/if}
			<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('pencil'), onclick: () => onchange(replacement(reference)) }}>{t('modals.shot.reference.replace')}</HostUi>
		{/if}
	</div>
{/if}

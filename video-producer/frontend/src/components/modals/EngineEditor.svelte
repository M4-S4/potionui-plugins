<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, act } from '../../lib/state.svelte.js';
	import { presetById } from '../../lib/production.svelte.js';
	import { getClient } from '../../lib/project.svelte.js';
	import { presetLabel } from '../../lib/generation.js';
	import { hasOwnEngine, shotEngineOf } from '../../lib/engine.js';
	import { projectDrafts } from '../../lib/shots.js';
	import { cleanOptions, groupsOf, mainMode, modelTypeOf, optionsOf, presetFields, resolveFields, sameOptions, setPresetOptions, stepCounts } from '../../lib/options.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';
	import DraftsField from '../shots/DraftsField.svelte';
	import OptionField from '../engine/OptionField.svelte';

	let { preset: asked = null } = $props();

	const projectPreset = doc.engine?.preset ?? null;
	const own = doc.clips.filter(hasOwnEngine).length;
	const videoPresets = $derived((ui.me?.presets ?? []).filter((p) => p.video && !p.upscaler));
	function initialPreset() {
		return asked ?? projectPreset ?? (ui.me?.presets ?? []).find((p) => p.video && !p.upscaler)?.id ?? null;
	}

	let chosen = $state(initialPreset());
	let drafts = $state({});
	let variants = $state(projectDrafts(doc.engine));
	let models = $state({});

	const preset = $derived(chosen ? presetById(chosen) : null);
	const name = $derived(preset ? presetLabel(preset) : t('generation.engine.unavailable'));
	const fields = $derived(preset ? presetFields(preset) : []);
	const main = $derived(mainMode(preset));
	const values = $derived(drafts[chosen] ?? optionsOf(doc.engine, chosen));
	const groups = $derived(groupsOf(resolveFields(fields, values).filter((row) => row.visible)));
	const steps = $derived(stepCounts(fields, values));
	const setCount = $derived(Object.keys(values).length);
	const choices = $derived.by(() => {
		const used = doc.clips.map((c) => shotEngineOf(c).preset).filter(Boolean);
		const ids = [...new Set([projectPreset, ...used, ...videoPresets.map((p) => p.id), chosen].filter(Boolean))];
		return ids.map((id) => {
			const found = presetById(id);
			const engine = found ? presetLabel(found) : t('generation.engine.unavailable');
			const shots = used.filter((x) => x === id).length;
			if (id === projectPreset) return { id, label: t('modals.engine.projectEngine', { engine }) };
			return { id, label: shots ? t('modals.engine.usedBy', { engine, count: shots }) : engine };
		});
	});

	function edit(field, value) {
		const next = { ...values };
		if (value === undefined) delete next[field];
		else next[field] = value;
		drafts[chosen] = cleanOptions(fields, next);
	}

	async function need(type) {
		const key = `${chosen}|${type}`;
		if (!chosen || models[key]) return;
		models[key] = { loading: true, list: [], failed: false };
		const result = await getClient()?.presetModels?.(chosen, type);
		models[key] = result?.ok ? { loading: false, list: result.data, failed: false } : { loading: false, list: [], failed: true };
	}

	function save() {
		const updates = Object.entries($state.snapshot(drafts))
			.map(([id, kept]) => [id, presetById(id) ? cleanOptions(presetFields(presetById(id)), kept) : kept])
			.filter(([id, kept]) => !sameOptions(kept, optionsOf(doc.engine, id)));
		const moved = variants !== projectDrafts(doc.engine);
		if (updates.length || moved) {
			act(() => {
				for (const [id, kept] of updates) setPresetOptions(doc.engine, id, kept);
				if (moved) doc.engine.variants = variants;
			});
		}
		ui.modal = null;
	}
</script>

<Modal title={t('modals.engine.title')} subtitle={t('modals.engine.subtitle')} icon="sliders" width={680}>
	<div class="space-y-4 p-4">
		<div class="space-y-1">
			<label class="vp-label block" for="vp-engine-preset">{t('modals.engine.preset')}</label>
			{#if choices.length}
				<select id="vp-engine-preset" class="vp-popup w-full" value={chosen ?? ''} onchange={(e) => (chosen = e.currentTarget.value)}>
					{#each choices as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
				</select>
				<p class="text-xs text-fg-subtle">{t('modals.engine.presetHint')}</p>
			{:else}
				<p class="rounded-lg border border-dashed border-line-hover p-2 text-xs text-fg-muted">{t('generation.engine.empty')}</p>
			{/if}
		</div>

		{#if own}
			<p class="flex items-start gap-1.5 text-xs text-fg-muted"><Icon name="info" class="mt-px h-3.5 w-3.5 shrink-0" />{t('modals.engine.priority', { count: own })}</p>
		{/if}

		<section class="space-y-2" aria-labelledby="vp-engine-project">
			<span id="vp-engine-project" class="vp-section-title">{t('modals.engine.project')}</span>
			<div class="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)] items-center gap-x-3">
				<label class="text-xs text-fg-muted" for="vp-engine-drafts">{t('modals.engine.drafts')}</label>
				<div class="flex flex-wrap items-center gap-2">
					<DraftsField id="vp-engine-drafts" value={variants} onchange={(n) => (variants = n)} label={false} />
					<span class="text-xs text-fg-subtle">{t('modals.engine.draftsHint')}</span>
				</div>
			</div>
		</section>

		{#if chosen && !preset}
			<p class="rounded-lg border border-dashed border-line-hover p-2 text-xs text-fg-muted">{t('modals.engine.unavailable')}</p>
		{:else if preset && !fields.length}
			<p class="rounded-lg border border-dashed border-line-hover p-2 text-xs text-fg-muted">{t('modals.engine.none', { engine: name })}</p>
		{:else}
			{#each groups as g (g.key)}
				<section class="space-y-0.5" aria-label={g.path.length ? g.path.join(' › ') : t('modals.engine.general')}>
					<span class="vp-section-title">{g.path.length ? g.path.join(' › ') : t('modals.engine.general')}</span>
					<div class="divide-y divide-line/70">
						{#each g.rows as row (row.field.name)}
							<OptionField {row} {main} models={models[`${chosen}|${modelTypeOf(row.field)}`] ?? null} {need} onchange={(value) => edit(row.field.name, value)} />
						{/each}
					</div>
				</section>
			{/each}
			{#if steps && steps.scale !== 1}
				<p class="flex items-start gap-1.5 text-xs text-fg-muted">
					<Icon name="history" class="mt-px h-3.5 w-3.5 shrink-0" />{t('modals.engine.time', { asked: formatNumber(steps.asked), base: formatNumber(steps.base), ratio: formatNumber(steps.scale, { maximumFractionDigits: 2 }) })}
				</p>
			{/if}
		{/if}
	</div>
	{#snippet footer()}
		<span class="mr-auto">
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', disabled: !setCount, onclick: () => (drafts[chosen] = {}) }}>{t('modals.engine.resetAll', { engine: name })}</HostUi>
		</span>
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: () => (ui.modal = null) }}>{t('modals.prompt.cancel')}</HostUi>
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', onclick: save }}>{t('modals.prompt.save')}</HostUi>
	{/snippet}
</Modal>

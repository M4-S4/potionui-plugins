<script>
	import { untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipAt, clipLabel, secs } from '../../lib/state.svelte.js';
	import { sceneState, sceneOf, saveCapture } from '../../lib/scene.svelte.js';
	import Modal from './Modal.svelte';

	const shot = $derived(sceneState.capture);
	const scene = $derived(sceneOf(shot?.sceneId));
	const initial = untrack(() => (ui.selection?.kind === 'clip' ? ui.selection.id : null) ?? clipAt(ui.playhead)?.id ?? doc.clips[0]?.id ?? '');
	let clipId = $state(initial);
	let usage = $state('first');

	const usages = $derived([
		{ id: 'first', label: t('modals.capture.first') },
		{ id: 'last', label: t('modals.capture.last') },
		{ id: 'reference', label: t('modals.capture.reference') }
	]);
	const hint = $derived(usage === 'first' ? t('modals.capture.firstHint') : usage === 'last' ? t('modals.capture.lastHint') : t('modals.capture.referenceHint'));
	const empty = $derived(shot?.coverage == null ? 0 : Math.max(0, 1 - shot.coverage));

	const close = () => (ui.modal = null);

	async function save() {
		if (await saveCapture(clipId, usage)) close();
	}
</script>

<Modal title={t('modals.capture.title')} subtitle={scene ? t('modals.capture.subtitle', { scene: scene.name, width: shot?.width ?? 0, height: shot?.height ?? 0 }) : ''} icon="camera" width={620}>
	<div class="space-y-3 p-4">
		<div class="relative overflow-hidden rounded-lg border border-line-strong bg-black" style:aspect-ratio={shot ? `${shot.width} / ${shot.height}` : '16 / 9'}>
			{#if shot?.url}
				<img src={shot.url} alt={t('modals.capture.preview')} class="h-full w-full object-contain" />
			{:else}
				<div class="absolute inset-0 flex items-center justify-center"><HostUi name="Spinner" props={{ size: 'md' }} /></div>
			{/if}
		</div>
		{#if shot?.url && empty > 0.005}
			<p class="text-xs {empty > 0.03 ? 'text-warning' : 'text-fg-subtle'}">{t('modals.capture.empty', { value: formatNumber(empty * 100, { maximumFractionDigits: 1 }) })}</p>
		{/if}
		<label class="flex items-center gap-2">
			<span class="w-24 shrink-0 text-xs text-fg-muted">{t('modals.capture.shot')}</span>
			<select class="input vp-dense min-w-0 flex-1" bind:value={clipId}>
				{#each doc.clips as c (c.id)}<option value={c.id}>{clipLabel(c)} · {secs(c.start)}–{secs(c.start + c.dur)}</option>{/each}
			</select>
		</label>
		<HostUi name="SegmentedControl" props={{ items: usages, selected: usage, variant: 'toggle', fullWidth: true, ariaLabel: t('modals.capture.usage'), onSelect: (id) => (usage = id) }} />
		<p class="text-xs text-fg-subtle">{hint}</p>
	</div>
	{#snippet footer()}
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: close }}>{t('modals.capture.cancel')}</HostUi>
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'check', disabled: !shot?.url || !clipId || sceneState.saving, onclick: save }}>{sceneState.saving ? t('modals.capture.saving') : t('modals.capture.save')}</HostUi>
	{/snippet}
</Modal>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui } from '../../lib/state.svelte.js';
	import { project, getClient } from '../../lib/project.svelte.js';
	import { currentEngine, engineOptionLabel, noteText } from '../../lib/production.svelte.js';

	let { source, shotId } = $props();

	const DELAY = 400;
	const LIVE_CHECKS = ['bible_label_missing'];
	const composed = $state({ loading: false, data: null, error: null });

	const option = $derived(currentEngine());
	const body = $derived(
		option && project.id
			? JSON.stringify({ shots: [shotId], preset_id: option.preset, model_id: option.model ?? null, production: ui.production.mode === 'render3d_ai' ? 'render3d_ai' : 'ai', doc: source })
			: null
	);
	const item = $derived(composed.data?.prompts.find((p) => p.shotId === shotId) ?? null);
	const warnings = $derived((item?.warnings ?? []).filter((w) => !LIVE_CHECKS.includes(w.code)));
	const blocks = $derived(item ? [] : (composed.data?.blocks ?? []));

	$effect(() => {
		const payload = body;
		if (!payload) {
			composed.loading = false;
			return;
		}
		composed.loading = true;
		const controller = new AbortController();
		const timer = setTimeout(async () => {
			const result = await getClient().prompts(project.id, JSON.parse(payload), controller.signal);
			if (controller.signal.aborted) return;
			Object.assign(composed, result.ok ? { loading: false, data: result.data, error: null } : { loading: false, data: null, error: result.error });
		}, DELAY);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});
</script>

<details class="rounded-lg border border-line-strong p-2.5 text-xs" open>
	<summary class="-mb-1 -mt-1 min-h-6 cursor-pointer py-1 font-medium text-fg-muted">
		{t('modals.shot.composed')}{#if item}<span class="font-normal text-fg-subtle"> · {engineOptionLabel(item.presetId)} · {item.profile}</span>{/if}
	</summary>
	<div class="mt-1.5 space-y-1.5">
		{#if !option}
			<p class="text-fg-subtle">{t('modals.shot.composedNone')}</p>
		{:else if !project.id}
			<p class="text-fg-subtle">{t('modals.shot.composedUnsaved')}</p>
		{:else if item}
			<p class="max-h-48 overflow-auto whitespace-pre-wrap leading-5 text-fg-muted {composed.loading ? 'opacity-60' : ''}" aria-live="polite">{item.prompt}</p>
			{#each warnings as w, i (i)}
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: true }}>{noteText(w)}</HostUi>
			{/each}
		{:else if composed.error}
			<p class="text-danger">{t('modals.shot.composedError')}</p>
		{:else if blocks.length}
			{#each blocks as b, i (i)}<p class="text-warning">{noteText(b)}</p>{/each}
		{:else}
			<p class="text-fg-subtle">{t('modals.shot.composedLoading')}</p>
		{/if}
		<p class="text-fg-subtle">{t('modals.shot.composedHint')}</p>
	</div>
</details>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { project, getClient } from '../../lib/project.svelte.js';
	import { currentEngine, engineOptionLabel, noteText } from '../../lib/production.svelte.js';
	import { marked } from '../../lib/director.js';
	import { TAG_CLASS } from '../../lib/reftags.js';
	import { labelParts, trackOf, vrefLabel } from '../../lib/vreftracks.js';
	import { roleLabel, trackName } from '../../lib/vreftracks.svelte.js';

	let { source, shotId, marks = [], current = $bindable(null) } = $props();

	const DELAY = 400;
	const ELSEWHERE = ['bible_label_missing', 'reference_prompt_changed', 'reference_prompt_ignored'];
	const composed = $state({ loading: false, data: null, error: null });

	const option = $derived(currentEngine());
	const body = $derived(
		option && project.id
			? JSON.stringify({ shots: [shotId], preset_id: option.preset, model_id: option.model ?? null, doc: source })
			: null
	);
	const item = $derived(composed.data?.prompts.find((p) => p.shotId === shotId) ?? null);
	const warnings = $derived((item?.warnings ?? []).filter((w) => !ELSEWHERE.includes(w.code)));
	const blocks = $derived(item ? [] : (composed.data?.blocks ?? []));
	const parts = $derived(item ? marked(item.prompt, marks) : []);
	const tracks = $derived(item?.videoTracks ?? []);

	function labelTip(slot) {
		const entry = tracks.find((x) => x.slot === slot);
		const track = entry?.trackId ? trackOf(source, entry.trackId) : null;
		return t('modals.shot.vref.labelTip', { label: entry?.label ?? '', track: track ? trackName(track) : vrefLabel(slot), role: track ? roleLabel(track.role) : '' });
	}

	$effect(() => {
		current = item;
	});

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

{#snippet labelled(text)}{#each labelParts(text, tracks) as piece, j (j)}{piece.text}{#if piece.slot}<span class="{TAG_CLASS} vp-tc ml-0.5 align-baseline" title={labelTip(piece.slot)} data-composed-vref={piece.slot}>{vrefLabel(piece.slot)}</span>{/if}{/each}{/snippet}

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
			<p class="max-h-48 overflow-auto whitespace-pre-wrap leading-5 text-fg-muted {composed.loading ? 'opacity-60' : ''}" aria-live="polite">{#each parts as part, i (i)}{#if part.mark}<mark class="rounded-sm text-fg" style:background-color="rgb(var(--warning) / 0.25)" data-composed-mark>{@render labelled(part.text)}</mark>{:else}{@render labelled(part.text)}{/if}{/each}</p>
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

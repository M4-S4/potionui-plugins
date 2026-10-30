<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs } from '../../lib/state.svelte.js';
	import { labelTake, promoteToFinal, retryTake, cancelTake, deleteTake, showDetails, toggleCompare, findTake, backendName, presetById, upscaleAvailable } from '../../lib/production.svelte.js';
	import { failureText, hasNativeEngine, isInFlight, presetLabel } from '../../lib/generation.js';
	import { takeThumb } from '../../lib/media.js';
	import { extractable, extractAtPlayhead, seamState } from '../../lib/seam.svelte.js';
	import { waitText } from '../../lib/chain.svelte.js';
	import { previewTake } from '../../lib/monitor.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import { canLabel, labelOf, toggledLabel, LABEL_TONES } from '../../lib/labels.js';
	import { isStale } from '../../lib/shots.js';
	import { formatValue, ratioText } from '../../lib/formats.js';
	import { framed, percent, sizeOf } from '../../lib/framing.js';
	import { TAG_CLASS } from '../../lib/reftags.js';
	import { takeTracks, vrefLabel } from '../../lib/vreftracks.js';
	import { roleLabel, trackName } from '../../lib/vreftracks.svelte.js';
	import { interpolatorChoice, pickInterpolator, takeCadence } from '../../lib/cadence.js';
	import { conformTakes, renditionStore } from '../../lib/renditions.svelte.js';
	import Icon from '../Icon.svelte';
	import TakeToRefs from './TakeToRefs.svelte';

	let { take, clip, onchoose = null, chosen = false } = $props();

	const active = $derived(clip?.take === take.id);
	const label = $derived(labelOf(take));
	const stale = $derived(isStale(take, clip));
	const choices = $derived([
		{ id: 'rejected', text: t('generation.card.rejectShort'), aria: t('generation.card.reject', { variant: take.variant }), tip: t('generation.card.rejectTip') },
		{ id: 'candidate', text: t('generation.card.candidateShort'), aria: t('generation.card.candidate', { variant: take.variant }), tip: t('generation.card.candidateTip') },
		{ id: 'final', text: t('generation.card.finalShort'), aria: t('generation.card.final', { variant: take.variant }), tip: label === 'final' ? t('generation.card.finalHeldTip') : t('generation.card.finalLabelTip') }
	]);
	const lockedTip = $derived(t('generation.card.finalLockedTip'));
	const inCompare = $derived(!!ui.compare?.includes(take.id));
	const previewed = $derived(ui.preview?.kind === 'result' && ui.preview.id === take.id);
	const flying = $derived(isInFlight(take));
	const done = $derived(take.status === 'done' && Boolean(take.url));
	const thumb = $derived(done ? takeThumb(take) : null);
	const vrefs = $derived(done ? takeTracks(doc, take.id) : []);
	const parent = $derived(take.parentTakeId ? findTake(take.parentTakeId) : null);
	const progress = $derived(take.status === 'running' ? Math.round(Math.min(100, Math.max(0, take.progress ?? 0))) : 0);
	const cadence = $derived(takeCadence(take, renditionStore.list, doc));
	const interpolator = $derived(pickInterpolator(interpolatorChoice(doc), ui.me));
	const cadenceRate = $derived({ from: cadence.from, to: cadence.to });
	const cadenceProgress = $derived(cadence.rendition?.status === 'running' && cadence.rendition.progress != null ? Math.round(cadence.rendition.progress) : null);
	const cadenceTip = $derived.by(() => {
		if (cadence.state === 'conformed') return t('generation.card.cadence.conformedTip', cadenceRate);
		if (cadence.state === 'conforming') return t('generation.card.cadence.conformingTip', cadenceRate);
		if (interpolator === null) return hasNativeEngine(ui.me) ? t('generation.cadence.noInterpolator') : t('generation.cadence.noNativeEngine');
		if (cadence.state === 'failed') return t('generation.card.cadence.failedTip', { ...cadenceRate, error: cadence.rendition?.errorMessage || '—' });
		return t('generation.card.cadence.slowTip', cadenceRate);
	});
	const engineName = $derived.by(() => {
		const preset = presetById(take.presetId);
		const model = take.modelId ? (ui.me?.engines ?? []).flatMap((e) => e.models).find((m) => m.id === take.modelId) : null;
		return (model?.name ?? (preset ? presetLabel(preset) : '')) || '—';
	});
	const backendText = $derived(take.backendId ? backendName(take.backendId) : '');

	function qualityText() {
		if (take.kind === 'upscale') return t('generation.card.upscale');
		if (take.kind === 'guided') return t('generation.card.guided');
		return take.quality === 'final' ? t('generation.card.qualityFinal') : t('generation.card.qualityDraft');
	}

	function stateText(status) {
		if (status === 'queued') return waitText(take) || t('lib.status.queued');
		if (status === 'running') return t('generation.state.running');
		if (status === 'failed') return t('lib.status.failed');
		if (status === 'cancelled') return t('lib.status.cancelled');
		return '';
	}

	function modeText() {
		const mode = take.directorMode;
		const label = mode === 't2v' ? t('generation.mode.t2v') : mode === 'i2v' ? t('generation.mode.i2v') : mode === 'flf' ? t('generation.mode.flf') : mode === 'refs' ? t('generation.mode.refs') : '';
		return [take.profile, label].filter(Boolean).join(' · ') || '—';
	}

	const resolution = $derived(take.width && take.height ? `${take.width}×${take.height}` : (take.resolution ?? '').replace('x', '×') || '—');
	const shown = $derived(done ? framed(sizeOf(take), doc) : null);
	const framing = $derived.by(() => {
		if (!shown || shown.mode === 'exact') return null;
		const ratio = ratioText(shown.ratio);
		const aspect = formatValue(doc.aspect);
		if (shown.mode === 'crop') return { text: t('generation.card.framedCrop', { ratio }), tip: t('generation.card.framedCropTip', { ratio, aspect, loss: percent(shown.loss) }) };
		return { text: t('generation.card.framedBars', { ratio }), tip: t('generation.card.framedBarsTip', { ratio, aspect }) };
	});
	const tone = $derived(take.status === 'failed' ? 'text-danger' : take.status === 'cancelled' ? 'text-fg-subtle' : 'text-signal');
	const dot = $derived(take.status === 'failed' ? 'bg-danger' : take.status === 'cancelled' ? 'bg-fg-subtle' : 'bg-signal');
	const failure = $derived(failureText(take, t));
	const finalTip = $derived(upscaleAvailable(take) ? t('generation.card.finalTip') : hasNativeEngine(ui.me) ? t('generation.block.upscaleUnsupported') : t('generation.block.noNativeEngine'));

	function open() {
		if (onchoose) onchoose(take);
		else previewTake(take);
	}

	function drag(e) {
		if (!done) return e.preventDefault();
		e.dataTransfer.effectAllowed = 'copyMove';
		e.dataTransfer.setData('text/x-take', take.id);
		ui.dragTake = take.id;
	}

	function dragEnd() {
		if (ui.dragTake === take.id) ui.dragTake = null;
	}

	function choose(e) {
		if (!onchoose || e.target.closest?.('button, a, input, select, textarea, label')) return;
		e.stopPropagation();
		onchoose(take);
	}
</script>

<li class="overflow-hidden rounded-lg border transition-colors {active ? 'border-signal ring-1 ring-signal' : previewed || inCompare || chosen ? 'border-signal/60' : 'border-line-strong hover:border-line-hover'} {chosen ? 'bg-surface-2' : ''}" aria-current={chosen ? 'true' : undefined} data-take-card={take.id}>
	<div role="presentation" class={onchoose ? 'cursor-pointer' : ''} onclick={choose}>
		<div class="flex gap-2.5 p-1.5">
			<button type="button" class="relative aspect-video w-28 shrink-0 overflow-hidden rounded bg-surface-3 disabled:cursor-default" disabled={!done} draggable={done} aria-label={t('generation.card.preview', { variant: take.variant })} title={done ? t('generation.card.dragTip') : undefined} ondragstart={drag} ondragend={dragEnd} onclick={open}>
				{#if thumb}
					<img src={thumb} alt="" class="h-full w-full object-cover" draggable="false" />
				{:else}
					<span class="absolute inset-0 flex items-center justify-center {tone}">
						{#if take.status === 'running'}
							<HostUi name="Spinner" props={{ size: 'sm' }} />
						{:else}
							<Icon name={take.status === 'failed' ? 'alert' : take.status === 'cancelled' ? 'x' : 'history'} class="h-4 w-4" />
						{/if}
					</span>
				{/if}
				<span class="absolute left-1 top-1 rounded bg-black/60 px-1 text-xs font-semibold text-white">{take.variant}</span>
				{#if active}<span class="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full border border-signal bg-surface-1 text-signal"><Icon name="check" class="h-3 w-3" strokeWidth={2.5} /></span>{/if}
			</button>
			<div class="min-w-0 flex-1 space-y-0.5 text-xs leading-4">
				<div class="flex items-center gap-1.5">
					<span class="truncate font-medium text-fg">{qualityText()}{#if parent}<span class="font-normal text-fg-subtle">{' · ' + t('generation.card.from', { variant: parent.variant })}</span>{/if}</span>
					{#if take.status !== 'done'}
						<span class="ml-auto flex shrink-0 items-center gap-1 {tone}"><span class="h-1.5 w-1.5 rounded-full {dot}"></span>{stateText(take.status)}</span>
					{:else if take.durationS}
						<span class="vp-tc ml-auto shrink-0 text-fg-subtle">{secs(take.durationS)}</span>
					{/if}
				</div>
				<div class="truncate text-fg-muted" title={[engineName, backendText].filter(Boolean).join(' · ')} data-take-engine>{engineName}</div>
				<div class="flex min-w-0 items-center gap-1.5">
					<span class="shrink-0 rounded-sm border px-1 text-2xs font-medium {LABEL_TONES[label]}">{t(`generation.label.${label}`)}</span>
					{#each vrefs as track (track.id)}<span class="{TAG_CLASS} vp-tc shrink-0" title={t('generation.card.refs.chipTip', { track: trackName(track), role: roleLabel(track.role) })} data-take-vref={track.slot}>{vrefLabel(track.slot)}</span>{/each}
					{#if cadence.state === 'conformed'}
						<span class="vp-tc shrink-0 rounded-sm border border-success/60 px-1 text-2xs text-success" title={cadenceTip} data-take-cadence="conformed">{t('generation.card.cadence.rate', cadenceRate)}</span>
					{:else if cadence.state === 'conforming'}
						<span class="vp-tc shrink-0 rounded-sm border border-signal/60 px-1 text-2xs text-signal" title={cadenceTip} data-take-cadence="conforming">{cadenceProgress === null ? t('generation.card.cadence.rate', cadenceRate) : t('generation.card.cadence.progress', { ...cadenceRate, value: cadenceProgress })}</span>
					{:else if cadence.state === 'slow' || cadence.state === 'failed'}
						<button type="button" class="vp-tc shrink-0 rounded-sm border border-warning/60 px-1 text-2xs {cadence.state === 'failed' ? 'text-danger' : 'text-warning'} disabled:opacity-60" title={cadenceTip} data-take-cadence={cadence.state} disabled={interpolator === null || renditionStore.sending} onclick={() => conformTakes([take.id])}>{t('generation.card.cadence.conform', { fps: cadence.to })}</button>
					{/if}
					{#if stale}<span class="flex min-w-0 items-center gap-1 text-warning" title={t('generation.card.staleTip')}><Icon name="alert" class="h-3 w-3 shrink-0" /><span class="truncate">{t('generation.card.stale')}</span></span>{/if}
				</div>
				<details class="text-fg-subtle" data-take-details>
					<summary onclick={(e) => e.stopPropagation()}>{t('generation.card.technical')}</summary>
					<div class="truncate">{modeText()}</div>
					<div class="truncate"><span class="vp-tc">{resolution}</span>{#if framing}<span class="ml-1 rounded-sm border border-line-strong px-1 text-2xs text-fg-muted" title={framing.tip}>{framing.text}</span>{/if}</div>
					<div class="vp-tc truncate">{t('generation.card.seed', { seed: take.seed === null || take.seed === undefined ? '—' : String(take.seed) })}</div>
					{#if backendText}<div class="truncate" title={backendText}>{backendText}</div>{/if}
				</details>
			</div>
		</div>
		{#if flying}
			<div class="px-2 pb-2">
				<div class="mb-1 flex justify-between gap-2 text-xs">
					<span class="truncate text-fg-muted">{take.step || stateText(take.status)}</span>
					{#if take.status === 'running'}<span class="vp-tc text-fg-subtle">{t('exports.percent', { value: progress })}</span>{/if}
				</div>
				{#if take.status === 'running'}
					<div class="h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('generation.card.progress', { variant: take.variant })} aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress}>
						<div class="h-full rounded-full bg-signal transition-[width] duration-150" style:width="{progress}%"></div>
					</div>
				{:else}
					<div class="h-1 rounded-full bg-surface-3" aria-hidden="true"></div>
				{/if}
			</div>
		{:else if take.status === 'failed'}
			<p class="px-2 pb-2 text-xs text-danger">{failure}</p>
		{/if}
		<div class="flex flex-wrap items-center gap-0.5 border-t border-line p-0.5">
			{#if done}
				<HostUi
					name="IconButton"
					props={{ icon: hostIconName('compare'), label: t('generation.card.compare', { variant: take.variant }), tooltip: t('generation.card.compareTip'), size: 'xs', class: 'vp-toggle', ariaPressed: inCompare, onclick: () => toggleCompare(take.id) }}
				/>
			{/if}
			{#if done}<TakeToRefs {take} {clip} />{/if}
			{#if clip && extractable(take)}
				<HostUi
					name="IconButton"
					props={{ icon: hostIconName('image'), label: t('lib.seam.extract'), tooltip: t('lib.seam.extractTip'), size: 'xs', disabled: Boolean(seamState.busy), onclick: () => extractAtPlayhead(take, clip) }}
				/>
			{/if}
			{#if take.generationId}
				<HostUi name="IconButton" props={{ icon: 'info', label: t('generation.card.details', { variant: take.variant }), tooltip: t('generation.card.detailsTip'), size: 'xs', onclick: () => showDetails(take) }} />
			{/if}
			<HostUi name="IconButton" props={{ icon: 'trash', label: t('generation.card.delete', { variant: take.variant }), tooltip: t('generation.card.deleteTip'), size: 'xs', onclick: () => deleteTake(take) }} />
			<span class="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-0.5">
				{#if flying}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => cancelTake(take) }}>{t('generation.card.cancel')}</HostUi>
				{:else if take.status === 'failed'}
					<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'refresh', onclick: () => retryTake(take) }}>{t('generation.card.retry')}</HostUi>
				{:else if done}
					{#if take.quality === 'draft'}
						<HostUi name="Tooltip" props={{ text: finalTip }}>
							<button type="button" class="h-6 whitespace-nowrap rounded px-1.5 text-xs font-medium text-signal hover:bg-surface-2" onclick={() => promoteToFinal(take.id)}>{t('generation.card.makeFinal')}</button>
						</HostUi>
					{/if}
				{/if}
			</span>
		</div>
		{#if !flying}
			<div class="flex items-center gap-1 border-t border-line px-1.5 py-1" role="group" aria-label={t('generation.card.labels', { variant: take.variant })}>
				{#each choices as c (c.id)}
					{@const allowed = c.id === 'final' ? canLabel(take, 'final') && Boolean(clip) : canLabel(take, c.id)}
					<HostUi name="Tooltip" props={{ text: !allowed && label === 'final' && c.id !== 'final' ? lockedTip : c.tip }}>
						<button
							type="button"
							class="vp-toggle h-6 rounded px-2 text-xs font-medium disabled:cursor-default disabled:opacity-50 {label === c.id ? '' : 'text-fg-muted hover:bg-surface-2 hover:text-fg'}"
							aria-pressed={label === c.id}
							aria-label={c.aria}
							disabled={!allowed}
							onclick={() => labelTake(clip, take, toggledLabel(take, c.id))}
						>
							{#if c.id === 'final' && label === 'final'}<Icon name="check" class="-ml-0.5 mr-0.5 inline h-3 w-3" />{/if}{c.text}
						</button>
					</HostUi>
				{/each}
			</div>
		{/if}
	</div>
</li>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, toast, clipLabel } from '../../lib/state.svelte.js';
	import { makeFinal, findTake, presetById } from '../../lib/production.svelte.js';
	import { UPSCALE_TARGETS, aspectOf, canUpscale as autoUpscale, finalResolution, hasNativeEngine, rtxUnchecked, upscalesItself } from '../../lib/generation.js';
	import { AUTO_TARGET, rtxSourceShown, upscalerReady } from '../../lib/finalpass.js';
	import { chosenSize } from '../../lib/formats.js';
	import { takeThumb } from '../../lib/media.js';
	import { guidedReady, guidedResolution, rememberRtxSource, savedChoice, targetLabel } from '../../lib/finalpass.svelte.js';
	import { finalCadence, interpolatorChoice, pickInterpolator } from '../../lib/cadence.js';
	import { hostIconName } from '../../lib/icons.js';
	import Modal from './Modal.svelte';
	import UpscaleControls from './UpscaleControls.svelte';

	let { takeId } = $props();

	const take = $derived(findTake(takeId));
	const clip = $derived(doc.clips.find((c) => c.id === take?.shotId));
	const targets = $derived([AUTO_TARGET, ...(ui.me?.upscaleTargets?.length ? ui.me.upscaleTargets : UPSCALE_TARGETS)]);
	const h3 = $derived(upscalesItself(take?.presetId));
	let upscaler = $state('auto');
	let rtxSource = $state(savedChoice().rtxSource);
	const rtxShown = $derived(rtxSourceShown(upscaler, ui.me) && !(upscaler === 'auto' && h3));
	const canUpscale = $derived(upscaler === 'auto' ? autoUpscale(take, ui.me) : upscalerReady(upscaler, ui.me, take ? [take.presetId] : []));
	const renderRes = $derived((finalResolution(presetById(take?.presetId), aspectOf(doc.aspect, doc.resolution), chosenSize(doc, take?.presetId, 'final')) ?? take?.resolution ?? '—').replace('x', '×'));
	let target = $state(AUTO_TARGET);
	const guided = $derived(guidedReady());
	const guidedRes = $derived(guidedResolution());
	let sending = $state(false);
	let conform = $state(true);
	const cadence = $derived(finalCadence(doc, take));
	const slow = $derived(cadence.slow);
	const interpolator = $derived(pickInterpolator(interpolatorChoice(doc), ui.me));
	const conforming = $derived(slow && conform && interpolator !== null);

	const close = () => (ui.modal = null);

	function upscaleHint(id) {
		if (id === 'rtx') return rtxUnchecked(ui.me) ? t('generation.finalPass.hint.rtxUnchecked') : t('generation.finalPass.hint.rtx');
		if (id === 'seedvr2') return t('generation.finalPass.hint.seedvr2');
		if (id === 'engine' || h3) return t('generation.final.upscaleH3');
		return t('generation.final.upscaleHint');
	}

	async function send(method) {
		if (!take || sending) return;
		const message = method === 'upscale' ? (target === AUTO_TARGET ? t('generation.final.startedUpscaleAuto') : t('generation.final.startedUpscale', { target: targetLabel(target) })) : method === 'guided' ? t('generation.final.startedGuided', { res: guidedRes }) : t('generation.final.startedRender', { res: renderRes });
		sending = true;
		if (method === 'upscale') rememberRtxSource(rtxSource);
		const ok = await makeFinal(take.id, method, target, upscaler, rtxSource, conforming);
		sending = false;
		if (!ok) return;
		close();
		toast(message);
	}
</script>

{#if take}
	<Modal title={t('generation.final.title', { shot: clipLabel(clip), variant: take.variant })} subtitle={t('generation.final.subtitle', { res: (take.resolution ?? '—').replace('x', '×'), seed: take.seed === null || take.seed === undefined ? '—' : String(take.seed) })} icon="arrow-up" width={guided ? 600 : 480}>
		<div class="space-y-4 p-4">
			<div class="flex items-center gap-3">
				{#if takeThumb(take)}<img src={takeThumb(take)} alt="" class="aspect-video w-28 shrink-0 rounded object-cover" />{/if}
				<p class="text-sm text-fg-muted">{t('generation.final.intro')}</p>
			</div>
			<section class="space-y-2">
				<div class="flex items-center gap-2">
					<span class="text-sm font-medium {canUpscale ? 'text-fg' : 'text-fg-muted'}">{t('generation.final.upscale')}</span>
					{#if !canUpscale}
						<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('generation.final.unavailable')}</HostUi>
					{/if}
				</div>
				<p class="text-xs text-fg-subtle">{canUpscale ? upscaleHint(upscaler) : hasNativeEngine(ui.me) ? t('generation.block.upscaleUnsupported') : t('generation.block.noNativeEngine')}</p>
				<UpscaleControls bind:upscaler bind:rtxSource bind:target {targets} ready={canUpscale} engine={h3} {rtxShown} />
			</section>
			{#if guided}<p class="text-xs text-fg-subtle">{t('generation.final.guidedHint', { res: guidedRes })}</p>{/if}
			<p class="text-xs text-fg-subtle">{t('generation.final.renderHint', { res: renderRes })}</p>
			{#if slow}
				<section class="space-y-1.5" aria-label={t('generation.finalPass.cadence.label')}>
					<div class="flex items-center gap-3">
						<label for="vp-make-final-conform" class="text-sm text-fg">{t('generation.final.conform', { from: take.fps, fps: cadence.fps })}</label>
						<span class="flex-1"></span>
						<HostUi name="Switch" props={{ id: 'vp-make-final-conform', checked: conforming, disabled: interpolator === null, size: 'lg', label: t('generation.final.conform', { from: take.fps, fps: cadence.fps }), onchange: (v) => (conform = Boolean(v)) }} />
					</div>
					<p class="text-xs text-fg-subtle">{interpolator === null ? (hasNativeEngine(ui.me) ? t('generation.cadence.noInterpolator') : t('generation.cadence.noNativeEngine')) : conforming ? t('generation.finalPass.cadence.with', { name: interpolator === 'rtx' ? t('generation.cadence.interpolator.rtx') : t('generation.cadence.interpolator.rife') }) : t('generation.finalPass.cadence.off')}</p>
				</section>
			{/if}
		</div>
		{#snippet footer()}
			<HostUi name="Button" props={{ variant: canUpscale ? 'secondary' : 'primary', size: 'sm', class: guided ? '' : 'mr-auto', disabled: sending, onclick: () => send('render') }}>{t('generation.final.render')}</HostUi>
		{#if guided}
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', class: 'mr-auto', disabled: sending, onclick: () => send('guided') }}>{t('generation.final.guided')}</HostUi>
		{/if}
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: close }}>{t('generation.final.cancel')}</HostUi>
			{#if canUpscale}
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('arrow-up'), disabled: sending, onclick: () => send('upscale') }}>{target === AUTO_TARGET ? t('generation.final.upscaleActionAuto') : t('generation.final.upscaleAction', { target: targetLabel(target) })}</HostUi>
			{/if}
		{/snippet}
	</Modal>
{/if}

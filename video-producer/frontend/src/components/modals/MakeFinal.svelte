<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, toast, clipLabel } from '../../lib/state.svelte.js';
	import { makeFinal, findTake, presetById } from '../../lib/production.svelte.js';
	import { UPSCALE_TARGETS, aspectOf, canUpscale as autoUpscale, finalResolution, upscalesItself } from '../../lib/generation.js';
	import { AUTO_TARGET, rtxSourceShown, upscalerReady } from '../../lib/finalpass.js';
	import { chosenSize } from '../../lib/formats.js';
	import { takeThumb } from '../../lib/media.js';
	import { guidedReady, guidedResolution, rememberRtxSource, savedChoice } from '../../lib/finalpass.svelte.js';
	import { interpolatorChoice, needsConform, pickInterpolator, targetOf } from '../../lib/cadence.js';
	import { hostIconName } from '../../lib/icons.js';
	import Modal from './Modal.svelte';

	let { takeId } = $props();

	const take = $derived(findTake(takeId));
	const clip = $derived(doc.clips.find((c) => c.id === take?.shotId));
	const targets = $derived([AUTO_TARGET, ...(ui.me?.upscaleTargets?.length ? ui.me.upscaleTargets : UPSCALE_TARGETS)]);
	const h3 = $derived(upscalesItself(take?.presetId));
	let upscaler = $state('auto');
	let rtxSource = $state(savedChoice().rtxSource);
	const rtxSources = $derived([
		{ id: 'compressed', label: t('generation.finalPass.rtxSource.compressed') },
		{ id: 'clean', label: t('generation.finalPass.rtxSource.clean') }
	]);
	const rtxShown = $derived(rtxSourceShown(upscaler, ui.me) && !(upscaler === 'auto' && h3));
	const canUpscale = $derived(upscaler === 'auto' ? autoUpscale(take, ui.me) : upscalerReady(upscaler, ui.me, take ? [take.presetId] : []));
	const upscalers = $derived([
		{ id: 'auto', label: t('generation.finalPass.upscaler.auto') },
		{ id: 'rtx', label: t('generation.finalPass.upscaler.rtx'), disabled: ui.me?.features?.upscalers?.rtx !== true },
		{ id: 'seedvr2', label: t('generation.finalPass.upscaler.seedvr2'), disabled: ui.me?.features?.upscalers?.seedvr2 !== true },
		...(h3 ? [{ id: 'engine', label: t('generation.finalPass.upscaler.engine') }] : [])
	]);
	const renderRes = $derived((finalResolution(presetById(take?.presetId), aspectOf(doc.aspect, doc.resolution), chosenSize(doc, take?.presetId, 'final')) ?? take?.resolution ?? '—').replace('x', '×'));
	let target = $state(AUTO_TARGET);
	const guided = $derived(guidedReady());
	const guidedRes = $derived(guidedResolution());
	let sending = $state(false);
	let conform = $state(true);
	const filmFps = $derived(targetOf(doc));
	const slow = $derived(filmFps !== null && needsConform(take?.fps, filmFps));
	const interpolator = $derived(pickInterpolator(interpolatorChoice(doc), ui.me));
	const conforming = $derived(slow && conform && interpolator !== null);

	const close = () => (ui.modal = null);

	function upscaleHint(id) {
		if (id === 'rtx') return t('generation.finalPass.hint.rtx');
		if (id === 'seedvr2') return t('generation.finalPass.hint.seedvr2');
		if (id === 'engine' || h3) return t('generation.final.upscaleH3');
		return t('generation.final.upscaleHint');
	}

	function targetLabel(id) {
		if (id === 'auto') return t('generation.target.auto');
		if (id === 'hd720') return t('generation.target.hd720');
		if (id === 'fhd1080') return t('generation.target.fhd1080');
		if (id === 'qhd1440') return t('generation.target.qhd1440');
		if (id === 'uhd2160') return t('generation.target.uhd2160');
		return id;
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
				<p class="text-xs text-fg-subtle">{canUpscale ? upscaleHint(upscaler) : t('generation.block.upscaleUnsupported')}</p>
				<div class="flex items-center gap-3">
					<span class="shrink-0 text-xs text-fg-muted">{t('generation.finalPass.upscaler.label')}</span>
					<HostUi name="SegmentedControl" props={{ variant: 'toggle', ariaLabel: t('generation.finalPass.upscaler.label'), items: upscalers, selected: upscaler, onSelect: (id) => (upscaler = id) }} />
				</div>
				{#if rtxShown}
					<div class="flex items-center gap-3">
						<span class="shrink-0 text-xs text-fg-muted">{t('generation.finalPass.rtxSource.label')}</span>
						<HostUi name="SegmentedControl" props={{ variant: 'toggle', ariaLabel: t('generation.finalPass.rtxSource.label'), items: rtxSources, selected: rtxSource, onSelect: (id) => (rtxSource = id) }} />
					</div>
					<p class="text-xs text-fg-subtle">{rtxSource === 'clean' ? t('generation.finalPass.rtxSource.cleanHint') : t('generation.finalPass.rtxSource.compressedHint')}</p>
				{/if}
				<HostUi
					name="SegmentedControl"
					props={{ variant: 'toggle', fullWidth: true, ariaLabel: t('generation.final.target'), items: targets.map((id) => ({ id, label: targetLabel(id), disabled: !canUpscale })), selected: target, onSelect: (id) => (target = id) }}
				/>
				{#if target === AUTO_TARGET}<p class="text-xs text-fg-subtle">{t('generation.finalPass.targetAuto')}</p>{/if}
			</section>
			{#if guided}<p class="text-xs text-fg-subtle">{t('generation.final.guidedHint', { res: guidedRes })}</p>{/if}
			<p class="text-xs text-fg-subtle">{t('generation.final.renderHint', { res: renderRes })}</p>
			{#if slow}
				<section class="space-y-1.5" aria-label={t('generation.finalPass.cadence.label')}>
					<div class="flex items-center gap-3">
						<label for="vp-make-final-conform" class="text-sm text-fg">{t('generation.final.conform', { from: take.fps, fps: filmFps })}</label>
						<span class="flex-1"></span>
						<HostUi name="Switch" props={{ id: 'vp-make-final-conform', checked: conforming, disabled: interpolator === null, size: 'lg', label: t('generation.final.conform', { from: take.fps, fps: filmFps }), onchange: (v) => (conform = Boolean(v)) }} />
					</div>
					<p class="text-xs text-fg-subtle">{interpolator === null ? t('generation.cadence.noInterpolator') : conforming ? t('generation.finalPass.cadence.with', { name: interpolator === 'rtx' ? t('generation.cadence.interpolator.rtx') : t('generation.cadence.interpolator.rife') }) : t('generation.finalPass.cadence.off')}</p>
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

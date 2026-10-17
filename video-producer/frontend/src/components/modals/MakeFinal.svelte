<script>
	import { untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, toast, clipLabel } from '../../lib/state.svelte.js';
	import { makeFinal, upscaleAvailable, findTake, presetById } from '../../lib/production.svelte.js';
	import { UPSCALE_TARGETS, aspectOf, finalResolution, upscaleTargetFor, upscalesItself } from '../../lib/generation.js';
	import { takeThumb } from '../../lib/media.js';
	import { hostIconName } from '../../lib/icons.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';

	let { takeId } = $props();

	const take = $derived(findTake(takeId));
	const clip = $derived(doc.clips.find((c) => c.id === take?.shotId));
	const targets = $derived(ui.me?.upscaleTargets?.length ? ui.me.upscaleTargets : UPSCALE_TARGETS);
	const canUpscale = $derived(upscaleAvailable(take));
	const h3 = $derived(upscalesItself(take?.presetId));
	const renderRes = $derived((finalResolution(presetById(take?.presetId), aspectOf(doc.aspect, doc.resolution)) ?? take?.resolution ?? '—').replace('x', '×'));
	let target = $state(untrack(() => upscaleTargetFor(doc.resolution, ui.me?.upscaleTargets?.length ? ui.me.upscaleTargets : UPSCALE_TARGETS)));
	let sending = $state(false);

	const close = () => (ui.modal = null);

	function targetLabel(id) {
		if (id === 'hd720') return t('generation.target.hd720');
		if (id === 'fhd1080') return t('generation.target.fhd1080');
		if (id === 'qhd1440') return t('generation.target.qhd1440');
		if (id === 'uhd2160') return t('generation.target.uhd2160');
		return id;
	}

	async function send(method) {
		if (!take || sending) return;
		const message = method === 'upscale' ? t('generation.final.startedUpscale', { target: targetLabel(target) }) : t('generation.final.startedRender', { res: renderRes });
		sending = true;
		const ok = await makeFinal(take.id, method, target);
		sending = false;
		if (!ok) return;
		close();
		toast(message);
	}
</script>

{#if take}
	<Modal title={t('generation.final.title', { shot: clipLabel(clip), variant: take.variant })} subtitle={t('generation.final.subtitle', { res: (take.resolution ?? '—').replace('x', '×'), seed: take.seed === null || take.seed === undefined ? '—' : String(take.seed) })} icon="arrow-up" width={480}>
		<div class="space-y-4 p-4">
			<div class="flex items-center gap-3">
				{#if takeThumb(take)}<img src={takeThumb(take)} alt="" class="aspect-video w-28 shrink-0 rounded object-cover" />{/if}
				<p class="text-sm text-fg-muted">{t('generation.final.intro')}</p>
			</div>
			<section class="space-y-2">
				<div class="flex items-center gap-2">
					<span class="text-sm font-medium {canUpscale ? 'text-fg' : 'text-fg-muted'}">{t('generation.final.upscale')}</span>
					{#if !canUpscale}
						<HostUi name="Tooltip" props={{ text: t('generation.final.unavailableWhy'), wrapperClass: 'inline-flex' }}>
							<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('generation.final.unavailable')}</span>
						</HostUi>
					{/if}
				</div>
				<p class="text-xs text-fg-subtle">{h3 ? t('generation.final.upscaleH3') : t('generation.final.upscaleHint')}</p>
				<HostUi
					name="SegmentedControl"
					props={{ variant: 'toggle', fullWidth: true, ariaLabel: t('generation.final.target'), items: targets.map((id) => ({ id, label: targetLabel(id), disabled: !canUpscale })), selected: target, onSelect: (id) => (target = id) }}
				/>
			</section>
			<p class="text-xs text-fg-subtle">{t('generation.final.renderHint', { res: renderRes })}</p>
		</div>
		{#snippet footer()}
			<HostUi name="Button" props={{ variant: canUpscale ? 'secondary' : 'primary', size: 'sm', class: 'mr-auto', disabled: sending, onclick: () => send('render') }}>{t('generation.final.render')}</HostUi>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: close }}>{t('generation.final.cancel')}</HostUi>
			{#if canUpscale}
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('arrow-up'), disabled: sending, onclick: () => send('upscale') }}>{t('generation.final.upscaleAction', { target: targetLabel(target) })}</HostUi>
			{/if}
		{/snippet}
	</Modal>
{/if}

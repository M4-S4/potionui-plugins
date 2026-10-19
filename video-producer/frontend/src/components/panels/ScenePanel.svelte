<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs, asset } from '../../lib/state.svelte.js';
	import { sceneLabel } from '../../lib/catalog.js';
	import { assetThumb } from '../../lib/media.js';
	import {
		sceneState,
		currentScene,
		currentPlan,
		sceneReady,
		sceneBusy,
		controlOf,
		newPlan,
		applyPreset,
		setPresetAmount,
		presetLabel,
		useBlenderCamera,
		openCapture,
		renderPlan,
		cancelRender,
		useStartEnd,
		retryScene,
		cancelScene,
		removeScene,
		chooseSceneFile,
		sceneErrorText,
		sceneProgress,
		sceneLocked,
		pickScene,
		focusPlan,
		videoSize
	} from '../../lib/scene.svelte.js';
	import { FPS, MAX_REFERENCE_SIDE, MIN_REFERENCE_SECONDS, PRESETS, PRESET_IDS, holesMatter, presetWarns } from '../../lib/scene3d/camera.js';
	import { hostIconName } from '../../lib/icons.js';
	import PanelHeader from './PanelHeader.svelte';
	import SliderField from '../inspector/SliderField.svelte';
	import Icon from '../Icon.svelte';

	const active = $derived(currentScene());
	const plan = $derived(currentPlan());
	const planScene = $derived(plan ? (doc.scenes.find((s) => s.id === plan.sceneId) ?? null) : active);
	const control = $derived(controlOf(plan));
	const preset = $derived(ui.scene.preset);
	const spec = $derived(PRESETS[preset]);
	const amount = $derived(ui.scene.amounts[preset] ?? spec.value);
	const warn = $derived(holesMatter(planScene) && presetWarns(preset, amount));
	const cameras = $derived(planScene?.kind === 'glb' ? planScene.cameras : []);
	let cameraName = $state('');
	const pickedCamera = $derived(cameras.find((c) => c.name === cameraName) ?? cameras.find((c) => c.animated) ?? cameras[0] ?? null);
	const busy = $derived(sceneLocked());
	const encoding = $derived(sceneState.render?.phase === 'encoding');
	const video = $derived(videoSize());
	const canRender = $derived(Boolean(plan && planScene && sceneReady(planScene) && plan.keyframes.length));
	const presetIcon = (id) => (id === 'orbit' ? 'orbit' : id === 'crane' ? 'arrow-up' : 'arrow-right');
	const unit = (id) => (PRESETS[id].unit === 'deg' ? '°' : ' %');

	function status(s) {
		if (s.kind === 'splat') {
			if (s.status === 'queued') return t('scene.status.queued');
			if (s.status === 'running') return t('scene.status.progress', { value: Math.round(sceneProgress(s)) });
			if (s.status === 'failed') return sceneErrorText(s.error);
			return s.count ? t('scene.status.splats', { count: s.count }) : sceneLabel(s);
		}
		if (s.kind === 'glb') return t('scene.status.cameras', { count: s.cameras.length });
		return sceneLabel(s);
	}

	function cameraMeta(c) {
		return c.animated ? t('scene.blender.animated', { name: c.name, duration: secs(c.duration ?? 0) }) : t('scene.blender.still', { name: c.name });
	}

	function sourceName(p) {
		if (p.source === 'trajectory' && p.preset) return presetLabel(p.preset);
		if (p.source === 'blender') return t('scene.source.blender');
		return t('scene.source.manual');
	}

	function useCamera() {
		if (!pickedCamera) return;
		const target = plan ?? newPlan();
		useBlenderCamera(target, pickedCamera.name);
	}
</script>

<PanelHeader icon="cube" title={t('panels.scene.title')} />

<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-3">
	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.scenes')}</div>
		{#if doc.scenes.length}
			<ul class="space-y-1">
				{#each doc.scenes as s (s.id)}
					{@const thumb = s.kind === 'splat' ? assetThumb(asset(s.sourceAssetId)) : null}
					<li class="flex items-center gap-1 rounded-lg border p-1.5 {active?.id === s.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}">
						<button type="button" class="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-not-allowed" aria-pressed={active?.id === s.id} disabled={busy && active?.id !== s.id} onclick={() => pickScene(s.id)}>
							{#if thumb}
								<img src={thumb} alt="" class="h-8 w-14 shrink-0 rounded object-cover" />
							{:else}
								<span class="flex h-8 w-14 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name={s.kind === 'glb' ? 'layers' : 'cube'} class="h-4 w-4 text-fg-muted" /></span>
							{/if}
							<span class="min-w-0 flex-1">
								<span class="block truncate text-sm">{s.name}</span>
								<span class="block truncate text-xs {s.kind === 'splat' && s.status === 'failed' ? 'text-warning' : 'text-fg-subtle'}">{status(s)}</span>
							</span>
						</button>
						{#if sceneBusy(s)}
							<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('scene.cancel'), tooltip: t('scene.cancel'), size: 'xs', onclick: () => cancelScene(s) }} />
						{:else if s.kind === 'splat' && s.status === 'failed'}
							<HostUi name="IconButton" props={{ icon: 'refresh', label: t('scene.retry'), tooltip: t('scene.retry'), size: 'xs', onclick: () => retryScene(s) }} />
						{/if}
						<HostUi name="IconButton" props={{ icon: 'trash', label: t('scene.remove'), tooltip: t('scene.remove'), size: 'xs', disabled: busy, onclick: () => removeScene(s) }} />
					</li>
				{/each}
			</ul>
		{:else}
			<HostUi name="EmptyState" props={{ compact: true, icon: 'cube', title: t('scene.empty.title'), description: t('scene.empty.text') }} />
		{/if}
		<div class="mt-1 flex flex-col gap-0.5">
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'w-full', onclick: () => (ui.modal = { type: 'scene-new' }) }}>{t('scene.new')}</HostUi>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'upload', class: 'w-full', disabled: sceneState.uploading, onclick: chooseSceneFile }}>{sceneState.uploading ? t('scene.uploading') : t('scene.import')}</HostUi>
		</div>
	</div>

	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.plans')}</div>
		<ul class="space-y-1">
			{#each doc.plans3d as p (p.id)}
				<li>
					<button
						type="button"
						class="flex w-full items-center gap-2 rounded border px-2 py-1.5 text-left text-sm {ui.selection?.id === p.id ? 'border-signal bg-surface-2' : 'border-transparent hover:bg-surface-2'}"
						onclick={() => focusPlan(p)}
					>
						<span class="h-2 w-2 rounded-sm bg-viz-8"></span><span class="flex-1 truncate">{p.name}</span>
						<span class="vp-tc text-xs text-fg-muted">{t('panels.scene.planMeta', { start: secs(p.start), source: sourceName(p) })}</span>
					</button>
				</li>
			{/each}
		</ul>
		<div class="mt-1">
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'w-full', onclick: newPlan }}>{t('panels.scene.newPlan')}</HostUi>
		</div>
	</div>

	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.presets')}</div>
		<div class="grid grid-cols-3 gap-1.5">
			{#each PRESET_IDS as id (id)}
				<HostUi
					name="Button"
					props={{ variant: plan?.source === 'trajectory' && plan.preset === id ? 'primary' : 'secondary', size: 'sm', icon: hostIconName(presetIcon(id)), class: 'w-full flex-col !text-xs py-2', onclick: () => applyPreset(id) }}
				>{presetLabel(id)}</HostUi>
			{/each}
		</div>
		<div class="mt-2">
			<SliderField label={t('panels.scene.amount', { preset: presetLabel(preset) })} value={amount} min={spec.min} max={spec.max} step={1} unit={unit(preset)} onchange={(v) => setPresetAmount(preset, v)} />
		</div>
		{#if warn}
			<p class="mt-1 flex gap-1.5 text-xs text-warning"><Icon name="alert" class="mt-px h-3.5 w-3.5 shrink-0" />{t('panels.scene.holesWarn')}</p>
		{:else}
			<p class="mt-1 text-xs text-fg-subtle">{planScene?.kind === 'glb' ? t('panels.scene.presetHintGlb') : t('panels.scene.presetHint')}</p>
		{/if}
	</div>

	{#if cameras.length}
		<div>
			<div class="vp-section-title mb-1.5">{t('panels.scene.blender')}</div>
			<div class="flex flex-col gap-1.5">
				<select class="input vp-dense w-full" value={pickedCamera?.name ?? ''} onchange={(e) => (cameraName = e.currentTarget.value)} aria-label={t('panels.scene.blender')}>
					{#each cameras as c (c.name)}<option value={c.name}>{cameraMeta(c)}</option>{/each}
				</select>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'camera', class: 'w-full', disabled: !pickedCamera || !sceneReady(planScene) || busy, onclick: useCamera }}>{t('panels.scene.useCamera')}</HostUi>
			</div>
		</div>
	{/if}

	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.outputs')}</div>
		{#if control?.stale}
			<div class="mb-2">
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: hostIconName('alert') }}>
					<span class="text-xs">{t('panels.scene.stale')}</span>
				</HostUi>
			</div>
		{/if}
		<div class="flex flex-col gap-1.5">
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'image', class: 'w-full', disabled: !sceneReady(active) || busy, onclick: openCapture }}>{t('panels.scene.capture')}</HostUi>
			{#if sceneState.render}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('x'), class: 'w-full', disabled: encoding, onclick: cancelRender }}>
					{encoding ? t('scene.render.encoding') : t('panels.scene.cancelRender', { done: sceneState.render.done, total: sceneState.render.total })}
				</HostUi>
			{:else}
				<HostUi name="Tooltip" props={{ text: t('panels.scene.renderTip'), wrapperClass: 'flex w-full' }}>
					<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName(control?.stale ? 'refresh' : 'route'), class: 'w-full', disabled: !canRender || busy, onclick: () => renderPlan(plan) }}>
						{control?.assetId ? t('panels.scene.rerender') : t('panels.scene.render')}
					</HostUi>
				</HostUi>
			{/if}
			<HostUi name="Tooltip" props={{ text: t('panels.scene.endsTip'), wrapperClass: 'flex w-full' }}>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('image'), class: 'w-full', disabled: !canRender || busy, onclick: () => useStartEnd(plan) }}>
					{sceneState.ends ? t('panels.scene.endsWorking') : t('panels.scene.ends')}
				</HostUi>
			</HostUi>
		</div>
		{#if plan && plan.dur < MIN_REFERENCE_SECONDS}
			<p class="mt-1.5 text-xs text-warning">{t('panels.scene.short', { min: secs(MIN_REFERENCE_SECONDS) })}</p>
		{:else if control?.assetId && !control.stale}
			<p class="mt-1.5 text-xs text-fg-subtle">{t('panels.scene.rendered', { duration: secs(control.dur), name: plan?.name ?? '' })}</p>
		{:else if !plan}
			<p class="mt-1.5 text-xs text-fg-subtle">{t('panels.scene.noPlan')}</p>
		{/if}
		<p class="mt-1.5 text-xs text-fg-subtle">{t('panels.scene.size', { width: formatNumber(video.width, { useGrouping: false }), height: formatNumber(video.height, { useGrouping: false }), fps: FPS, max: formatNumber(MAX_REFERENCE_SIDE, { useGrouping: false }) })}</p>
	</div>
</div>

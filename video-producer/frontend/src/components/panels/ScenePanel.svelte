<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs, select } from '../../lib/state.svelte.js';
	import { motionPresets, motionPresetLabel, sceneLabel } from '../../lib/catalog.js';
	import { applyPreset, renderGuide, captureFrame, newPlan, currentScene, addSampleScene } from '../../lib/scene.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import PanelHeader from './PanelHeader.svelte';
	import Icon from '../Icon.svelte';

	const stale = $derived(doc.controls.filter((c) => c.source === 'scene3d' && c.stale));
	const captures = $derived(doc.frames.filter((f) => f.role === 'Capture 3D'));
	const presetIcon = (name) => (name === 'Orbite' ? 'orbit' : name === 'Élévation' ? 'arrow-up' : 'arrow-right');
	const active = $derived(currentScene());
	const hasSample = $derived(doc.scenes.some((s) => s.kind === 'sample'));
</script>

<PanelHeader icon="cube" title={t('panels.scene.title')} />

<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-3">
	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.scenes')}</div>
		{#if doc.scenes.length}
			<ul class="space-y-1">
				{#each doc.scenes as s (s.id)}
					<li>
						<button
							type="button"
							class="flex w-full items-center gap-2 rounded-lg border p-2 text-left {active?.id === s.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}"
							aria-pressed={active?.id === s.id}
							onclick={() => (ui.scene.current = s.id)}
						>
							<Icon name={s.kind === 'sample' ? 'cube' : 'link'} class="h-4 w-4 text-fg-muted" />
							<span class="min-w-0 flex-1">
								<span class="block truncate text-sm">{s.name}</span>
								<span class="block truncate text-xs text-fg-subtle">{s.kind === 'file' ? s.file : sceneLabel(s)}</span>
							</span>
							{#if s.kind === 'sample'}<span class="vp-sim shrink-0"><Icon name="flask" class="h-3 w-3" />{t('shell.window.simulated')}</span>{/if}
						</button>
					</li>
				{/each}
			</ul>
		{:else}
			<HostUi name="EmptyState" props={{ compact: true, icon: 'cube', title: t('scene.empty.title'), description: t('scene.empty.text') }} />
		{/if}
		<div class="mt-1 flex flex-col gap-0.5">
			{#if !hasSample}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'w-full', onclick: addSampleScene }}>{t('scene.sample.name')}</HostUi>
			{/if}
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'w-full', onclick: () => (ui.modal = { type: 'splat' }) }}>{t('panels.scene.splat')}</HostUi>
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
						onclick={() => (select('plan3d', p.id), seek(p.start))}
					>
						<span class="h-2 w-2 rounded-sm bg-viz-8"></span><span class="flex-1 truncate">{p.name}</span>
						<span class="vp-tc text-xs text-fg-muted">{t('panels.scene.planMeta', { start: secs(p.start), count: p.keyframes.length })}</span>
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
			{#each Object.keys(motionPresets) as name (name)}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName(presetIcon(name)), class: 'w-full flex-col !text-xs py-2', onclick: () => applyPreset(name) }}>{motionPresetLabel(name)}</HostUi>
			{/each}
		</div>
	</div>

	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.outputs')}</div>
		{#if stale.length}
			<div class="mb-2">
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: hostIconName('alert') }}>
					<span class="text-xs">{t('panels.scene.stale', { count: stale.length })}</span>
				</HostUi>
			</div>
		{/if}
		<div class="flex flex-col gap-1.5">
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'image', class: 'w-full', onclick: captureFrame }}>{t('panels.scene.capture')}</HostUi>
			<HostUi name="Tooltip" props={{ text: t('panels.scene.renderTip'), wrapperClass: 'flex w-full' }}>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName(stale.length ? 'refresh' : 'route'), class: 'w-full', onclick: renderGuide }}>
					{stale.length ? t('panels.scene.recompute') : t('panels.scene.render')}
				</HostUi>
			</HostUi>
		</div>
		{#if captures.length}<p class="mt-1.5 text-xs text-fg-subtle">{t('panels.scene.captures', { count: captures.length })}</p>{/if}
	</div>
</div>

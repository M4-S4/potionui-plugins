<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, asset } from '../../lib/state.svelte.js';
	import { sceneLabel } from '../../lib/catalog.js';
	import { assetThumb } from '../../lib/media.js';
	import {
		currentScene,
		shownScenes,
		sceneReady,
		sceneBusy,
		openCapture,
		retryScene,
		cancelScene,
		removeScene,
		sceneErrorText,
		sceneProgress,
		sceneLocked,
		pickScene
	} from '../../lib/scene.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import PanelHeader from './PanelHeader.svelte';
	import Icon from '../Icon.svelte';

	const active = $derived(currentScene());
	const scenes = $derived(shownScenes());
	const busy = $derived(sceneLocked());

	function status(s) {
		if (s.kind === 'splat') {
			if (s.status === 'queued') return t('scene.status.queued');
			if (s.status === 'running') return t('scene.status.progress', { value: Math.round(sceneProgress(s)) });
			if (s.status === 'failed') return sceneErrorText(s.error);
			return s.count ? t('scene.status.splats', { count: s.count }) : sceneLabel(s);
		}
		return sceneLabel(s);
	}
</script>

<PanelHeader icon="cube" title={t('panels.scene.title')} />

<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-3">
	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.scenes')}</div>
		{#if scenes.length}
			<ul class="space-y-1">
				{#each scenes as s (s.id)}
					{@const thumb = s.kind === 'splat' ? assetThumb(asset(s.sourceAssetId)) : null}
					<li class="flex items-center gap-1 rounded-lg border p-1.5 {active?.id === s.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}">
						<button type="button" class="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-not-allowed" aria-pressed={active?.id === s.id} disabled={busy && active?.id !== s.id} onclick={() => pickScene(s.id)}>
							{#if thumb}
								<img src={thumb} alt="" class="h-8 w-14 shrink-0 rounded object-cover" />
							{:else}
								<span class="flex h-8 w-14 shrink-0 items-center justify-center rounded bg-surface-3"><Icon name="cube" class="h-4 w-4 text-fg-muted" /></span>
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
		<div class="mt-1">
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'w-full', onclick: () => (ui.modal = { type: 'scene-new' }) }}>{t('scene.new')}</HostUi>
		</div>
	</div>

	<div>
		<div class="vp-section-title mb-1.5">{t('panels.scene.outputs')}</div>
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'image', class: 'w-full', disabled: !sceneReady(active) || busy, onclick: openCapture }}>{t('panels.scene.capture')}</HostUi>
	</div>
</div>

<script>
	import { t } from '../../i18n/index.svelte.js';
	import { ui, bandView } from '../../lib/state.svelte.js';
	import MediaBrowser from './MediaBrowser.svelte';
	import DirectorDock from './DirectorDock.svelte';
	import StoryPanel from './StoryPanel.svelte';
	import ScenePanel from './ScenePanel.svelte';
	import MixerPanel from './MixerPanel.svelte';
</script>

<aside class="flex min-h-0 flex-col overflow-hidden border-r border-line bg-surface-1" aria-label={t('panels.left.label')} class:invisible={!ui.sidebarOpen || bandView()}>
	{#if ui.workspace === 'media'}
		<MediaBrowser />
	{:else if ui.workspace === 'director'}
		<DirectorDock />
	{:else if ui.workspace === 'storyboard'}
		<StoryPanel />
	{:else if ui.workspace === 'scene'}
		<ScenePanel />
	{:else}
		<MixerPanel />
	{/if}
</aside>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { getLocale, t } from '../../i18n/index.svelte.js';
	import { ui, doc, selected, seqDuration, secs, allIssues } from '../../lib/state.svelte.js';
	import { sceneState, sceneBusy, sceneProgress } from '../../lib/scene.svelte.js';
	import Icon from '../Icon.svelte';

	const sel = $derived(selected());
	const issues = $derived(allIssues().filter((i) => i.level !== 'missing'));
	const ratio = $derived(ui.quota?.limit > 0 ? Math.min(1, ui.quota.used / ui.quota.limit) : 0);
	const building = $derived(doc.scenes.filter(sceneBusy));
	const language = $derived(getLocale() === 'fr' ? t('shell.locale.fr') : t('shell.locale.en'));

	function kindLabel(kind) {
		if (kind === 'clip') return t('shell.kind.clip');
		if (kind === 'audio') return t('shell.kind.audio');
		if (kind === 'title') return t('shell.kind.title');
		if (kind === 'prompt') return t('shell.kind.prompt');
		if (kind === 'frame') return t('shell.kind.frame');
		if (kind === 'control') return t('shell.kind.control');
		if (kind === 'plan3d') return t('shell.kind.plan3d');
		if (kind === 'marker') return t('shell.kind.marker');
		if (kind === 'lane') return t('shell.kind.lane');
		return t('shell.kind.reference');
	}

	function toolName(tool) {
		if (tool === 'range') return t('shell.status.toolName.range');
		if (tool === 'blade') return t('shell.status.toolName.blade');
		return t('shell.status.toolName.select');
	}

	function directionIssues() {
		ui.workspace = 'director';
		ui.dockTab = 'direction';
	}
</script>

<footer class="vp-statusbar">
	<HostUi name="Tooltip" props={{ text: t('shell.status.localeTip', { language }) }}>
		<button type="button" class="vp-statusbar-locale" onclick={() => (ui.modal = { type: 'prefs' })}>{t('shell.status.locale')}</button>
	</HostUi>
	<span>{t('shell.status.summary', { count: doc.clips.length, duration: secs(seqDuration()), resolution: doc.resolution, fps: doc.fps, aspect: doc.aspect })}</span>
	<span class="text-fg-muted">{toolName(ui.tool)}</span>
	{#if sel}
		<span>{t('shell.status.selection')} <span class="text-fg-muted">{kindLabel(ui.selection.kind)}</span></span>
	{/if}
	{#if ui.range}
		<span>{t('shell.status.range')} <span class="vp-tc text-fg-muted">{secs(ui.range.in)} → {secs(ui.range.out)}</span></span>
	{/if}
	<div class="flex-1"></div>
	{#if issues.length}
		<button type="button" class="flex h-6 items-center gap-1 text-warning hover:underline" onclick={directionIssues}>
			<Icon name="alert" class="h-3 w-3" />{t('shell.status.issues', { count: issues.length })}
		</button>
	{/if}
	{#if sceneState.render}
		<button type="button" class="flex h-6 items-center gap-1 text-signal hover:underline" onclick={() => (ui.workspace = 'scene')}>
			<Icon name="cube" class="h-3 w-3" />{t('shell.status.rendering', { done: sceneState.render.done, total: sceneState.render.total })}
		</button>
	{:else if building.length}
		<button type="button" class="flex h-6 items-center gap-1 text-signal hover:underline" onclick={() => (ui.workspace = 'scene')}>
			<Icon name="cube" class="h-3 w-3" />{t('shell.status.building', { count: building.length, value: Math.round(building.reduce((sum, s) => sum + sceneProgress(s), 0) / building.length) })}
		</button>
	{/if}
	{#if ui.production.queue.length}
		<span>{t('shell.status.queue', { count: ui.production.queue.length })}</span>
	{/if}
	<span>{ui.snapping ? t('shell.status.snapping.on') : t('shell.status.snapping.off')}</span>
	{#if ui.quota}
		<HostUi name="Tooltip" props={{ text: t('shell.status.quotaTip'), position: 'top' }}>
			<span class="flex items-center gap-1.5">
				{t('shell.status.quota')}
				<span class="h-1 w-16 overflow-hidden rounded-full bg-surface-3"><span class="block h-full rounded-full {ratio > 0.85 ? 'bg-warning' : 'bg-fg-muted'}" style:width="{ratio * 100}%"></span></span>
				<span class="vp-tc text-fg-muted">{t('shell.status.quotaValue', { used: Math.round(ui.quota.used), limit: ui.quota.limit })}</span>
			</span>
		</HostUi>
	{/if}
</footer>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatTime, t } from '../../i18n/index.svelte.js';
	import { ui, doc } from '../../lib/state.svelte.js';
	import { commandById, save, shortcutLabel } from '../../lib/commands.js';
	import { chat } from '../../lib/host.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	const workspaces = [
		{ id: 'media', icon: 'image', keys: 'ctrl+1' },
		{ id: 'director', icon: 'sparkles', keys: 'ctrl+2' },
		{ id: 'storyboard', icon: 'grid', keys: 'ctrl+3' },
		{ id: 'scene', icon: 'cube', keys: 'ctrl+4' },
		{ id: 'mixer', icon: 'sliders', keys: 'ctrl+5' }
	];

	function workspaceLabel(id) {
		if (id === 'media') return t('shell.workspace.media');
		if (id === 'director') return t('shell.workspace.director');
		if (id === 'storyboard') return t('shell.workspace.storyboard');
		if (id === 'scene') return t('shell.workspace.scene');
		return t('shell.workspace.mixer');
	}

	const tip = (id) => ({ text: commandById(id)?.label ?? '', kbd: commandById(id)?.key || undefined });
	const savedTime = $derived(ui.savedAt ? formatTime(ui.savedAt) : null);

	function nameChanged() {
		if (!doc.name.trim()) doc.name = t('lib.default.project');
	}
</script>

<header class="vp-projectbar">
	<div class="flex min-w-0 items-center gap-2">
		<HostUi
			name="IconButton"
			props={{
				icon: hostIconName('panel-left'),
				label: t('shell.project.showSidebar'),
				size: 'sm',
				class: 'vp-h7 vp-toggle',
				ariaPressed: ui.sidebarOpen,
				tooltip: commandById('sidebar')?.label,
				kbd: commandById('sidebar')?.key,
				onclick: () => (ui.sidebarOpen = !ui.sidebarOpen)
			}}
		/>
		<div class="flex min-w-0 flex-col">
			<input class="vp-projectbar-name" bind:value={doc.name} onchange={nameChanged} aria-label={t('shell.project.name')} />
			<HostUi name="Tooltip" props={tip('save')}>
				<button type="button" class="flex h-6 items-center gap-1.5 self-start text-xs leading-none text-fg-muted hover:text-fg" onclick={save} aria-live="polite">
					{#if ui.dirty}
						<span class="h-1.5 w-1.5 rounded-full bg-warning"></span>{t('shell.project.dirty')}
					{:else if savedTime}
						{t('shell.project.savedAt', { time: savedTime })}
					{:else}
						{t('shell.project.unsaved')}
					{/if}
				</button>
			</HostUi>
		</div>
	</div>

	<div class="vp-seg-lg" role="tablist" aria-label={t('shell.workspace.group')}>
		{#each workspaces as w (w.id)}
			<HostUi name="Tooltip" props={{ text: workspaceLabel(w.id), kbd: shortcutLabel(w.keys), wrapperClass: 'flex' }}>
				<button type="button" role="tab" aria-selected={ui.workspace === w.id} onclick={() => (ui.workspace = w.id)}>
					<Icon name={w.icon} class="h-3.5 w-3.5" />{workspaceLabel(w.id)}
				</button>
			</HostUi>
		{/each}
	</div>

	<div class="flex min-w-0 items-center justify-end gap-0.5">
		<HostUi name="Tooltip" props={{ text: t('shell.project.importTip'), kbd: commandById('import')?.key }}>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: 'upload', onclick: () => (ui.modal = { type: 'import' }) }}>{t('shell.project.import')}</HostUi>
		</HostUi>
		<HostUi name="Tooltip" props={{ text: t('shell.project.exportTip'), kbd: commandById('export')?.key }}>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: hostIconName('export'), onclick: () => (ui.modal = { type: 'export' }) }}>{t('shell.project.export')}</HostUi>
		</HostUi>
		<div class="vp-divider"></div>
		<HostUi name="Tooltip" props={tip('assistant')}>
			<button type="button" class="vp-assistant" onclick={() => chat.open()}>
				<span class="vp-assistant-ring"></span>
				<Icon name="sparkles" class="h-3.5 w-3.5 text-ai-1" />{t('shell.project.assistant')}
			</button>
		</HostUi>
		<HostUi
			name="IconButton"
			props={{ icon: 'search', label: t('shell.project.search'), size: 'sm', class: 'vp-h7', tooltip: t('shell.project.search'), kbd: commandById('palette')?.key, onclick: () => (ui.paletteOpen = true) }}
		/>
		<HostUi
			name="IconButton"
			props={{
				icon: hostIconName('panel-right'),
				label: t('shell.project.showInspector'),
				size: 'sm',
				class: 'vp-h7 vp-toggle',
				ariaPressed: ui.inspectorOpen,
				tooltip: commandById('inspector')?.label,
				kbd: commandById('inspector')?.key,
				onclick: () => (ui.inspectorOpen = !ui.inspectorOpen)
			}}
		/>
	</div>
</header>

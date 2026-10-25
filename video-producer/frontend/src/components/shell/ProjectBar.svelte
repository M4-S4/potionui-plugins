<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatTime, t } from '../../i18n/index.svelte.js';
	import { ui, doc, bandView } from '../../lib/state.svelte.js';
	import { commandById, save, toggleSidebar } from '../../lib/commands.js';
	import { WORKSPACES, isPlayer } from '../../lib/workspaces.js';
	import { chat } from '../../lib/host.js';
	import { openImport, openLocalImport } from '../../lib/importer.js';
	import { project } from '../../lib/project.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';
	import Dropdown from './Dropdown.svelte';

	function workspaceLabel(id) {
		if (id === 'media') return t('shell.workspace.media');
		if (id === 'play') return t('shell.workspace.play');
		if (id === 'director') return t('shell.workspace.director');
		if (id === 'storyboard') return t('shell.workspace.storyboard');
		return t('shell.workspace.mixer');
	}

	const importItems = $derived([
		{ label: t('shell.project.importLibrary'), icon: 'folder', key: commandById('import')?.key, run: () => openImport() },
		{ label: t('shell.project.importLocal'), icon: 'upload', key: commandById('import-local')?.key, run: () => openLocalImport() }
	]);
	const tip = (id) => ({ text: commandById(id)?.label ?? '', kbd: commandById(id)?.key || undefined });
	const savedTime = $derived(project.savedAt ? formatTime(project.savedAt) : null);
	const saveState = $derived(project.status === 'saving' ? 'saving' : project.status === 'error' ? 'error' : ui.dirty ? 'dirty' : 'saved');
	const player = $derived(isPlayer(ui.workspace));

	function nameChanged() {
		if (!doc.name.trim()) doc.name = t('lib.default.project');
	}

	function pick(e, id) {
		ui.workspace = id;
		if (e.detail > 0) e.currentTarget.blur();
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
				ariaPressed: (bandView() ? ui.storyOpen : ui.sidebarOpen) && !player,
				disabled: player,
				tooltip: commandById('sidebar')?.label,
				kbd: commandById('sidebar')?.key,
				onclick: toggleSidebar
			}}
		/>
		<div class="flex min-w-0 flex-col">
			<input class="vp-projectbar-name" bind:value={doc.name} onchange={nameChanged} aria-label={t('shell.project.name')} />
			<HostUi name="Tooltip" props={tip('save')}>
				<button type="button" class="flex h-6 items-center gap-1.5 self-start text-xs leading-none text-fg-muted hover:text-fg" onclick={save}>
					{#if saveState === 'saving'}
						<span class="h-1.5 w-1.5 rounded-full bg-signal"></span>{t('project.status.saving')}
					{:else if saveState === 'error'}
						<span class="h-1.5 w-1.5 rounded-full bg-danger"></span>{t('project.status.error')}
					{:else if saveState === 'dirty'}
						<span class="h-1.5 w-1.5 rounded-full bg-warning"></span>{t('shell.project.dirty')}
					{:else if savedTime}
						{t('shell.project.savedAt', { time: savedTime })}
					{:else}
						{t('shell.project.unsaved')}
					{/if}
				</button>
			</HostUi>
			<span class="sr-only" aria-live="polite">{saveState === 'error' ? t('project.status.error') : ''}</span>
		</div>
	</div>

	<div class="vp-seg-lg" role="tablist" aria-label={t('shell.workspace.group')}>
		{#each WORKSPACES as w (w.id)}
			<button type="button" role="tab" aria-selected={ui.workspace === w.id} onclick={(e) => pick(e, w.id)}>
				<Icon name={w.icon} class="h-3.5 w-3.5" />{workspaceLabel(w.id)}
			</button>
		{/each}
	</div>

	<div class="flex min-w-0 items-center justify-end gap-0.5">
		<Dropdown label={t('shell.project.import')} title={t('shell.project.importTip')} icon="upload" size="sm" align="right" items={importItems} />
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
				ariaPressed: ui.inspectorOpen && !player,
				disabled: player,
				tooltip: commandById('inspector')?.label,
				kbd: commandById('inspector')?.key,
				onclick: () => (ui.inspectorOpen = !ui.inspectorOpen)
			}}
		/>
	</div>
</header>

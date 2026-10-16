<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, addAssetToTimeline, secs } from '../../lib/state.svelte.js';
	import { openImport } from '../../lib/importer.js';
	import { roleColor, audioRoleLabel } from '../../lib/catalog.js';
	import PanelHeader from './PanelHeader.svelte';
	import Icon from '../Icon.svelte';

	const roles = ['Dialogue', 'Musique', 'Ambiance', 'SFX'];
	const sounds = $derived(doc.assets.filter((a) => a.kind === 'audio'));

	function soundMeta(s) {
		const params = { role: s.role ? audioRoleLabel(s.role) : t('project.origin.imported'), duration: s.srcDur === null ? '—' : secs(s.srcDur) };
		return s.generated ? t('panels.mixer.soundMetaPrepared', params) : t('panels.mixer.soundMeta', params);
	}
</script>

<PanelHeader icon="sliders" title={t('panels.mixer.title')}>
	<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => openImport('audio') }}>{t('panels.mixer.addSound')}</HostUi>
</PanelHeader>

<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-3">
	<button type="button" class="flex w-full items-center gap-3 rounded-lg border border-line-strong bg-surface-2 p-3 text-left hover:border-line-hover" onclick={() => (ui.modal = { type: 'sound' })}>
		<Icon name="wave" class="h-5 w-5 text-fg-muted" />
		<span class="flex-1">
			<span class="block text-sm font-medium">{t('panels.mixer.soundDesign')}</span>
			<span class="block text-xs text-fg-muted">{t('panels.mixer.soundDesignHint')}</span>
		</span>
		<Icon name="chevron-right" class="h-4 w-4 text-fg-muted" />
	</button>

	<div>
		<div class="vp-section-title mb-1.5">{t('panels.mixer.sounds')}</div>
		{#if !sounds.length}<p class="px-2 text-xs text-fg-subtle">{t('panels.mixer.noSounds')}</p>{/if}
		<ul class="space-y-1">
			{#each sounds as s (s.id)}
				<li class="group flex items-center gap-2 rounded px-2 py-1.5 hover:bg-surface-2" draggable="true" ondragstart={(e) => e.dataTransfer.setData('text/x-asset', s.id)}>
					<span class="h-2 w-2 shrink-0 rounded-sm" style:background="rgb(var(--{roleColor[s.role] ?? 'line-hover'}))"></span>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-sm">{s.name}</span>
						<span class="block text-xs text-fg-subtle group-hover:text-fg-muted">{soundMeta(s)}</span>
					</span>
					<HostUi
						name="IconButton"
						props={{
							icon: 'plus',
							label: t('panels.mixer.addAtPlayhead', { name: s.name }),
							size: 'xs',
							class: 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100',
							tooltip: t('panels.mixer.addAtPlayheadTip'),
							onclick: () => addAssetToTimeline(s.id)
						}}
					/>
				</li>
			{/each}
		</ul>
	</div>

	<div>
		<div class="vp-section-title mb-1.5">{t('panels.mixer.roles')}</div>
		<ul class="space-y-1 text-sm">
			{#each roles as r (r)}
				<li class="flex items-center gap-2 px-2">
					<span class="h-2 w-2 rounded-sm" style:background="rgb(var(--{roleColor[r]}))"></span>
					<span class="flex-1">{audioRoleLabel(r)}</span>
					<span class="text-xs text-fg-subtle">{t('panels.mixer.lanes', { count: doc.lanes.filter((l) => l.role === r).length })}</span>
				</li>
			{/each}
		</ul>
	</div>
</div>

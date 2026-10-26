<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { getLocale, t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, globalPrompt, itemsIn, productionRange, secs, select, openDirector } from '../../lib/state.svelte.js';
	import { promptLanguageOf } from '../../lib/starter.js';
	import { chainOn, ignoresFirstFrame, setChain } from '../../lib/chain.js';
	import { engineOptions, optionFor } from '../../lib/generation.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { allCommands } from '../../lib/commands.js';
	import { frameRoleLabel } from '../../lib/catalog.js';
	import { openReferences, refRoleLabel } from '../../lib/references.js';
	import Modal from './Modal.svelte';
	import OpenProject from './OpenProject.svelte';
	import VersionHistory from './VersionHistory.svelte';
	import PromptEditor from './PromptEditor.svelte';
	import ShotEditor from './ShotEditor.svelte';
	import EngineEditor from './EngineEditor.svelte';
	import PromptLibrary from './PromptLibrary.svelte';
	import SoundDesign from './SoundDesign.svelte';
	import ExportDialog from './ExportDialog.svelte';
	import MakeFinal from './MakeFinal.svelte';
	import FinalPass from './FinalPass.svelte';
	import { flyingTakes } from '../../lib/takes.svelte.js';
	import Icon from '../Icon.svelte';

	let { version = null, setLanguage = () => {} } = $props();

	const m = $derived(ui.modal);
	const projectEngine = $derived(optionFor(engineOptions(ui.me), doc.engine));
	const close = () => (ui.modal = null);

	const recap = $derived.by(() => {
		if (m?.type !== 'recap') return null;
		const range = productionRange();
		const it = itemsIn(range);
		return { range, it, local: it.prompts.map((p) => p.text) };
	});

	const shortcutList = $derived(allCommands.filter((c) => c.keys));
	const introParts = $derived(t('shell.simulations.intro').split('{badge}'));

	const tour = $derived([
		[t('shell.tour.project.title'), t('shell.tour.project.text'), () => (ui.modal = { type: 'project' })],
		[t('shell.tour.direction.title'), t('shell.tour.direction.text'), () => (openDirector('direction'), close())],
		[t('shell.tour.references.title'), t('shell.tour.references.text'), () => (openReferences(), close())],
		[t('shell.tour.shots.title'), t('shell.tour.shots.text'), () => ((ui.workspace = 'storyboard'), close())],
		[t('shell.tour.drafts.title'), t('shell.tour.drafts.text'), () => ((ui.production.quality = 'draft'), close())],
		[t('shell.tour.final.title'), t('shell.tour.final.text'), () => ((ui.inspectorTab = 'takes'), close())],
		[t('shell.tour.mix.title'), t('shell.tour.mix.text'), () => ((ui.workspace = 'mixer'), close())],
		[t('shell.tour.delivery.title'), t('shell.tour.delivery.text'), () => (ui.modal = { type: 'export' })]
	]);

	const simList = $derived([
		[t('shell.simulations.identity.title'), t('shell.simulations.identity.text')],
		[t('shell.simulations.lipSync.title'), t('shell.simulations.lipSync.text')],
		[t('shell.simulations.voice.title'), t('shell.simulations.voice.text')],
		[t('shell.simulations.console.title'), t('shell.simulations.console.text')],
		[t('shell.simulations.formats.title'), t('shell.simulations.formats.text')]
	]);

	const timelineIndex = $derived(
		[
			...doc.prompts.map((p) => ['prompt', p, p.start, t('shell.kind.prompt'), p.text]),
			...doc.frames.map((f) => ['frame', f, f.time, t('shell.kind.frame'), frameRoleLabel(f.role)]),
			...doc.markers.map((x) => ['marker', x, x.time, t('shell.kind.marker'), x.label])
		].sort((a, b) => a[2] - b[2])
	);

	const languages = $derived([
		{ id: 'en', label: t('shell.locale.en') },
		{ id: 'fr', label: t('shell.locale.fr') }
	]);

	const promptLanguage = $derived(promptLanguageOf(doc.promptLanguage));

	function setPromptLanguage(id) {
		if (id !== promptLanguage) act(() => (doc.promptLanguage = id));
	}
</script>

{#key m}
	{#if m?.type === 'prompt'}
		<PromptEditor id={m.id} isNew={m.isNew} />
	{:else if m?.type === 'shot'}
		<ShotEditor id={m.id} draft={m.draft ?? null} baseline={m.baseline ?? null} />
	{:else if m?.type === 'engine'}
		<EngineEditor preset={m.preset ?? null} />
	{:else if m?.type === 'library'}
		<PromptLibrary target={m.target} tab={m.tab} />
	{:else if m?.type === 'sound'}
		<SoundDesign type={m.kind ?? 'Ambiance'} />
	{:else if m?.type === 'export'}
		<ExportDialog tab={m.tab ?? 'video'} />
	{:else if m?.type === 'final'}
		<MakeFinal takeId={m.take} />
	{:else if m?.type === 'final-pass'}
		<FinalPass />
	{:else if m?.type === 'recap' && recap}
		<Modal title={t('shell.recap.title')} subtitle="{secs(recap.range[0])} → {secs(recap.range[1])}" icon="list" width={640}>
			<div class="space-y-3 p-4 text-sm">
				<section class="rounded-lg border border-line-strong p-3">
					<div class="mb-1 flex items-center gap-2">
						<span class="flex h-4 w-4 items-center justify-center rounded-sm bg-surface-3 text-2xs font-semibold">1</span>
						<span class="font-medium">{t('shell.recap.global')}</span>
						<span class="text-xs text-fg-subtle">{t('shell.recap.allVideos')}</span>
					</div>
					<p class="text-xs leading-5 text-fg-muted">{globalPrompt()}</p>
				</section>
				<section class="rounded-lg border border-line-strong p-3">
					<div class="mb-1 flex items-center gap-2">
						<span class="flex h-4 w-4 items-center justify-center rounded-sm bg-surface-3 text-2xs font-semibold">2</span>
						<span class="font-medium">{t('shell.recap.local')}</span>
					</div>
					{#each recap.local as line}<p class="text-xs text-fg-muted">{t('shell.recap.quote', { text: line })}</p>{:else}<p class="text-xs text-fg-subtle">{t('shell.recap.none')}</p>{/each}
				</section>
				<section class="rounded-lg border border-line-strong p-3">
					<div class="mb-1 flex items-center gap-2">
						<span class="flex h-4 w-4 items-center justify-center rounded-sm bg-surface-3 text-2xs font-semibold">3</span>
						<span class="font-medium">{t('shell.recap.refs')}</span>
					</div>
					<ul class="text-xs text-fg-muted">
						{#each recap.it.references as r}<li>{r.name} · {refRoleLabel(r.role)} · {r.scope.type === 'global' ? t('shell.recap.scopeGlobal') : t('shell.recap.scopeLocal')}</li>{/each}
						{#each recap.it.frames as f}<li>{t('shell.recap.frame', { role: frameRoleLabel(f.role), time: secs(f.time), strength: f.strength })}</li>{/each}
					</ul>
				</section>
			</div>
		</Modal>
	{:else if m?.type === 'simulations'}
		<Modal title={t('shell.simulations.title')} subtitle={t('shell.simulations.subtitle')} icon="flask" width={620}>
			<div class="space-y-3 p-4">
				<p class="text-sm text-fg-muted">{introParts[0]}<span class="vp-sim align-middle"><Icon name="flask" class="h-3 w-3" />{t('shell.window.simulated')}</span>{introParts[1] ?? ''}</p>
				<ul class="space-y-2">
					{#each simList as [title, text]}
						<li class="rounded-lg border border-line-strong p-2.5">
							<div class="text-sm font-medium">{title}</div>
							<div class="text-xs text-fg-muted">{text}</div>
						</li>
					{/each}
				</ul>
			</div>
		</Modal>
	{:else if m?.type === 'shortcuts'}
		<Modal title={t('shell.shortcuts.title')} icon="command" width={680}>
			<dl class="columns-2 gap-6 p-4">
				{#each shortcutList as c (c.id)}
					<div class="flex break-inside-avoid items-center justify-between gap-3 py-1 text-sm">
						<dt class="text-fg-muted">{c.label}</dt>
						<dd class="flex shrink-0 gap-1"><kbd class="vp-kbd text-xs">{c.key}</kbd>{#if c.alias}<kbd class="vp-kbd text-xs">{c.aliasKey}</kbd>{/if}</dd>
					</div>
				{/each}
			</dl>
		</Modal>
	{:else if m?.type === 'about'}
		<Modal title={t('shell.app.name')} subtitle={t('shell.about.subtitle', { version: version ?? '—' })} icon="film" width={440}>
			<div class="space-y-2 p-4 text-sm text-fg-muted">
				<p>{t('shell.about.body')}</p>
				<p class="text-xs text-fg-subtle">{t('shell.about.credits')}</p>
			</div>
		</Modal>
	{:else if m?.type === 'prefs'}
		<Modal title={t('shell.prefs.title')} icon="settings" width={520}>
			<div class="space-y-3 p-4">
				<div class="flex items-center justify-between text-sm">
					<span>{t('shell.prefs.language')}</span>
					<HostUi name="SegmentedControl" props={{ items: languages, selected: getLocale(), onSelect: setLanguage, ariaLabel: t('shell.prefs.language'), variant: 'toggle' }} />
				</div>
				<div class="flex items-center justify-between gap-3 text-sm">
					<span class="min-w-0"><span class="block">{t('project.promptLanguage.label')}</span><span class="block text-xs text-fg-subtle">{t('project.promptLanguage.hint')}</span></span>
					<HostUi name="SegmentedControl" props={{ items: languages, selected: promptLanguage, onSelect: setPromptLanguage, ariaLabel: t('project.promptLanguage.label'), variant: 'toggle' }} />
				</div>
				<label class="flex items-center justify-between text-sm">
					{t('shell.prefs.quality')}
					<select class="input vp-dense w-40" bind:value={ui.previewQuality}>
						<option value="performance">{t('shell.prefs.qualityOption.performance')}</option>
						<option value="balanced">{t('shell.prefs.qualityOption.balanced')}</option>
						<option value="best">{t('shell.prefs.qualityOption.best')}</option>
					</select>
				</label>
				<div class="flex items-center justify-between text-sm">
					<label for="vp-pref-snapping">{t('shell.prefs.snapping')}</label>
					<HostUi name="Switch" props={{ id: 'vp-pref-snapping', checked: ui.snapping, size: 'lg', label: t('shell.prefs.snapping'), onchange: (v) => (ui.snapping = v) }} />
				</div>
				<div class="flex items-center justify-between text-sm">
					<label for="vp-pref-guides">{t('shell.prefs.guides')}</label>
					<HostUi name="Switch" props={{ id: 'vp-pref-guides', checked: ui.guides, size: 'lg', label: t('shell.prefs.guides'), onchange: (v) => (ui.guides = v) }} />
				</div>
				<div class="flex items-center justify-between text-sm">
					<label for="vp-pref-single-key">{t('shell.prefs.singleKey')}</label>
					<HostUi name="Switch" props={{ id: 'vp-pref-single-key', checked: ui.singleKeyShortcuts, size: 'lg', label: t('shell.prefs.singleKey'), onchange: (v) => (ui.singleKeyShortcuts = v) }} />
				</div>
			</div>
		</Modal>
	{:else if m?.type === 'project'}
		<Modal title={t('shell.properties.title')} icon="film" width={480}>
			<div class="space-y-3 p-4">
				<label class="block space-y-1"><span class="vp-label">{t('shell.properties.name')}</span><input class="input vp-dense" bind:value={doc.name} /></label>
				<div class="grid grid-cols-3 gap-3">
					<label class="space-y-1"
						><span class="vp-label">{t('shell.properties.aspect')}</span><select class="input vp-dense" bind:value={doc.aspect}>{#each ['16:9', '2.39:1', '9:16', '1:1', '4:5'] as a}<option>{a}</option>{/each}</select></label
					>
					<label class="space-y-1"
						><span class="vp-label">{t('shell.properties.resolution')}</span><select class="input vp-dense" bind:value={doc.resolution}><option>720p</option><option>1080p</option><option>4K</option></select></label
					>
					<label class="space-y-1"
						><span class="vp-label">{t('shell.properties.fps')}</span><select class="input vp-dense" bind:value={doc.fps}
							>{#each [24, 25, 30] as fps}<option value={fps}>{t('shell.properties.fpsValue', { fps })}</option>{/each}</select
						></label
					>
				</div>
				<div class="space-y-1">
					<div class="flex items-center justify-between gap-3">
						<span class="vp-label">{t('project.promptLanguage.label')}</span>
						<HostUi name="SegmentedControl" props={{ items: languages, selected: promptLanguage, onSelect: setPromptLanguage, ariaLabel: t('project.promptLanguage.label'), variant: 'toggle' }} />
					</div>
					<p class="text-xs text-fg-subtle">{t('project.promptLanguage.help')}</p>
				</div>
				<div class="space-y-1">
					<div class="flex items-center justify-between gap-3">
						<label for="vp-project-chain" class="vp-label">{t('shell.properties.chain')}</label>
						<HostUi name="Switch" props={{ id: 'vp-project-chain', checked: chainOn(doc), size: 'lg', label: t('shell.properties.chain'), onchange: (v) => act(() => setChain(doc, v)) }} />
					</div>
					<p class="text-xs text-fg-subtle">{t('shell.properties.chainHelp')}</p>
					{#if chainOn(doc) && ignoresFirstFrame(projectEngine)}<p class="text-xs text-warning">{t('shell.properties.chainTextOnly', { engine: projectEngine.label })}</p>{/if}
				</div>
			</div>
		</Modal>
	{:else if m?.type === 'open'}
		<OpenProject />
	{:else if m?.type === 'versions'}
		<VersionHistory />
	{:else if m?.type === 'index'}
		<Modal title={t('shell.index.title')} icon="list" width={560}>
			<ul class="divide-y divide-line p-2 text-sm">
				{#each timelineIndex as [kind, item, time, kindName, label] (item.id)}
					<li>
						<button type="button" class="flex w-full items-center gap-3 px-2 py-1.5 text-left hover:bg-surface-2" onclick={() => (select(kind, item.id), seek(time), close())}>
							<span class="vp-tc w-14 text-xs text-fg-muted">{secs(time)}</span>
							<span class="w-24 text-xs text-fg-muted">{kindName}</span>
							<span class="flex-1 truncate">{label || '—'}</span>
						</button>
					</li>
				{/each}
			</ul>
		</Modal>
	{:else if m?.type === 'tasks'}
		<Modal title={t('shell.tasks.title')} icon="history" width={480}>
			<div class="space-y-2 p-4 text-sm">
				{#if ui.production.state === 'running'}
					<div class="rounded-lg border border-line-strong p-2.5">
						<div>{t('shell.tasks.generation', { step: ui.production.step || t('lib.status.queued') })}</div>
						<div class="mt-1 text-xs text-fg-subtle">{t('generation.tasks.takes', { count: flyingTakes().length })}</div>
						<div class="mt-1 h-1 rounded-full bg-surface-3" role="progressbar" aria-label={t('production.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={ui.production.running ? Math.round(ui.production.progress) : undefined}>
							<div class="h-full bg-signal" style:width="{ui.production.progress}%"></div>
						</div>
					</div>
				{:else}
					<p class="text-fg-muted">{t('shell.tasks.none')}</p>
				{/if}
			</div>
		</Modal>
	{:else if m?.type === 'tour'}
		<Modal title={t('shell.tour.title')} subtitle={t('shell.tour.subtitle')} icon="help" width={600}>
			<ol class="space-y-1 p-4">
				{#each tour as [title, text, go], i}
					<li>
						<button type="button" class="flex w-full items-start gap-3 rounded-lg p-2 text-left hover:bg-surface-2" onclick={go}>
							<span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line-hover text-xs">{i + 1}</span>
							<span class="flex-1"><span class="block text-sm font-medium">{title}</span><span class="block text-xs text-fg-muted">{text}</span></span>
							<Icon name="chevron-right" class="mt-1 h-4 w-4 text-fg-subtle" />
						</button>
					</li>
				{/each}
			</ol>
		</Modal>
	{/if}
{/key}

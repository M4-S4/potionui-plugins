<script>
	import { onMount, untrack } from 'svelte';
	import { fade } from 'svelte/transition';
	import HostUi from '../../../../sdk/HostUi.svelte';
	import { createClient } from './lib/api.js';
	import { download } from './lib/exchange.js';
	import { disposeExports, resumeExports } from './lib/exports.svelte.js';
	import { detectLocale, getLocale, requestCause, setLocale, t } from './i18n/index.svelte.js';
	import { ms } from './lib/motion.js';
	import { ui, doc, applyMe, bottomKey, bandView, closeDrawer, drawerMode, generates, sidebarShown, dispose as disposeState, toast } from './lib/state.svelte.js';
	import { project, bindClient, currentJson, disposeProject, flushSave, noteChange, openLatestOrStarter } from './lib/project.svelte.js';
	import { startProduction } from './lib/production.svelte.js';
	import { startLooks } from './lib/looks.svelte.js';
	import { setPluginRoot } from './lib/focus.js';
	import { needsProbe, probeAsset } from './lib/importer.js';
	import { dispose as disposePlayback } from './lib/playback.svelte.js';
	import { handleKeydown } from './lib/commands.js';
	import { isPlayer } from './lib/workspaces.js';
	import { keyboard, mountHostSlot, registerIcons } from './lib/host.js';
	import { viewport, watchViewport } from './lib/viewport.svelte.js';
	import { closesOnOutsidePointer, drawerFocus } from './lib/drawer.js';
	import { startAssistant } from './lib/assistant.svelte.js';
	import MenuBar from './components/shell/MenuBar.svelte';
	import ProjectBar from './components/shell/ProjectBar.svelte';
	import StatusBar from './components/shell/StatusBar.svelte';
	import Splitter from './components/shell/Splitter.svelte';
	import Toasts from './components/shell/Toasts.svelte';
	import Uploads from './components/shell/Uploads.svelte';
	import { hasFiles } from './lib/upload.js';
	import CommandPalette from './components/shell/CommandPalette.svelte';
	import Modals from './components/modals/Modals.svelte';
	import LeftPanel from './components/panels/LeftPanel.svelte';
	import Viewer from './components/viewer/Viewer.svelte';
	import StoryboardView from './components/storyboard/StoryboardView.svelte';
	import DirectorCenter from './components/director/DirectorCenter.svelte';
	import RightPanel from './components/panels/RightPanel.svelte';
	import ProductionBar from './components/production/ProductionBar.svelte';
	import Timeline from './components/timeline/Timeline.svelte';
	import Console from './components/mixer/Console.svelte';

	let { api, setHeaderHidden } = $props();

	let phase = $state('loading');
	let loadError = $state.raw(null);
	let root = $state();

	let alive = true;
	let loadSeq = 0;
	let saveSeq = 0;
	let localePicked = false;

	setLocale(detectLocale(null, navigator.language));

	const client = $derived(createClient(api, download));
	const locale = $derived(getLocale());
	const errorText = $derived(requestCause(loadError));
	const center = $derived(ui.workspace === 'storyboard' ? 'story' : ui.workspace === 'director' ? 'director' : 'viewer');
	const player = $derived(isPlayer(ui.workspace));
	const band = $derived(bandView());
	const bare = $derived(band || ui.workspace === 'director');
	const drawers = $derived(drawerMode());
	const leftOpen = $derived(drawers && sidebarShown());
	const rightOpen = $derived(drawers && ui.inspectorOpen);
	const columns = $derived(player || drawers ? 'minmax(0, 1fr)' : `${ui.sidebarOpen && !band ? '280px' : '0px'} minmax(0, 1fr) ${ui.inspectorOpen ? '320px' : '0px'}`);
	let inspectorBefore = null;
	let wideBefore = null;

	$effect(() => {
		const narrow = viewport.narrow;
		untrack(() => {
			if (narrow && wideBefore === null) {
				wideBefore = { sidebar: ui.sidebarOpen, inspector: ui.inspectorOpen };
				ui.sidebarOpen = false;
				ui.inspectorOpen = false;
			} else if (!narrow && wideBefore !== null) {
				ui.sidebarOpen = wideBefore.sidebar;
				ui.inspectorOpen = wideBefore.inspector;
				wideBefore = null;
			}
		});
	});

	$effect(() => {
		if (!leftOpen && !rightOpen) return;
		const onpointerdown = (e) => closesOnOutsidePointer(root, e.target) && closeDrawer();
		document.addEventListener('pointerdown', onpointerdown, true);
		return () => document.removeEventListener('pointerdown', onpointerdown, true);
	});

	$effect(() => {
		const inBand = band;
		untrack(() => {
			if (inBand && inspectorBefore === null) {
				inspectorBefore = ui.inspectorOpen;
				ui.inspectorOpen = false;
			} else if (!inBand && inspectorBefore !== null) {
				ui.inspectorOpen = inspectorBefore;
				inspectorBefore = null;
			}
		});
	});

	$effect(() => {
		ui.bottomView = ui.workspace === 'mixer' ? 'console' : 'timeline';
	});

	$effect(() => {
		bindClient(client);
	});

	$effect(() => {
		setPluginRoot(root);
	});

	$effect(() => {
		if (!project.fatal || phase !== 'ready') return;
		loadError = project.fatal;
		phase = 'error';
	});

	$effect(() => {
		if (phase !== 'ready') return;
		const json = currentJson();
		untrack(() => noteChange(json));
	});

	$effect(() => {
		if (phase !== 'ready') return;
		for (const a of doc.assets) if (needsProbe(a)) untrack(() => probeAsset(a.id));
	});

	function refuseStrayFiles(e) {
		if (e.defaultPrevented || !hasFiles(e.dataTransfer)) return;
		e.preventDefault();
		e.dataTransfer.dropEffect = 'none';
	}

	onMount(() => {
		setHeaderHidden?.(true);
		registerIcons();
		const release = keyboard.suppress();
		const onkeydown = (e) => phase === 'ready' && !viewport.tiny && handleKeydown(e, root);
		window.addEventListener('keydown', onkeydown);
		const stopAssistant = startAssistant();
		const onvisibility = () => document.visibilityState === 'hidden' && flushSave();
		document.addEventListener('visibilitychange', onvisibility);
		const stopProduction = startProduction();
		const stopLooks = startLooks();
		const stopViewport = watchViewport();
		load();
		return () => {
			alive = false;
			loadSeq += 1;
			saveSeq += 1;
			document.removeEventListener('visibilitychange', onvisibility);
			stopViewport();
			stopProduction();
			stopLooks();
			disposeExports();
			flushSave();
			disposeProject();
			window.removeEventListener('keydown', onkeydown);
			stopAssistant();
			release();
			disposePlayback();
			disposeState();
		};
	});

	async function load() {
		const seq = ++loadSeq;
		phase = 'loading';
		loadError = null;
		project.fatal = null;
		const result = await client.me();
		if (!alive || seq !== loadSeq) return;
		if (!result.ok) {
			loadError = result.error;
			phase = 'error';
			return;
		}
		applyMe(result.data);
		if (ui.me.locale && !localePicked) setLocale(ui.me.locale);
		bindClient(client);
		const opened = await openLatestOrStarter().catch(() => ({ ok: false, error: { status: 0, code: 'invalid_response', message: '', data: null } }));
		if (!alive || seq !== loadSeq) return;
		if (!opened.ok) {
			loadError = opened.error;
			phase = 'error';
			return;
		}
		phase = 'ready';
		resumeExports();
	}

	async function setLanguage(value) {
		localePicked = true;
		const next = setLocale(value);
		const seq = ++saveSeq;
		const result = await client.saveLocale(next);
		if (!alive || seq !== saveSeq) return;
		if (result.ok) {
			if (ui.me) ui.me.locale = next;
			return;
		}
		toast(t('shell.toast.localeNotSaved'), 'warning');
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div bind:this={root} tabindex="-1" class="vp-root bg-canvas font-sans text-base text-fg antialiased" lang={locale} ondragover={refuseStrayFiles} ondrop={refuseStrayFiles}>
	{#if viewport.tiny}
		<div class="vp-too-narrow" data-vp-too-narrow>
			<div class="w-full max-w-lg">
				<HostUi name="EmptyState" props={{ icon: 'warning', title: t('shell.app.narrow'), description: t('shell.app.narrowHint') }} />
			</div>
		</div>
	{/if}
	{#if phase === 'loading'}
		<div class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-6">
			<HostUi name="Spinner" props={{ size: 'lg' }} />
			<p class="text-sm text-fg-muted">{t('shell.app.loading')}</p>
		</div>
	{:else if phase === 'error'}
		<div class="flex min-h-0 flex-1 items-center justify-center p-6">
			<div class="w-full max-w-lg">
				<HostUi
					name="EmptyState"
					props={{
						icon: 'warning',
						tone: 'danger',
						title: t('shell.error.meLoad'),
						description: errorText,
						actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'sm', icon: 'refresh', onclick: load, children: t('shell.app.retry') }) }
					}}
				/>
			</div>
		</div>
	{:else}
		<div class="grid min-h-0 flex-1 overflow-hidden" style="grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto minmax(0, 1fr) auto auto auto" inert={viewport.tiny}>
			<MenuBar />
			<ProjectBar />

			<main class="grid min-h-0 overflow-hidden border-t border-line" class:vp-drawers={drawers} style:grid-template-columns={columns}>
				{#if !player}
					<div class="vp-drawer" data-vp-drawer="start" role={drawers ? 'dialog' : undefined} aria-modal={drawers ? 'true' : undefined} aria-label={drawers ? t('panels.left.label') : undefined} tabindex="-1" hidden={drawers && !leftOpen} use:drawerFocus={leftOpen}>
						<LeftPanel />
					</div>
				{/if}
				{#if leftOpen || rightOpen}<div class="vp-drawer-veil" aria-hidden="true"></div>{/if}
				{#key center}
					<div class="grid min-h-0 min-w-0" in:fade={{ duration: ms(160) }}>
						{#if center === 'story'}
							<StoryboardView />
						{:else if center === 'director'}
							<DirectorCenter />
						{:else}
							<Viewer {player} />
						{/if}
					</div>
				{/key}
				{#if !player}
					<div class="vp-drawer" data-vp-drawer="end" role={drawers ? 'dialog' : undefined} aria-modal={drawers ? 'true' : undefined} aria-label={drawers ? t('panels.right.label') : undefined} tabindex="-1" hidden={drawers && !rightOpen} use:drawerFocus={rightOpen}>
						<RightPanel />
					</div>
				{/if}
			</main>

			<div>
				{#if !bare}<Splitter />{/if}
				{#if generates()}<ProductionBar />{/if}
			</div>

			<section class="min-h-0 overflow-hidden" style:height={`${ui[bottomKey()]}px`} hidden={bare} aria-label={ui.bottomView === 'console' ? t('shell.layout.console') : t('shell.layout.timeline')}>
				{#if ui.bottomView === 'console'}
					<Console />
				{:else}
					<Timeline />
				{/if}
			</section>

			<StatusBar />
		</div>

		<Modals version={ui.me?.version ?? null} {setLanguage} />
		<CommandPalette />
		<Toasts />
		<Uploads />
	{/if}
</div>

<style>
	:global {
		.vp-root {
			position: relative;
			display: flex;
			flex-direction: column;
			height: 100%;
			min-height: 0;
			overflow: hidden;
		}
		.vp-root:focus {
			outline: none;
		}
		.vp-root button:not(:disabled) {
			cursor: pointer;
		}
		.vp-root :focus-visible,
		.vp-root [data-focus-ring]:focus {
			outline: 2px solid rgb(var(--signal));
			outline-offset: 2px;
		}
		.vp-root .input:focus-visible,
		.vp-root .vp-modal:focus-visible,
		.vp-root .vp-modal:focus {
			outline: none;
		}
		.vp-root :has(> [role='switch']:focus-visible),
		.vp-root :has(> [role='switch'][data-focus-ring]:focus) {
			border-radius: 9999px;
			outline: 2px solid rgb(var(--signal));
			outline-offset: 2px;
		}
		.vp-root input[type='number']::-webkit-inner-spin-button {
			opacity: 0.4;
		}
		.vp-root input[type='checkbox'],
		.vp-root input[type='radio'] {
			accent-color: rgb(var(--signal));
		}
		.vp-root
			:is(.bg-surface-2, .bg-surface-3, [class*='bg-surface-2/'], [class*='bg-surface-3/'], [class*='bg-signal/'], .vp-seg, .vp-seg-lg, .vp-pill, .vp-menu, .vp-palette, .vp-toast)
			.text-fg-subtle,
		.vp-root :is(.bg-surface-2, .bg-surface-3, [class*='bg-surface-2/'], [class*='bg-surface-3/'], [class*='bg-signal/']).text-fg-subtle {
			color: rgb(var(--fg-muted));
		}

		.vp-root .vp-h7 {
			min-width: 1.75rem;
			min-height: 1.75rem;
			padding: 0.375rem;
		}
		.vp-root .vp-toggle[aria-pressed='true'] {
			color: rgb(var(--fg));
			background-color: rgb(var(--surface-3));
			box-shadow: inset 0 0 0 1px rgb(var(--signal));
		}
		.vp-root .input.vp-dense {
			min-height: 1.75rem;
			height: 1.75rem;
			padding: 0 0.5rem;
			font-size: 12px;
			line-height: 16px;
		}
		.vp-root select.input.vp-dense {
			padding-right: 1.75rem;
			background-position: right 0.25rem center;
			background-size: 1.25em 1.25em;
		}
		.vp-root textarea.input.vp-dense {
			height: auto;
			padding: 0.375rem 0.5rem;
			line-height: 20px;
			resize: vertical;
		}
		.vp-root .vp-numfield {
			padding-right: 1.75rem;
			text-align: right;
			font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, 'Cascadia Mono', Menlo, Consolas, monospace;
			font-variant-numeric: tabular-nums;
		}

		.vp-root .vp-label {
			font-size: 11px;
			line-height: 16px;
			font-weight: 500;
			color: rgb(var(--fg-muted));
		}
		.vp-root .vp-section-title {
			font-size: 11px;
			line-height: 16px;
			font-weight: 600;
			text-transform: uppercase;
			letter-spacing: 0.025em;
			color: rgb(var(--fg-subtle));
		}
		.vp-root .vp-divider {
			margin: 0 0.25rem;
			height: 1.25rem;
			width: 1px;
			flex-shrink: 0;
			background-color: rgb(var(--line-strong));
		}
		.vp-root .vp-tc {
			font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, 'Cascadia Mono', Menlo, Consolas, monospace;
			font-variant-numeric: tabular-nums;
		}
		.vp-root .vp-kbd {
			border-radius: 2px;
			border: 1px solid rgb(var(--line-strong));
			background-color: rgb(var(--surface-2));
			padding: 0 0.25rem;
			font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, 'Cascadia Mono', Menlo, Consolas, monospace;
			font-size: 10px;
			line-height: 14px;
			color: rgb(var(--fg-muted));
		}
		.vp-root .vp-pill {
			display: inline-flex;
			height: 1.75rem;
			align-items: center;
			gap: 0.375rem;
			white-space: nowrap;
			border-radius: 9999px;
			border: 1px solid rgb(var(--line-strong));
			padding: 0 0.75rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
			transition: color 120ms, border-color 120ms, background-color 120ms;
		}
		.vp-root .vp-pill:hover:not(:disabled) {
			border-color: rgb(var(--line-hover));
			color: rgb(var(--fg));
		}
		.vp-root .vp-pill:is([aria-pressed='true'], [aria-selected='true']) {
			border-color: rgb(var(--signal));
			background-color: rgb(var(--surface-3));
			color: rgb(var(--fg));
		}
		.vp-root .vp-pill:disabled {
			color: rgb(var(--fg-disabled));
		}
		.vp-root .vp-popup {
			height: 1.75rem;
			cursor: pointer;
			appearance: none;
			border-radius: 4px;
			border: 1px solid rgb(var(--line-strong));
			background-color: rgb(var(--surface-2));
			background-image: linear-gradient(45deg, transparent 50%, rgb(var(--fg-muted)) 50%), linear-gradient(135deg, rgb(var(--fg-muted)) 50%, transparent 50%);
			background-position: calc(100% - 13px) 52%, calc(100% - 9px) 52%;
			background-size: 4px 4px;
			background-repeat: no-repeat;
			padding: 0 1.75rem 0 0.625rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg));
			transition: color 120ms, border-color 120ms, background-color 120ms;
		}
		.vp-root .vp-popup:hover:not(:disabled) {
			border-color: rgb(var(--line-hover));
			background-color: rgb(var(--surface-3));
		}
		.vp-root .vp-popup:disabled {
			color: rgb(var(--fg-disabled));
		}
		.vp-root .vp-seg {
			display: inline-flex;
			height: 1.75rem;
			align-items: center;
			border-radius: 4px;
			border: 1px solid rgb(var(--line));
			background-color: rgb(var(--surface-2));
			padding: 1px;
		}
		.vp-root .vp-seg button {
			height: 100%;
			white-space: nowrap;
			border-radius: 2px;
			padding: 0 0.5rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
			transition: color 120ms, background-color 120ms;
		}
		.vp-root .vp-seg button:hover {
			color: rgb(var(--fg));
		}
		.vp-root .vp-seg button:is([aria-pressed='true'], [aria-selected='true']) {
			background-color: rgb(var(--surface-3));
			color: rgb(var(--fg));
			box-shadow: var(--shadow-raised);
		}
		.vp-root .vp-seg .vp-icon-s svg {
			width: 0.75rem;
			height: 0.75rem;
		}
		.vp-root .vp-seg .vp-icon-l svg {
			width: 1rem;
			height: 1rem;
		}
		.vp-root .vp-seg-lg {
			display: inline-flex;
			height: 2rem;
			align-items: center;
			border-radius: 4px;
			border: 1px solid rgb(var(--line));
			background-color: rgb(var(--surface-2));
			padding: 2px;
		}
		.vp-root .vp-seg-lg button {
			display: flex;
			height: 1.625rem;
			align-items: center;
			gap: 0.375rem;
			white-space: nowrap;
			border-radius: 2px;
			padding: 0 0.75rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
			transition: color 120ms, background-color 120ms;
		}
		.vp-root .vp-seg-lg button:hover {
			color: rgb(var(--fg));
		}
		.vp-root .vp-seg-lg button:is([aria-pressed='true'], [aria-selected='true']) {
			background-color: rgb(var(--surface-3));
			color: rgb(var(--fg));
			box-shadow: var(--shadow-raised);
		}
		:where(.vp-root .vp-slider) {
			width: 100%;
		}
		.vp-root .vp-slider {
			height: 1.75rem;
			cursor: pointer;
			appearance: none;
			background: transparent;
		}
		.vp-root .vp-slider::-webkit-slider-runnable-track {
			height: 4px;
			border-radius: 9999px;
			background-color: rgb(var(--line-hover));
		}
		.vp-root .vp-slider::-webkit-slider-thumb {
			margin-top: -6px;
			height: 1rem;
			width: 1rem;
			appearance: none;
			border-radius: 9999px;
			border: 1px solid rgb(var(--line-hover));
			background-color: rgb(var(--fg));
			box-shadow: var(--shadow-floating);
		}
		.vp-root .vp-slider::-moz-range-track {
			height: 4px;
			border-radius: 9999px;
			background-color: rgb(var(--line-hover));
		}
		.vp-root .vp-slider::-moz-range-thumb {
			height: 1rem;
			width: 1rem;
			border-radius: 9999px;
			border: 1px solid rgb(var(--line-hover));
			background-color: rgb(var(--fg));
		}
		.vp-root .vp-hit:not(.absolute) {
			position: relative;
		}
		.vp-root .vp-hit,
		.vp-root .vp-touch-none {
			touch-action: none;
		}
		.vp-root .vp-hit::before {
			content: '';
			position: absolute;
			inset: -8px;
		}
		.vp-root .vp-hit.vp-edge-start::before {
			inset: 0 -16px 0 0;
		}
		.vp-root .vp-hit.vp-edge-end::before {
			inset: 0 0 0 -16px;
		}
		.vp-root .vp-link-hit {
			display: inline-block;
			min-width: 1.5rem;
			padding-block: 5px;
			margin-block: -5px;
		}
		.vp-root .vp-clip-head {
			color: rgb(var(--canvas));
		}
		:root[data-theme='light'] .vp-root .vp-clip-head {
			color: #fff;
			background-color: color-mix(in srgb, rgb(var(--viz-1)) 84%, #000);
		}

		.vp-root .vp-menubar {
			display: flex;
			height: 1.75rem;
			align-items: center;
			gap: 2px;
			background-color: rgb(var(--surface-1));
			padding: 0 0.5rem;
		}
		.vp-root .vp-menubar-item {
			height: 1.5rem;
			border-radius: 2px;
			padding: 0 0.5rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
			transition: color 120ms, background-color 120ms;
		}
		.vp-root .vp-menubar-app {
			font-weight: 600;
			color: rgb(var(--fg));
		}
		.vp-root .vp-menubar-item:hover {
			background-color: rgb(var(--surface-2));
			color: rgb(var(--fg));
		}
		.vp-root .vp-menubar-item[aria-expanded='true'] {
			background-color: rgb(var(--surface-3));
			color: rgb(var(--fg));
		}
		.vp-root .vp-menu {
			position: absolute;
			min-width: 16rem;
			border-radius: 10px;
			border: 1px solid rgb(var(--line-strong));
			background-color: rgb(var(--surface-3) / 0.95);
			padding: 0.25rem;
			box-shadow: var(--shadow-overlay);
			-webkit-backdrop-filter: blur(24px);
			backdrop-filter: blur(24px);
		}
		.vp-root .vp-menu :is([role='menuitem'], [role='menuitemradio'], [role='menuitemcheckbox']) {
			display: flex;
			height: 1.75rem;
			width: 100%;
			align-items: center;
			gap: 0.5rem;
			border-radius: 4px;
			padding: 0 0.5rem;
			text-align: left;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg));
		}
		.vp-root .vp-menu :is([role='menuitem'], [role='menuitemradio'], [role='menuitemcheckbox']):is(:hover, :focus-visible) {
			background-color: rgb(var(--signal) / 0.2);
		}
		.vp-root .vp-menu.vp-menu-list {
			width: max-content;
			max-width: calc(100vw - 1rem);
		}
		.vp-root .vp-menu-label {
			white-space: nowrap;
		}
		.vp-root .vp-menu-sep {
			margin: 0.25rem 0.5rem;
			height: 1px;
			background-color: rgb(var(--line-hover) / 0.6);
		}
		.vp-root .vp-menu-key {
			white-space: nowrap;
			font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, 'Cascadia Mono', Menlo, Consolas, monospace;
			font-size: 11px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
		}

		.vp-root .vp-palette-backdrop {
			position: fixed;
			inset: 0;
			display: flex;
			justify-content: center;
			padding-top: 6rem;
			background-color: rgb(0 0 0 / 0.4);
			-webkit-backdrop-filter: blur(2px);
			backdrop-filter: blur(2px);
		}
		.vp-root .vp-palette {
			height: fit-content;
			width: 560px;
			max-width: calc(100vw - 2rem);
			overflow: hidden;
			border-radius: 10px;
			border: 1px solid rgb(var(--line-strong));
			background-color: rgb(var(--surface-3) / 0.95);
			box-shadow: var(--shadow-overlay);
			-webkit-backdrop-filter: blur(24px);
			backdrop-filter: blur(24px);
		}
		.vp-root .vp-palette-search {
			display: flex;
			align-items: center;
			gap: 0.5rem;
			border-bottom: 1px solid rgb(var(--line-hover) / 0.6);
			padding: 0 0.75rem;
		}
		.vp-root .vp-palette-search input {
			height: 2.75rem;
			flex: 1;
			background: transparent;
			font-size: 14px;
			line-height: 20px;
			color: rgb(var(--fg));
		}
		.vp-root .vp-palette-search input:is(:focus, :focus-visible) {
			outline: none;
		}
		.vp-root .vp-palette-search input::placeholder {
			color: rgb(var(--fg-muted));
		}
		.vp-root .vp-palette-item {
			display: flex;
			height: 2rem;
			width: 100%;
			align-items: center;
			gap: 0.5rem;
			border-radius: 4px;
			padding: 0 0.5rem;
			text-align: left;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg));
		}
		.vp-root .vp-palette-item:hover {
			background-color: rgb(var(--surface-2));
		}
		.vp-root .vp-palette-item[data-active='true'] {
			background-color: rgb(var(--signal) / 0.2);
		}

		.vp-root .vp-splitter {
			position: relative;
			height: 6px;
			cursor: row-resize;
			border-top: 1px solid rgb(var(--line));
			background-color: rgb(var(--surface-1));
		}
		.vp-root .vp-splitter::before {
			content: '';
			position: absolute;
			inset: -1px 0 -18px;
		}
		:where(.vp-root .vp-splitter + *) :where(button, select, input, a[href], [role='button'], [tabindex='0']) {
			z-index: 1;
		}
		.vp-root .vp-splitter:hover {
			background-color: rgb(var(--signal) / 0.3);
		}
		.vp-root .vp-splitter-grip {
			position: absolute;
			left: 50%;
			top: 2px;
			height: 2px;
			width: 2rem;
			transform: translateX(-50%);
			border-radius: 9999px;
			background-color: rgb(var(--line-hover));
		}
		.vp-root .vp-splitter:hover .vp-splitter-grip {
			background-color: rgb(var(--signal));
		}

		.vp-root .vp-tabs {
			display: flex;
			height: 2.5rem;
			flex-shrink: 0;
			align-items: center;
			gap: 1rem;
			border-bottom: 1px solid rgb(var(--line));
			padding: 0 0.75rem;
		}
		.vp-root .vp-tabs.vp-tabs-head {
			height: 100%;
			min-width: 0;
			border-bottom: 0;
			padding: 0;
		}
		.vp-root .vp-tabs > [role='tab'] {
			position: relative;
			display: flex;
			align-self: stretch;
			min-width: 1.5rem;
			align-items: center;
			justify-content: center;
			gap: 0.375rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
			transition: color 120ms;
		}
		.vp-root .vp-tabs > [role='tab']:is(:hover, [aria-selected='true']) {
			color: rgb(var(--fg));
		}
		.vp-root .vp-tabs > [role='tab'][aria-selected='true']::after {
			content: '';
			position: absolute;
			left: 0;
			right: 0;
			bottom: -1px;
			height: 2px;
			border-radius: 9999px;
			background-color: rgb(var(--signal));
		}
		.vp-root .vp-tabs-badge {
			border-radius: 2px;
			background-color: rgb(var(--surface-3));
			padding: 0 0.25rem;
			font-size: 11px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
		}

		.vp-root .vp-toasts {
			pointer-events: none;
			position: fixed;
			bottom: 2.5rem;
			left: 50%;
			display: flex;
			transform: translateX(-50%);
			flex-direction: column;
			align-items: center;
			gap: 0.5rem;
		}
		.vp-root .vp-toast {
			pointer-events: auto;
			display: flex;
			align-items: center;
			gap: 0.5rem;
			border-radius: 10px;
			border: 1px solid rgb(var(--line-strong));
			background-color: rgb(var(--surface-3) / 0.95);
			padding: 0.5rem 0.5rem 0.5rem 0.75rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg));
			box-shadow: var(--shadow-overlay);
			-webkit-backdrop-filter: blur(24px);
			backdrop-filter: blur(24px);
		}
		.vp-root .vp-dropzone {
			pointer-events: none;
			position: absolute;
			inset: 0.375rem;
			z-index: 30;
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			gap: 0.5rem;
			border-radius: 8px;
			border: 2px dashed rgb(var(--signal));
			background-color: rgb(var(--surface-1) / 0.94);
			padding: 1rem;
			text-align: center;
			font-size: 13px;
			line-height: 18px;
			color: rgb(var(--fg));
		}
		.vp-root .vp-dropzone-refused {
			border-color: rgb(var(--danger));
			color: rgb(var(--danger));
		}
		.vp-root .vp-uploads {
			position: fixed;
			right: 1rem;
			bottom: 2.5rem;
			width: 20rem;
			max-width: calc(100vw - 2rem);
			overflow: hidden;
			border-radius: 10px;
			border: 1px solid rgb(var(--line-strong));
			background-color: rgb(var(--surface-3) / 0.95);
			color: rgb(var(--fg));
			box-shadow: var(--shadow-overlay);
			-webkit-backdrop-filter: blur(24px);
			backdrop-filter: blur(24px);
		}
		.vp-root .vp-upload-x {
			display: flex;
			height: 1.5rem;
			width: 1.5rem;
			flex-shrink: 0;
			align-items: center;
			justify-content: center;
			border-radius: 4px;
			color: rgb(var(--fg-muted));
		}
		.vp-root .vp-upload-x:hover {
			background-color: rgb(var(--surface-2));
			color: rgb(var(--fg));
		}
		.vp-root .vp-modal-backdrop {
			position: fixed;
			inset: 0;
			display: flex;
			align-items: center;
			justify-content: center;
			padding: 1.5rem;
			background-color: rgb(0 0 0 / 0.5);
			-webkit-backdrop-filter: blur(2px);
			backdrop-filter: blur(2px);
		}
		.vp-root .vp-modal {
			display: flex;
			max-height: 100%;
			max-width: 100%;
			flex-direction: column;
			overflow: hidden;
			border-radius: 10px;
			border: 1px solid rgb(var(--line-strong));
			background-color: rgb(var(--surface-1));
			box-shadow: var(--shadow-overlay);
		}
		.vp-root .vp-modal-head {
			display: flex;
			flex-shrink: 0;
			align-items: flex-start;
			gap: 0.625rem;
			border-bottom: 1px solid rgb(var(--line));
			padding: 0.75rem 1rem;
		}
		.vp-root .vp-pickrow {
			display: flex;
			min-height: 3rem;
			align-items: center;
			gap: 0.75rem;
			border-radius: 8px;
			border: 1px solid rgb(var(--line-strong));
			padding: 0 0.5rem 0 0.75rem;
			transition: border-color 120ms, background-color 120ms;
		}
		.vp-root .vp-pickrow:hover {
			border-color: rgb(var(--line-hover));
		}
		.vp-root .vp-pickrow:has(input:checked) {
			border-color: rgb(var(--signal));
			box-shadow: inset 0 0 0 1px rgb(var(--signal));
		}
		.vp-root .vp-pickrow:has(input:focus-visible),
		.vp-root .vp-pickrow:has(input[data-focus-ring]:focus) {
			outline: 2px solid rgb(var(--signal));
			outline-offset: 2px;
		}
		.vp-root .vp-modal-foot {
			display: flex;
			flex-shrink: 0;
			align-items: center;
			justify-content: flex-end;
			gap: 0.5rem;
			border-top: 1px solid rgb(var(--line));
			padding: 0.75rem 1rem;
		}

		.vp-root .vp-panel-head {
			display: flex;
			height: 2.5rem;
			flex-shrink: 0;
			align-items: center;
			gap: 0.5rem;
			padding: 0 0.75rem;
		}
		.vp-root .vp-zone-head {
			display: flex;
			height: 2.5rem;
			flex-shrink: 0;
			align-items: center;
			gap: 0.75rem;
			border-bottom: 1px solid rgb(var(--line));
			padding: 0 1rem;
		}

		.vp-root .vp-projectbar {
			display: grid;
			height: 3rem;
			grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
			align-items: center;
			gap: 1rem;
			background-color: rgb(var(--surface-1));
			padding: 0 0.75rem;
		}
		.vp-root .vp-projectbar-name {
			margin: 0 -0.25rem;
			height: 1.5rem;
			width: 14rem;
			max-width: 100%;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
			border-radius: 4px;
			border: 1px solid transparent;
			background: transparent;
			padding: 0 0.25rem;
			font-size: 14px;
			line-height: 20px;
			font-weight: 600;
			color: rgb(var(--fg));
		}
		.vp-root .vp-projectbar-name:hover {
			border-color: rgb(var(--line-strong));
		}
		.vp-root .vp-projectbar-name:is(:focus, :focus-visible) {
			border-color: rgb(var(--signal));
			outline: none;
		}
		.vp-root .vp-assistant {
			position: relative;
			display: inline-flex;
			height: 1.75rem;
			align-items: center;
			gap: 0.375rem;
			border-radius: 4px;
			padding: 0 0.625rem;
			font-size: 12px;
			line-height: 16px;
			color: rgb(var(--fg-muted));
			transition: color 120ms, background-color 120ms;
		}
		.vp-root .vp-assistant:hover {
			background-color: rgb(var(--surface-2));
			color: rgb(var(--fg));
		}
		.vp-root .vp-assistant-ring {
			pointer-events: none;
			position: absolute;
			inset: 0;
			border-radius: 4px;
			padding: 1px;
			background: linear-gradient(135deg, rgb(var(--ai-1)), rgb(var(--ai-2)), rgb(var(--ai-3)));
			opacity: 0;
			transition: opacity 120ms;
			-webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
			-webkit-mask-composite: xor;
			mask: linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0);
		}
		.vp-root .vp-assistant:hover .vp-assistant-ring {
			opacity: 0.7;
		}

		.vp-root .vp-cost {
			display: none;
		}
		@media (min-width: 1280px) {
			.vp-root .vp-cost {
				display: inline;
			}
		}
		.vp-root .vp-too-narrow {
			position: absolute;
			inset: 0;
			z-index: 40;
			display: flex;
			align-items: center;
			justify-content: center;
			padding: 1.5rem;
			background-color: rgb(var(--canvas));
		}
		.vp-root .vp-drawer {
			display: contents;
		}
		.vp-root .vp-drawers {
			position: relative;
		}
		.vp-root .vp-drawers > .vp-drawer {
			position: absolute;
			top: 0;
			bottom: 0;
			z-index: 20;
			display: grid;
			width: 280px;
			max-width: 100%;
			box-shadow: var(--shadow-overlay);
			outline: none;
		}
		.vp-root .vp-drawers > .vp-drawer[hidden] {
			display: none;
		}
		.vp-root .vp-drawers > .vp-drawer[data-vp-drawer='start'] {
			left: 0;
		}
		.vp-root .vp-drawers > .vp-drawer[data-vp-drawer='end'] {
			right: 0;
			width: 320px;
		}
		.vp-root .vp-drawers > .vp-drawer > aside {
			min-height: 0;
		}
		.vp-root .vp-drawer-veil {
			position: absolute;
			inset: 0;
			z-index: 19;
			background-color: rgb(0 0 0 / 0.25);
		}
		.vp-root [data-take-details] > summary {
			display: inline-block;
			min-height: 1.25rem;
			margin-inline: -0.125rem;
			padding-inline: 0.125rem;
			border-radius: 4px;
			cursor: pointer;
		}
		.vp-root [data-take-details] > summary:hover {
			color: rgb(var(--fg));
		}
		.vp-root .vp-production-wrap {
			height: auto;
			min-height: 2.75rem;
			flex-wrap: wrap;
			row-gap: 0.375rem;
			padding-block: 0.375rem;
		}
		.vp-root .vp-production-wrap > [data-vp-engine] {
			order: 1;
			flex-basis: 100%;
		}
		.vp-root .vp-production-wrap > [data-vp-actions] {
			margin-left: auto;
		}
		@media (max-width: 1279px) {
			.vp-root .vp-wide-only {
				position: absolute;
				width: 1px;
				height: 1px;
				margin: -1px;
				padding: 0;
				overflow: hidden;
				clip-path: inset(50%);
				white-space: nowrap;
				border: 0;
			}
			.vp-root .vp-projectbar-name {
				width: 10rem;
			}
		}
		@media (max-width: 899px) {
			.vp-root .vp-workspace-label {
				display: none;
			}
		}
		.vp-root .vp-pills[data-shade='end'] {
			-webkit-mask-image: linear-gradient(to right, #000 calc(100% - 2.5rem), transparent);
			mask-image: linear-gradient(to right, #000 calc(100% - 2.5rem), transparent);
		}
		.vp-root .vp-pills[data-shade='start'] {
			-webkit-mask-image: linear-gradient(to right, transparent, #000 2.5rem);
			mask-image: linear-gradient(to right, transparent, #000 2.5rem);
		}
		.vp-root .vp-pills[data-shade='both'] {
			-webkit-mask-image: linear-gradient(to right, transparent, #000 2.5rem, #000 calc(100% - 2.5rem), transparent);
			mask-image: linear-gradient(to right, transparent, #000 2.5rem, #000 calc(100% - 2.5rem), transparent);
		}
		.vp-root .vp-notice {
			display: flex;
			height: 1rem;
			min-width: 0;
			max-width: 320px;
			align-items: center;
			justify-content: flex-end;
			gap: 0.375rem;
			overflow: hidden;
		}
		.vp-root .vp-notice-text {
			min-width: 0;
			flex: 0 1 auto;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
			line-height: 1rem;
		}

		.vp-root .vp-statusbar {
			display: flex;
			height: 1.5rem;
			align-items: center;
			gap: 1rem;
			overflow: hidden;
			white-space: nowrap;
			border-top: 1px solid rgb(var(--line));
			background-color: rgb(var(--surface-1));
			padding: 0 0.75rem;
			font-size: 11px;
			line-height: 16px;
			color: rgb(var(--fg-subtle));
		}
		.vp-root .vp-statusbar-locale {
			display: flex;
			height: 1.5rem;
			min-width: 1.5rem;
			align-items: center;
			justify-content: center;
			border-radius: 2px;
			padding: 0 0.375rem;
			font-weight: 500;
			color: rgb(var(--fg-muted));
		}
		.vp-root .vp-statusbar-locale:hover {
			background-color: rgb(var(--surface-2));
			color: rgb(var(--fg));
		}
	}
</style>

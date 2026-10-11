<script>
	// A model's detail, in a drawer over the results (the page route stays; Escape, the close
	// button or a click beside the drawer closes it). Built from the host's detail components:
	// DetailHeader (name, chips, source link and close button), DetailTabs for the versions (a
	// select past 8), DetailBody, and DetailLayout with the main column (DetailMain) and the side
	// column (DetailAside). `GET /{source}/models/{id}` answers 404 for a model the user may not
	// see; `POST /installed` marks the files already installed.
	//
	// Some sources send one version in full and the others as shells (`partial: true`, CivArchive):
	// a shell is fetched when it comes on screen, `GET /{source}/models/<model id>:<version id>`,
	// and replaces itself in the detail (lib/versions.js). Nothing is kept once the drawer closes.
	import { onMount, untrack } from 'svelte';
	import HostUi from '../../../../../sdk/HostUi.svelte';
	import Icon from './Icon.svelte';
	import DetailAside from './DetailAside.svelte';
	import DetailMain from './DetailMain.svelte';
	import { getInstalled, getModel } from '../lib/client.js';
	import { escapeCloses, hostLayer, onEscape, portal, slotOf, trapFocus } from '../lib/dom.js';
	import { modelTypeLabel } from '../lib/format.js';
	import { hasPartialVersions, isPartial, mergeVersion, versionRef } from '../lib/versions.js';

	let {
		api,
		me,
		source,
		sourceLabel = '',
		baseModelLabel = '',
		modelId,
		item = null,
		revealCache,
		reloadToken = 0,
		installedToken = 0,
		onClose,
		onDownload,
		onRequest
	} = $props();

	const uid = $props.id();
	const MAX_TABS = 8;
	const SHA256 = /^[0-9a-f]{64}$/;

	let phase = $state('loading');
	let detail = $state.raw(null);
	let error = $state.raw(null);
	let versionId = $state('');
	let installed = $state.raw(new Map());
	let preview = $state.raw(null);
	let actionsEl = $state();
	let mainEl = $state();
	let asideEl = $state();
	let seq = 0;
	// Versions the source sent as shells: the ids being fetched, and the errors by id (a failed
	// version is fetched again by its Retry button only). `byVersion`: some version of this detail
	// was a shell, so the NSFW previews of every version are revealed through its own
	// `<model id>:<version id>` (the server holds the images of the version it was asked for).
	let loadingIds = new Set();
	let failedIds = $state.raw(new Map());
	let byVersion = $state(false);
	// The drawer is moved under <body> (use:portal). Svelte removes a block by walking from its
	// first node to its last, so a moved node must be the only node of its block: hence its own
	// `{#if mounted}`.
	let mounted = $state(false);
	onMount(() => {
		mounted = true;
	});

	// Built once: DetailLayout then keeps its two slots for good.
	const layoutProps = { main: slotOf(() => mainEl), aside: slotOf(() => asideEl) };

	const versions = $derived(detail?.versions ?? []);
	const version = $derived(versions.find((entry) => entry.id === versionId) ?? versions[0] ?? null);
	const name = $derived(detail?.name ?? item?.name ?? 'Model');
	const creator = $derived(detail?.creator ?? item?.creator ?? '');
	const sourceUrl = $derived(detail?.source_url ?? item?.source_url ?? '');
	const sourceHost = $derived(hostOf(sourceUrl));
	const subtitle = $derived([creator ? `by ${creator}` : '', sourceLabel].filter(Boolean).join(' · '));
	const tabs = $derived(versions.map((entry) => ({ id: entry.id, label: entry.name || entry.id })));
	const headerProps = $derived({
		title: name,
		icon: iconFor(detail ? detail.mb_type : item?.mb_type),
		chipItems: chipsFor(detail ?? item, version),
		subtitle: subtitle ? { slot: subtitle } : undefined,
		actions: slotOf(() => actionsEl)
	});
	const errorTitle = $derived(
		error?.status === 404 ? 'Model not found' : error?.status === 429 ? 'Rate limited' : "Couldn't load the model"
	);
	const errorMessage = $derived(
		error?.status === 404 && error?.code === 'not_found'
			? 'It does not exist on the source any more, or your content settings hide it.'
			: (error?.message ?? 'Something went wrong')
	);
	const redLink = $derived(sourceHost === 'civitai.red');
	const versionError = $derived(version ? (failedIds.get(version.id) ?? null) : null);

	$effect(() => {
		// Reload when the model changes, or when the page asks (the NSFW mode changed).
		void source;
		void modelId;
		void reloadToken;
		untrack(load);
	});

	$effect(() => {
		// A download answered "already installed": the badges may have changed.
		void installedToken;
		untrack(() => {
			if (detail) loadInstalled(seq, detail);
		});
	});

	// A shell version that comes on screen (picked in the tabs, or kept across a reload) is fetched.
	$effect(() => {
		const current = version;
		if (phase !== 'ready' || !isPartial(current)) return;
		const id = current.id;
		untrack(() => loadVersion(id));
	});

	// The image preview closes before the drawer on Escape.
	$effect(() => {
		if (!preview) return;
		return onEscape(() => (preview = null));
	});

	function hostOf(url) {
		try {
			return new URL(url).hostname;
		} catch {
			return '';
		}
	}

	function iconFor(type) {
		if (type === 'lora') return 'lora';
		if (type === 'embedding') return 'embedding';
		return 'model';
	}

	function chipsFor(model, current) {
		if (!model) return [];
		const chips = [];
		const type = model.mb_type ? modelTypeLabel(model.mb_type) : model.type;
		if (type) chips.push({ key: 'type', label: type, tone: 'neutral' });
		if (model.nsfw) chips.push({ key: 'nsfw', label: 'NSFW', tone: 'danger' });
		if (current?.early_access || (!current && model.early_access)) chips.push({ key: 'early', label: 'Early access', tone: 'warning' });
		if (model.gated) chips.push({ key: 'gated', label: 'Needs login', tone: 'warning' });
		if (model.poi) chips.push({ key: 'poi', label: 'Real person', tone: 'warning' });
		return chips;
	}

	async function load() {
		const mine = ++seq;
		phase = 'loading';
		error = null;
		loadingIds = new Set();
		failedIds = new Map();
		const result = await getModel(api, source, modelId);
		if (mine !== seq) return;
		if (!result.ok || !result.data || typeof result.data !== 'object') {
			error = result.ok ? { status: 0, code: 'invalid_response', message: 'Unexpected answer from the server' } : result.error;
			phase = 'error';
			return;
		}
		const data = { ...result.data, versions: Array.isArray(result.data.versions) ? result.data.versions : [] };
		detail = data;
		byVersion = hasPartialVersions(data);
		if (!data.versions.some((entry) => entry.id === versionId)) versionId = data.versions[0]?.id ?? '';
		phase = 'ready';
		loadInstalled(mine, data);
	}

	async function loadInstalled(mine, data) {
		const hashes = [
			...new Set(
				data.versions
					.flatMap((entry) => entry.files ?? [])
					.map((file) => (typeof file.sha256 === 'string' ? file.sha256.toLowerCase() : ''))
					.filter((sha) => SHA256.test(sha))
			)
		].slice(0, 200);
		if (hashes.length === 0) return;
		const result = await getInstalled(api, hashes);
		if (mine !== seq || !result.ok) return;
		installed = new Map(Object.entries(result.data?.installed ?? {}));
	}

	/**
	 * A shell version in full: `GET /{source}/models/<model id>:<version id>`, whose answer replaces
	 * the shell in the detail as it is when the answer comes (the other versions and the selection
	 * stay). A failure is kept for the version, shown in its panel with a Retry button: it is not
	 * fetched again unless `retry`. An answer of a detail that was reloaded meanwhile is dropped.
	 */
	async function loadVersion(id, { retry = false } = {}) {
		if (!detail || loadingIds.has(id)) return;
		if (failedIds.has(id)) {
			if (!retry) return;
			failedIds = new Map([...failedIds].filter(([key]) => key !== id));
		}
		const mine = seq;
		loadingIds.add(id);
		const result = await getModel(api, source, versionRef(detail.id, id));
		if (mine !== seq) return;
		loadingIds.delete(id);
		const merged = result.ok ? mergeVersion(detail, id, result.data) : result;
		if (!merged.ok) {
			failedIds = new Map(failedIds).set(id, merged.error);
			return;
		}
		detail = merged.detail;
		loadInstalled(mine, merged.detail);
	}

	function onBackdrop(event) {
		if (event.target === event.currentTarget) onClose?.();
	}
</script>

{#if mounted}
<div
	use:portal
	use:hostLayer
	use:escapeCloses={() => onClose?.()}
	class="fixed inset-0 flex justify-end bg-black/60 backdrop-blur-sm"
	role="presentation"
	onclick={onBackdrop}
>
	<div
		class="flex h-full w-full flex-col bg-surface-1 shadow-overlay outline-none md:w-[min(60rem,94vw)]"
		role="dialog"
		aria-modal="true"
		aria-label={name}
		tabindex="-1"
		use:trapFocus
		onkeydown={(event) => event.stopPropagation()}
	>
		<HostUi name="DetailHeader" props={headerProps} />

		{#if phase === 'ready' && tabs.length > 1 && tabs.length <= MAX_TABS}
			<HostUi name="DetailTabs" props={{ tabs, active: version?.id ?? '', onSelect: (id) => (versionId = id), ariaLabel: 'Versions' }} />
		{:else if phase === 'ready' && tabs.length > MAX_TABS}
			<div class="flex flex-shrink-0 items-center gap-2 border-b border-line bg-surface-1 px-4 py-1.5 sm:px-5">
				<label class="text-xs font-medium text-fg-muted" for="{uid}-version">Version</label>
				<select id="{uid}-version" class="input h-7 w-auto max-w-full py-0 text-xs" bind:value={versionId}>
					{#each tabs as tab (tab.id)}
						<option value={tab.id}>{tab.label}</option>
					{/each}
				</select>
				<span class="font-mono text-2xs text-fg-subtle">{tabs.length} versions</span>
			</div>
		{/if}

		<HostUi name="DetailBody">
			{#if phase === 'loading'}
				<div class="flex items-center justify-center py-16">
					<HostUi name="Spinner" props={{ size: 'lg' }} />
				</div>
			{:else if phase === 'error'}
				<HostUi name="LoadErrorState" props={{ title: errorTitle, message: errorMessage, onRetry: load }} />
			{:else}
				<HostUi name="DetailLayout" props={layoutProps} />
			{/if}
		</HostUi>

		<!-- What the host components show in their slots (moved there once they mount). -->
		<div hidden>
			<div bind:this={actionsEl} class="flex items-center gap-2">
				{#if sourceUrl}
					<!-- Short on a phone ("civitai.red"), whole from `sm` up; the full text is the link's name. -->
					<a
						class="inline-flex items-center gap-1.5 whitespace-nowrap rounded bg-surface-3 px-2.5 py-1 text-xs font-medium text-fg transition-colors duration-100 hover:bg-line-hover"
						href={sourceUrl}
						target="_blank"
						rel="noopener noreferrer"
						aria-label={redLink
							? 'Open on civitai.red, the CivitAI site that shows NSFW models (new tab)'
							: `Open on ${sourceHost || 'the source'} (new tab)`}
						title={redLink ? 'civitai.red: the CivitAI site that shows NSFW models' : `Open this model on ${sourceHost}`}
					>
						<span class="hidden sm:inline">Open on</span>
						{sourceHost || 'the source'}
						{#if redLink}<span class="hidden sm:inline">(NSFW site)</span>{/if}
						<Icon name="external-link" class="h-3.5 w-3.5" />
					</a>
				{/if}
				<button
					type="button"
					class="inline-flex min-h-8 min-w-8 items-center justify-center rounded p-1.5 text-fg-muted transition-colors duration-100 hover:bg-surface-3/50 hover:text-fg"
					aria-label="Close the details"
					title="Close (Esc)"
					data-autofocus
					onclick={() => onClose?.()}
				>
					<Icon name="close" class="h-4 w-4" />
				</button>
			</div>
			<div bind:this={mainEl} class="flex flex-col gap-4">
				{#if detail}
					<DetailMain
						{detail}
						{version}
						{me}
						{installed}
						{sourceLabel}
						{revealCache}
						{byVersion}
						{versionError}
						onRetryVersion={() => version && loadVersion(version.id, { retry: true })}
						{onDownload}
						{onRequest}
						onPreview={(media) => (preview = media)}
					/>
				{/if}
			</div>
			<div bind:this={asideEl} class="flex flex-col gap-4">
				{#if detail}
					<DetailAside {detail} {version} {sourceUrl} {sourceHost} {baseModelLabel} />
				{/if}
			</div>
		</div>
	</div>
</div>
{/if}

{#if preview}
	<HostUi
		name="MediaPreviewModal"
		props={{ isOpen: true, onClose: () => (preview = null), kind: preview.kind, url: preview.url, label: preview.alt }}
	/>
{/if}

<script>
	// The Model Browser page (PLAN.md section 9, phase 4), mounted by the host at
	// /plugins/model-browser with `{ api, setHeaderHidden, ... }` (see index.js).
	//
	// - `GET /me` first: without `browse`, an EmptyState and nothing else; the capabilities decide
	//   which buttons exist (lib/capabilities.js), the NSFW part feeds the mode control.
	// - `GET /sources`: one rail section of the host's LibraryPage per enabled source.
	// - The search state (source, text, types, base model, sort, period, open model) lives in the
	//   URL query string (`history.replaceState`), so a reload restores it (lib/search.js).
	// - Results page by cursor (infinite scroll in ResultGrid); `POST /installed` fills the
	//   "Installed" badges when the server sends `primary_sha256` without `installed`.
	// - A card opens DetailPanel over the results; a file opens DownloadDialog; DownloadTray
	//   follows the downloads.
	import { onMount } from 'svelte';
	// Host wrapper from the PotionUI plugin SDK: resolves only when the plugin sits at
	// content/plugins/<tree>/model-browser (scripts/build-plugins.ps1 mirrors it there).
	import HostUi from '../../../../sdk/HostUi.svelte';
	import DetailPanel from './components/DetailPanel.svelte';
	import DownloadDialog from './components/DownloadDialog.svelte';
	import DownloadTray from './components/DownloadTray.svelte';
	import FilterChips from './components/FilterChips.svelte';
	import FilterPopover from './components/FilterPopover.svelte';
	import NsfwModeControl from './components/NsfwModeControl.svelte';
	import ResultGrid from './components/ResultGrid.svelte';
	import { getInstalled, getMe, getNsfwMedia, getSources, searchModels, setNsfwMode } from './lib/client.js';
	import { can, normalizeMe } from './lib/capabilities.js';
	import { MODE_LABELS, createRevealCache, effectiveMode, isRevealable, nsfwInfo } from './lib/nsfw.js';
	import {
		applyInstalled,
		clearFilters,
		decodeState,
		emptyState,
		enabledSources,
		encodeState,
		filterChips,
		mergeItems,
		normalizeState,
		removeChip,
		searchKey,
		searchRequest,
		sourceDefaults,
		sourceSections,
		switchSource,
		unknownInstalledHashes
	} from './lib/search.js';
	import { scrollParent, toast } from './lib/dom.js';

	// `api` and `setHeaderHidden` come from the host's plugin page (see index.js).
	let { api, setHeaderHidden } = $props();

	const SEARCH_DELAY_MS = 400;
	// Pages in a row that bring no new result before the list stops asking for more.
	const MAX_EMPTY_PAGES = 3;

	/** 'loading' | 'error' | 'denied' | 'empty' | 'ready' */
	let phase = $state('loading');
	let bootError = $state.raw(null);
	let me = $state.raw(null);
	let sources = $state.raw([]);
	let query = $state.raw(emptyState());
	/** The results of `results.key`, searched with `results.request` (its state and source info). */
	let results = $state.raw({ key: '', request: null, items: [], cursor: null, status: 'loading', error: null });
	let loadingMore = $state(false);
	let moreError = $state.raw(null);
	let detailItem = $state.raw(null);
	let downloadTarget = $state.raw(null);
	let modeBusy = $state(false);
	let reloadToken = $state(0);
	let installedToken = $state(0);
	let tray = $state();
	let content = $state();

	let searchSeq = 0;
	let searchTimer = null;
	let emptyPages = 0;
	let detailOpener = null;
	let alive = true;

	const revealCache = createRevealCache((source, id) => getNsfwMedia(api, source, id));

	const info = $derived(sources.find((source) => source.id === query.source));
	const sections = $derived(sourceSections(sources));
	const chips = $derived(filterChips(query, info));
	const showTray = $derived(can(me, 'download') || can(me, 'request'));
	const emptyDescription = $derived(
		nsfwInfo(me).locked
			? 'Try other words, another sort, or fewer filters. NSFW models are never shown to you here.'
			: effectiveMode(me) === 'hide'
				? 'Try other words, another sort, or fewer filters. NSFW models are hidden: your sensitive content setting is Hide.'
				: 'Try other words, another sort, or fewer filters.'
	);
	const pageProps = $derived({
		title: 'Model Browser',
		titleLabel: 'Model Browser',
		persistKey: 'model-browser:page',
		sections,
		section: query.source,
		onSelectSection: selectSource,
		count: results.status === 'ready' ? results.items.length : null,
		q: query.q,
		onQueryChange,
		searchPlaceholder: info ? `Search ${info.label}` : 'Search models',
		sortBy: query.sort || sourceDefaults(info).sort,
		sortOptions: info?.sorts ?? [],
		onSortChange
	});

	onMount(() => {
		// LibraryPage draws its own header (title, search, sort), so hide the host's header row.
		setHeaderHidden?.(true);
		boot();
		return () => {
			alive = false;
			searchSeq += 1;
			clearTimeout(searchTimer);
		};
	});

	async function boot() {
		phase = 'loading';
		bootError = null;
		const meResult = await getMe(api);
		if (!alive) return;
		if (!meResult.ok) {
			bootError = meResult.error;
			phase = 'error';
			return;
		}
		me = normalizeMe(meResult.data);
		if (!can(me, 'browse')) {
			phase = 'denied';
			return;
		}
		const sourcesResult = await getSources(api);
		if (!alive) return;
		if (!sourcesResult.ok) {
			bootError = sourcesResult.error;
			phase = 'error';
			return;
		}
		sources = enabledSources(sourcesResult.data);
		if (sources.length === 0) {
			phase = 'empty';
			return;
		}
		query = normalizeState(decodeState(location.search), sources);
		phase = 'ready';
		if (query.model) detailItem = { source: query.source, id: query.model };
		runSearch(true);
	}

	// The URL ---------------------------------------------------------------------------------

	/** Write the state in the query string, keeping the router's own `history.state`. */
	function writeUrl() {
		const search = encodeState(query, location.search);
		const url = `${location.pathname}${search ? `?${search}` : ''}${location.hash}`;
		if (url !== `${location.pathname}${location.search}${location.hash}`) {
			history.replaceState(history.state, '', url);
		}
	}

	// Searching -------------------------------------------------------------------------------

	async function runSearch(force = false) {
		clearTimeout(searchTimer);
		searchTimer = null;
		if (phase !== 'ready' || !info) return;
		writeUrl();
		const key = searchKey(query);
		if (!force && key === results.key && results.status !== 'error') return;
		const mine = ++searchSeq;
		const request = { source: query.source, state: query, info };
		results = { key, request, items: [], cursor: null, status: 'loading', error: null };
		loadingMore = false;
		moreError = null;
		emptyPages = 0;
		scrollParent(content)?.scrollTo?.({ top: 0 });
		const result = await searchModels(api, request.source, searchRequest(request.state, request.info));
		if (mine !== searchSeq || !alive) return;
		if (!result.ok) {
			results = { ...results, status: 'error', error: result.error };
			return;
		}
		const items = mergeItems([], result.data?.items);
		results = { ...results, items, cursor: result.data?.next_cursor || null, status: 'ready' };
		fillInstalled(mine, items);
	}

	async function loadMore(force = false) {
		if (results.status !== 'ready' || !results.cursor || loadingMore) return;
		if (moreError && !force) return;
		const mine = searchSeq;
		const { request, cursor } = results;
		loadingMore = true;
		moreError = null;
		const result = await searchModels(api, request.source, searchRequest(request.state, request.info, { cursor }));
		if (mine !== searchSeq || !alive) return;
		loadingMore = false;
		if (!result.ok) {
			moreError = result.error;
			return;
		}
		const before = results.items.length;
		const items = mergeItems(results.items, result.data?.items);
		emptyPages = items.length === before ? emptyPages + 1 : 0;
		let next = result.data?.next_cursor || null;
		if (next === cursor || emptyPages >= MAX_EMPTY_PAGES) next = null;
		results = { ...results, items, cursor: next };
		fillInstalled(mine, items.slice(before));
	}

	/** Ask which of these results are installed when the server did not say. */
	async function fillInstalled(mine, items) {
		const hashes = unknownInstalledHashes(items);
		if (hashes.length === 0) return;
		const result = await getInstalled(api, hashes);
		if (mine !== searchSeq || !alive || !result.ok) return;
		results = { ...results, items: applyInstalled(results.items, result.data?.installed) };
	}

	function onQueryChange(value) {
		query = { ...query, q: value };
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => runSearch(), SEARCH_DELAY_MS);
	}

	/** Enter in the search box searches at once. */
	function onPageKeydown(event) {
		const target = event.target;
		if (event.key === 'Enter' && target instanceof HTMLInputElement && target.type === 'search') {
			event.preventDefault();
			runSearch();
		}
	}

	function selectSource(id) {
		if (id === query.source || !sources.some((source) => source.id === id)) return;
		closeDetail(false);
		query = normalizeState(switchSource(query, id), sources);
		runSearch(true);
	}

	function onSortChange(value) {
		query = normalizeState({ ...query, sort: value }, sources);
		runSearch();
	}

	function applyFilters(next) {
		query = normalizeState({ ...next, q: query.q, model: query.model }, sources);
		runSearch();
	}

	// NSFW ------------------------------------------------------------------------------------

	/** A thumbnail's "click to reveal", when it has one. */
	function revealFor(item) {
		if (!isRevealable(item?.thumbnail, me)) return null;
		return () => revealCache.urlFor(item.source, item.id, item.thumbnail.id);
	}

	/** Save the app-wide display mode, then reload what depends on it. */
	async function changeMode(mode) {
		if (modeBusy || !me || mode === me.nsfw.mode) return;
		modeBusy = true;
		const saved = await setNsfwMode(api, mode, { key: nsfwInfo(me).settingKey });
		if (!alive) return;
		if (!saved.ok) {
			modeBusy = false;
			toast('error', `Could not change the sensitive content setting: ${saved.error.message}`);
			return;
		}
		const meResult = await getMe(api);
		if (!alive) return;
		modeBusy = false;
		me = meResult.ok ? normalizeMe(meResult.data) : { ...me, nsfw: { ...me.nsfw, mode } };
		revealCache.reset();
		toast('success', `Sensitive content: ${MODE_LABELS[me.nsfw.mode] ?? me.nsfw.mode} (app-wide setting)`);
		reloadToken += 1;
		runSearch(true);
	}

	// Detail and downloads ----------------------------------------------------------------------

	function openDetail(item, opener) {
		detailOpener = opener ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
		detailItem = item;
		query = { ...query, model: String(item.id) };
		writeUrl();
	}

	function closeDetail(restoreFocus = true) {
		if (!detailItem) return;
		detailItem = null;
		downloadTarget = null;
		query = { ...query, model: '' };
		writeUrl();
		const opener = detailOpener;
		detailOpener = null;
		if (restoreFocus && opener?.isConnected) requestAnimationFrame(() => opener.focus({ preventScroll: true }));
	}

	function onDownloadStarted(data) {
		tray?.noteStarted?.(data?.pending);
		if (data?.already_installed) installedToken += 1;
	}

	function sourceLabel(id) {
		return sources.find((source) => source.id === id)?.label ?? id;
	}
</script>

{#if phase === 'loading'}
	<div class="flex h-full items-center justify-center p-6">
		<HostUi name="Spinner" props={{ size: 'lg' }} />
	</div>
{:else if phase === 'error'}
	<HostUi
		name="LoadErrorState"
		props={{ title: "Couldn't open the Model Browser", message: bootError?.message ?? 'Something went wrong', onRetry: boot, compact: false }}
	/>
{:else if phase === 'denied'}
	<div class="flex h-full items-center justify-center p-6">
		<div class="w-full max-w-lg">
			<HostUi
				name="EmptyState"
				props={{
					icon: 'shield',
					title: 'You do not have access to the Model Browser',
					description: 'Ask an administrator to give one of your user groups the Browse permission.'
				}}
			/>
		</div>
	</div>
{:else if phase === 'empty'}
	<div class="flex h-full items-center justify-center p-6">
		<div class="w-full max-w-lg">
			<HostUi
				name="EmptyState"
				props={{
					icon: 'globe',
					title: 'No source is enabled',
					description: 'There is no model source to browse at the moment. Ask an administrator.'
				}}
			/>
		</div>
	</div>
{:else}
	<div class="contents" role="presentation" onkeydown={onPageKeydown}>
		<HostUi name="LibraryPage" props={pageProps}>
			<div class="flex min-h-full flex-col" bind:this={content}>
				<!-- The search syntax of the source, under the search box; the controls move to their own
				     line when the row is too narrow for both. -->
				<div class="sticky top-0 z-20 flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-canvas px-4 py-2 sm:px-6">
					<p class="min-w-[12rem] flex-1 truncate text-xs text-fg-subtle" title={info?.search_help || undefined}>
						{#if info?.search_help}
							<span class="sr-only">Search syntax:</span>
							{info.search_help}
						{/if}
					</p>
					<div class="ml-auto flex flex-wrap items-center gap-2">
						<FilterPopover {info} filters={query} count={chips.length} onChange={applyFilters} />
						<NsfwModeControl {me} busy={modeBusy} onChange={changeMode} />
						{#if showTray}
							<DownloadTray bind:this={tray} {api} />
						{/if}
					</div>
				</div>

				{#if chips.length > 0}
					<div class="px-4 pt-3 sm:px-6">
						<FilterChips
							{chips}
							shown={results.items.length}
							hasMore={!!results.cursor}
							onRemove={(key) => applyFilters(removeChip(query, key))}
							onClear={() => applyFilters(clearFilters(query))}
						/>
					</div>
				{/if}

				<div class="flex-1 px-4 py-4 sm:px-6">
					<ResultGrid
						items={results.items}
						status={results.status}
						error={results.error}
						hasMore={!!results.cursor}
						{loadingMore}
						{moreError}
						sourceLabel={info?.label ?? 'The source'}
						{emptyDescription}
						onLoadMore={loadMore}
						onRetry={() => runSearch(true)}
						onOpen={openDetail}
						{revealFor}
					/>
				</div>
			</div>
		</HostUi>
	</div>
{/if}

{#if detailItem}
	<DetailPanel
		{api}
		{me}
		source={detailItem.source}
		sourceLabel={sourceLabel(detailItem.source)}
		modelId={detailItem.id}
		item={detailItem}
		{revealCache}
		{reloadToken}
		{installedToken}
		onClose={() => closeDetail()}
		onDownload={(target) => (downloadTarget = target)}
	/>
{/if}

{#if downloadTarget}
	{#key downloadTarget}
		<DownloadDialog {api} {me} target={downloadTarget} onClose={() => (downloadTarget = null)} onStarted={onDownloadStarted} />
	{/key}
{/if}

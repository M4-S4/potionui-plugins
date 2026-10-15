<script>
	import { onMount } from 'svelte';
	import HostUi from '../../../../sdk/HostUi.svelte';
	import HistoryPanel from './components/HistoryPanel.svelte';
	import ImportForm from './components/ImportForm.svelte';
	import NewPresetForm from './components/NewPresetForm.svelte';
	import PresetList from './components/PresetList.svelte';
	import Workbench from './components/Workbench.svelte';
	import { isAdmin, pageIntent } from './lib/access.js';
	import { normalizeCatalog, sortPresets } from './lib/catalog.js';
	import { createDraft, deleteDraft, deletePreset, editPreset, getDraft, getMe, importDraft, listCatalog, listDrafts, pipesReference } from './lib/client.js';
	import { initialCopyForm } from './lib/drafts.js';
	import { familiesFrom } from './lib/families.js';
	import { confirm, replaceQuery, toast } from './lib/dom.js';
	import { openPluginModal } from './lib/modal.js';

	let { api, user } = $props();

	let phase = $state(isAdmin(user) ? 'loading' : 'forbidden');
	let error = $state.raw(null);
	let catalog = $state.raw([]);
	let drafts = $state.raw([]);
	let view = $state.raw({ kind: 'list' });
	let busyId = $state(null);
	let catalogError = $state('');
	let pipes = $state.raw(null);

	const intent = pageIntent(typeof location === 'undefined' ? '' : location.search);

	onMount(() => {
		if (phase !== 'forbidden') boot();
	});

	async function boot() {
		const me = await getMe(api);
		if (!me.ok) {
			error = me.error;
			phase = me.error.status === 401 || me.error.status === 403 ? 'forbidden' : 'error';
			return;
		}
		await Promise.all([refreshCatalog(), refreshDrafts()]);
		phase = 'ready';
		await followIntent();
	}

	async function refreshCatalog() {
		const result = await listCatalog(api);
		if (!result.ok) {
			catalogError = result.error.message;
			return;
		}
		catalogError = '';
		catalog = sortPresets(normalizeCatalog(result.data));
	}

	async function refreshDrafts() {
		const result = await listDrafts(api);
		if (result.ok) drafts = Array.isArray(result.data) ? result.data : [];
	}

	async function loadPipes() {
		if (pipes) return pipes;
		const result = await pipesReference(api);
		if (result.ok) pipes = result.data;
		return pipes;
	}

	async function followIntent() {
		if (intent.kind === 'new') {
			openNewDialog(null);
		} else if (intent.kind === 'draft') {
			const result = await getDraft(api, intent.id);
			if (result.ok) openDraft(result.data);
			else {
				toast('error', result.error.message);
				showList();
			}
		} else if (intent.kind === 'preset') {
			const entry = catalog.find((item) => item.id === intent.id);
			if (entry) await edit(entry);
			else {
				toast('error', `No local preset ${intent.id}`);
				showList();
			}
		}
	}

	async function openDraft(draft) {
		let full = draft;
		if (!Array.isArray(draft.files)) {
			const result = await getDraft(api, draft.draft_id);
			if (!result.ok) {
				toast('error', result.error.message);
				return;
			}
			full = result.data;
		}
		rememberDraft(full);
		view = { kind: 'draft', draft: full };
		replaceQuery({ draft: full.draft_id });
	}

	function showList() {
		view = { kind: 'list' };
		replaceQuery({});
		refreshCatalog();
		refreshDrafts();
	}

	function rememberDraft(draft) {
		drafts = [draft, ...drafts.filter((item) => item.draft_id !== draft.draft_id)];
	}

	function openImportDialog() {
		let latest = { body: null, problems: {} };
		let handle = null;
		handle = openPluginModal({
			title: 'Import a preset archive',
			subtitle: 'A zip of a preset folder becomes a draft',
			confirmLabel: 'Import',
			size: 'md',
			body: ImportForm,
			props: {
				onChange: (next) => {
					latest = next;
					handle?.update({ confirmDisabled: !next.body });
				}
			},
			onConfirm: async (modal) => {
				if (!latest.body) return;
				modal.update({ busy: true });
				const result = await importDraft(api, latest.body);
				if (!result.ok) {
					modal.update({ busy: false });
					toast('error', result.error.message);
					return;
				}
				modal.close();
				toast('success', `Draft created from the archive: ${result.data.name}`);
				rememberDraft(result.data);
				openDraft(result.data);
			}
		});
		if (!handle) toast('error', 'The host has no dialog component: update PotionUI');
	}

	function openNewDialog(source) {
		let latest = { kind: 'copy', body: null, problems: {}, publishNow: false };
		let handle = null;
		const props = $state({
			sources: catalog,
			families: [],
			pipes: null,
			initial: initialCopyForm(source),
			kind: 'copy',
			onChange: (next) => {
				latest = next;
				handle?.update({ confirmDisabled: !next.body });
			}
		});
		handle = openPluginModal({
			title: source ? `Duplicate ${source.name}` : 'New preset',
			subtitle: 'A local preset you can edit and publish',
			confirmLabel: 'Create draft',
			size: 'lg',
			body: NewPresetForm,
			props,
			onConfirm: async (modal) => {
				if (!latest.body) return;
				modal.update({ busy: true });
				const result = await createDraft(api, latest.body);
				if (!result.ok) {
					modal.update({ busy: false });
					toast('error', result.error.message);
					return;
				}
				modal.close();
				toast('success', `Draft created: ${result.data.name}`);
				rememberDraft(result.data);
				openDraft(result.data);
			}
		});
		if (!handle) {
			toast('error', 'The host has no dialog component: update PotionUI');
			return;
		}
		handle.update({ confirmDisabled: !latest.body });
		loadPipes().then((reference) => {
			if (reference) {
				props.pipes = reference;
				props.families = familiesFrom(reference);
			}
		});
	}

	async function edit(entry) {
		busyId = entry.id;
		const result = await editPreset(api, entry.id);
		busyId = null;
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		rememberDraft(result.data);
		openDraft(result.data);
	}

	async function remove(entry) {
		const ok = await confirm({
			title: `Delete ${entry.name}?`,
			message: 'The preset leaves the catalogue and is uninstalled first if needed. Its folder is kept in the Preset Editor history.',
			variant: 'danger'
		});
		if (!ok) return;
		busyId = entry.id;
		const result = await deletePreset(api, entry.id);
		busyId = null;
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		toast('success', `${entry.name} deleted${result.data.uninstalled ? ' and uninstalled' : ''}`);
		await refreshCatalog();
	}

	async function discardDraft(draft) {
		const ok = await confirm({ title: `Discard the draft of ${draft.name}?`, message: 'The draft folder is deleted.', variant: 'danger' });
		if (!ok) return;
		const result = await deleteDraft(api, draft.draft_id);
		if (!result.ok) {
			toast('error', result.error.message);
			return;
		}
		drafts = drafts.filter((item) => item.draft_id !== draft.draft_id);
	}

	function draftChanged(draft) {
		rememberDraft(draft);
		view = { kind: 'draft', draft };
	}
</script>

<HostUi name="PageContainer" props={{ width: 'lg' }}>
	{#if phase === 'forbidden'}
		<HostUi
			name="EmptyState"
			props={{
				icon: 'shield',
				title: 'Reserved for administrators',
				description: 'The Preset Editor creates and publishes presets for the whole instance.'
			}}
		/>
	{:else if phase === 'error'}
		<HostUi
			name="EmptyState"
			props={{ icon: 'shield', tone: 'danger', title: 'The Preset Editor could not start', description: error?.message ?? 'Request failed' }}
		/>
	{:else if phase === 'loading'}
		<div class="flex items-center justify-center py-14">
			<HostUi name="Spinner" props={{ size: 'lg' }} />
		</div>
	{:else if view.kind === 'draft'}
		<Workbench {api} draft={view.draft} onChange={draftChanged} onBack={showList} onPublished={() => refreshCatalog()} onDiscarded={() => { drafts = drafts.filter((item) => item.draft_id !== view.draft.draft_id); showList(); }} />
	{:else if view.kind === 'history'}
		<HistoryPanel {api} preset={view.preset} onBack={showList} onRestored={(draft) => { rememberDraft(draft); openDraft(draft); }} />
	{:else}
		<div class="mb-4 flex flex-wrap items-center gap-2">
			<p class="text-sm text-fg-muted">Start from a copy of a preset or from a blank skeleton, then edit, lint and publish into <span class="font-mono">content/presets/local</span>.</p>
			<span class="flex-1"></span>
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: openImportDialog }}>Import zip</HostUi>
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'plus', onclick: () => openNewDialog(null) }}>New Preset</HostUi>
		</div>
		{#if catalogError}
			<div class="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">{catalogError}</div>
		{/if}
		<PresetList
			entries={catalog}
			{drafts}
			{busyId}
			onDuplicate={openNewDialog}
			onEdit={edit}
			onDelete={remove}
			onHistory={(entry) => (view = { kind: 'history', preset: entry })}
			onOpenDraft={openDraft}
			onDiscardDraft={discardDraft}
			onRefresh={() => { refreshCatalog(); refreshDrafts(); }}
		/>
	{/if}
</HostUi>

<script>
	import { onMount } from 'svelte';
	import ActionButton from './components/ActionButton.svelte';
	import LocalPresetMenu from './components/LocalPresetMenu.svelte';
	import NewPresetForm from './components/NewPresetForm.svelte';
	import { localPresets, normalizeCatalog, sortPresets } from './lib/catalog.js';
	import { createDraft, listCatalog, pipesReference, publishDraft } from './lib/client.js';
	import { initialCopyForm } from './lib/drafts.js';
	import { familiesFrom } from './lib/families.js';
	import { navigateTo, toast } from './lib/dom.js';
	import { standaloneApi } from './lib/hostApi.js';
	import { openPluginModal } from './lib/modal.js';

	let { context = {} } = $props();

	const PAGE_ROUTE = '/plugins/preset-editor';
	const api = standaloneApi();

	let phase = $state('loading');
	let error = $state('');
	let catalog = $state.raw([]);
	let entries = $state.raw([]);
	let pipes = $state.raw(null);
	let dialogProps = null;

	onMount(load);

	async function load() {
		phase = 'loading';
		const result = await listCatalog(api);
		if (!result.ok) {
			error = result.error.message;
			phase = 'error';
			return;
		}
		catalog = sortPresets(normalizeCatalog(result.data));
		entries = localPresets(catalog);
		phase = 'ready';
		if (dialogProps) dialogProps.sources = catalog;
	}

	async function loadPipes() {
		if (pipes) return pipes;
		const result = await pipesReference(api);
		if (result.ok) pipes = result.data;
		return pipes;
	}

	function draftUrl(draftId) {
		return `${PAGE_ROUTE}?draft=${encodeURIComponent(draftId)}`;
	}

	function openDialog() {
		let latest = { body: null, publishNow: false };
		let handle = null;
		const props = $state({
			sources: catalog,
			families: [],
			pipes: null,
			initial: initialCopyForm(null),
			kind: 'copy',
			withPublishNow: true,
			onChange: (next) => {
				latest = next;
				handle?.update({ confirmDisabled: !next.body });
			}
		});
		dialogProps = props;
		if (phase !== 'ready') load();
		handle = openPluginModal({
			title: 'New preset',
			subtitle: 'A local preset, from a copy or from a blank skeleton',
			confirmLabel: 'Create',
			size: 'lg',
			body: NewPresetForm,
			props,
			onConfirm: async (modal) => {
				if (!latest.body) return;
				modal.update({ busy: true });
				const created = await createDraft(api, latest.body);
				if (!created.ok) {
					modal.update({ busy: false });
					toast('error', created.error.message);
					return;
				}
				if (!latest.publishNow) {
					modal.close();
					navigateTo(draftUrl(created.data.draft_id));
					return;
				}
				const published = await publishDraft(api, created.data.draft_id, {});
				modal.close();
				if (!published.ok) {
					toast('error', `${published.error.message}: the draft is kept`);
					navigateTo(draftUrl(created.data.draft_id));
					return;
				}
				toast('success', `${published.data.preset.name} is published${published.data.installed ? ' and installed' : ''}`);
				context.refreshPresets?.();
				context.selectPreset?.(published.data.preset_id);
				load();
			},
			onCancel: () => {
				dialogProps = null;
			}
		});
		if (!handle) {
			navigateTo(`${PAGE_ROUTE}?new=1`);
			return;
		}
		handle.update({ confirmDisabled: true });
		loadPipes().then((reference) => {
			if (reference) {
				props.pipes = reference;
				props.families = familiesFrom(reference);
			}
		});
	}
</script>

<div class="flex items-center gap-2">
	<ActionButton icon="plus" title="Create a preset with the Preset Editor" onclick={openDialog}>New Preset</ActionButton>
	<LocalPresetMenu {entries} {phase} {error} pageRoute={PAGE_ROUTE} />
</div>

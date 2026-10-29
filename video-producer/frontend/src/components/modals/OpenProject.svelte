<script>
	import { onMount, tick } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatDuration, formatRelative, t } from '../../i18n/index.svelte.js';
	import { ui, toast } from '../../lib/state.svelte.js';
	import { project, listProjects, openProject, deleteProject } from '../../lib/project.svelte.js';
	import { createProject } from '../../lib/commands.js';
	import { confirm, mountHostSlot } from '../../lib/host.js';
	import { focusWithRing } from '../../lib/focus.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';

	let phase = $state('loading');
	let projects = $state([]);
	let picked = $state(project.id);
	let busy = $state(false);
	let now = $state(Date.now());
	let alive = true;
	let list = $state();

	const close = () => (ui.modal = null);
	const canOpen = $derived(!!picked && picked !== project.id && !busy);
	const nameOf = (p) => p.name || t('lib.default.project');
	const meta = (p) => t('project.open.meta', { when: formatRelative(p.updatedAt, now), count: p.shots, duration: formatDuration(p.duration) });

	async function load() {
		phase = 'loading';
		const result = await listProjects();
		if (!alive) return;
		if (!result.ok) {
			phase = 'error';
			return;
		}
		projects = result.data;
		if (!projects.some((p) => p.id === picked)) picked = projects[0]?.id ?? null;
		now = Date.now();
		phase = 'ready';
		await tick();
		focusWithRing(list?.querySelector('input:checked'));
	}

	async function open(id = picked) {
		if (!id || busy) return;
		if (id === project.id) return close();
		busy = true;
		const result = await openProject(id);
		busy = false;
		if (result.error?.code === 'cancelled') return;
		if (!result.ok) return toast(t('project.toast.openFailed'), 'error');
		close();
	}

	async function fresh() {
		close();
		await createProject();
	}

	async function remove(p) {
		if (busy) return;
		const current = p.id === project.id;
		const next = current ? (projects.find((x) => x.id !== p.id)?.id ?? null) : null;
		const message = !current ? t('project.delete.message', { name: nameOf(p) }) : next ? t('project.delete.messageCurrent', { name: nameOf(p) }) : t('project.delete.messageLast', { name: nameOf(p) });
		const ok = await confirm({ title: t('project.delete.title'), message, variant: 'danger', confirmLabel: t('project.delete.confirm') });
		if (!ok || !alive) return;
		busy = true;
		const result = await deleteProject(p.id, next);
		busy = false;
		if (!alive) return;
		if (!result.ok) return toast(t('project.toast.deleteFailed'), 'error');
		toast(t('project.toast.deleted', { name: nameOf(p) }));
		if (current) return load();
		projects = projects.filter((x) => x.id !== p.id);
		if (picked === p.id) picked = project.id;
	}

	onMount(() => {
		load();
		return () => (alive = false);
	});

	const emptyProps = $derived({ compact: true, icon: 'folder', title: t('project.open.empty'), description: t('project.open.emptyHint') });
	const errorProps = $derived({
		variant: 'danger',
		title: t('project.open.loadFailed'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'xs', icon: 'refresh', onclick: load, children: t('project.retry') }) }
	});
</script>

<Modal title={t('shell.open.title')} icon="folder" width={560}>
	<div class="p-4">
		{#if phase === 'loading'}
			<div class="flex items-center justify-center gap-2 py-10 text-sm text-fg-muted"><HostUi name="Spinner" props={{ size: 'sm' }} />{t('project.open.loading')}</div>
		{:else if phase === 'error'}
			<HostUi name="Alert" props={errorProps} />
		{:else if !projects.length}
			<HostUi name="EmptyState" props={emptyProps} />
		{:else}
			<div class="space-y-1.5" bind:this={list} role="radiogroup" aria-label={t('shell.open.title')}>
				{#each projects as p (p.id)}
					<div class="vp-pickrow">
						<label class="flex min-w-0 flex-1 cursor-pointer items-center gap-3 py-1.5" ondblclick={() => open(p.id)}>
							<input type="radio" class="sr-only" name="vp-open-project" value={p.id} bind:group={picked} onkeydown={(e) => e.key === 'Enter' && open(p.id)} />
							<Icon name="film" class="h-4 w-4 shrink-0 text-fg-muted" />
							<span class="min-w-0 flex-1">
								<span class="block truncate text-sm font-medium">{nameOf(p)}</span>
								<span class="block truncate text-xs text-fg-muted">{meta(p)}</span>
							</span>
							{#if p.id === project.id}<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('shell.open.current')}</HostUi>{/if}
						</label>
						<HostUi name="IconButton" props={{ icon: 'trash', label: t('project.delete.label', { name: nameOf(p) }), tooltip: t('project.delete.title'), size: 'sm', class: 'vp-h7', disabled: busy, onclick: () => remove(p) }} />
					</div>
				{/each}
			</div>
		{/if}
	</div>
	{#snippet footer()}
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'plus', class: 'mr-auto', onclick: fresh }}>{t('project.open.new')}</HostUi>
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', disabled: !canOpen, loading: busy, onclick: () => open() }}>{t('project.open.confirm')}</HostUi>
	{/snippet}
</Modal>

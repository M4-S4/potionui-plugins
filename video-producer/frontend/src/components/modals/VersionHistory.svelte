<script>
	import { onMount, tick } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatDate, t } from '../../i18n/index.svelte.js';
	import { ui, toast } from '../../lib/state.svelte.js';
	import { project, listVersions, restoreVersion } from '../../lib/project.svelte.js';
	import { confirm, mountHostSlot } from '../../lib/host.js';
	import { focusWithRing } from '../../lib/focus.js';
	import Modal from './Modal.svelte';
	import Icon from '../Icon.svelte';

	let phase = $state('loading');
	let versions = $state([]);
	let picked = $state(null);
	let busy = $state(false);
	let alive = true;
	let list = $state();

	const close = () => (ui.modal = null);
	const canRestore = $derived(picked !== null && picked !== project.version && !busy);

	function meta(v) {
		const parts = [formatDate(v.createdAt, { dateStyle: 'medium', timeStyle: 'medium' }), t('project.versions.shots', { count: v.shots })];
		if (v.label) parts.push(v.label);
		return parts.join(' · ');
	}

	async function load() {
		phase = 'loading';
		const result = await listVersions();
		if (!alive) return;
		if (!result.ok) {
			phase = 'error';
			return;
		}
		versions = result.data;
		phase = 'ready';
		await tick();
		focusWithRing(list?.querySelector('input:not(:disabled)'));
	}

	async function restore() {
		if (!canRestore) return;
		const n = picked;
		const ok = await confirm({ title: t('project.versions.confirmTitle', { n }), message: t('project.versions.confirmMessage', { n }), variant: 'warning', confirmLabel: t('project.versions.restore') });
		if (!ok || !alive) return;
		busy = true;
		const result = await restoreVersion(n);
		busy = false;
		if (result.error?.code === 'cancelled') return;
		if (!result.ok) return toast(t('project.toast.restoreFailed'), 'error');
		close();
		toast(t('project.toast.restored', { n }), 'success');
	}

	onMount(() => {
		load();
		return () => (alive = false);
	});

	const emptyProps = $derived({ compact: true, icon: 'history', title: t('project.versions.empty') });
	const errorProps = $derived({
		variant: 'danger',
		title: t('project.versions.loadFailed'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'xs', icon: 'refresh', onclick: load, children: t('project.retry') }) }
	});
</script>

<Modal title={t('project.versions.title')} subtitle={t('project.versions.subtitle')} icon="history" width={560}>
	<div class="p-4">
		{#if phase === 'loading'}
			<div class="flex items-center justify-center gap-2 py-10 text-sm text-fg-muted"><HostUi name="Spinner" props={{ size: 'sm' }} />{t('project.versions.loading')}</div>
		{:else if phase === 'error'}
			<HostUi name="Alert" props={errorProps} />
		{:else if !versions.length}
			<HostUi name="EmptyState" props={emptyProps} />
		{:else}
			<div class="space-y-1.5" bind:this={list} role="radiogroup" aria-label={t('project.versions.title')}>
				{#each versions as v (v.id)}
					{@const current = v.version === project.version}
					<label class="vp-pickrow py-1.5 {current ? '' : 'cursor-pointer'}">
						<input type="radio" class="sr-only" name="vp-version" value={v.version} bind:group={picked} disabled={current} onkeydown={(e) => e.key === 'Enter' && restore()} />
						<Icon name="history" class="h-4 w-4 shrink-0 text-fg-muted" />
						<span class="min-w-0 flex-1">
							<span class="block truncate text-sm font-medium">{t('project.versions.name', { n: v.version })}</span>
							<span class="block truncate text-xs text-fg-muted">{meta(v)}</span>
							{#if v.sourceVersion !== null}<span class="block truncate text-xs text-fg-muted">{t('project.versions.restoredFrom', { n: v.sourceVersion })}</span>{/if}
						</span>
						{#if current}<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('shell.open.current')}</HostUi>{/if}
					</label>
				{/each}
			</div>
		{/if}
	</div>
	{#snippet footer()}
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: close }}>{t('project.versions.cancel')}</HostUi>
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'history', disabled: !canRestore, loading: busy, onclick: restore }}>{t('project.versions.restore')}</HostUi>
	{/snippet}
</Modal>

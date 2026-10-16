<script>
	import { onMount } from 'svelte';
	import HostUi from '../../../../sdk/HostUi.svelte';
	import { createClient } from './lib/api.js';
	import { detectLocale, formatNumber, getLocale, has, setLocale, t } from './i18n/index.svelte.js';

	let { api, user, setHeaderHidden } = $props();

	let phase = $state('loading');
	let me = $state.raw(null);
	let loadError = $state.raw(null);

	let alive = true;
	let loadSeq = 0;
	let saveSeq = 0;
	let localePicked = false;

	setLocale(detectLocale(null, navigator.language));

	const client = $derived(createClient(api));
	const locale = $derived(getLocale());
	const username = $derived(me?.username || user?.username || '');
	const languageNames = $derived({ en: t('locale.en'), fr: t('locale.fr') });
	const localeTip = $derived(t('status.localeTip', { language: languageNames[locale] }));
	const errorText = $derived.by(() => {
		const code = loadError?.code;
		if (code && has(`error.${code}`)) return t(`error.${code}`);
		return loadError?.status >= 500 ? t('error.server_error') : t('error.unknown');
	});

	onMount(() => {
		setHeaderHidden?.(true);
		load();
		return () => {
			alive = false;
			loadSeq += 1;
			saveSeq += 1;
		};
	});

	async function load() {
		const seq = ++loadSeq;
		phase = 'loading';
		loadError = null;
		const result = await client.me();
		if (!alive || seq !== loadSeq) return;
		if (!result.ok) {
			loadError = result.error;
			phase = 'error';
			return;
		}
		me = result.data;
		if (me.locale && !localePicked) setLocale(me.locale);
		phase = 'ready';
	}

	async function toggleLocale() {
		localePicked = true;
		const next = setLocale(locale === 'fr' ? 'en' : 'fr');
		const seq = ++saveSeq;
		const result = await client.saveLocale(next);
		if (!alive || seq !== saveSeq) return;
		if (result.ok) {
			if (me) me = { ...me, locale: next };
			return;
		}
		window.__potionui?.notifications?.toast?.('warning', t('toast.localeNotSaved'));
	}
</script>

<div class="vp-root h-full min-h-0 bg-canvas font-sans text-base text-fg antialiased overflow-hidden" lang={locale}>
	<div class="flex min-h-0 flex-1 items-center justify-center overflow-auto p-6">
		{#if phase === 'loading'}
			<div class="flex flex-col items-center gap-3">
				<HostUi name="Spinner" props={{ size: 'lg' }} />
				<p class="text-sm text-fg-muted">{t('app.loading')}</p>
			</div>
		{:else if phase === 'error'}
			<div class="flex w-full max-w-lg flex-col items-center gap-4">
				<div class="w-full">
					<HostUi
						name="EmptyState"
						props={{ icon: 'warning', tone: 'danger', title: t('error.meLoad'), description: errorText }}
					/>
				</div>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'refresh', onclick: load }}>
					{t('app.retry')}
				</HostUi>
			</div>
		{:else}
			<div class="w-full max-w-lg">
				<HostUi
					name="EmptyState"
					props={{ icon: 'film', title: t('workspace.empty.title'), description: t('workspace.empty.description') }}
				/>
			</div>
		{/if}
	</div>

	<footer class="flex h-6 shrink-0 items-center gap-4 whitespace-nowrap border-t border-line bg-surface-1 px-3 text-xs text-fg-subtle">
		<span class="font-medium text-fg-muted">{t('app.name')}</span>
		<span class="min-w-0 truncate">{t('app.untitledProject')}</span>
		<div class="flex-1"></div>
		{#if phase === 'ready' && me}
			{#if username}
				<span class="min-w-0 truncate">{t('status.signedInAs', { name: username })}</span>
			{/if}
			<span>{me.isAdmin ? t('status.role.admin') : t('status.role.user')}</span>
			{#if me.quota}
				<span class="tabular-nums text-fg-muted">
					{t('status.quota', {
						remaining: formatNumber(me.quota.remaining, { maximumFractionDigits: 1 }),
						limit: formatNumber(me.quota.limit, { maximumFractionDigits: 1 })
					})}
				</span>
			{/if}
		{/if}
		<button
			type="button"
			class="flex h-6 min-w-6 items-center justify-center rounded-sm px-1.5 font-medium text-fg-muted hover:bg-surface-2 hover:text-fg"
			title={localeTip}
			onclick={toggleLocale}
		>
			{t('status.locale')}
		</button>
	</footer>
</div>

<style>
	:global(.vp-root) {
		display: flex;
		flex-direction: column;
	}

	:global(.vp-root :focus-visible) {
		outline: 2px solid rgb(var(--signal));
		outline-offset: 2px;
	}
</style>

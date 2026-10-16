<script>
	import { onDestroy } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, seqDuration, secs, allIssues, toast, clipLabel } from '../../lib/state.svelte.js';
	import { fcpxml, otio, edl, srt, srtCues, download } from '../../lib/exchange.js';
	import { hostIconName } from '../../lib/icons.js';
	import Modal from './Modal.svelte';
	import Tabs from '../shell/Tabs.svelte';
	import Icon from '../Icon.svelte';

	let { tab: initialTab = 'video' } = $props();
	let tab = $state(firstTab());
	let format = $state('master');
	let res = $state(doc.resolution);
	let extent = $state(ui.range ? 'range' : 'whole');
	let stems = $state(true);
	let st = $state('idle');
	let progress = $state(0);
	let exchange = $state('fcpxml');
	let timer = null;

	function firstTab() {
		return ['video', 'exchange', 'subtitles'].includes(initialTab) ? initialTab : 'video';
	}

	const tabs = $derived([
		{ id: 'video', label: t('modals.export.tab.video') },
		{ id: 'exchange', label: t('modals.export.tab.exchange') },
		{ id: 'subtitles', label: t('modals.export.tab.subtitles') }
	]);
	const formats = ['master', 'web', 'social', 'archive'];
	const simulatedFormat = $derived(format === 'master' || format === 'archive');
	const notFinal = $derived(doc.clips.filter((c) => c.stage === 'draft' || c.stage === 'todo'));
	const pending = $derived(doc.results.filter((r) => r.status === 'redo').length);
	const issues = $derived(allIssues().filter((i) => i.level === 'conflict').length);
	const dur = $derived(extent === 'range' && ui.range ? ui.range.out - ui.range.in : seqDuration());
	const base = $derived(doc.name.replace(/\s+/g, '_'));
	const fileName = $derived(`${base}_${res}.${format === 'master' ? 'mov' : 'mp4'}`);
	const cues = $derived(srtCues());
	const targets = {
		fcpxml: { label: 'Final Cut Pro', ext: 'fcpxml', make: fcpxml, mime: 'application/xml' },
		otio: { label: 'OpenTimelineIO', ext: 'otio', make: otio, mime: 'application/json' },
		edl: { label: 'EDL CMX 3600', ext: 'edl', make: edl, mime: 'text/plain' }
	};
	const exchangePreview = $derived(tab === 'exchange' ? targets[exchange].make().slice(0, 900) : '');

	function formatLabel(id) {
		if (id === 'master') return t('modals.export.formatMaster');
		if (id === 'web') return t('modals.export.formatWeb');
		if (id === 'social') return t('modals.export.formatSocial');
		return t('modals.export.formatArchive');
	}

	function noteOf(id) {
		if (id === 'fcpxml') return t('modals.export.noteFcpxml');
		if (id === 'otio') return t('modals.export.noteOtio');
		return t('modals.export.noteEdl');
	}

	function go() {
		clearInterval(timer);
		st = 'running';
		progress = 0;
		timer = setInterval(() => {
			progress = Math.min(100, progress + 4 + Math.random() * 6);
			if (progress >= 100) {
				clearInterval(timer);
				timer = null;
				st = 'done';
			}
		}, 120);
	}
	function exportExchange() {
		const target = targets[exchange];
		const file = `${base}.${target.ext}`;
		download(file, target.make(), target.mime);
		toast(t('modals.export.downloaded', { file }), 'success');
	}
	function exportSrt() {
		const file = `${base}.srt`;
		download(file, srt());
		toast(t('modals.export.downloaded', { file }), 'success');
	}

	onDestroy(() => clearInterval(timer));
</script>

<Modal title={t('modals.export.title')} subtitle="{t('modals.count.shots', { count: doc.clips.length })} · {secs(dur)}" icon="export" width={600}>
	<Tabs label={t('modals.export.tabs')} class="!px-4" value={tab} onselect={(id) => (tab = id)} items={tabs} />

	<div class="space-y-4 p-4">
		{#if notFinal.length || pending || issues}
			<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact' }}>
				<div class="space-y-1 text-xs">
					{#if notFinal.length}<div class="flex gap-1.5"><Icon name="layers" class="h-3.5 w-3.5 shrink-0 text-warning" />{t('modals.export.notFinal', { count: notFinal.length, list: notFinal.map(clipLabel).join(', ') })}</div>{/if}
					{#if pending}<div class="flex gap-1.5"><Icon name="flag" class="h-3.5 w-3.5 shrink-0 text-warning" />{t('modals.export.redo', { count: pending })}</div>{/if}
					{#if issues}<div class="flex gap-1.5"><Icon name="alert" class="h-3.5 w-3.5 shrink-0 text-warning" />{t('modals.export.conflicts', { count: issues })}</div>{/if}
				</div>
			</HostUi>
		{/if}

		{#if tab === 'video'}
			<div class="grid grid-cols-2 gap-3">
				<label class="col-span-2 space-y-1">
					<span class="flex items-center gap-2"><span class="vp-label">{t('modals.export.format')}</span>{#if simulatedFormat}<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('shell.window.simulated')}</span>{/if}</span>
					<select class="input vp-dense w-full" bind:value={format}>
						{#each formats as f (f)}<option value={f}>{formatLabel(f)}</option>{/each}
					</select>
				</label>
				<label class="space-y-1">
					<span class="vp-label">{t('modals.export.resolution')}</span>
					<select class="input vp-dense w-full" bind:value={res}><option value="720p">720p</option><option value="1080p">1080p</option><option value="4K">4K</option></select>
				</label>
				<label class="space-y-1">
					<span class="vp-label">{t('modals.export.extent')}</span>
					<select class="input vp-dense w-full" bind:value={extent}>
						<option value="whole">{t('modals.export.whole')}</option>
						<option value="range" disabled={!ui.range}>{t('modals.export.range')}</option>
					</select>
				</label>
			</div>
			<div class="flex min-h-7 items-center gap-2 text-sm">
				<HostUi name="Switch" props={{ id: 'vp-export-stems', checked: stems, size: 'lg', label: t('modals.export.stems'), onchange: (v) => (stems = v) }} />
				<label for="vp-export-stems">{t('modals.export.stems')}</label>
				<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('shell.window.simulated')}</span>
			</div>
			<div class="rounded-lg border border-line-strong p-3 text-xs text-fg-muted">
				<div class="mb-1 text-sm text-fg">{fileName}</div>
				{t('modals.export.fileInfo', { fps: doc.fps, aspect: doc.aspect })}{stems ? ` · ${t('modals.export.fileStems')}` : ''}
			</div>
			{#if st === 'running'}
				<div class="h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('modals.export.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(progress)}>
					<div class="h-full rounded-full bg-signal transition-[width]" style:width="{progress}%"></div>
				</div>
			{:else if st === 'done'}
				<div class="flex gap-2 rounded-lg border border-success/40 bg-success/5 p-2.5 text-sm" role="status"><Icon name="check" class="h-4 w-4 text-success" />{t('modals.export.done')}</div>
			{/if}
		{:else if tab === 'exchange'}
			<div class="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t('modals.export.exchangeFormat')}>
				{#each Object.entries(targets) as [k, target] (k)}
					<button
						type="button"
						role="radio"
						class="rounded-lg border p-3 text-left transition-colors {exchange === k ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}"
						aria-checked={exchange === k}
						onclick={() => (exchange = k)}
					>
						<span class="block text-sm font-medium">{target.label}</span>
						<span class="vp-tc block text-xs text-fg-subtle">.{target.ext}</span>
					</button>
				{/each}
			</div>
			<p class="text-xs text-fg-muted">{noteOf(exchange)}</p>
			<pre class="max-h-40 overflow-auto rounded-lg border border-line-strong bg-canvas p-2.5 font-mono text-2xs leading-4 text-fg-muted">{exchangePreview}…</pre>
		{:else if cues.length}
			<ol class="max-h-56 space-y-1 overflow-auto">
				{#each cues as c, i (i)}
					<li class="flex gap-3 rounded-md px-2 py-1.5 text-sm odd:bg-surface-2/50">
						<span class="vp-tc w-6 text-xs text-fg-muted">{i + 1}</span>
						<span class="vp-tc w-24 shrink-0 text-xs text-fg-muted">{secs(c.start)} → {secs(c.end)}</span>
						<span class="whitespace-pre-line text-fg-muted">{c.text}</span>
					</li>
				{/each}
			</ol>
			<p class="text-xs text-fg-subtle">{t('modals.export.subtitlesNote')}</p>
		{:else}
			<HostUi name="EmptyState" props={{ compact: true, icon: hostIconName('type'), title: t('modals.export.noSubtitles') }} />
		{/if}
	</div>

	{#snippet footer()}
		{#if tab === 'video'}<span class="vp-sim mr-auto"><Icon name="flask" class="h-3 w-3" />{t('modals.export.simulated')}</span>{/if}
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: () => (ui.modal = null) }}>{t('modals.export.close')}</HostUi>
		{#if tab === 'video'}
			{#if st !== 'done'}
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('export'), disabled: st === 'running', onclick: go }}>{t('modals.export.export')}</HostUi>
			{/if}
		{:else if tab === 'exchange'}
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('export'), onclick: exportExchange }}>{t('modals.export.download', { file: `${base}.${targets[exchange].ext}` })}</HostUi>
		{:else}
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('export'), disabled: !cues.length, onclick: exportSrt }}>{t('modals.export.download', { file: `${base}.srt` })}</HostUi>
		{/if}
	{/snippet}
</Modal>

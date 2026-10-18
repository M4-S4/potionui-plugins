<script>
	import { onDestroy, onMount } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatBytes, formatRelative, t } from '../../i18n/index.svelte.js';
	import { ui, doc, seqDuration, secs, allIssues, clipLabel } from '../../lib/state.svelte.js';
	import { EXCHANGE } from '../../lib/exchange.js';
	import { README_HREF, RESOLUTIONS, VIDEO_FORMATS, exchangeFile, historyOf, isJobActive, isRealFormat, slugify, videoFile } from '../../lib/exports.js';
	import {
		exportState,
		exchangeText,
		subtitleCues,
		exportExchange,
		startVideoExport,
		cancelJob,
		deleteJob,
		downloadJob,
		showInLibrary,
		canShowLibrary,
		watchExports,
		jobErrorText
	} from '../../lib/exports.svelte.js';
	import { findTake } from '../../lib/production.svelte.js';
	import { announcer } from '../../lib/announce.js';
	import { hostIconName } from '../../lib/icons.js';
	import Modal from './Modal.svelte';
	import Tabs from '../shell/Tabs.svelte';
	import Icon from '../Icon.svelte';

	let { tab: initialTab = 'video' } = $props();
	let tab = $state(firstTab());
	let format = $state('web');
	let res = $state(RESOLUTIONS.includes(doc.resolution) ? doc.resolution : '1080p');
	let extent = $state(ui.range ? 'range' : 'whole');
	let stems = $state(false);
	let simState = $state('idle');
	let simProgress = $state(0);
	let exchange = $state('fcpxml');
	let timer = null;
	let spoken = $state('');
	const voice = announcer();

	function firstTab() {
		return ['video', 'exchange', 'subtitles'].includes(initialTab) ? initialTab : 'video';
	}

	const tabs = $derived([
		{ id: 'video', label: t('modals.export.tab.video') },
		{ id: 'exchange', label: t('modals.export.tab.exchange') },
		{ id: 'subtitles', label: t('modals.export.tab.subtitles') }
	]);
	const real = $derived(isRealFormat(format));
	const ffmpegMissing = $derived(ui.me?.ffmpeg === false);
	const job = $derived(exportState.job);
	const running = $derived(isJobActive(job));
	const history = $derived(historyOf(exportState.jobs, job));
	const library = $derived(canShowLibrary());
	const span = $derived(real ? 'whole' : extent);
	const notFinal = $derived(doc.clips.filter((c) => c.stage === 'draft' || c.stage === 'todo'));
	const pending = $derived(doc.clips.filter((c) => findTake(c.take)?.flag === 'reject').length);
	const issues = $derived(allIssues().filter((i) => i.level === 'conflict').length);
	const dur = $derived(span === 'range' && ui.range ? ui.range.out - ui.range.in : seqDuration());
	const fileName = $derived(real ? videoFile(doc.name, res) : `${slugify(doc.name)}_${res}.${format === 'master' ? 'mov' : 'mp4'}`);
	const cues = $derived(subtitleCues());
	const targets = {
		fcpxml: { label: 'FCPXML', ext: EXCHANGE.fcpxml.ext },
		otio: { label: 'OpenTimelineIO', ext: EXCHANGE.otio.ext },
		edl: { label: 'EDL CMX 3600', ext: EXCHANGE.edl.ext }
	};
	const exchangePreview = $derived(tab === 'exchange' ? exchangeText(exchange).slice(0, 900) : '');

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

	function stepText(j) {
		if (j.status === 'queued') return t('exports.step.queued');
		if (j.step === 'assemble') return t('exports.step.assemble');
		if (j.step === 'mix') return t('exports.step.mix');
		if (j.step === 'transcode') return t('exports.step.transcode');
		if (j.step === 'store') return t('exports.step.store');
		return t('exports.status.running');
	}

	function statusText(status) {
		if (status === 'queued') return t('lib.status.queued');
		if (status === 'running') return t('exports.status.running');
		if (status === 'done') return t('exports.status.done');
		if (status === 'failed') return t('lib.status.failed');
		return t('lib.status.cancelled');
	}

	const tone = (status) => (status === 'done' ? 'text-success' : status === 'failed' ? 'text-danger' : status === 'cancelled' ? 'text-fg-subtle' : 'text-signal');
	const dot = (status) => (status === 'done' ? 'bg-success' : status === 'failed' ? 'bg-danger' : status === 'cancelled' ? 'bg-fg-subtle' : 'bg-signal');
	const nameOf = (j) => j.file?.name ?? videoFile(doc.name, j.resolution ?? res);

	$effect(() => {
		if (!running || !job) {
			voice.reset();
			spoken = '';
			return;
		}
		const said = voice.next(stepText(job), job.progress);
		if (said) spoken = `${said.label} · ${t('exports.percent', { value: said.value })}`;
	});

	function simulate() {
		clearInterval(timer);
		simState = 'running';
		simProgress = 0;
		timer = setInterval(() => {
			simProgress = Math.min(100, simProgress + 4 + Math.random() * 6);
			if (simProgress >= 100) {
				clearInterval(timer);
				timer = null;
				simState = 'done';
			}
		}, 120);
	}

	function pickFormat(value) {
		format = value;
		simState = 'idle';
		simProgress = 0;
		clearInterval(timer);
		timer = null;
	}

	onMount(() => watchExports());
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
			{#if real && ffmpegMissing}
				<HostUi name="Alert" props={{ variant: 'danger', class: '[&>div]:text-fg', density: 'compact', icon: true, live: 'off' }}>
					<p class="text-xs">
						{t('exports.ffmpeg.missing')}
						{#if ui.isAdmin}
							<a class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" href={README_HREF}>{t('exports.ffmpeg.guide')}</a>
						{:else}
							{t('exports.ffmpeg.ask')}
						{/if}
					</p>
				</HostUi>
			{/if}
			<div class="grid grid-cols-2 gap-3">
				<label class="col-span-2 space-y-1">
					<span class="flex items-center gap-2"><span class="vp-label">{t('modals.export.format')}</span>{#if !real}<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('shell.window.simulated')}</span>{/if}</span>
					<select class="input vp-dense w-full" value={format} disabled={running} onchange={(e) => pickFormat(e.currentTarget.value)}>
						{#each VIDEO_FORMATS as f (f)}<option value={f}>{formatLabel(f)}</option>{/each}
					</select>
				</label>
				<label class="space-y-1">
					<span class="vp-label">{t('modals.export.resolution')}</span>
					<select class="input vp-dense w-full" bind:value={res} disabled={running}>
						{#each RESOLUTIONS as r (r)}<option value={r}>{r}</option>{/each}
					</select>
				</label>
				<label class="space-y-1">
					<span class="vp-label">{t('modals.export.extent')}</span>
					<select class="input vp-dense w-full" value={span} disabled={running} onchange={(e) => (extent = e.currentTarget.value)}>
						<option value="whole">{t('modals.export.whole')}</option>
						<option value="range" disabled={!ui.range || real}>{t('modals.export.range')}</option>
					</select>
				</label>
				{#if real && ui.range}<p class="col-span-2 text-xs text-fg-subtle">{t('exports.rangeWhole')}</p>{/if}
			</div>
			<div class="flex min-h-7 items-center gap-2 text-sm">
				<HostUi name="Switch" props={{ id: 'vp-export-stems', checked: stems, size: 'lg', label: t('modals.export.stems'), onchange: (v) => (stems = v) }} />
				<label for="vp-export-stems">{t('modals.export.stems')}</label>
				<span class="vp-sim"><Icon name="flask" class="h-3 w-3" />{t('shell.window.simulated')}</span>
			</div>
			<div class="rounded-lg border border-line-strong p-3 text-xs text-fg-muted">
				<div class="mb-1 text-sm text-fg">{fileName}</div>
				{t('modals.export.fileInfo', { fps: doc.fps, aspect: format === 'social' ? '9:16' : doc.aspect })}{stems ? ` · ${t('modals.export.fileStems')}` : ''}{real ? ` · ${t('exports.real')}` : ''}
			</div>

			{#if real}
				{#if job}
					<section class="rounded-lg border border-line-strong p-3" aria-label={t('exports.progress')}>
						<div class="flex items-center gap-2 text-sm">
							<span class="min-w-0 flex-1 truncate text-fg">{nameOf(job)}</span>
							<span class="flex shrink-0 items-center gap-1 text-xs {tone(job.status)}"><span class="h-1.5 w-1.5 rounded-full {dot(job.status)}"></span>{statusText(job.status)}</span>
						</div>
						{#if running}
							<div class="mt-2 flex justify-between gap-2 text-xs">
								<span class="truncate text-fg-muted">{stepText(job)}</span>
								<span class="vp-tc text-fg-subtle">{t('exports.percent', { value: Math.round(job.progress) })}</span>
							</div>
							<div class="sr-only" aria-live="polite">{spoken}</div>
							<div class="mt-1 h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('exports.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(job.progress)}>
								<div class="h-full rounded-full bg-signal transition-[width] duration-150" style:width="{job.progress}%"></div>
							</div>
							<div class="mt-2 flex justify-end">
								<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => cancelJob(job) }}>{t('exports.cancel')}</HostUi>
							</div>
						{:else if job.status === 'done'}
							<div class="mt-2 flex items-center gap-2" role="status">
								<Icon name="check" class="h-4 w-4 shrink-0 text-success" />
								<span class="min-w-0 flex-1 truncate text-xs text-fg-muted">{t('exports.ready', { file: nameOf(job) })}{job.file?.size ? ` · ${formatBytes(job.file.size)}` : ''}</span>
								{#if library}
									<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: showInLibrary }}>{t('exports.showLibrary')}</HostUi>
								{/if}
								<HostUi name="Button" props={{ variant: 'primary', size: 'xs', icon: hostIconName('export'), onclick: () => downloadJob(job) }}>{t('exports.download')}</HostUi>
							</div>
						{:else if job.status === 'failed'}
							<p class="mt-1.5 text-xs text-danger" role="alert">{jobErrorText(job)}</p>
						{:else}
							<p class="mt-1.5 text-xs text-fg-muted">{t('exports.error.cancelled')}</p>
						{/if}
					</section>
				{/if}

				<section>
					<div class="vp-section-title mb-1.5">{t('exports.history.title')}</div>
					{#if !exportState.loaded && !history.length}
						<p class="text-xs text-fg-subtle">{t('exports.history.loading')}</p>
					{:else if !history.length}
						<p class="text-xs text-fg-subtle">{t('exports.history.empty')}</p>
					{:else}
						<ul class="max-h-40 space-y-0.5 overflow-auto">
							{#each history as j (j.id)}
								<li class="flex min-h-7 items-center gap-2 rounded-md px-2 text-xs odd:bg-surface-2/50">
									<span class="min-w-0 flex-1 truncate text-fg">{formatLabel(j.format)} · <span class="vp-tc">{j.resolution ?? '—'}</span></span>
									<span class="shrink-0 {tone(j.status)}">{statusText(j.status)}</span>
									{#if isJobActive(j)}
										<span class="vp-tc shrink-0 text-fg-subtle">{t('exports.percent', { value: Math.round(j.progress) })}</span>
									{:else}
										<span class="vp-tc shrink-0 text-fg-subtle">{formatRelative(j.finishedAt ?? j.createdAt)}</span>
									{/if}
									{#if j.file?.size}<span class="vp-tc shrink-0 text-fg-subtle">{formatBytes(j.file.size)}</span>{/if}
									<span class="flex shrink-0 items-center">
										{#if j.status === 'done'}
											<HostUi name="IconButton" props={{ icon: hostIconName('export'), label: t('exports.history.download', { file: nameOf(j) }), tooltip: t('exports.history.download', { file: nameOf(j) }), size: 'xs', onclick: () => downloadJob(j) }} />
										{/if}
										{#if !isJobActive(j)}
											<HostUi name="IconButton" props={{ icon: 'trash', label: t('exports.history.delete', { file: nameOf(j) }), tooltip: t('exports.history.delete', { file: nameOf(j) }), size: 'xs', onclick: () => deleteJob(j) }} />
										{/if}
									</span>
								</li>
							{/each}
						</ul>
					{/if}
				</section>
			{:else if simState === 'running'}
				<div class="h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('modals.export.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(simProgress)}>
					<div class="h-full rounded-full bg-signal transition-[width]" style:width="{simProgress}%"></div>
				</div>
			{:else if simState === 'done'}
				<div class="flex gap-2 rounded-lg border border-line-strong bg-surface-1 p-2.5 text-sm" role="status"><Icon name="flask" class="h-4 w-4 text-fg-muted" />{t('modals.export.done')}</div>
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
			<p class="flex items-center gap-1.5 text-xs text-fg-subtle"><Icon name="folder" class="h-3.5 w-3.5 shrink-0" />{t('exports.exchangeNote')}</p>
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
		{#if tab === 'video' && !real}<span class="vp-sim mr-auto"><Icon name="flask" class="h-3 w-3" />{t('modals.export.simulated')}</span>{/if}
		<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', onclick: () => (ui.modal = null) }}>{t('modals.export.close')}</HostUi>
		{#if tab === 'video'}
			{#if real}
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('export'), disabled: ffmpegMissing || running || exportState.starting, onclick: () => startVideoExport({ format, resolution: res }) }}>{t('modals.export.export')}</HostUi>
			{:else if simState !== 'done'}
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('export'), disabled: simState === 'running', onclick: simulate }}>{t('modals.export.export')}</HostUi>
			{/if}
		{:else if tab === 'exchange'}
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('export'), disabled: Boolean(exportState.busy), onclick: () => exportExchange(exchange) }}>{t('modals.export.download', { file: exchangeFile(doc.name, exchange) })}</HostUi>
		{:else}
			<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('export'), disabled: !cues.length || Boolean(exportState.busy), onclick: () => exportExchange('srt') }}>{t('modals.export.download', { file: exchangeFile(doc.name, 'srt') })}</HostUi>
		{/if}
	{/snippet}
</Modal>

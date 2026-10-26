<script>
	import { untrack } from 'svelte';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, clipLabel, fmtDuration } from '../../lib/state.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { upscalesItself } from '../../lib/generation.js';
	import { passFlying, passPlan } from '../../lib/finalpass.js';
	import { cancelFinalPass, guidedReady, guidedResolution, passNoteText, passState, passTargets, savedChoice, schedulePassEstimate, startFinalPass, stopPassEstimate } from '../../lib/finalpass.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';
	import Modal from './Modal.svelte';

	const initial = untrack(savedChoice);
	let method = $state(initial.method);
	let target = $state(initial.target);
	let upscaler = $state(initial.upscaler);
	let redo = $state(false);

	const plan = $derived(passPlan(doc.clips, takeStore.list, redo));
	const sources = $derived(plan.sources);
	const targets = $derived(passTargets());
	const flying = $derived(passFlying(takeStore.list));
	const progress = $derived(flying.length ? flying.reduce((sum, x) => sum + (x.status === 'running' ? Math.min(100, Math.max(0, x.progress ?? 0)) : 0), 0) / flying.length : 0);
	const ownUpscale = $derived(plan.included.some((row) => upscalesItself(row.source?.presetId)));
	const upscaleReady = $derived(ui.me?.features?.upscaler === true || plan.included.every((row) => upscalesItself(row.source?.presetId)));
	const guided = $derived(guidedReady());
	const usable = $derived(method === 'upscale' ? upscaleReady : method === 'guided' ? guided : true);
	const est = $derived(passState.data);
	const blocks = $derived(est && !passState.loading ? est.blocks : []);
	const notes = $derived(est && !passState.loading ? est.warnings : []);
	const sounds = $derived((est?.shots ?? []).filter((shot) => shot.sound).length);
	const count = $derived(sources.length);
	const num = (clip) => String(doc.clips.indexOf(clip) + 1).padStart(2, '0');
	const one = (v) => formatNumber(v ?? 0, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
	const minutes = (v) => formatNumber(v ?? 0, { maximumFractionDigits: 1 });
	const tone = { ready: 'text-fg', running: 'text-signal', done: 'text-success', missing: 'text-warning', source: 'text-fg-subtle' };
	const close = () => (ui.modal = null);

	const methods = $derived([
		{ id: 'upscale', label: t('generation.finalPass.method.upscale') },
		{ id: 'guided', label: t('generation.finalPass.method.guided'), disabled: !guided },
		{ id: 'render', label: t('generation.finalPass.method.render') }
	]);
	const upscalers = $derived([
		{ id: 'auto', label: t('generation.finalPass.upscaler.auto') },
		{ id: 'seedvr2', label: t('generation.finalPass.upscaler.seedvr2'), disabled: ui.me?.features?.upscaler !== true }
	]);

	const hint = $derived.by(() => {
		if (method === 'guided') return guided ? t('generation.finalPass.hint.guided', { res: guidedResolution() }) : t('generation.finalPass.hint.guidedMissing');
		if (method === 'render') return t('generation.finalPass.hint.render');
		return upscaleReady ? t('generation.finalPass.hint.upscale') : t('generation.block.upscaleUnsupported');
	});
	const soundText = $derived(method === 'render' ? t('generation.finalPass.sound.render') : method === 'guided' ? t('generation.finalPass.sound.guided') : t('generation.finalPass.sound.upscale'));

	const estLines = $derived.by(() => {
		if (!count) return [];
		if (!est) return [passState.loading ? t('generation.estimate.loading') : t('generation.estimate.pending')];
		const lines = [est.time.seconds != null ? t('generation.finalPass.estimate.time', { duration: fmtDuration(est.time.seconds), count: est.time.samples }) : t('generation.finalPass.estimate.timeUnknown')];
		const vram = est.vram;
		if (vram && !vram.unknown && vram.estimateGb != null) lines.push(t('generation.estimate.vramNeed', { need: one(vram.estimateGb) }));
		else lines.push(t('generation.estimate.vramUnknown'));
		const quota = est.quota;
		if (quota?.exempt) lines.push(t('generation.estimate.quotaExempt'));
		else if (quota?.applies && quota.limit !== null) lines.push(t('generation.estimate.quota', { need: minutes(quota.neededMinutes), remaining: minutes(quota.remaining), limit: minutes(quota.limit) }));
		else if (quota && !quota.applies) lines.push(t('generation.estimate.noQuota'));
		if (method === 'guided' && est.shots.length) lines.push(t('generation.finalPass.estimate.sounds', { count: sounds, total: est.shots.length }));
		return lines;
	});

	function stateText(row) {
		if (row.state === 'source') return t('generation.finalPass.state.source');
		if (row.state === 'missing') return t('generation.finalPass.state.missing');
		if (row.state === 'running') return row.take?.status === 'running' ? t('generation.finalPass.state.running', { value: Math.round(row.take.progress ?? 0) }) : t('lib.status.queued');
		if (row.state === 'done') return row.include ? t('generation.finalPass.state.redo') : t('generation.finalPass.state.done');
		return t('generation.finalPass.state.ready');
	}

	function sourceText(row) {
		const take = row.state === 'done' && !row.include ? row.final : row.source;
		if (!take) return '';
		const size = take.width && take.height ? `${take.width}×${take.height}` : (take.resolution ?? '').replace('x', '×');
		return [t('generation.finalPass.take', { variant: take.variant }), size].filter(Boolean).join(' · ');
	}

	function targetLabel(id) {
		if (id === 'hd720') return t('generation.target.hd720');
		if (id === 'fhd1080') return t('generation.target.fhd1080');
		if (id === 'qhd1440') return t('generation.target.qhd1440');
		if (id === 'uhd2160') return t('generation.target.uhd2160');
		return id;
	}

	$effect(() => {
		const list = sources;
		const choice = { method, target, upscaler };
		const ready = usable;
		untrack(() => (ready ? schedulePassEstimate(list, choice) : stopPassEstimate()));
	});

	$effect(() => () => stopPassEstimate());

	async function start() {
		if (await startFinalPass(sources, { method, target, upscaler })) close();
	}
</script>

<Modal title={t('generation.finalPass.title')} subtitle={t('generation.finalPass.subtitle', { count: plan.counts.done, total: plan.generated })} icon="arrow-up" width={640}>
	<div class="space-y-4 p-4">
		<p class="text-sm text-fg-muted">{t('generation.finalPass.intro')}</p>
		<section class="space-y-2" aria-label={t('generation.finalPass.method.label')}>
			<span class="vp-label block">{t('generation.finalPass.method.label')}</span>
			<HostUi name="SegmentedControl" props={{ variant: 'toggle', fullWidth: true, ariaLabel: t('generation.finalPass.method.label'), items: methods, selected: method, onSelect: (id) => (method = id) }} />
			<p class="text-xs text-fg-subtle">{hint}</p>
			{#if method === 'upscale'}
				<HostUi name="SegmentedControl" props={{ variant: 'toggle', fullWidth: true, ariaLabel: t('generation.final.target'), items: targets.map((id) => ({ id, label: targetLabel(id), disabled: !upscaleReady })), selected: target, onSelect: (id) => (target = id) }} />
				{#if ownUpscale}
					<div class="flex items-center gap-3">
						<span class="shrink-0 text-xs text-fg-muted">{t('generation.finalPass.upscaler.label')}</span>
						<HostUi name="SegmentedControl" props={{ variant: 'toggle', ariaLabel: t('generation.finalPass.upscaler.label'), items: upscalers, selected: upscaler, onSelect: (id) => (upscaler = id) }} />
					</div>
				{/if}
			{/if}
			<p class="flex items-start gap-1.5 text-xs text-fg-subtle"><Icon name="wave" class="mt-0.5 h-3 w-3 shrink-0" />{soundText}</p>
		</section>

		<section class="space-y-2" aria-label={t('generation.finalPass.shots')}>
			<div class="flex items-center gap-2">
				<span class="vp-label">{t('generation.finalPass.shots')}</span>
				<span class="flex-1"></span>
				{#if plan.counts.done}
					<label for="vp-final-pass-redo" class="text-xs text-fg-muted">{t('generation.finalPass.redo', { count: plan.counts.done })}</label>
					<HostUi name="Switch" props={{ id: 'vp-final-pass-redo', checked: redo, size: 'lg', label: t('generation.finalPass.redo', { count: plan.counts.done }), onchange: (v) => (redo = Boolean(v)) }} />
				{/if}
			</div>
			<ul class="overflow-auto rounded-lg border border-line" style:max-height="13rem">
				{#each plan.rows as row (row.clip.id)}
					<li class="flex min-h-8 items-center gap-2.5 border-b border-line px-2.5 py-1 text-xs last:border-b-0 {row.include ? '' : 'text-fg-muted'}">
						<span class="vp-tc text-fg-subtle">{num(row.clip)}</span>
						<span class="min-w-0 flex-1 truncate {row.include ? 'text-fg' : ''}">{clipLabel(row.clip)}</span>
						{#if row.stale}<span class="flex shrink-0 items-center gap-1 text-warning" title={t('generation.card.staleTip')}><Icon name="pencil" class="h-3 w-3" />{t('generation.card.stale')}</span>{/if}
						{#if row.failed && row.state === 'ready'}<span class="flex shrink-0 items-center gap-1 {row.failed.status === 'failed' ? 'text-danger' : 'text-fg-subtle'}"><Icon name={row.failed.status === 'failed' ? 'alert' : 'x'} class="h-3 w-3" />{row.failed.status === 'failed' ? t('generation.finalPass.lastFailed') : t('generation.finalPass.lastCancelled')}</span>{/if}
						<span class="vp-tc shrink-0 text-fg-subtle">{sourceText(row)}</span>
						<span class="w-32 shrink-0 text-right {tone[row.state]}">{stateText(row)}</span>
					</li>
				{/each}
			</ul>
			{#if plan.missing.length}
				<p class="flex items-start gap-1.5 text-xs text-warning" role="status"><Icon name="alert" class="mt-0.5 h-3 w-3 shrink-0" />{t('generation.finalPass.missing', { count: plan.missing.length, shots: plan.missing.map(num).join(', ') })}</p>
			{/if}
		</section>

		{#if flying.length}
			<section class="space-y-1.5 rounded-lg border border-line p-2.5" aria-label={t('generation.finalPass.runningTitle')}>
				<div class="flex items-center gap-2 text-xs">
					<HostUi name="Spinner" props={{ size: 'sm' }} />
					<span class="text-fg">{t('generation.finalPass.running', { count: flying.length })}</span>
					<span class="vp-tc ml-auto text-fg-muted">{t('exports.percent', { value: Math.round(progress) })}</span>
				</div>
				<div class="h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('generation.finalPass.runningTitle')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(progress)}>
					<div class="h-full rounded-full bg-signal transition-[width] duration-150" style:width="{progress}%"></div>
				</div>
			</section>
		{/if}

		{#if count}
			<section class="space-y-1 text-xs" aria-label={t('generation.finalPass.estimate.label')}>
				{#each estLines as line, i (i)}
					<p class="flex items-start gap-1.5 {i ? 'text-fg-subtle' : 'text-fg-muted'} {passState.loading ? 'opacity-60' : ''}">{#if !i}<Icon name="history" class="mt-0.5 h-3 w-3 shrink-0" />{/if}<span style:padding-left={i ? '1.125rem' : null}>{line}</span></p>
				{/each}
				{#each blocks as block, i (i)}
					<p class="flex items-start gap-1.5 text-danger"><Icon name="alert" class="mt-0.5 h-3 w-3 shrink-0" />{passNoteText(block)}</p>
				{/each}
				{#each notes as note, i (i)}
					<p class="flex items-start gap-1.5 text-warning"><Icon name="alert" class="mt-0.5 h-3 w-3 shrink-0" />{passNoteText(note)}</p>
				{/each}
				{#if passState.error}
					<p class="flex items-start gap-1.5 text-warning"><Icon name="alert" class="mt-0.5 h-3 w-3 shrink-0" />{t('generation.finalPass.estimate.failed')}</p>
				{/if}
			</section>
		{:else if !flying.length}
			<p class="text-xs text-fg-subtle">{plan.counts.done && plan.counts.done === plan.generated ? t('generation.finalPass.allDone') : t('generation.finalPass.nothing')}</p>
		{/if}
	</div>
	{#snippet footer()}
		{#if flying.length}
			<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', class: 'mr-auto', disabled: passState.cancelling, onclick: cancelFinalPass }}>{t('generation.finalPass.cancelPass', { count: flying.length })}</HostUi>
		{/if}
		<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: close }}>{t('generation.finalPass.close')}</HostUi>
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: hostIconName('arrow-up'), disabled: !count || !usable || passState.sending || blocks.length > 0, onclick: start }}>
			{plan.missing.length ? t('generation.finalPass.startWithout', { count }) : t('generation.finalPass.start', { count })}
		</HostUi>
	{/snippet}
</Modal>

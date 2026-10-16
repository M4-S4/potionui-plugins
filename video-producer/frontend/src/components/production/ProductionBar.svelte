<script>
	import { fade } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, readiness, startGeneration, pauseGeneration, resumeGeneration, cancelGeneration, queueWindow, openResults, secs, allIssues, fmtDuration, backend } from '../../lib/state.svelte.js';
	import { backends, engineName, modeLabel } from '../../lib/catalog.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	const modes = ['Génération IA', 'Rendu 3D', 'Rendu 3D + IA'];

	const p = $derived(ui.production);
	const ready = $derived(readiness());
	const it = $derived(ready.items);
	const est = $derived(ready.est);
	const be = $derived(backend());
	const conflicts = $derived(allIssues().filter((i) => i.level !== 'missing' && it.prompts.includes(i.prompt)));
	const status = $derived(p.state === 'running' ? 'running' : p.state === 'paused' ? 'paused' : p.state === 'done' ? 'done' : ready.missing.length ? 'missing' : 'ready');
	const busy = $derived(status === 'running' || status === 'paused');
	const blocked = $derived(ready.missing.length > 0);
	const notes = $derived(blocked ? ready.missing : ready.warnings);
	const primary = $derived(p.mode === 'Rendu 3D' ? t('production.prepareRender') : t('production.generate'));
	const targets = $derived([
		{ id: 'clip', label: t('production.target.clip') },
		{ id: 'range', label: t('production.target.range') },
		{ id: 'sequence', label: t('production.target.sequence') }
	]);
	const qualities = $derived([
		{ id: 'draft', label: t('production.quality.draft') },
		{ id: 'final', label: t('production.quality.final') }
	]);
	const one = (v) => formatNumber(v, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
	const money = (v) => formatNumber(v, { style: 'currency', currency: 'EUR' });
	const scope = $derived(
		[
			t('production.count.shots', { count: est.clips.length }),
			t('production.count.prompts', { count: it.prompts.length }),
			t('production.count.frames', { count: it.frames.length }),
			t('production.count.references', { count: it.references.length }),
			it.controls.length ? t('production.count.controls', { count: it.controls.length }) : ''
		]
			.filter(Boolean)
			.join(' · ')
	);
	const showCost = $derived(Boolean(be.cost) && ui.isAdmin);
	const estTip = $derived(
		[
			t('production.estimate.windows', { shots: t('production.count.shots', { count: est.clips.length }), variants: t('production.count.variants', { count: doc.engine.variants }), res: est.res }),
			t('production.estimate.gpu', { duration: fmtDuration(est.gpuSec), engine: engineName(be) }),
			t('production.estimate.vram', { need: est.vram, have: be.vram }),
			be.cost ? (showCost ? t('production.estimate.cost', { cost: money(est.cost) }) : '') : ui.quota ? t('production.estimate.quota', { used: Math.round(ui.quota.used), need: one(est.quotaMin), limit: ui.quota.limit }) : '',
			t('production.estimate.simulated')
		]
			.filter(Boolean)
			.join(' · ')
	);
	const over = $derived(est.overVram || est.overQuota);
	const queueTip = $derived(p.queue.length ? `${t('production.queue')} · ${t('production.queued', { count: p.queue.length })}` : t('production.queue'));

	function pick(id) {
		p.target = id;
		if (id === 'range' && !ui.range) ui.range = { in: ready.range[0], out: ready.range[1] };
	}

	function directionIssues() {
		ui.workspace = 'director';
		ui.dockTab = 'direction';
	}
</script>

<div class="flex h-11 items-center gap-2 border-b border-line bg-surface-1 px-3" role="region" aria-label={t('production.region')}>
	<HostUi name="SegmentedControl" props={{ items: targets, selected: p.target, variant: 'toggle', ariaLabel: t('production.target.label'), onSelect: pick }} />
	<HostUi name="Tooltip" props={{ text: scope, wrapperClass: 'flex shrink-0' }}>
		<div class="flex flex-col pl-1 leading-tight">
			<span class="vp-tc whitespace-nowrap text-sm text-fg">{secs(ready.range[0])} → {secs(ready.range[1])}</span>
			<span class="flex items-center gap-1 whitespace-nowrap text-xs text-fg-subtle">
				{t('production.count.shots', { count: est.clips.length })} · {t('production.count.prompts', { count: it.prompts.length })}
				{#if conflicts.length}
					<HostUi name="Tooltip" props={{ text: conflicts.map((c) => c.text).join(' · ') }}>
						<button type="button" class="ml-0.5 flex min-h-6 items-center gap-0.5 text-warning hover:underline" aria-label={t('production.conflicts', { count: conflicts.length })} onclick={directionIssues}>
							<Icon name="alert" class="h-3 w-3" />{conflicts.length}
						</button>
					</HostUi>
				{/if}
			</span>
		</div>
	</HostUi>

	<div class="vp-divider"></div>

	<HostUi name="Tooltip" props={{ text: p.quality === 'draft' ? t('production.quality.draftTip') : t('production.quality.finalTip', { resolution: doc.engine.resolution }) }}>
		<HostUi name="SegmentedControl" props={{ items: qualities, selected: p.quality, variant: 'toggle', ariaLabel: t('production.quality.label'), onSelect: (id) => (ui.production.quality = id) }} />
	</HostUi>
	<select class="vp-popup" bind:value={ui.production.mode} disabled={busy} aria-label={t('production.mode.label')}>
		{#each modes as m (m)}<option value={m}>{modeLabel(m)}</option>{/each}
	</select>
	<HostUi name="Tooltip" props={{ text: t('production.engine.tip', { name: engineName(be), vram: be.vram }), wrapperClass: 'hidden items-center min-[1400px]:inline-flex' }}>
		<select class="vp-popup" bind:value={doc.engine.backend} aria-label={t('production.engine.label')}>
			{#each backends as b (b.id)}<option value={b.id}>{engineName(b)}</option>{/each}
		</select>
	</HostUi>
	<HostUi
		name="IconButton"
		props={{ icon: hostIconName('sliders'), label: t('production.advanced'), tooltip: t('production.advanced'), kbd: commandById('advanced')?.key, size: 'sm', class: 'vp-h7', onclick: () => (ui.modal = { type: 'advanced', step: 0 }) }}
	/>

	<div class="flex-1"></div>

	<div class="flex min-w-0 items-center gap-2" aria-live="polite">
		{#if busy}
			<div class="w-44" in:fade={{ duration: ms(120) }}>
				<div class="flex justify-between gap-2 text-xs">
					<span class="truncate {status === 'paused' ? 'text-warning' : 'text-signal'}">{status === 'paused' ? t('production.paused') : p.step}</span>
					<span class="vp-tc text-fg-muted">{Math.round(p.progress)} %</span>
				</div>
				<div class="mt-1 h-1 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-label={t('production.progress')} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(p.progress)}>
					<div class="h-full rounded-full bg-signal transition-[width] duration-150" style:width="{p.progress}%"></div>
				</div>
			</div>
			{#if status === 'running'}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('pause'), onclick: pauseGeneration }}>{t('production.pause')}</HostUi>
			{:else}
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('play'), onclick: resumeGeneration }}>{t('production.resume')}</HostUi>
			{/if}
			<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: cancelGeneration }}>{t('production.cancel')}</HostUi>
		{:else}
			{#if status === 'done'}
				<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', onclick: openResults }}>
					<Icon name="check" class="h-3.5 w-3.5 text-success" />{t('production.ready', { count: p.lastCount })}
				</HostUi>
			{/if}
			{#if notes.length}
				<HostUi name="Tooltip" props={{ text: notes.join(' · '), wrapperClass: 'flex min-w-3.5' }}>
					<span class="vp-notice text-xs text-warning"><Icon name="alert" class="h-3.5 w-3.5 shrink-0" /><span class="vp-notice-text">{notes[0]}</span></span>
				</HostUi>
			{/if}
			<HostUi name="Tooltip" props={{ text: estTip, wrapperClass: 'inline-flex shrink-0 items-center' }}>
				<span class="flex items-center gap-1.5 whitespace-nowrap text-xs {over ? 'text-warning' : 'text-fg-muted'}">
					<Icon name={over ? 'alert' : 'history'} class="h-3.5 w-3.5" />
					<span class="vp-tc">≈ {fmtDuration(est.gpuSec)}</span>
					<span class="text-fg-subtle">·</span>
					<span class="vp-tc">{t('production.estimate.vramShort', { value: est.vram })}</span>
					{#if !be.cost || showCost}
						<span class="hidden text-fg-subtle min-[1500px]:inline">·</span>
						<span class="vp-tc hidden min-[1500px]:inline">{showCost ? money(est.cost) : t('production.estimate.quotaShort', { value: one(est.quotaMin) })}</span>
					{/if}
				</span>
			</HostUi>
			<HostUi name="IconButton" props={{ icon: hostIconName('list'), label: t('production.queueLabel'), tooltip: queueTip, kbd: commandById('queue')?.key, size: 'sm', class: 'vp-h7', disabled: blocked, onclick: queueWindow }} />
			<HostUi name="Tooltip" props={{ text: primary, kbd: commandById('generate')?.key }}>
				<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'sparkles', class: 'h-8 px-3.5', disabled: blocked, onclick: () => startGeneration() }}>{primary}</HostUi>
			</HostUi>
		{/if}
	</div>
</div>

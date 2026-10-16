<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, takesOf, useTake, promoteToFinal, startGeneration, estimate, fmtDuration, toast } from '../../lib/state.svelte.js';
	import { takeThumb } from '../../lib/media.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let { clip } = $props();
	const takes = $derived(takesOf(clip));
	const groups = $derived(
		[
			['final', t('inspector.takes.final'), takes.filter((r) => r.quality === 'final')],
			['draft', t('inspector.takes.drafts'), takes.filter((r) => r.quality === 'draft')]
		].filter(([, , list]) => list.length)
	);
	const busy = $derived(ui.production.state === 'running' || ui.production.state === 'paused');
	const draftEst = $derived(estimate({ seconds: clip.dur, quality: 'draft' }));
	const finalEst = $derived(estimate({ seconds: clip.dur, quality: 'final', variants: 1 }));

	function compare(r) {
		const c = ui.compare ? [...ui.compare] : [];
		const i = c.indexOf(r.id);
		i >= 0 ? c.splice(i, 1) : c.push(r.id);
		ui.compare = c.slice(-2);
		ui.preview = null;
		if (ui.compare.length === 1) toast(t('inspector.takes.pickSecond'));
	}
</script>

{#if !takes.length}
	<HostUi name="EmptyState" props={{ compact: true, icon: 'layers', title: t('inspector.takes.empty'), description: t('inspector.takes.emptyHint') }} />
{/if}

{#each groups as [key, title, list] (key)}
	<section class="space-y-1.5">
		<div class="vp-section-title">{title} · {list.length}</div>
		<ul class="grid grid-cols-2 gap-2">
			{#each list as take (take.id)}
				{@const active = clip.take === take.id}
				{@const cmp = ui.compare?.includes(take.id)}
				<li class="overflow-hidden rounded-lg border transition-colors {active ? 'border-signal ring-1 ring-signal' : cmp ? 'border-signal/60' : 'border-line-strong hover:border-line-hover'}">
					<HostUi name="Tooltip" props={{ text: t('inspector.takes.use'), wrapperClass: 'block w-full' }}>
						<button
							type="button"
							class="relative block aspect-video w-full"
							aria-label={t('inspector.takes.useLabel', { variant: take.variant })}
							aria-pressed={active}
							onclick={() => useTake(clip, take.id)}
							ondblclick={() => (ui.preview = { kind: 'result', id: take.id })}
						>
							<img src={takeThumb(take)} alt="" class="h-full w-full object-cover" />
							<span class="absolute left-1 top-1 rounded bg-black/60 px-1 text-xs font-semibold text-white">{take.variant}</span>
							{#if active}<span class="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full border border-signal bg-surface-1 text-signal"><Icon name="check" class="h-3 w-3" strokeWidth={2.5} /></span>{/if}
							{#if take.status === 'redo'}<span class="absolute bottom-1 left-1 flex items-center gap-1 rounded bg-black/60 px-1 text-2xs text-white"><span class="h-1.5 w-1.5 rounded-full bg-warning-solid"></span>{t('inspector.takes.redo')}</span>{/if}
							{#if take.parent}<span class="absolute bottom-1 right-1 rounded bg-black/60 px-1 text-2xs text-white">{t('inspector.takes.from', { variant: doc.results.find((r) => r.id === take.parent)?.variant ?? '—' })}</span>{/if}
						</button>
					</HostUi>
					<div class="flex items-center gap-0.5 p-0.5">
						<HostUi name="IconButton" props={{ icon: hostIconName('eye'), label: t('inspector.takes.previewLabel', { variant: take.variant }), tooltip: t('inspector.takes.preview'), size: 'xs', onclick: () => (ui.preview = { kind: 'result', id: take.id }) }} />
						<HostUi
							name="IconButton"
							props={{ icon: hostIconName('compare'), label: t('inspector.takes.compareLabel', { variant: take.variant }), tooltip: t('inspector.takes.compare'), size: 'xs', class: 'vp-toggle', ariaPressed: !!cmp, onclick: () => compare(take) }}
						/>
						<HostUi
							name="IconButton"
							props={{
								icon: hostIconName('flag'),
								label: t('inspector.takes.flagLabel', { variant: take.variant }),
								tooltip: t('inspector.takes.flag'),
								size: 'xs',
								class: 'vp-toggle',
								ariaPressed: take.status === 'redo',
								onclick: () => act(() => (take.status = take.status === 'redo' ? 'new' : 'redo'))
							}}
						/>
						<HostUi name="IconButton" props={{ icon: 'info', label: t('inspector.takes.infoLabel', { variant: take.variant }), tooltip: t('inspector.takes.info'), size: 'xs', onclick: () => (ui.modal = { type: 'recap', result: take.id }) }} />
						{#if take.quality === 'draft'}
							<span class="ml-auto">
								<HostUi name="Tooltip" props={{ text: t('inspector.takes.promoteTip', { duration: fmtDuration(finalEst.gpuSec) }) }}>
									<button type="button" class="h-6 rounded px-1.5 text-xs font-medium text-signal hover:bg-surface-2 disabled:text-fg-disabled" onclick={() => promoteToFinal(take.id)} disabled={busy}>{t('inspector.takes.promote')}</button>
								</HostUi>
							</span>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	</section>
{/each}

<div class="space-y-1.5 rounded-lg bg-surface-2/60 p-2.5">
	<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: 'sparkles', class: 'w-full', disabled: busy, onclick: () => startGeneration({ clips: [clip], quality: 'draft' }) }}>
		<span class="flex-1 text-left">{t('inspector.takes.more', { count: doc.engine.variants })}</span>
		<span class="text-fg-muted">≈ {fmtDuration(draftEst.gpuSec)}</span>
	</HostUi>
	<p class="text-xs text-fg-muted">{t('inspector.takes.note', { res: draftEst.res, final: doc.engine.resolution })}</p>
</div>

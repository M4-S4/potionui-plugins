<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs } from '../../lib/state.svelte.js';
	import { retryTake, openEngineSettings, backendName, presetById } from '../../lib/production.svelte.js';
	import { FAILURE_CODES, presetLabel } from '../../lib/generation.js';
	import { instructionPromptOf } from '../../lib/bible.js';
	import { failureFixes } from '../../lib/director.js';
	import { showInReview, showInStoryboard } from '../../lib/band.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import ShotSummary from './ShotSummary.svelte';
	import Icon from '../Icon.svelte';

	let { clip, take } = $props();

	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const previous = $derived(doc.clips[doc.clips.indexOf(clip) - 1] ?? null);
	const errorText = $derived(FAILURE_CODES.includes(take.errorCode) ? t(`generation.failed.${take.errorCode}`, { id: take.generationId ?? '—' }) : take.errorMessage || t('generation.card.error', { code: take.errorCode ?? '—' }));
	const resolution = $derived(take.width && take.height ? `${take.width}×${take.height}` : (take.resolution ?? '').replace('x', '×'));
	const asked = $derived([resolution, secs(clip.dur)].filter(Boolean).join(' · '));
	const engineText = $derived([presetLabel(presetById(take.presetId)) || '', take.profile, take.backendId ? backendName(take.backendId) : ''].filter(Boolean).join(' · ') || '—');

	function editInstruction() {
		const prompt = instructionPromptOf(doc, clip);
		ui.modal = prompt ? { type: 'prompt', id: prompt.id } : { type: 'shot', id: clip.id };
	}

	const fixes = $derived(
		failureFixes(take)
			.map((id) => {
				if (id === 'retry') return { id, icon: 'refresh', title: t('panels.director.pick.fix.retry', { variant: take.variant }), hint: t('panels.director.pick.fix.retryHint'), run: () => retryTake(take) };
				if (id === 'engine') return { id, icon: 'sliders', title: t('panels.director.pick.fix.engine'), hint: t('panels.director.pick.fix.engineHint'), run: () => openEngineSettings() };
				if (id === 'shorter') return { id, icon: 'range', title: t('panels.director.pick.fix.shorter', { shot: num(clip) }), hint: t('panels.director.pick.fix.shorterHint'), run: () => showInStoryboard(clip) };
				if (id === 'instruction') return { id, icon: 'pencil', title: t('panels.director.aside.edit', { shot: num(clip) }), hint: t('panels.director.pick.fix.instructionHint'), run: editInstruction };
				if (id === 'previous' && previous) return { id, icon: 'layers', title: t('panels.director.pick.fix.previous', { shot: num(previous) }), hint: t('panels.director.pick.fix.previousHint', { shot: num(previous) }), run: () => showInReview(previous) };
				return null;
			})
			.filter(Boolean)
	);
</script>

<section class="space-y-2" data-take-failure={take.errorCode ?? ''}>
	<div class="vp-section-title">{t('panels.director.pick.what')}</div>
	<HostUi name="Alert" props={{ variant: 'danger', class: '[&>div]:text-fg', density: 'compact', icon: hostIconName('alert'), live: 'off' }}>
		<p class="text-xs">{errorText}</p>
	</HostUi>
	<dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
		<dt class="text-fg-subtle">{t('panels.director.pick.asked')}</dt>
		<dd class="vp-tc min-w-0 truncate text-fg-muted">{asked}</dd>
		<dt class="text-fg-subtle">{t('panels.director.pick.engine')}</dt>
		<dd class="min-w-0 truncate text-fg-muted" title={engineText}>{engineText}</dd>
	</dl>
</section>

<section class="space-y-2">
	<div class="vp-section-title">{t('panels.director.pick.todo')}</div>
	{#each fixes as fix (fix.id)}
		<button type="button" class="flex w-full items-start gap-2.5 rounded-lg border border-line-strong p-2.5 text-left transition-colors hover:border-line-hover hover:bg-surface-2" data-take-fix={fix.id} onclick={fix.run}>
			<Icon name={fix.icon} class="mt-px h-3.5 w-3.5 shrink-0 text-fg-muted" />
			<span class="min-w-0 flex-1 space-y-0.5">
				<span class="block text-xs font-medium text-fg">{fix.title}</span>
				<span class="block text-xs text-fg-subtle">{fix.hint}</span>
			</span>
		</button>
	{/each}
</section>

<ShotSummary {clip} />

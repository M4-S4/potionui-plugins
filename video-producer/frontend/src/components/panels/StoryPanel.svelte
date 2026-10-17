<script>
	import { slide } from 'svelte/transition';
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ms } from '../../lib/motion.js';
	import { ui, doc, select, clipLabel, proposeShots, acceptProposal, secs } from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { stages } from '../../lib/catalog.js';
	import { seams, matchToPrevious } from '../../lib/continuity.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import PanelHeader from './PanelHeader.svelte';
	import Icon from '../Icon.svelte';

	const open = $derived(doc.clips.filter((c) => c.stage === 'todo' || c.stage === 'draft'));
	const allSeams = $derived(seams());
	const issues = $derived(allSeams.flatMap((s) => s.issues.map((x) => ({ ...x, clip: s.to }))));
	const measured = $derived(allSeams.some((s) => s.measured));
	const todo = $derived(doc.clips.filter((c) => c.stage === 'todo'));
	const footage = (list) => t('generation.story.footage', { count: list.length, duration: secs(list.reduce((sum, c) => sum + c.dur, 0)) });
	const kept = $derived(ui.storyProposal?.filter((x) => x.keep).length ?? 0);
</script>

<PanelHeader icon="grid" title={t('panels.story.title')} />

<div class="flex min-h-0 flex-1 flex-col gap-5 overflow-auto p-3">
	<section>
		<div class="mb-1.5 flex items-center justify-between">
			<label for="vp-synopsis" class="vp-section-title">{t('panels.story.synopsis')}</label>
			<span class="vp-tc text-xs text-fg-subtle">{t('panels.story.chars', { chars: doc.synopsis.length })}</span>
		</div>
		<textarea id="vp-synopsis" class="input text-sm leading-5" rows="5" bind:value={doc.synopsis} placeholder={t('panels.story.placeholder')}></textarea>
		<div class="mt-2">
			<HostUi name="Tooltip" props={{ text: t('panels.story.proposeTip'), wrapperClass: 'flex w-full' }}>
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('wand'), class: 'w-full', disabled: !doc.synopsis.trim(), onclick: proposeShots }}>{t('panels.story.propose')}</HostUi>
			</HostUi>
		</div>
	</section>

	{#if ui.storyProposal}
		<section class="rounded-xl border border-signal/40 bg-signal/5 p-2.5" transition:slide={{ duration: ms(180) }}>
			<div class="mb-2 flex items-center justify-between">
				<span class="text-sm font-medium">{t('panels.story.proposal')}</span>
				<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('panels.story.closeProposal'), tooltip: t('panels.story.closeProposal'), size: 'xs', onclick: () => (ui.storyProposal = null) }} />
			</div>
			<ol class="space-y-1.5">
				{#each ui.storyProposal as sp (sp.id)}
					<li class="flex items-start gap-2 rounded-lg bg-surface-1 p-2">
						<label class="-m-1 flex h-6 w-6 shrink-0 cursor-pointer items-center justify-center">
							<input type="checkbox" class="h-4 w-4" bind:checked={sp.keep} aria-label={t('panels.story.keep', { n: sp.n })} />
						</label>
						<div class="min-w-0 flex-1">
							<input class="w-full bg-transparent text-sm font-medium focus:outline-none" bind:value={sp.label} aria-label={t('panels.story.shotName', { n: sp.n })} />
							<p class="line-clamp-2 text-xs text-fg-subtle">{sp.prompt}</p>
						</div>
						<span class="vp-tc shrink-0 text-xs text-fg-muted">{t('panels.story.seconds', { dur: sp.dur })}</span>
					</li>
				{/each}
			</ol>
			<div class="mt-2.5">
				<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', class: 'w-full', disabled: !kept, onclick: acceptProposal }}>{t('panels.story.accept', { count: kept })}</HostUi>
			</div>
		</section>
	{/if}

	<section>
		<div class="vp-section-title mb-1.5">{t('panels.story.toProduce')}</div>
		{#if open.length}
			<ul class="space-y-0.5">
				{#each open as c (c.id)}
					<li>
						<button
							type="button"
							class="flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left text-sm hover:bg-surface-2 {ui.selection?.id === c.id ? 'border-signal bg-surface-2' : 'border-transparent'}"
							onclick={() => (select('clip', c.id), seek(c.start))}
						>
							<span class="h-1.5 w-1.5 shrink-0 rounded-full {stages[c.stage].dot}"></span>
							<span class="min-w-0 flex-1 truncate">{clipLabel(c)}</span>
							<span class="text-xs {ui.selection?.id === c.id ? 'text-fg' : 'text-fg-muted'}">{stages[c.stage].label}</span>
						</button>
					</li>
				{/each}
			</ul>
			<div class="mt-2 grid grid-cols-2 gap-2 text-xs">
				<div class="rounded-lg border border-line-strong p-2">
					<div class="text-fg-subtle">{t('panels.story.draftsLeft')}</div>
					<div class="vp-tc mt-0.5 text-sm text-fg">{footage(todo)}</div>
				</div>
				<div class="rounded-lg border border-line-strong p-2">
					<div class="text-fg-subtle">{t('panels.story.toFinal')}</div>
					<div class="vp-tc mt-0.5 text-sm text-fg">{footage(open)}</div>
				</div>
			</div>
			<p class="mt-2 text-xs text-fg-subtle">{t('panels.story.sequenceHint')}</p>
		{:else if !doc.clips.length}
			<p class="text-xs text-fg-subtle">{t('panels.story.noShots')}</p>
		{:else}
			<p class="flex items-center gap-2 rounded-lg border border-success/40 bg-success/5 p-2.5 text-xs text-success"><Icon name="check" class="h-3.5 w-3.5" />{t('panels.story.allDone')}</p>
		{/if}
	</section>

	<section>
		<div class="vp-section-title mb-1.5">{t('panels.story.continuity')}</div>
		{#if issues.length}
			<ul class="space-y-1.5">
				{#each issues as i, n (n)}
					<li>
						<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: i.kind === 'identity' ? 'user' : hostIconName('palette'), live: 'off' }}>
							<div class="text-xs text-fg-muted">{i.text}</div>
							{#if i.fix}<button type="button" class="vp-link-hit mt-1.5 text-xs text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => matchToPrevious(i.clip)}>{t('panels.story.matchColor')}</button>{/if}
						</HostUi>
					</li>
				{/each}
			</ul>
		{:else if measured}
			<p class="flex items-center gap-2 text-xs text-fg-subtle"><Icon name="link" class="h-3.5 w-3.5" />{t('panels.story.continuityOk')}</p>
		{:else}
			<p class="flex items-center gap-2 text-xs text-fg-subtle"><Icon name="link" class="h-3.5 w-3.5" />{t('panels.story.continuityNone')}</p>
		{/if}
	</section>
</div>

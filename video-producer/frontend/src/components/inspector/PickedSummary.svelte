<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc, secs, clipLabel, pickedClips, clearPicked } from '../../lib/state.svelte.js';
	import { shotActivity } from '../../lib/production.svelte.js';
	import { pickShot } from '../../lib/band.svelte.js';
	import { stages } from '../../lib/catalog.js';
	import { clickLabel, commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	const clips = $derived(pickedClips());
	const total = $derived(clips.reduce((sum, c) => sum + c.dur, 0));
	const counts = $derived(Object.keys(stages).map((k) => [k, clips.filter((c) => c.stage === k).length]).filter(([, n]) => n));
	const running = $derived(clips.filter((c) => shotActivity(c.id).state === 'running').length);
	const generateKey = $derived(commandById('generate')?.key ?? '');
</script>

<section class="space-y-3" aria-label={t('storyboard.pick.count', { count: clips.length })} data-picked-summary={clips.length}>
	<div class="flex items-center gap-2.5">
		<span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-signal" style:background="rgb(var(--signal) / 0.12)"><Icon name="layers" class="h-4 w-4" /></span>
		<div class="min-w-0 flex-1">
			<div class="truncate text-sm font-medium">{t('storyboard.pick.count', { count: clips.length })}</div>
			<div class="flex flex-wrap items-center gap-x-2 text-xs text-fg-subtle">
				<span class="vp-tc">{secs(total)}</span>
				{#each counts as [k, n] (k)}<span class="flex items-center gap-1 {stages[k].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[k].dot}"></span>{stages[k].label} {n}</span>{/each}
			</div>
		</div>
	</div>
	<ol class="space-y-0.5">
		{#each clips as c (c.id)}
			{@const busy = shotActivity(c.id).state === 'running'}
			<li>
				<button type="button" class="flex min-h-7 w-full items-center gap-2 rounded px-1.5 text-left text-xs hover:bg-surface-2" title={t('storyboard.pick.only', { shot: clipLabel(c) })} onclick={() => pickShot(c)}>
					<span class="vp-tc w-5 shrink-0 text-fg-subtle">{String(doc.clips.indexOf(c) + 1).padStart(2, '0')}</span>
					<span class="h-1.5 w-1.5 shrink-0 rounded-full {stages[c.stage].dot}"></span>
					<span class="min-w-0 flex-1 truncate text-fg">{clipLabel(c)}</span>
					{#if busy}<Icon name="history" class="h-3 w-3 shrink-0 text-signal" />{/if}
					<span class="vp-tc shrink-0 text-fg-subtle">{secs(c.dur)}</span>
				</button>
			</li>
		{/each}
	</ol>
	<div class="space-y-1.5 rounded-xl border border-dashed border-line-hover p-3 text-xs text-fg-muted">
		<p class="text-fg">{t('storyboard.pick.generateHint', { key: generateKey })}</p>
		{#if running}<p>{t('storyboard.pick.running', { count: running })}</p>{/if}
		<p>{t('storyboard.pick.hint', { toggle: clickLabel('mod'), range: clickLabel('shift'), esc: t('commands.kbd.escape') })}</p>
	</div>
	<HostUi name="Button" props={{ variant: 'secondary', size: 'sm', icon: hostIconName('x'), class: 'w-full', onclick: clearPicked }}>{t('storyboard.pick.clear')}</HostUi>
</section>

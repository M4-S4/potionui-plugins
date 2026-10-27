<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc } from '../../lib/state.svelte.js';
	import { CHARACTERS, PLACES, castOf, cardsOf, instructionOf, labelOf } from '../../lib/bible.js';
	import { effectiveEngine, hasOwnEngine } from '../../lib/engine.js';
	import { engineOptionLabel } from '../../lib/production.svelte.js';
	import { showInStoryboard } from '../../lib/band.svelte.js';
	import { CARD_ICONS } from '../../lib/reftags.js';
	import { hostIconName } from '../../lib/icons.js';
	import Icon from '../Icon.svelte';

	let { clip } = $props();

	const text = $derived(instructionOf(doc, clip));
	const cast = $derived.by(() => {
		const own = castOf(clip);
		const people = cardsOf(doc, CHARACTERS).filter((c) => own.characters.includes(c.id));
		const place = cardsOf(doc, PLACES).find((c) => c.id === own.place);
		return [...people.map((card) => [CHARACTERS, card]), ...(place ? [[PLACES, place]] : [])].filter(([, card]) => labelOf(card));
	});
	const engine = $derived(effectiveEngine(clip, doc));
	const engineText = $derived([engineOptionLabel(engine.preset, engine.model), engine.profile, hasOwnEngine(clip) ? t('panels.director.pick.ownEngine') : ''].filter(Boolean).join(' · '));
</script>

<section class="space-y-2 border-t border-line pt-3" data-shot-summary={clip.id}>
	<div class="flex items-center gap-2">
		<span class="vp-section-title min-w-0 flex-1">{t('panels.director.pick.shot')}</span>
		<HostUi name="Tooltip" props={{ text: t('panels.director.pick.storyboardTip'), wrapperClass: 'inline-flex' }}>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('grid'), onclick: () => showInStoryboard(clip) }}>{t('panels.director.pick.storyboard')}</HostUi>
		</HostUi>
	</div>
	<p class="line-clamp-3 text-xs text-fg-muted" title={text || null}>{text || t('panels.director.pick.noInstruction')}</p>
	<dl class="grid grid-cols-[auto_1fr] items-start gap-x-3 gap-y-1.5 text-xs">
		<dt class="text-fg-subtle">{t('inspector.section.cast')}</dt>
		<dd class="flex min-w-0 flex-wrap gap-1">
			{#each cast as [kind, card] (card.id)}
				<span class="inline-flex max-w-full items-center gap-1 rounded border border-line-strong px-1.5 text-fg-muted"><Icon name={CARD_ICONS[kind]} class="h-3 w-3 shrink-0" /><span class="truncate">{labelOf(card)}</span></span>
			{:else}
				<span class="text-fg-subtle">{t('panels.director.pick.nobody')}</span>
			{/each}
		</dd>
		<dt class="text-fg-subtle">{t('panels.director.pick.engine')}</dt>
		<dd class="min-w-0 truncate text-fg-muted" title={engineText}>{engineText}</dd>
	</dl>
</section>

<script>
	import { t } from '../../i18n/index.svelte.js';
	import { doc } from '../../lib/state.svelte.js';
	import { CHARACTERS, PLACES, castCards, castOf, cardsOf, labelOf, missingLabels, usable } from '../../lib/bible.js';

	let { cast, text = '', onchange, onopen = null } = $props();

	const chosen = $derived(castOf({ cast }));
	const characters = $derived(cardsOf(doc, CHARACTERS).filter(usable));
	const places = $derived(cardsOf(doc, PLACES).filter(usable));
	const missing = $derived(missingLabels(text, castCards(doc, cast).characters));

	function toggle(id, on) {
		onchange({ ...chosen, characters: on ? [...chosen.characters, id] : chosen.characters.filter((x) => x !== id) });
	}
</script>

{#if !characters.length && !places.length}
	<p class="text-xs text-fg-subtle">
		{t('modals.shot.castEmpty')}
		{#if onopen}<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={onopen}>{t('modals.shot.castOpen')}</button>{/if}
	</p>
{:else}
	<div class="space-y-2">
		{#if characters.length}
			<div class="space-y-1">
				<div class="text-xs font-medium text-fg-muted">{t('modals.shot.castCharacters')}</div>
				<ul class="flex flex-wrap gap-x-3 gap-y-0.5">
					{#each characters as card (card.id)}
						<li>
							<label class="flex min-h-6 items-center gap-1.5 text-xs text-fg">
								<input type="checkbox" checked={chosen.characters.includes(card.id)} onchange={(e) => toggle(card.id, e.currentTarget.checked)} />
								{labelOf(card)}
							</label>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
		{#if places.length}
			<label class="block space-y-1">
				<span class="text-xs font-medium text-fg-muted">{t('modals.shot.castPlace')}</span>
				<select class="vp-popup w-full" value={chosen.place ?? ''} onchange={(e) => onchange({ ...chosen, place: e.currentTarget.value || null })}>
					<option value="">{t('modals.shot.castNoPlace')}</option>
					{#each places as card (card.id)}<option value={card.id}>{labelOf(card)}</option>{/each}
				</select>
			</label>
		{/if}
		{#if missing.length}<p class="text-xs text-warning">{t('modals.shot.castMissing', { labels: missing.join(', ') })}</p>{/if}
	</div>
{/if}

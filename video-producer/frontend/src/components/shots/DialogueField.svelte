<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { doc } from '../../lib/state.svelte.js';
	import { CHARACTERS, castOf, cardsOf, cardLabel, usable } from '../../lib/bible.js';
	import { newLine, nextSpeaker, spokenWords, wordLimit } from '../../lib/dialogue.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ulid } from '../../lib/ulid.js';

	let { lines = [], cast = null, seconds = 0, onchange } = $props();

	const characters = $derived(cardsOf(doc, CHARACTERS).filter(usable));
	const known = (id) => characters.some((card) => card.id === id);
	const castIds = $derived(castOf({ cast }).characters.filter(known));
	const words = $derived(spokenWords(lines));
	const limit = $derived(wordLimit(seconds));

	const replace = (i, line) => onchange(lines.map((l, j) => (j === i ? line : l)));

	function setOffscreen(i, on) {
		const { offscreen, ...rest } = lines[i];
		replace(i, on ? { ...rest, offscreen: true } : rest);
	}

	function add() {
		onchange([...lines, newLine(ulid(), nextSpeaker(lines, castIds))]);
	}
</script>

<div class="space-y-2">
	{#if lines.length}
		<ol class="space-y-2">
			{#each lines as line, i (line.id)}
				<li class="space-y-1.5 rounded-md border border-line-strong p-2">
					<div class="flex items-center gap-2">
						<select class="vp-popup min-w-0 flex-1" aria-label={t('modals.shot.dialogue.speaker')} value={line.speaker ?? ''} onchange={(e) => replace(i, { ...line, speaker: e.currentTarget.value || null })}>
							<option value="">{t('modals.shot.dialogue.unnamed')}</option>
							{#each characters as card (card.id)}<option value={card.id}>{cardLabel(card)}</option>{/each}
							{#if line.speaker && !known(line.speaker)}<option value={line.speaker}>{t('modals.shot.dialogue.missing')}</option>{/if}
						</select>
						<label class="flex min-h-6 shrink-0 items-center gap-1.5 text-xs text-fg-muted">
							<input type="checkbox" checked={line.offscreen === true} onchange={(e) => setOffscreen(i, e.currentTarget.checked)} />
							{t('modals.shot.dialogue.offscreen')}
						</label>
						<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('modals.shot.dialogue.remove'), tooltip: t('modals.shot.dialogue.remove'), size: 'sm', onclick: () => onchange(lines.filter((_, j) => j !== i)) }} />
					</div>
					<textarea class="input w-full text-sm" rows="2" aria-label={t('modals.shot.dialogue.words')} value={line.text} placeholder={t('modals.shot.dialogue.placeholder')} oninput={(e) => replace(i, { ...line, text: e.currentTarget.value })}></textarea>
					{#if line.speaker && !line.offscreen && known(line.speaker) && !castIds.includes(line.speaker)}
						<p class="text-xs text-warning">{t('modals.shot.dialogue.notCast')}</p>
					{/if}
				</li>
			{/each}
		</ol>
	{/if}
	<div class="flex items-center justify-between gap-2">
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: add }}>{t('modals.shot.dialogue.add')}</HostUi>
		{#if lines.length}<span class="text-xs {words > limit ? 'text-warning' : 'text-fg-subtle'}">{t('modals.shot.dialogue.count', { words, limit })}</span>{/if}
	</div>
	{#if words > limit}<p class="text-xs text-warning">{t('modals.shot.dialogue.tooLong', { limit })}</p>{/if}
	<p class="text-xs text-fg-subtle">{t('modals.shot.dialogue.hint')}</p>
</div>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, asset, select, toast, clipLabel } from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { CHARACTERS, PLACES, addCard, cardsOf, labelOf, newCard, shotsCasting, usable } from '../../lib/bible.js';
	import { DEFAULT_LANGUAGE, LANGUAGES, spokenLanguage } from '../../lib/dialogue.js';
	import { VIEW_ICONS, cardImages, castWhereCited, citedWithout, isCast, recast, unnamedIn } from '../../lib/director.js';
	import { assetThumb } from '../../lib/media.js';
	import { commandById } from '../../lib/commands.js';
	import { mountHostSlot } from '../../lib/host.js';
	import { ulid } from '../../lib/ulid.js';
	import DirectorViews from './DirectorViews.svelte';
	import ZoneHeader from '../shell/ZoneHeader.svelte';
	import Icon from '../Icon.svelte';

	const groups = $derived([
		{ kind: CHARACTERS, icon: 'user', kindLabel: t('panels.director.bible.character'), add: t('panels.dock.bible.addCharacter') },
		{ kind: PLACES, icon: 'mountain', kindLabel: t('panels.director.bible.place'), add: t('panels.dock.bible.addPlace') }
	]);
	const cards = $derived(groups.flatMap((g) => cardsOf(doc, g.kind).map((card) => ({ ...g, card }))));
	const characters = $derived(cardsOf(doc, CHARACTERS).length);
	const places = $derived(cardsOf(doc, PLACES).length);
	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const numbers = (list) => list.map(num).join(', ');

	function setLanguage(name) {
		act(() => {
			if (name === DEFAULT_LANGUAGE) delete doc.dialogueLanguage;
			else doc.dialogueLanguage = name;
		});
	}

	function add(kind) {
		const card = newCard(kind, ulid());
		act(() => addCard(doc, kind, card));
		ui.bibleCard = card.id;
		ui.inspectorOpen = true;
	}

	function castCited(e, kind, card) {
		e.stopPropagation();
		let shots = [];
		act(() => (shots = castWhereCited(doc, kind, card)));
		if (shots.length) toast(t('panels.director.bible.castDone', { name: labelOf(card), shots: numbers(shots) }), 'success');
	}

	function goTo(e, clip) {
		e.stopPropagation();
		select('clip', clip.id);
		seek(clip.start);
	}

	function cellTip(clip, kind, card) {
		const name = labelOf(card);
		if (isCast(clip, kind, card.id)) return t('panels.director.bible.cellOn', { name, shot: num(clip) });
		if (citedWithout(doc, kind, card).includes(clip)) return t('panels.director.bible.cellCited', { name, shot: num(clip) });
		return t('panels.director.bible.cellOff', { name, shot: num(clip) });
	}

	const empty = $derived({
		icon: 'book',
		title: t('panels.director.bible.empty'),
		description: t('panels.director.bible.emptyHint'),
		actions: { slot: (el) => mountHostSlot(el, 'Button', { variant: 'secondary', size: 'sm', icon: 'user', onclick: () => add(CHARACTERS), children: t('panels.dock.bible.addCharacter') }) }
	});
</script>

<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas" aria-label={commandById('view-bible')?.label}>
	<ZoneHeader icon={ui.sidebarOpen ? VIEW_ICONS.bible : null} title={commandById('view-bible')?.label}>
		{#snippet lead()}<DirectorViews />{/snippet}
		<span class="min-w-0 flex-1 truncate text-xs text-fg-subtle">{t('panels.director.sum.bible', { characters, places })}</span>
		<label class="flex shrink-0 items-center gap-1.5 text-xs text-fg-muted" title={t('panels.director.bible.languageTip')}>
			{t('panels.director.bible.language')}
			<select class="vp-popup" value={spokenLanguage(doc, null)} onchange={(e) => setLanguage(e.currentTarget.value)}>
				{#each LANGUAGES as name (name)}<option value={name}>{t(`lib.language.${name}`)}</option>{/each}
			</select>
		</label>
		{#each groups as g (g.kind)}
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'shrink-0', onclick: () => add(g.kind) }}>{g.add}</HostUi>
		{/each}
	</ZoneHeader>

	<div class="min-h-0 flex-1 overflow-auto">
		{#if !cards.length}
			<div class="m-auto w-full max-w-lg p-6"><HostUi name="EmptyState" props={empty} /></div>
		{:else}
			<ul class="grid gap-3 p-4" style:grid-template-columns="repeat(auto-fill, minmax(240px, 1fr))">
				{#each cards as { kind, icon, kindLabel, card } (card.id)}
					{@const images = cardImages(doc, card)}
					{@const cast = shotsCasting(doc, kind, card.id)}
					{@const cited = citedWithout(doc, kind, card)}
					{@const unnamed = unnamedIn(doc, kind, card)}
					<li class="flex flex-col gap-2 rounded-xl border bg-surface-1 p-2.5 transition-colors {ui.bibleCard === card.id ? 'border-signal shadow-[0_0_0_1px_rgb(var(--signal))]' : 'border-line-strong hover:border-line-hover'}">
						<button type="button" class="flex flex-col gap-2 text-left" aria-pressed={ui.bibleCard === card.id} onclick={() => ((ui.bibleCard = card.id), (ui.inspectorOpen = true))}>
							<span class="flex w-full gap-1">
								{#each images.slice(0, 3) as r (r.id)}
									{@const thumb = assetThumb(asset(r.assetId))}
									<span class="relative block aspect-video min-w-0 flex-1 overflow-hidden rounded-lg bg-surface-3" title={r.name}>
										{#if thumb}<img src={thumb} alt="" class="h-full w-full object-cover" />{:else}<span class="flex h-full items-center justify-center text-fg-subtle"><Icon name="image" class="h-5 w-5" /></span>{/if}
									</span>
								{:else}
									<span class="flex flex-1 items-center justify-center rounded-lg bg-surface-3 text-fg-subtle" style:height="4.5rem"><Icon name={icon} class="h-5 w-5" /></span>
								{/each}
							</span>
							<span class="flex w-full min-w-0 items-center gap-2">
								<span class="min-w-0 truncate text-sm font-semibold {usable(card) ? 'text-fg' : 'italic text-fg-subtle'}">{usable(card) ? labelOf(card) : t('panels.dock.bible.unnamed')}</span>
								<span class="flex shrink-0 items-center gap-1 rounded-sm border border-line-strong px-1 text-2xs text-fg-muted"><Icon name={icon} class="h-3 w-3" />{kindLabel}</span>
								<span class="flex-1"></span>
								<span class="shrink-0 text-2xs text-fg-subtle">{t('panels.director.bible.images', { count: images.length })}</span>
							</span>
						</button>
						{#if card.text}<p class="text-xs text-fg-muted" style:display="-webkit-box" style:-webkit-line-clamp="3" style:-webkit-box-orient="vertical" style:overflow="hidden">{card.text}</p>{/if}
						{#if kind === CHARACTERS && card.props}<p class="truncate text-xs text-fg-subtle">{t('panels.dock.bible.props')} · {card.props}</p>{/if}
						<div class="flex flex-wrap items-center gap-1">
							<span class="mr-1 text-xs text-fg-subtle">{t('panels.director.bible.cast', { count: cast.length })}</span>
							{#each cast as clip (clip.id)}
								<button type="button" class="vp-tc min-h-6 rounded-sm border border-line-strong px-1 text-2xs text-fg-muted hover:text-fg" title={clipLabel(clip)} onclick={(e) => goTo(e, clip)}>{num(clip)}</button>
							{/each}
						</div>
						{#if cited.length}
							<div class="flex flex-wrap items-center gap-x-2 text-xs text-warning">
								<Icon name="alert" class="h-3.5 w-3.5 shrink-0" />
								<span class="min-w-0">{t('panels.director.bible.cited', { shots: numbers(cited) })}</span>
								<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={(e) => castCited(e, kind, card)}>{t('panels.director.bible.castCited')}</button>
							</div>
						{/if}
						{#if unnamed.length}
							<div class="flex items-center gap-2 text-xs text-warning"><Icon name="alert" class="h-3.5 w-3.5 shrink-0" /><span class="min-w-0">{t('panels.director.bible.unnamed', { shots: numbers(unnamed) })}</span></div>
						{/if}
					</li>
				{/each}
			</ul>

			{#if doc.clips.length}
				<section class="px-4 pb-4" aria-labelledby="vp-bible-matrix">
					<div id="vp-bible-matrix" class="vp-section-title mb-2">{t('panels.director.bible.matrix')}</div>
					<div class="overflow-x-auto">
						<table class="text-xs">
							<thead>
								<tr>
									<th class="px-1 py-1"></th>
									<th class="px-1 py-1"></th>
									{#each cards as { card } (card.id)}<th class="truncate px-1 py-1 text-center font-medium text-fg-muted" style:max-width="6rem">{usable(card) ? labelOf(card) : t('panels.dock.bible.unnamed')}</th>{/each}
								</tr>
							</thead>
							<tbody>
								{#each doc.clips as clip (clip.id)}
									<tr>
										<td class="vp-tc px-1 py-0.5 text-fg-subtle">{num(clip)}</td>
										<td class="max-w-48 truncate px-1 py-0.5 text-fg-muted">{clipLabel(clip)}</td>
										{#each cards as { kind, card } (card.id)}
											{@const on = isCast(clip, kind, card.id)}
											{@const cites = !on && citedWithout(doc, kind, card).includes(clip)}
											{@const misses = on && unnamedIn(doc, kind, card).includes(clip)}
											<td class="px-1 py-0.5">
												<button
													type="button"
													class="flex h-6 w-14 items-center justify-center rounded border text-2xs {on ? 'border-signal bg-surface-3 text-fg' : 'border-line-strong text-fg-subtle hover:border-line-hover'}"
													style:border-color={cites || misses ? 'rgb(var(--warning))' : null}
													style:border-style={cites ? 'dashed' : null}
													style:color={cites || misses ? 'rgb(var(--warning))' : null}
													aria-pressed={on}
													aria-label={cellTip(clip, kind, card)}
													title={cellTip(clip, kind, card)}
													onclick={() => act(() => recast(clip, kind, card.id))}
												>
													{#if on}<Icon name="check" class="h-3 w-3" />{:else if cites}{t('panels.director.bible.citedShort')}{/if}
												</button>
											</td>
										{/each}
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</section>
			{/if}
		{/if}
	</div>
</section>

<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, toast, undo } from '../../lib/state.svelte.js';
	import { ulid } from '../../lib/ulid.js';
	import { CHARACTERS, PLACES, LABEL_MAX, addCard, cardsOf, convertDirection, labelOf, linkable, newCard, removeCard, shotsCasting, usable } from '../../lib/bible.js';
	import { refTypeLabel } from '../../lib/references.js';
	import Icon from '../Icon.svelte';

	let open = $state(null);

	const groups = $derived([
		{ kind: CHARACTERS, title: t('panels.dock.bible.characters'), icon: 'user', add: t('panels.dock.bible.addCharacter') },
		{ kind: PLACES, title: t('panels.dock.bible.places'), icon: 'mountain', add: t('panels.dock.bible.addPlace') }
	]);
	const free = $derived(String(doc.direction.personnages ?? '').trim());

	const labelHint = (kind) => (kind === CHARACTERS ? t('panels.dock.bible.labelHint.characters') : t('panels.dock.bible.labelHint.places'));
	const textLabel = (kind) => (kind === CHARACTERS ? t('panels.dock.bible.text.characters') : t('panels.dock.bible.text.places'));
	const textHint = (kind) => (kind === CHARACTERS ? t('panels.dock.bible.textHint.characters') : t('panels.dock.bible.textHint.places'));
	const referencesHint = (kind) => (kind === CHARACTERS ? t('panels.dock.bible.referencesHint.characters') : t('panels.dock.bible.referencesHint.places'));
	const noReferences = (kind) => (kind === CHARACTERS ? t('panels.dock.bible.noReferences.characters') : t('panels.dock.bible.noReferences.places'));

	function add(kind) {
		const card = newCard(kind, ulid());
		act(() => addCard(doc, kind, card));
		open = card.id;
	}

	function remove(kind, card) {
		act(() => removeCard(doc, kind, card.id));
		toast(t('panels.dock.bible.removed'), 'info', { label: t('shell.toast.undo'), run: undo });
	}

	function convert() {
		let card = null;
		act(() => (card = convertDirection(doc, ulid())));
		if (!card) return;
		open = card.id;
		toast(t('panels.dock.bible.converted', { count: doc.clips.length }), 'success', { label: t('shell.toast.undo'), run: undo });
	}

	function link(card, id, on) {
		act(() => (card.references = on ? [...card.references, id] : card.references.filter((x) => x !== id)));
	}
</script>

<section class="border-t border-line" aria-labelledby="vp-bible-title">
	<div class="flex items-center gap-1.5 px-3 pb-1 pt-3">
		<Icon name="book" class="h-3.5 w-3.5 text-fg-subtle" />
		<span id="vp-bible-title" class="vp-section-title">{t('panels.dock.bible.title')}</span>
	</div>
	<p class="px-3 pb-2 text-xs text-fg-subtle">{t('panels.dock.bible.hint')}</p>
	{#if free}
		<div class="mx-3 mb-2 rounded-lg border border-line-strong p-2 text-xs text-fg-muted">
			<p>{t('panels.dock.bible.convert')}</p>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'user', class: 'mt-1', onclick: convert }}>{t('panels.dock.bible.convertAction')}</HostUi>
		</div>
	{/if}
	{#each groups as g (g.kind)}
		{@const list = cardsOf(doc, g.kind)}
		<div class="px-3 pb-2">
			<div class="flex items-center justify-between gap-2">
				<span class="text-xs font-medium text-fg-muted">{g.title}</span>
				<span class="vp-tc text-xs text-fg-subtle">{list.length}</span>
			</div>
			{#if list.length}
				<ul class="mt-1 divide-y divide-line rounded-lg border border-line-strong">
					{#each list as card (card.id)}
						{@const cast = shotsCasting(doc, g.kind, card.id).length}
						{@const references = linkable(doc, g.kind)}
						<li class="text-sm">
							<button type="button" class="flex min-h-8 w-full items-center gap-1.5 px-2 text-left" aria-expanded={open === card.id} onclick={() => (open = open === card.id ? null : card.id)}>
								<Icon name={open === card.id ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5 shrink-0 text-fg-subtle" />
								<Icon name={g.icon} class="h-3.5 w-3.5 shrink-0 text-fg-subtle" />
								<span class="min-w-0 flex-1 truncate {usable(card) ? 'text-fg' : 'italic text-fg-subtle'}">{usable(card) ? labelOf(card) : t('panels.dock.bible.unnamed')}</span>
								<span class="shrink-0 text-xs text-fg-subtle">{t('panels.dock.bible.cast', { count: cast })}</span>
							</button>
							{#if open === card.id}
								<div class="space-y-2 px-2 pb-2.5">
									<label class="block space-y-1">
										<span class="vp-label">{t('panels.dock.bible.label')}</span>
										<input class="input vp-dense w-full" maxlength={LABEL_MAX} bind:value={card.label} placeholder={labelHint(g.kind)} oninput={() => (ui.dirty = true)} />
									</label>
									{#if !usable(card)}<p class="text-xs text-warning">{t('panels.dock.bible.noLabel')}</p>{/if}
									<label class="block space-y-1">
										<span class="vp-label">{textLabel(g.kind)}</span>
										<textarea class="input text-sm" rows="3" bind:value={card.text} placeholder={textHint(g.kind)} oninput={() => (ui.dirty = true)}></textarea>
									</label>
									{#if g.kind === CHARACTERS}
										<label class="block space-y-1">
											<span class="vp-label">{t('panels.dock.bible.props')}</span>
											<input class="input vp-dense w-full" bind:value={card.props} placeholder={t('panels.dock.bible.propsHint')} oninput={() => (ui.dirty = true)} />
										</label>
									{/if}
									<div class="space-y-1">
										<div class="vp-label">{t('panels.dock.bible.references')}</div>
										{#if references.length}
											<ul class="space-y-0.5">
												{#each references as r (r.id)}
													<li>
														<label class="flex min-h-6 items-center gap-1.5 text-xs text-fg-muted">
															<input type="checkbox" checked={card.references.includes(r.id)} onchange={(e) => link(card, r.id, e.currentTarget.checked)} />
															<span class="min-w-0 flex-1 truncate">{r.name || refTypeLabel(r.type)}</span>
														</label>
													</li>
												{/each}
											</ul>
										{:else}
											<p class="text-xs text-fg-subtle">{noReferences(g.kind)}</p>
										{/if}
										<p class="text-xs text-fg-subtle">{referencesHint(g.kind)}</p>
									</div>
									<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'trash', onclick: () => remove(g.kind, card) }}>{t('panels.dock.bible.remove')}</HostUi>
								</div>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', class: 'mt-1 w-full !justify-start', onclick: () => add(g.kind) }}>{g.add}</HostUi>
		</div>
	{/each}
</section>

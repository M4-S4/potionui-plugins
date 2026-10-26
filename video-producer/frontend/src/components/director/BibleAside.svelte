<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, asset, toast, undo } from '../../lib/state.svelte.js';
	import { CHARACTERS, PLACES, SPACES, LABEL_MAX, cardsOf, linkable, removeCard, shotsCasting, usable } from '../../lib/bible.js';
	import { addCardImage, refTypeLabel } from '../../lib/references.js';
	import { assetThumb } from '../../lib/media.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import MediaPicker from '../shots/MediaPicker.svelte';
	import Icon from '../Icon.svelte';

	const found = $derived([CHARACTERS, PLACES].map((kind) => [kind, cardsOf(doc, kind).find((c) => c.id === ui.bibleCard)]).find(([, card]) => card) ?? null);
	const kind = $derived(found?.[0] ?? null);
	const card = $derived(found?.[1] ?? null);
	const references = $derived(kind ? linkable(doc, kind) : []);
	const cast = $derived(card ? shotsCasting(doc, kind, card.id).length : 0);

	const labelHint = (k) => (k === CHARACTERS ? t('panels.dock.bible.labelHint.characters') : t('panels.dock.bible.labelHint.places'));
	const textLabel = (k) => (k === CHARACTERS ? t('panels.dock.bible.text.characters') : t('panels.dock.bible.text.places'));
	const textHint = (k) => (k === CHARACTERS ? t('panels.dock.bible.textHint.characters') : t('panels.dock.bible.textHint.places'));
	const referencesHint = (k) => (k === CHARACTERS ? t('panels.dock.bible.referencesHint.characters') : t('panels.dock.bible.referencesHint.places'));
	const noReferences = (k) => (k === CHARACTERS ? t('panels.dock.bible.noReferences.characters') : t('panels.dock.bible.noReferences.places'));

	function link(id, on) {
		act(() => (card.references = on ? [...card.references, id] : card.references.filter((x) => x !== id)));
	}

	function remove() {
		act(() => removeCard(doc, kind, card.id));
		ui.bibleCard = null;
		toast(t('panels.dock.bible.removed'), 'info', { label: t('shell.toast.undo'), run: undo });
	}
</script>

<aside class="flex min-h-0 flex-col overflow-hidden border-l border-line bg-surface-1" aria-label={t('panels.director.aside.card')} class:invisible={!ui.inspectorOpen}>
	<div class="vp-panel-head border-b border-line">
		<Icon name={kind === PLACES ? 'mountain' : 'user'} class="h-4 w-4 text-fg-muted" />
		<span class="truncate text-sm font-semibold">{card ? (kind === PLACES ? t('panels.director.bible.place') : t('panels.director.bible.character')) : t('panels.director.aside.card')}</span>
		<div class="flex-1"></div>
		<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('inspector.close'), tooltip: t('inspector.closeTip'), kbd: commandById('inspector')?.key, size: 'sm', class: 'vp-h7', onclick: () => (ui.inspectorOpen = false) }} />
	</div>
	{#if card}
		{#key card.id}
			<div class="min-h-0 flex-1 space-y-4 overflow-auto p-3">
				<label class="block space-y-1">
					<span class="vp-label">{t('panels.dock.bible.label')}</span>
					<input class="input vp-dense w-full" maxlength={LABEL_MAX} bind:value={card.label} placeholder={labelHint(kind)} oninput={() => (ui.dirty = true)} />
				</label>
				{#if !usable(card)}<p class="text-xs text-warning">{t('panels.dock.bible.noLabel')}</p>{/if}
				<label class="block space-y-1">
					<span class="vp-label">{textLabel(kind)}</span>
					<textarea class="input text-sm" rows="4" bind:value={card.text} placeholder={textHint(kind)} oninput={() => (ui.dirty = true)}></textarea>
				</label>
				{#if kind === CHARACTERS}
					<label class="block space-y-1">
						<span class="vp-label">{t('panels.dock.bible.props')}</span>
						<input class="input vp-dense w-full" bind:value={card.props} placeholder={t('panels.dock.bible.propsHint')} oninput={() => (ui.dirty = true)} />
					</label>
				{/if}
				<section class="space-y-2">
					<div class="vp-section-title">{t('panels.director.aside.images')}</div>
					{#if references.length}
						<ul class="space-y-1">
							{#each references as r (r.id)}
								{@const thumb = r.assetId ? assetThumb(asset(r.assetId)) : null}
								<li>
									<label class="flex min-h-7 items-center gap-2 text-xs text-fg-muted">
										<input type="checkbox" checked={card.references.includes(r.id)} onchange={(e) => link(r.id, e.currentTarget.checked)} />
										<span class="block h-7 w-12 shrink-0 overflow-hidden rounded bg-surface-3">{#if thumb}<img src={thumb} alt="" class="h-full w-full object-cover" />{/if}</span>
										<span class="min-w-0 flex-1 truncate">{r.name || refTypeLabel(r.type)}</span>
									</label>
								</li>
							{/each}
						</ul>
					{:else}
						<p class="text-xs text-fg-subtle">{noReferences(kind)}</p>
					{/if}
					<MediaPicker title={t('panels.director.aside.addImage')} onpick={(id) => addCardImage(card, SPACES[kind], id)} removable={false} compact />
					<p class="text-xs text-fg-subtle">{referencesHint(kind)}</p>
				</section>
				<p class="text-xs text-fg-subtle">{t('panels.director.bible.cast', { count: cast })}</p>
			</div>
			<div class="flex shrink-0 items-center border-t border-line px-3 py-2">
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'trash', onclick: remove }}>{t('panels.dock.bible.remove')}</HostUi>
			</div>
		{/key}
	{:else}
		<div class="p-3"><HostUi name="EmptyState" props={{ compact: true, icon: hostIconName('book'), title: t('panels.director.aside.noCardTitle'), description: t('panels.director.aside.noCard') }} /></div>
	{/if}
</aside>

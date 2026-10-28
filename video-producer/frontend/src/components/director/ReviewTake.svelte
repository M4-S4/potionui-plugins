<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatNumber, t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs } from '../../lib/state.svelte.js';
	import { takesOf, toggleCompare } from '../../lib/production.svelte.js';
	import { instructionOf } from '../../lib/bible.js';
	import { missingWords } from '../../lib/director.js';
	import { labelOf } from '../../lib/labels.js';
	import { isStale } from '../../lib/shots.js';
	import { seamChainOf } from '../../lib/chain.svelte.js';
	import { currentLooks, lookState, measureLooks } from '../../lib/looks.svelte.js';
	import { driftOf, finalLook, lowCard as cardIsLow, lowDrift, lowFinal, percent, takeLook } from '../../lib/looks.js';
	import { seam } from '../../lib/continuity.svelte.js';
	import { seamImage } from '../../lib/seam.js';
	import { clipThumb, takeThumb } from '../../lib/media.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import ShotSummary from './ShotSummary.svelte';
	import { TAG_CLASS } from '../../lib/reftags.js';
	import { labelParts, trackOf, vrefLabel } from '../../lib/vreftracks.js';
	import { roleLabel, sentSeconds, showTrack, sideText, trackName } from '../../lib/vreftracks.svelte.js';
	import { engineTitle, takeReceptionFor } from '../../lib/references.js';
	import { matchState, matchToSuite, suiteAnchors } from '../../lib/match.svelte.js';

	let { clip, take } = $props();

	const num = (c) => String(doc.clips.indexOf(c) + 1).padStart(2, '0');
	const index = $derived(doc.clips.indexOf(clip));
	const previous = $derived(index > 0 ? doc.clips[index - 1] : null);
	const next = $derived(doc.clips[index + 1] ?? null);
	const placed = $derived(clip.take === take.id);
	const stale = $derived(isStale(take, clip));
	const today = $derived(instructionOf(doc, clip));
	const parts = $derived(take.promptText ? missingWords(today, take.promptText) : [{ text: today, mark: false }]);
	const missing = $derived(parts.some((p) => p.mark));
	const final = $derived(takesOf(clip).find((x) => x.id !== take.id && labelOf(x) === 'final' && x.status === 'done' && x.url) ?? null);
	const isFinal = $derived(labelOf(take) === 'final');
	const withFinal = $derived(Boolean(final) && ui.compare?.length === 2 && ui.compare.includes(final.id) && ui.compare.includes(take.id));
	const inCompare = $derived(!withFinal && Boolean(ui.compare?.includes(take.id)));
	const nextChain = $derived(next ? seamChainOf(next) : null);
	const chained = $derived(Boolean(nextChain) && !['off', 'textOnly', 'own'].includes(nextChain.state));
	const thumb = $derived(takeThumb(take));
	const looks = $derived(currentLooks());
	const look = $derived(takeLook(looks, take.id));
	const unmeasured = $derived(Boolean(look) && ['missing', 'failed', 'unavailable'].includes(look.status) && Boolean(looks?.embedder.available));
	const lowCard = (card) => cardIsLow(looks, card);
	const fromDraft = $derived(finalLook(looks, take.id));
	const methodText = (card) => (card.kind === 'place' ? t('panels.director.pick.lookPlace') : card.method === 'face' ? t('panels.director.pick.lookFace', { seen: percent(card.seen) }) : card.seen === 0 ? t('panels.director.pick.lookNoFace') : '');
	const endOf = (c) => seamImage(doc, c.id, 'last')?.src ?? clipThumb(c);
	const startOf = (c) => seamImage(doc, c.id, 'first')?.src ?? clipThumb(c);
	const verdict = (i) => {
		const sm = placed ? seam(i) : null;
		if (!sm?.measured) return [];
		return sm.issues.length ? sm.issues.map((x) => ({ text: x.text, warn: true })) : [{ text: t('panels.story.continuityOk'), warn: false }];
	};
	const chainNote = $derived(chained ? { text: placed ? t('panels.director.pick.chainedPlaced', { next: num(next), shot: num(clip) }) : t('panels.director.pick.chained', { next: num(next), shot: num(clip) }), warn: !placed } : null);
	const pairs = $derived(
		[
			previous ? { left: endOf(previous), right: thumb, title: `${num(previous)} → ${num(clip)}`, notes: verdict(index) } : null,
			next ? { left: thumb, right: startOf(next), title: `${num(clip)} → ${num(next)}`, notes: [...verdict(index + 1), ...(chainNote ? [chainNote] : [])] } : null
		].filter(Boolean)
	);

	const refs = $derived(take.videoRefs ?? []);
	const labels = $derived(refs.filter((r) => r.label).map((r) => ({ slot: r.slot, label: r.label })));
	const pieces = $derived(take.promptText ? labelParts(take.promptText, labels) : []);
	const asTaken = $derived(take.kind === 'render' && take.presetId ? takeReceptionFor(clip, take) : null);
	const unsent = $derived(asTaken ? asTaken.videoTracks.filter((x) => x.status === 'ignored' && !refs.some((r) => r.slot === x.slot)) : []);
	const unsentEngine = $derived(asTaken ? engineTitle(asTaken.engine) : '');
	const suites = $derived(placed ? suiteAnchors(clip) : []);
	const refTrack = (r) => (r.trackId ? trackOf(doc, r.trackId) : null);
	const refName = (r) => {
		const track = refTrack(r);
		return track ? trackName(track) : vrefLabel(r.slot);
	};
	const refTip = (slot) => {
		const r = refs.find((x) => x.slot === slot);
		return r ? t('panels.director.pick.vrefTip', { label: r.label ?? '', track: refName(r), role: roleLabel(r.role) }) : vrefLabel(slot);
	};

	function toFinal() {
		ui.preview = null;
		ui.compare = withFinal ? null : [final.id, take.id];
	}
</script>

{#if stale}
	<section class="space-y-2" data-take-since>
		<div class="vp-section-title">{t('panels.director.pick.since')}</div>
		<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: hostIconName('pencil'), live: 'off' }}>
			<p class="text-xs">{t('panels.director.pick.changed', { shot: num(clip) })}</p>
		</HostUi>
		<div class="space-y-1 rounded-lg border border-line-strong p-2.5 text-xs">
			<div class="text-2xs uppercase tracking-wide text-fg-subtle">{t('panels.director.pick.today')}</div>
			<p class="whitespace-pre-wrap leading-5 text-fg-muted">{#each parts as part, i (i)}{#if part.mark}<mark class="rounded-sm text-fg" style:background-color="rgb(var(--success) / 0.22)" data-take-missing>{part.text}</mark>{:else}{part.text}{/if}{/each}</p>
		</div>
		<p class="text-xs text-fg-subtle">{missing ? `${t('panels.director.pick.missing')} ` : ''}{t('panels.director.pick.relaunch', { key: commandById('generate')?.key ?? '', shot: num(clip) })}</p>
	</section>
{/if}

<section class="space-y-2" data-take-sent>
	<div class="flex items-center gap-2">
		<span class="vp-section-title min-w-0 flex-1">{t('panels.director.pick.sent')}</span>
		{#if take.promptText}<span class="vp-tc text-2xs text-fg-subtle">{t('panels.story.chars', { chars: formatNumber(take.promptText.length) })}</span>{/if}
	</div>
	{#if take.promptText}
		<p class="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-line-strong p-2.5 text-xs leading-5 text-fg-muted">{#each pieces as piece, j (j)}{piece.text}{#if piece.slot}<span class="{TAG_CLASS} vp-tc ml-0.5 align-baseline" title={refTip(piece.slot)} data-sent-vref={piece.slot}>{vrefLabel(piece.slot)}</span>{/if}{/each}</p>
		<p class="text-xs text-fg-subtle">{t('panels.director.pick.sentHint')}</p>
	{:else}
		<p class="text-xs text-fg-subtle">{t('panels.director.pick.noSent')}</p>
	{/if}
	{#if refs.length}
		<ul class="space-y-1 text-xs" data-take-vrefs>
			{#each refs as r (r.slot)}
				<li class="flex items-baseline gap-2">
					<button type="button" class="{TAG_CLASS} vp-tc shrink-0 border-success text-success hover:text-fg" title={t('panels.director.pick.vrefSee', { track: refName(r) })} onclick={() => r.trackId && showTrack(r.trackId)}>{vrefLabel(r.slot)}</button>
					<span class="min-w-0 flex-1 text-fg-muted">{t('panels.director.pick.vrefSent', { role: roleLabel(r.role), seconds: sentSeconds(r.frames), side: sideText(r.role), start: secs(r.start ?? 0), end: secs(r.end ?? 0) })}{#if r.label}<span class="text-fg-subtle"> → {r.label}</span>{/if}</span>
				</li>
			{/each}
		</ul>
		<p class="text-xs text-fg-subtle" data-take-vrefs-again>{t('panels.director.pick.vrefAgain', { labels: refs.map((r) => vrefLabel(r.slot)).join(', '), count: refs.length })}</p>
	{/if}
	{#if unsent.length}
		<p class="text-xs text-fg-subtle" data-take-vrefs-unsent>{t('panels.director.pick.vrefUnsent', { labels: unsent.map((x) => vrefLabel(x.slot)).join(', '), engine: unsentEngine, count: unsent.length })}</p>
	{/if}
</section>

{#if suites.length}
	<section class="space-y-2" data-take-suite>
		<div class="vp-section-title">{t('panels.director.pick.suite')}</div>
		{#each suites as anchor (anchor.id)}
			<p class="text-xs text-fg-subtle">{t('panels.director.pick.suiteText', { label: vrefLabel(anchor.slot) })}</p>
			<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('palette'), disabled: Boolean(matchState.busy), onclick: () => matchToSuite(clip, anchor.id) }}>{t('panels.director.pick.suiteMatch')}</HostUi>
		{/each}
	</section>
{/if}

<section class="space-y-2">
	<div class="vp-section-title">{t('panels.director.pick.compare')}</div>
	<div class="flex flex-wrap gap-1.5">
		<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: hostIconName('compare'), class: 'vp-toggle', ariaPressed: withFinal, disabled: !final, onclick: toFinal }}>
			{final ? t('panels.director.pick.toFinal', { variant: final.variant }) : isFinal ? t('panels.director.pick.isFinal') : t('panels.director.pick.noFinal')}
		</HostUi>
		<HostUi name="Tooltip" props={{ text: t('panels.director.pick.toOtherTip'), wrapperClass: 'inline-flex' }}>
			<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('compare'), class: 'vp-toggle', ariaPressed: inCompare, onclick: () => toggleCompare(take.id) }}>{t('panels.director.pick.toOther')}</HostUi>
		</HostUi>
	</div>
</section>

{#if previous || next}
	<section class="space-y-2" data-take-seams>
		<div class="vp-section-title">{placed ? t('panels.director.pick.seamsPlaced') : t('panels.director.pick.seams')}</div>
		{#each pairs as pair (pair.title)}
			<div class="flex items-start gap-2">
				{#each [pair.left, pair.right] as src, k (k)}
					<span class="block aspect-video w-16 shrink-0 overflow-hidden rounded bg-surface-3">{#if src}<img {src} alt="" class="h-full w-full object-cover" />{/if}</span>
				{/each}
				<span class="min-w-0 flex-1 space-y-0.5 text-xs">
					<span class="vp-tc block font-medium text-fg">{pair.title}</span>
					{#each pair.notes as note, n (n)}<span class="block {note.warn ? 'text-warning' : 'text-fg-subtle'}">{note.text}</span>{/each}
				</span>
			</div>
		{/each}
		{#if !placed}<p class="text-xs text-fg-subtle">{t('panels.director.pick.seamsHint')}</p>{/if}
	</section>
{/if}

{#if look?.cards.length || fromDraft?.status === 'done'}
	<section class="space-y-2" data-take-looks>
		<div class="flex items-center gap-2">
			<span class="vp-section-title min-w-0 flex-1">{t('panels.director.pick.looks')}</span>
			{#if unmeasured}<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', disabled: lookState.asking, onclick: measureLooks }}>{t('panels.director.pick.measure')}</HostUi>{/if}
		</div>
		<ul class="space-y-1 text-xs">
			{#each look.cards as card (card.cardId)}
				{@const drift = driftOf(looks, take.id, card.cardId)}
				<li class="space-y-0.5" data-take-look={card.status} data-look-method={card.method ?? ''}>
					<div class="flex items-center gap-2">
						<span class="min-w-0 flex-1 truncate text-fg-muted">{card.label}</span>
						<span class="shrink-0 {lowCard(card) ? 'text-warning' : 'text-fg-subtle'}">{#if card.status === 'done'}<span class="vp-tc">{percent(card.score)} %</span>{#if lowCard(card)}{` · ${t('panels.director.pick.lookLow')}`}{/if}{:else}{t(`panels.director.pick.lookState.${card.status}`)}{/if}</span>
					</div>
					{#if card.status === 'done' && methodText(card)}<div class="truncate text-2xs text-fg-subtle">{methodText(card)}</div>{/if}
					{#if lowDrift(looks, drift)}<div class="text-2xs text-warning" data-look-drift>{t('panels.director.pick.lookDrift', { score: percent(drift.score) })}</div>{/if}
				</li>
			{/each}
		</ul>
		{#if fromDraft?.status === 'done'}<p class="text-xs {lowFinal(looks, fromDraft) ? 'text-warning' : 'text-fg-subtle'}" data-look-final>{lowFinal(looks, fromDraft) ? t('panels.director.pick.lookFinalLow', { score: percent(fromDraft.score) }) : t('panels.director.pick.lookFinal', { score: percent(fromDraft.score) })}</p>{/if}
		<p class="text-xs text-fg-subtle">{t('panels.director.pick.lookHint')}</p>
	</section>
{/if}

<ShotSummary {clip} />

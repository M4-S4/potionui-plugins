<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, secs, clipLabel, proposeShots, acceptProposal, shotNumber } from '../../lib/state.svelte.js';
	import { shotActivity, startGeneration, retryTake } from '../../lib/production.svelte.js';
	import { flyingTakes } from '../../lib/takes.svelte.js';
	import { castCards, CHARACTERS, PLACES, cardsOf, names } from '../../lib/bible.js';
	import { draftsOf } from '../../lib/shots.js';
	import { stages } from '../../lib/catalog.js';
	import { hostIconName } from '../../lib/icons.js';
	import { suggest } from '../../lib/assistant.svelte.js';
	import { AVG_MAX, AVG_MIN, BAND_STEP, METHODS, mergeItem, moveItem, musicParts, removeItem, sentencesOf, splitItem } from '../../lib/band.js';
	import { bandChecks, compareSeam, pickShot, selectedShot } from '../../lib/band.svelte.js';
	import { ulid } from '../../lib/ulid.js';
	import SeamFix from './SeamFix.svelte';
	import FinalPassButton from '../production/FinalPassButton.svelte';
	import Icon from '../Icon.svelte';

	const proposal = $derived(ui.storyProposal);
	const kept = $derived(proposal?.filter((x) => x.keep) ?? []);
	const keptDur = $derived(kept.reduce((sum, x) => sum + x.dur, 0));
	const sentences = $derived(sentencesOf(doc.synopsis));
	const recognized = $derived([...cardsOf(doc, CHARACTERS), ...cardsOf(doc, PLACES)].filter((card) => card.label && names(doc.synopsis, card.label)));
	const parts = $derived(musicParts(doc));
	const estimate = $derived(parts.reduce((sum, p) => sum + Math.max(1, Math.round((p.end - p.start) / ui.storyAvg)), 0));
	const sel = $derived(selectedShot());
	const open = $derived(doc.clips.filter((c) => c.stage === 'todo' || c.stage === 'draft'));
	const todo = $derived(doc.clips.filter((c) => c.stage === 'todo'));
	const draftsLeft = $derived(todo.reduce((sum, c) => sum + draftsOf(c, doc.engine), 0));
	const flying = $derived(flyingTakes().length);
	const checks = $derived(bandChecks());
	const footage = (list) => t('generation.story.footage', { count: list.length, duration: secs(list.reduce((sum, c) => sum + c.dur, 0)) });
	const castNames = (cast) => {
		const cards = castCards(doc, cast);
		return [...cards.characters, ...(cards.place ? [cards.place] : [])].map((card) => card.label);
	};
	const methodLabel = { phrases: () => t('storyboard.story.method.phrases'), music: () => t('storyboard.story.method.music'), assistant: () => t('storyboard.story.method.assistant') };
	const methodHint = { phrases: () => t('storyboard.story.hint.phrases'), music: () => t('storyboard.story.hint.music'), assistant: () => t('storyboard.story.hint.assistant') };
	const methodIcon = { phrases: 'list', music: 'music', assistant: 'sparkles' };

	function setMethod(method) {
		ui.storyMethod = method;
		if (proposal && method !== 'assistant') proposeShots(method);
	}

	function propose() {
		if (ui.storyMethod === 'assistant') return suggest(t('assistant.suggest.split'));
		proposeShots(ui.storyMethod);
	}

	function setAvg(value) {
		ui.storyAvg = Number(value);
		if (proposal && ui.storyMethod === 'music') proposeShots('music');
	}

	function edit(fn) {
		if (!proposal) return;
		fn(proposal);
	}

	function nudge(item, delta) {
		item.dur = Math.max(1, Math.round((item.dur + delta * BAND_STEP) * 100) / 100);
	}

	function toggleAll() {
		const all = proposal.every((x) => x.keep);
		proposal.forEach((x) => (x.keep = !all));
	}

	function add() {
		if (kept.length) acceptProposal(ui.storyAt);
		if (!ui.storyProposal) ui.storyTab = 'todo';
	}

	function showCheck(check) {
		if (check.kind === 'seam') return compareSeam(check.clip);
		pickShot(check.clip);
	}

	function writePrompt(clip) {
		pickShot(clip);
		ui.storyOpen = false;
		queueMicrotask(() => document.getElementById('vp-quick-prompt')?.focus());
	}

	function onKeydown(e) {
		if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && ui.storyTab === 'cut' && kept.length) {
			e.preventDefault();
			add();
		}
	}
</script>

<div class="m-2 flex min-h-0 flex-col overflow-hidden rounded-xl border border-line-strong bg-surface-1 shadow-overlay" role="dialog" tabindex="-1" aria-label={t('storyboard.story.title')} onkeydown={onKeydown}>
	<div class="flex h-10 shrink-0 items-center gap-3 border-b border-line px-3">
		<Icon name="book" class="h-4 w-4 text-fg-muted" />
		<span class="text-sm font-semibold">{t('storyboard.story.title')}</span>
		<div class="ml-3 flex h-full items-stretch gap-4" role="tablist">
			{#each [['cut', t('storyboard.story.tab.cut'), kept.length], ['todo', t('panels.story.toProduce'), open.length], ['check', t('storyboard.story.tab.check'), checks.length]] as [id, label, count] (id)}
				<button type="button" role="tab" aria-selected={ui.storyTab === id} class="flex items-center gap-1.5 border-b-2 text-sm {ui.storyTab === id ? 'border-fg text-fg' : 'border-transparent text-fg-muted hover:text-fg'}" onclick={() => (ui.storyTab = id)}>
					{label}{#if count}<span class="vp-tc text-2xs text-fg-subtle">{count}</span>{/if}
				</button>
			{/each}
		</div>
		<div class="flex-1"></div>
		{#if ui.storyTab === 'cut' && kept.length}<span class="flex items-center gap-1.5 text-2xs text-fg-subtle"><span class="inline-block h-2.5 w-4 rounded-sm border-[1.5px] border-dashed border-signal"></span>{t('storyboard.story.ghostsHint')}</span>{/if}
		<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => (ui.storyOpen = false) }}>{t('storyboard.band.close')}</HostUi>
	</div>

	{#if ui.storyTab === 'cut'}
		<div class="grid min-h-0 flex-1 grid-cols-[380px_minmax(0,1fr)]">
			<div class="flex min-h-0 flex-col gap-2 overflow-auto border-r border-line p-3">
				<div class="flex items-baseline justify-between">
					<label for="vp-story-synopsis" class="vp-section-title">{t('panels.story.synopsis')}</label>
					<span class="vp-tc text-2xs text-fg-subtle">{t('storyboard.story.counts', { chars: doc.synopsis.length, count: sentences.length })}</span>
				</div>
				<textarea id="vp-story-synopsis" class="input text-sm leading-5" rows="5" bind:value={doc.synopsis} placeholder={t('panels.story.placeholder')}></textarea>
				<div class="flex flex-wrap items-center gap-1">
					<span class="vp-label mr-1">{t('storyboard.story.recognized')}</span>
					{#each recognized as card (card.id)}<span class="inline-flex h-5 items-center gap-1 rounded border border-line-strong px-1.5 text-2xs text-fg-muted"><Icon name="user" class="h-3 w-3" />{card.label}</span>{/each}
					{#if !recognized.length}<span class="text-xs text-fg-subtle">{t('storyboard.story.noneRecognized')}</span>{/if}
				</div>
				<span class="vp-label mt-1">{t('storyboard.story.methodLabel')}</span>
				<div class="vp-seg self-start" role="group" aria-label={t('storyboard.story.methodLabel')}>
					{#each METHODS as m (m)}
						<button type="button" aria-pressed={ui.storyMethod === m} disabled={m === 'music' && !parts.length} onclick={() => setMethod(m)}><Icon name={methodIcon[m]} class="mr-1 inline h-3 w-3" />{methodLabel[m]()}</button>
					{/each}
				</div>
				<p class="text-xs leading-4 text-fg-muted">{methodHint[ui.storyMethod]()}</p>
				{#if !parts.length}<p class="text-2xs text-fg-subtle">{t('storyboard.story.noMusic')}</p>{/if}
				{#if ui.storyMethod === 'music' && parts.length}
					<label class="flex items-center gap-2">
						<span class="vp-label shrink-0">{t('storyboard.story.average')}</span>
						<input class="vp-slider min-w-0 flex-1" type="range" min={AVG_MIN} max={AVG_MAX} step="0.5" value={ui.storyAvg} onchange={(e) => setAvg(e.currentTarget.value)} aria-label={t('storyboard.story.average')} />
						<span class="vp-tc shrink-0 text-2xs text-fg-muted">{t('storyboard.story.estimate', { dur: secs(ui.storyAvg), count: estimate })}</span>
					</label>
				{/if}
				<div class="mt-1 flex items-center gap-2">
					<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: ui.storyMethod === 'assistant' ? 'sparkles' : hostIconName('wand'), disabled: !doc.synopsis.trim(), onclick: propose }}>{ui.storyMethod === 'assistant' ? t('storyboard.story.ask') : proposal ? t('storyboard.story.again') : t('panels.story.propose')}</HostUi>
				</div>
			</div>

			<div class="flex min-h-0 min-w-0 flex-col">
				<div class="flex h-10 shrink-0 items-center gap-3 px-3 text-xs">
					<span class="font-semibold text-fg">{t('panels.story.proposal')}</span>
					{#if proposal}<span class="vp-tc text-fg-subtle">{t('generation.story.footage', { count: kept.length, duration: secs(keptDur) })}</span>{/if}
					<div class="flex-1"></div>
					<label class="flex items-center gap-1.5">
						<span class="vp-label">{t('storyboard.story.insert')}</span>
						<select class="vp-popup max-w-[280px]" value={ui.storyAt} onchange={(e) => (ui.storyAt = e.currentTarget.value)}>
							<option value="end">{doc.clips.length ? t('storyboard.story.atEnd', { n: doc.clips.length }) : t('storyboard.story.atStart')}</option>
							{#if sel}<option value="after">{t('storyboard.story.after', { n: doc.clips.indexOf(sel) + 1, shot: clipLabel(sel) })}</option>{/if}
						</select>
					</label>
				</div>
				<div class="min-h-0 flex-1 overflow-auto px-3">
					{#if proposal}
						{#each proposal as item, i (item.id)}
							<div class="grid grid-cols-[18px_34px_minmax(0,1fr)_auto_108px_auto] items-center gap-2 border-b border-line py-1 {item.keep ? '' : 'opacity-45'}">
								<input type="checkbox" class="h-4 w-4" bind:checked={item.keep} aria-label={t('panels.story.keep', { n: i + 1 })} />
								<span class="vp-tc text-2xs {item.keep ? 'text-signal' : 'text-fg-subtle'}">#{item.n}</span>
								<div class="flex min-w-0 flex-col">
									<input class="min-w-0 rounded border border-transparent bg-transparent px-1 text-sm font-medium hover:border-line-strong focus:border-signal focus:outline-none" bind:value={item.label} aria-label={t('panels.story.shotName', { n: i + 1 })} />
									<input class="min-w-0 rounded border border-transparent bg-transparent px-1 text-xs text-fg-muted hover:border-line-strong focus:border-signal focus:outline-none" bind:value={item.prompt} aria-label={t('storyboard.story.itemPrompt', { n: i + 1 })} />
								</div>
								<span class="flex gap-1">{#each castNames(item.cast) as name, k (k)}<span class="inline-flex h-5 items-center gap-1 rounded border border-line-strong px-1.5 text-2xs text-fg-muted"><Icon name="user" class="h-3 w-3" />{name}</span>{/each}</span>
								<span class="flex items-center justify-between">
									<HostUi name="IconButton" props={{ icon: 'minus', label: t('storyboard.quick.shorter'), size: 'xs', onclick: () => nudge(item, -1) }} />
									<span class="vp-tc text-xs">{secs(item.dur)}</span>
									<HostUi name="IconButton" props={{ icon: 'plus', label: t('storyboard.quick.longer'), size: 'xs', onclick: () => nudge(item, 1) }} />
								</span>
								<span class="flex">
									<HostUi name="IconButton" props={{ icon: 'scissors', label: t('storyboard.story.split'), tooltip: t('storyboard.story.split'), size: 'xs', onclick: () => edit((list) => splitItem(list, i, ulid)) }} />
									<HostUi name="IconButton" props={{ icon: hostIconName('link'), label: t('storyboard.story.merge'), tooltip: t('storyboard.story.merge'), size: 'xs', disabled: i === proposal.length - 1, onclick: () => edit((list) => mergeItem(list, i)) }} />
									<HostUi name="IconButton" props={{ icon: hostIconName('chevron-left'), label: t('storyboard.story.up'), tooltip: t('storyboard.story.up'), size: 'xs', disabled: i === 0, onclick: () => edit((list) => moveItem(list, i, -1)) }} />
									<HostUi name="IconButton" props={{ icon: hostIconName('chevron-right'), label: t('storyboard.story.down'), tooltip: t('storyboard.story.down'), size: 'xs', disabled: i === proposal.length - 1, onclick: () => edit((list) => moveItem(list, i, 1)) }} />
									<HostUi name="IconButton" props={{ icon: 'trash', label: t('storyboard.story.remove'), tooltip: t('storyboard.story.remove'), size: 'xs', onclick: () => edit((list) => removeItem(list, i)) }} />
								</span>
							</div>
						{/each}
					{:else}
						<div class="flex h-full items-center justify-center gap-3 p-6 text-xs leading-5 text-fg-muted"><Icon name="wand" class="h-5 w-5 text-fg-subtle" /><span>{t('storyboard.story.empty')}</span></div>
					{/if}
				</div>
				<div class="flex h-11 shrink-0 items-center gap-2 border-t border-line px-3">
					{#if proposal}<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: toggleAll }}>{proposal.every((x) => x.keep) ? t('storyboard.story.none') : t('storyboard.story.all')}</HostUi>{/if}
					<div class="flex-1"></div>
					{#if proposal}<span class="text-2xs text-fg-subtle">{t('storyboard.story.safe')}</span>{/if}
					<HostUi name="Button" props={{ variant: 'primary', size: 'sm', icon: 'plus', disabled: !kept.length, onclick: add }}>{t('storyboard.story.add', { count: kept.length })}</HostUi>
				</div>
			</div>
		</div>
	{:else if ui.storyTab === 'todo'}
		<div class="grid min-h-0 flex-1 grid-cols-[320px_minmax(0,1fr)]">
			<div class="flex flex-col gap-2.5 overflow-auto border-r border-line p-3 text-xs">
				<div class="flex flex-col items-start gap-1 rounded-lg border border-line-strong p-2.5">
					<span class="text-fg-subtle">{t('panels.story.draftsLeft')}</span>
					<span class="vp-tc text-sm text-fg">{footage(todo)}</span>
					<span class="text-fg-subtle">{t('storyboard.story.takesCount', { count: draftsLeft })}</span>
					<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', icon: 'sparkles', class: 'mt-1', disabled: !todo.length, onclick: () => startGeneration({ clips: todo, quality: 'draft' }) }}>{t('storyboard.story.generateTodo')}</HostUi>
				</div>
				<div class="flex flex-col items-start gap-1 rounded-lg border border-line-strong p-2.5">
					<span class="text-fg-subtle">{t('panels.story.toFinal')}</span>
					<span class="vp-tc text-sm text-fg">{footage(open)}</span>
					<span class="text-fg-subtle">{t('panels.story.sequenceHint')}</span>
					<span class="mt-1"><FinalPassButton variant="secondary" /></span>
				</div>
				<div class="flex flex-col items-start gap-1 rounded-lg border border-line-strong p-2.5">
					<span class="text-fg-subtle">{t('storyboard.story.queue')}</span>
					<span class="vp-tc text-sm text-fg">{t('storyboard.story.queueCount', { count: flying })}</span>
				</div>
			</div>
			<div class="min-h-0 overflow-auto px-3 py-1.5">
				{#each open as c (c.id)}
					{@const activity = shotActivity(c.id)}
					<div class="flex items-center gap-2.5 border-b border-line py-1.5 text-xs">
						<span class="vp-tc text-fg-subtle">{shotNumber(c)}</span>
						<span class="h-1.5 w-1.5 shrink-0 rounded-full {stages[c.stage].dot}"></span>
						<span class="min-w-0 flex-1 truncate">{clipLabel(c)}</span>
						<span class="vp-tc text-fg-subtle">{secs(c.dur)}</span>
						<span class="w-28 {activity.state === 'running' ? 'text-signal' : stages[c.stage].tone}">{activity.state === 'running' ? (activity.running ? t('generation.state.running') : t('lib.status.queued')) : stages[c.stage].label}</span>
						<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => pickShot(c) }}>{t('storyboard.story.show')}</HostUi>
					</div>
				{:else}
					<p class="flex items-center gap-2 py-3 text-xs text-success"><Icon name="check" class="h-3.5 w-3.5" />{doc.clips.length ? t('panels.story.allDone') : t('panels.story.noShots')}</p>
				{/each}
			</div>
		</div>
	{:else}
		<div class="min-h-0 flex-1 overflow-auto px-3 py-1.5">
			{#each checks as check, n (n)}
				<div class="flex items-center gap-2.5 border-b border-line py-1.5 text-xs">
					<Icon name={check.kind === 'seam' ? 'link' : check.kind === 'failed' ? 'alert' : 'pencil'} class="h-3.5 w-3.5 shrink-0 text-warning" />
					<span class="vp-tc text-fg-subtle">{shotNumber(check.clip)}</span>
					<span class="min-w-0 flex-1 text-fg-muted">{check.text}</span>
					{#if check.kind === 'seam'}<SeamFix clip={check.clip} issue={check.issue} />{/if}
					{#if check.kind === 'failed'}<button type="button" class="vp-link-hit shrink-0 text-fg underline decoration-signal underline-offset-2" onclick={() => retryTake(check.take)}>{t('storyboard.check.retry')}</button>{/if}
					{#if check.kind === 'stale'}<button type="button" class="vp-link-hit shrink-0 text-fg underline decoration-signal underline-offset-2" onclick={() => startGeneration({ clips: [check.clip], quality: 'draft' })}>{t('storyboard.check.regenerate')}</button>{/if}
					{#if check.kind === 'prompt'}<button type="button" class="vp-link-hit shrink-0 text-fg underline decoration-signal underline-offset-2" onclick={() => writePrompt(check.clip)}>{t('storyboard.check.write')}</button>{/if}
					<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => showCheck(check) }}>{t('storyboard.story.show')}</HostUi>
				</div>
			{:else}
				<p class="flex items-center gap-2 py-3 text-xs text-success"><Icon name="check" class="h-3.5 w-3.5" />{t('storyboard.check.none')}</p>
			{/each}
		</div>
	{/if}
</div>

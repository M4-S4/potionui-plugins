<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatTime, t } from '../../i18n/index.svelte.js';
	import { ui, doc, globalPrompt, allIssues, directorView, followIssue } from '../../lib/state.svelte.js';
	import { showInReview } from '../../lib/band.svelte.js';
	import { engineLabel, openEngineSettings, takesOf } from '../../lib/production.svelte.js';
	import { takeStore } from '../../lib/takes.svelte.js';
	import { seams, matchToPrevious, seamTip } from '../../lib/continuity.svelte.js';
	import { currentLooks, lookState, measureLooks } from '../../lib/looks.svelte.js';
	import { castIssues, percent } from '../../lib/looks.js';
	import { review, reviewFix, reviewText, seamNames, suggest } from '../../lib/assistant.svelte.js';
	import { project } from '../../lib/project.svelte.js';
	import { CHARACTERS, PLACES, cardsOf, labelOf } from '../../lib/bible.js';
	import { VIEWS, VIEW_ICONS, citedWithout, promptShot, reviewCounts, reviewState, unnamedIn } from '../../lib/director.js';
	import { hasOwnEngine } from '../../lib/engine.js';
	import { isGlobal } from '../../lib/shots.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import { engineTitle, shotReceptionFor } from '../../lib/references.js';
	import { videoTracksOf } from '../../lib/vrefs.js';
	import { trackIssues, vrefLabel } from '../../lib/vreftracks.js';
	import { leaveAside, leastText, shotList, showTrack, sideText } from '../../lib/vreftracks.svelte.js';
	import { LIMITS } from '../../lib/reception.js';
	import PanelHeader from '../panels/PanelHeader.svelte';
	import SeamAction from '../takes/SeamAction.svelte';
	import Icon from '../Icon.svelte';

	const view = $derived(directorView());
	const chars = $derived(globalPrompt().length);
	const conflicts = $derived(allIssues().filter((i) => i.level !== 'missing'));
	const counts = $derived(reviewCounts(doc.clips, takeStore.list));
	const characters = $derived(cardsOf(doc, CHARACTERS));
	const places = $derived(cardsOf(doc, PLACES));
	const bibleIssues = $derived(
		[...characters.map((card) => [CHARACTERS, card]), ...places.map((card) => [PLACES, card])].flatMap(([kind, card]) => [
			...citedWithout(doc, kind, card).map((clip) => ({ cited: true, card, clip })),
			...unnamedIn(doc, kind, card).map((clip) => ({ cited: false, card, clip }))
		])
	);
	const seamIssues = $derived(seams().flatMap((s) => s.issues.map((x) => ({ ...x, clip: s.to }))));
	const looks = $derived(currentLooks());
	const lookIssues = $derived(castIssues(looks, doc.clips));
	const unmeasured = $derived(looks?.embedder.available ? looks.missing : 0);
	const failed = $derived(doc.clips.filter((c) => reviewState(takesOf(c)).failed));
	const checked = $derived(review.current?.projectId === project.id ? review.current : null);
	const globals = $derived(doc.references.filter(isGlobal).length);
	const own = $derived(doc.clips.filter(hasOwnEngine).length);
	const vrefTracks = $derived(videoTracksOf(doc));
	const trackChecks = $derived(vrefTracks.length ? trackIssues(doc.clips.map(shotReceptionFor), vrefTracks) : []);
	const total = $derived(conflicts.length + bibleIssues.length + seamIssues.length + failed.length + lookIssues.length + trackChecks.length);
	const lines = $derived({
		review: t('panels.director.sum.review', counts),
		direction: conflicts.length ? t('panels.director.sum.conflicts', { chars, count: conflicts.length }) : t('panels.director.sum.direction', { chars }),
		bible: t('panels.director.sum.bible', { characters: characters.length, places: places.length }),
		references: t('panels.director.sum.references', { count: doc.references.length, global: globals })
	});
	const warns = $derived({ review: counts.review, direction: conflicts.length, bible: bibleIssues.length, references: 0 });
	const engineLine = $derived(own ? t('panels.director.sum.engineOwn', { engine: engineLabel(), profile: doc.direction.mode, count: own }) : t('panels.director.sum.engine', { engine: engineLabel(), profile: doc.direction.mode }));
	const kindIcons = { identity: 'user', lum: 'palette', warm: 'palette', camera_change: 'camera', fl2va_no_frame: 'image', no_instruction: 'sparkles', conflict: 'sparkles', duration: 'range', cast_unnamed: 'user' };

	const num = (clip) => String(doc.clips.indexOf(clip) + 1).padStart(2, '0');
	const clipById = (id) => doc.clips.find((c) => c.id === id) ?? null;

	function trackText(issue) {
		const params = { label: vrefLabel(issue.track.slot), shots: shotList(issue.clips) };
		if (issue.status === 'ignored') return t('panels.director.check.vrefIgnored', { ...params, engine: engineTitle(issue.engine) });
		if (issue.status === 'trimmed') return t('panels.director.check.vrefTrimmed', { ...params, max: LIMITS.video });
		if (issue.status === 'short') return t('panels.director.check.vrefShort', { ...params, seconds: leastText(), side: sideText(issue.track.role) });
		return t('panels.director.check.vrefMissing', params);
	}

	function openCard(item) {
		ui.bibleCard = item.card.id;
		ui.directorView = 'bible';
	}

	function seamLabel(s) {
		const { from, to } = seamNames(s);
		return from && to && s.fromShotId !== s.toShotId ? t('assistant.review.seam', { from, to }) : to || from;
	}

	function goToSeam(s) {
		const c = clipById(s.toShotId) ?? clipById(s.fromShotId);
		if (c) showInReview(c);
	}
</script>

<PanelHeader icon="sparkles" title={t('shell.workspace.director')}>
	<HostUi name="IconButton" props={{ icon: 'sparkles', label: t('assistant.check'), tooltip: t('assistant.check'), size: 'sm', class: 'vp-h7', onclick: () => suggest(t('assistant.suggest.continuity')) }} />
</PanelHeader>

<div class="min-h-0 flex-1 overflow-auto">
	<nav class="border-b border-line py-1.5" aria-label={t('panels.director.views')}>
		{#each VIEWS as id (id)}
			{@const command = commandById(`view-${id}`)}
			<button
				type="button"
				class="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors {view === id ? 'bg-surface-2' : 'hover:bg-surface-2'}"
				style:box-shadow={view === id ? 'inset 2px 0 0 rgb(var(--signal))' : null}
				aria-current={view === id ? 'page' : undefined}
				onclick={() => (ui.directorView = id)}
			>
				<span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-3 {view === id ? 'text-fg' : 'text-fg-muted'}"><Icon name={VIEW_ICONS[id]} class="h-4 w-4" /></span>
				<span class="min-w-0 flex-1">
					<span class="block text-sm font-medium text-fg">{command?.label}</span>
					<span class="block truncate text-xs {warns[id] && id !== 'review' ? 'text-warning' : 'text-fg-muted'}">{lines[id]}</span>
				</span>
				{#if command?.key}<kbd class="vp-kbd shrink-0">{command.key}</kbd>{/if}
			</button>
		{/each}
		<div class="flex items-center gap-2.5 px-3 py-2">
			<span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-3 text-fg-muted"><Icon name="sliders" class="h-4 w-4" /></span>
			<span class="min-w-0 flex-1">
				<span class="block text-sm font-medium text-fg">{t('panels.director.engine')}</span>
				<span class="block truncate text-xs text-fg-muted">{engineLine}</span>
			</span>
			<HostUi name="Tooltip" props={{ text: t('production.editEngineTip', { engine: engineLabel() }), kbd: commandById('engine')?.key, wrapperClass: 'inline-flex shrink-0' }}>
				<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', onclick: () => openEngineSettings() }}>{t('production.editEngine')}</HostUi>
			</HostUi>
		</div>
	</nav>

	<section class="space-y-2 p-3" aria-labelledby="vp-director-check">
		<div class="flex items-center justify-between gap-2">
			<span id="vp-director-check" class="vp-section-title">{t('panels.director.check.title')}</span>
			{#if total}<span class="vp-tc text-xs text-fg-subtle">{total}</span>{/if}
		</div>
		{#if !total && !checked}
			<p class="flex items-center gap-2 text-xs text-fg-subtle"><Icon name="check" class="h-3.5 w-3.5 text-success" />{t('panels.director.check.none')}</p>
		{/if}
		{#if unmeasured}
			<p class="flex flex-wrap items-center gap-x-2 text-xs text-fg-subtle" data-looks-missing>
				<span>{t('panels.director.check.looksMissing', { count: unmeasured })}</span>
				<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2 disabled:opacity-50" disabled={lookState.asking} onclick={measureLooks}>{t('panels.director.pick.measure')}</button>
			</p>
		{/if}
		<ul class="space-y-1.5 text-xs">
			{#each conflicts as i, n (n)}
				{@const shot = promptShot(doc, i.prompt)}
				<li>
					<button type="button" class="flex w-full items-start gap-1.5 text-left text-fg-muted hover:text-fg" onclick={() => followIssue(i)}>
						<Icon name="sparkles" class="mt-px h-3.5 w-3.5 shrink-0 text-warning" /><span class="min-w-0 flex-1">{shot ? `${num(shot)} · ${i.text}` : i.text}</span>
					</button>
				</li>
			{/each}
			{#each bibleIssues as item, n (n)}
				<li>
					<button type="button" class="flex w-full items-start gap-1.5 text-left text-fg-muted hover:text-fg" onclick={() => openCard(item)}>
						<Icon name="user" class="mt-px h-3.5 w-3.5 shrink-0 text-warning" />
						<span class="min-w-0 flex-1">{item.cited ? t('panels.director.check.cited', { shot: num(item.clip), name: labelOf(item.card) }) : t('panels.director.check.unnamed', { shot: num(item.clip), name: labelOf(item.card) })}</span>
					</button>
				</li>
			{/each}
			{#each trackChecks as issue (issue.key)}
				<li class="flex gap-1.5 text-fg-muted" data-track-check={issue.status}>
					<Icon name="film" class="mt-px h-3.5 w-3.5 shrink-0 {issue.status === 'ignored' ? 'text-fg-subtle' : 'text-warning'}" />
					<div class="min-w-0 flex-1">
						<button type="button" class="block text-left hover:text-fg" onclick={() => showTrack(issue.track.id)}>{trackText(issue)}</button>
						<div class="mt-0.5 flex flex-wrap items-center gap-x-3">
							<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => (ui.modal = { type: 'shot', id: issue.clips[0].id })}>{t('panels.director.check.open', { shot: num(issue.clips[0]) })}</button>
							<button type="button" class="vp-link-hit text-fg underline decoration-line-hover underline-offset-2 hover:decoration-2" onclick={() => leaveAside(issue.track.id, issue.clips)}>{t('panels.director.check.leave')}</button>
						</div>
					</div>
				</li>
			{/each}
			{#each failed as clip (clip.id)}
				<li>
					<button type="button" class="flex w-full items-start gap-1.5 text-left text-fg-muted hover:text-fg" onclick={() => showInReview(clip)}>
						<Icon name="alert" class="mt-px h-3.5 w-3.5 shrink-0 text-danger" /><span class="min-w-0 flex-1">{t('panels.director.check.failed', { shot: num(clip) })}</span>
					</button>
				</li>
			{/each}
			{#each lookIssues as item (`${item.takeId}:${item.card.cardId}`)}
				<li>
					<button type="button" class="flex w-full items-start gap-1.5 text-left text-fg-muted hover:text-fg" data-look-issue={item.clip.id} onclick={() => showInReview(item.clip)}>
						<Icon name="user" class="mt-px h-3.5 w-3.5 shrink-0 text-warning" />
						<span class="min-w-0 flex-1">{t('panels.director.check.castLook', { shot: num(item.clip), name: item.card.label, score: percent(item.card.score) })}</span>
					</button>
				</li>
			{/each}
			{#each seamIssues as i, n (n)}
				<li class="flex gap-1.5 text-fg-muted">
					<Icon name={i.kind === 'identity' ? 'user' : 'palette'} class="mt-px h-3.5 w-3.5 shrink-0 text-warning" />
					<div class="min-w-0 flex-1">
						<span>{i.text}</span>
						<div class="mt-0.5 flex flex-wrap items-center gap-x-3">
							{#if i.fix}
								<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => matchToPrevious(i.clip)}>{t('panels.dock.match')}</button>
							{:else}
								<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => showInReview(i.clip)}>{t('panels.dock.seeTakes')}</button>
							{/if}
							<SeamAction clip={i.clip} />
						</div>
					</div>
				</li>
			{/each}
		</ul>

		{#if checked}
			<section class="rounded-lg border border-line-strong p-2.5" aria-label={t('assistant.review.title')}>
				<div class="mb-1.5 flex items-center justify-between gap-2">
					<span class="vp-section-title">{t('assistant.review.title')}</span>
					<span class="flex items-center gap-1">
						<span class="vp-tc text-xs text-fg-subtle">{t('assistant.review.meta', { time: formatTime(new Date(checked.checkedAt)) })}</span>
						<HostUi name="IconButton" props={{ icon: hostIconName('x'), label: t('assistant.review.dismiss'), tooltip: t('assistant.review.dismiss'), size: 'xs', onclick: () => (review.current = null) }} />
					</span>
				</div>
				{#if checked.seams.length}
					<ul class="space-y-2">
						{#each checked.seams as s, n (n)}
							<li class="text-xs">
								<button type="button" class="vp-link-hit block max-w-full truncate text-left font-medium text-fg hover:underline" onclick={() => goToSeam(s)}>{seamLabel(s)}</button>
								<ul class="mt-1 space-y-1.5">
									{#each s.issues as i, k (k)}
										<li class="flex items-start gap-1.5 text-fg-muted">
											<Icon name={kindIcons[i.kind] ?? 'link'} class="mt-px h-3.5 w-3.5 shrink-0 text-fg-subtle" />
											<div class="min-w-0 flex-1">
												<p>{reviewText(s, i)}</p>
												{#if reviewFix(s, i)}<p class="mt-0.5 text-fg-subtle">{reviewFix(s, i)}</p>{/if}
												{#if i.kind === 'fl2va_no_frame' && clipById(i.shotId ?? s.toShotId)}<div class="mt-0.5"><SeamAction clip={clipById(i.shotId ?? s.toShotId)} /></div>{/if}
											</div>
											{#if i.measured}
												<HostUi name="Tooltip" props={{ text: i.kind === 'identity' ? t('assistant.review.measuredLookTip') : seamTip(s.toShotId), wrapperClass: 'inline-flex shrink-0' }}>
													<HostUi name="Badge" props={{ variant: 'neutral', size: 'md' }}>{t('assistant.review.measured')}</HostUi>
												</HostUi>
											{/if}
										</li>
									{/each}
								</ul>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="flex items-center gap-2 text-xs text-fg-subtle"><Icon name="check" class="h-3.5 w-3.5 text-success" />{t('assistant.review.clear')}</p>
				{/if}
			</section>
		{/if}
	</section>
</div>

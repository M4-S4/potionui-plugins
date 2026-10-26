<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, undo, toast, select, secs, globalPrompt, allIssues } from '../../lib/state.svelte.js';
	import { seek } from '../../lib/playback.svelte.js';
	import { directionFields } from '../../lib/catalog.js';
	import { convertDirection } from '../../lib/bible.js';
	import { ulid } from '../../lib/ulid.js';
	import { commandById } from '../../lib/commands.js';
	import { hostIconName } from '../../lib/icons.js';
	import DirectorViews from './DirectorViews.svelte';
	import Icon from '../Icon.svelte';

	const MAX = 4000;
	let freeOpen = $state(false);
	const chars = $derived(globalPrompt().length);
	const conflicts = $derived(allIssues().filter((i) => i.level !== 'missing'));
	const free = $derived(String(doc.direction.personnages ?? '').trim());

	function openPrompt(p) {
		select('prompt', p.id);
		seek(p.start);
		ui.modal = { type: 'prompt', id: p.id };
	}

	function library(key) {
		ui.modal = { type: 'library', target: { kind: 'direction', key } };
	}

	function convert() {
		let card = null;
		act(() => (card = convertDirection(doc, ulid())));
		if (!card) return;
		ui.bibleCard = card.id;
		toast(t('panels.dock.bible.converted', { count: doc.clips.length }), 'success', { label: t('shell.toast.undo'), run: undo });
	}
</script>

<section class="isolate flex min-h-0 min-w-0 flex-col bg-canvas" aria-label={commandById('view-direction')?.label}>
	<div class="flex h-10 shrink-0 items-center gap-3 border-b border-line px-4">
		<DirectorViews />
		<span class="shrink-0 text-sm font-semibold">{commandById('view-direction')?.label}</span>
		<span class="min-w-0 truncate text-xs {chars > MAX ? 'text-danger' : 'text-fg-subtle'}">{t('panels.director.direction.subtitle', { chars, max: MAX })}</span>
	</div>

	<div class="min-h-0 flex-1 overflow-auto">
		<div class="space-y-3 p-5" style:max-width="800px">
			{#if conflicts.length}
				<HostUi name="Alert" props={{ variant: 'warning', class: '[&>div]:text-fg', density: 'compact', icon: hostIconName('alert'), title: t('panels.director.direction.conflicts', { count: conflicts.length }), live: 'off' }}>
					<ul class="mt-1.5 space-y-1.5">
						{#each conflicts as i, n (n)}
							<li class="text-xs text-fg-muted">
								{i.text}
								<button type="button" class="vp-link-hit text-fg underline decoration-signal underline-offset-2 hover:decoration-2" onclick={() => openPrompt(i.prompt)}>{t('panels.dock.issuePrompt', { time: secs(i.prompt.start) })}</button>
							</li>
						{/each}
					</ul>
				</HostUi>
			{/if}

			{#each directionFields as f (f.key)}
				{#if f.key === 'personnages' && !free && !freeOpen}
					<div class="flex flex-wrap items-center gap-3 rounded-lg border border-line-strong p-3">
						<Icon name="book" class="h-4 w-4 shrink-0 text-fg-muted" />
						<div class="min-w-0 flex-1">
							<div class="text-sm font-semibold text-fg">{f.label}</div>
							<p class="text-xs text-fg-muted">{t('panels.director.direction.castText')}</p>
						</div>
						<HostUi name="Button" props={{ variant: 'secondary', size: 'xs', onclick: () => (ui.directorView = 'bible') }}>{t('panels.director.direction.openBible')}</HostUi>
						<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'plus', onclick: () => (freeOpen = true) }}>{t('panels.director.direction.addFree')}</HostUi>
					</div>
				{:else}
					<div class="space-y-1.5 rounded-lg border border-line p-3">
						<div class="flex items-center gap-2">
							<label for="vp-direction-{f.key}" class="text-sm font-semibold text-fg">{f.label}</label>
							<span class="min-w-0 flex-1 truncate text-xs text-fg-subtle">{f.hint}</span>
							<span class="vp-tc shrink-0 text-xs text-fg-subtle">{String(doc.direction[f.key] ?? '').length}</span>
							<button type="button" class="flex min-h-6 shrink-0 items-center gap-1 text-xs text-fg-muted hover:text-fg" onclick={() => library(f.key)}><Icon name="wand" class="h-3.5 w-3.5" />{t('panels.dock.library')}</button>
						</div>
						<textarea id="vp-direction-{f.key}" class="input text-sm" rows="3" bind:value={doc.direction[f.key]} placeholder={f.hint} oninput={() => (ui.dirty = true)}></textarea>
						{#if f.key === 'personnages' && free}
							<div class="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
								<p class="min-w-0 flex-1">{t('panels.dock.bible.convert')}</p>
								<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: 'user', onclick: convert }}>{t('panels.dock.bible.convertAction')}</HostUi>
							</div>
						{/if}
					</div>
				{/if}
			{/each}
		</div>
	</div>
</section>

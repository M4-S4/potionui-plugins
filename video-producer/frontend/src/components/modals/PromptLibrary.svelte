<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { formatTime, t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, toast, overlaps, itemsIn, secs, clipLabel, promptEdited } from '../../lib/state.svelte.js';
	import {
		templates,
		libraries,
		categories,
		profiles,
		libraryLabel,
		categoryLabel,
		tplName,
		tplDescription,
		tplKeywords,
		tplText,
		materialize,
		assistantParts,
		partLabel,
		optionLabel,
		composePrompt,
		fillVars,
		missingVars,
		varLabel,
		varName,
		defaultVars,
		promptLocale
	} from '../../lib/library.svelte.js';
	import { directionFields } from '../../lib/catalog.js';
	import { suggest } from '../../lib/assistant.svelte.js';
	import { hostIconName } from '../../lib/icons.js';
	import { ulid } from '../../lib/ulid.js';
	import { copyText } from '../../lib/clipboard.js';
	import Modal from './Modal.svelte';
	import Tabs from '../shell/Tabs.svelte';
	import Icon from '../Icon.svelte';

	let { target = null, tab: initialTab = 'library' } = $props();
	let tab = $state(firstTab());

	function firstTab() {
		return initialTab === 'assistant' ? 'assistant' : 'library';
	}

	const targetPrompt = $derived(target?.kind === 'prompt' ? doc.prompts.find((p) => p.id === target.id) : null);
	const targetShot = $derived(target?.kind === 'shot' ? doc.clips.find((c) => c.id === target.id) : null);
	const targetLabel = $derived(
		target?.kind === 'direction'
			? t('library.target.direction', { field: directionFields.find((f) => f.key === target.key)?.label ?? '' })
			: targetPrompt
				? t('library.target.prompt', { time: secs(targetPrompt.start) })
				: targetShot
					? t('library.target.shot', { shot: clipLabel(targetShot) })
					: t('library.target.none')
	);
	const range = $derived(targetPrompt ? [targetPrompt.start, targetPrompt.start + targetPrompt.dur] : targetShot ? [targetShot.start, targetShot.start + targetShot.dur] : null);
	let mode = $state('append');

	const tabs = $derived([
		{ id: 'library', label: t('library.tab.library') },
		{ id: 'assistant', label: t('library.tab.composer') }
	]);
	const modes = $derived([
		{ id: 'append', label: t('library.append') },
		{ id: 'replace', label: t('library.replace') }
	]);
	const profileItems = profiles.map((p) => ({ id: p, label: p }));

	function back() {
		ui.modal = target?.returnTo ?? null;
	}

	function suggestion() {
		if (target?.kind === 'direction') return t('assistant.suggest.direction', { field: directionFields.find((f) => f.key === target.key)?.label ?? '' });
		if (targetShot) return t('assistant.suggest.shot', { shot: clipLabel(targetShot) });
		if (!targetPrompt) return t('assistant.suggest.library');
		const shot = doc.clips.find((c) => c.id === targetPrompt.shotId);
		return shot ? t('assistant.suggest.shot', { shot: clipLabel(shot) }) : t('assistant.suggest.promptAt', { time: secs(targetPrompt.start) });
	}

	function askAssistant() {
		const text = suggestion();
		ui.modal = null;
		suggest(text);
	}

	async function insert(text) {
		const clean = text.trim();
		if (!clean) return;
		const merge = (old) => (mode === 'replace' || !old?.trim() ? clean : `${old.trim()} ${clean}`);
		if (target?.kind === 'direction') act(() => (doc.direction[target.key] = merge(doc.direction[target.key])));
		else if (targetPrompt)
			act(() => {
				const before = targetPrompt.text;
				targetPrompt.text = merge(before);
				promptEdited(targetPrompt, before);
			});
		else if (targetShot && target.returnTo?.draft) target.returnTo.draft.text = merge(target.returnTo.draft.text);
		else if (!(await copyText(clean))) return toast(t('library.copyFailed'), 'warning');
		templates.push({
			id: ulid(),
			lib: 'Historique',
			cat: current?.cat ?? 'Cinéma',
			profiles: [doc.direction.mode],
			fav: false,
			name: clean.slice(0, 32) + '…',
			description: t('library.insertedAt', { time: formatTime(new Date()) }),
			keywords: [],
			text: clean
		});
		toast(target ? (mode === 'replace' ? t('library.replaced', { target: targetLabel }) : t('library.added', { target: targetLabel })) : t('library.copied'));
		back();
	}

	let lib = $state('Intégrée');
	let cat = $state(null);
	let q = $state('');
	const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
	const inLib = (x, l) => (l === 'Favoris' ? x.fav : x.lib === l);
	const list = $derived(templates.filter((x) => inLib(x, lib) && (!cat || x.cat === cat) && (!q || norm(`${tplName(x)} ${tplDescription(x)} ${tplKeywords(x).join(' ')}`).includes(norm(q)))));
	let currentId = $state('t1');
	const current = $derived(templates.find((x) => x.id === currentId));
	function initialCast() {
		if (target?.returnTo?.draft) return target.returnTo.draft.cast ?? null;
		const shotId = target?.kind === 'shot' ? target.id : target?.kind === 'prompt' ? doc.prompts.find((p) => p.id === target.id)?.shotId : null;
		return doc.clips.find((c) => c.id === shotId)?.cast ?? null;
	}
	let vars = $state(defaultVars(initialCast()));
	const tVars = $derived(current ? missingVars(tplText(current)) : []);
	let edited = $state(null);
	const preview = $derived(edited ?? (current ? fillVars(tplText(current), vars) : ''));
	const stillMissing = $derived(missingVars(preview));

	function choose(id) {
		currentId = id;
		edited = null;
	}

	function libIcon(l) {
		if (l === 'Favoris') return 'star';
		if (l === 'Historique') return 'history';
		if (l === 'Projet') return 'film';
		if (l === 'Personnelle') return 'user';
		return 'book';
	}

	function saveCopy() {
		const f = materialize(current);
		templates.push({ id: ulid(), lib: 'Personnelle', cat: current.cat, profiles: [...current.profiles], fav: false, name: t('library.copyName', { name: f.name }), description: f.description, keywords: [...f.keywords], text: preview });
		toast(t('library.saved'));
	}

	let parts = $state({ camera: 'dolly', light: 'morning', style: 'contemplative', acting: 'silence' });
	let custom = $state({ camera: '', light: '', style: '', acting: '' });
	let profile = $state(doc.direction.mode);
	let aEdited = $state(null);
	const composed = $derived(
		composePrompt(
			{
				camera: custom.camera || optionLabel(parts.camera, promptLocale()),
				light: custom.light || optionLabel(parts.light, promptLocale()),
				style: custom.style || optionLabel(parts.style, promptLocale()),
				acting: custom.acting || optionLabel(parts.acting, promptLocale())
			},
			vars,
			profile
		)
	);
	const aText = $derived(aEdited ?? composed);
	const aMissing = $derived(missingVars(aText));
	const scope = $derived(range ? itemsIn(range) : null);
	const needs = $derived.by(() => {
		const out = [];
		if (profile === 'FL2VA') out.push({ ok: scope ? scope.frames.length >= 1 : false, text: t('library.need.frames') });
		if (profile === 'Ref2VA') out.push({ ok: doc.references.some((r) => r.role === 'Identité'), text: t('library.need.identity') });
		if (profile === 'Hybrid AV') out.push({ ok: range ? doc.audio.some((a) => overlaps(a.start, a.dur, range)) : false, text: t('library.need.audio') });
		return out;
	});
	const profileHint = $derived(profile === 'FL2VA' ? t('library.profile.fl2va') : profile === 'Ref2VA' ? t('library.profile.ref2va') : t('library.profile.hybrid'));

	function pick(k, v) {
		parts[k] = parts[k] === v ? '' : v;
		custom[k] = '';
		aEdited = null;
	}

	function setProfile(id) {
		profile = id;
		aEdited = null;
	}
</script>

<Modal title={t('library.title')} subtitle={t('library.subtitle', { target: targetLabel })} icon="wand" width={1000} onclose={back}>
	<Tabs label={t('library.tabs')} class="!px-4" value={tab} onselect={(id) => (tab = id)} items={tabs}>
		<button type="button" class="flex min-h-6 items-center gap-1.5 self-center text-xs text-fg-muted hover:text-fg" onclick={askAssistant}><Icon name="sparkles" class="h-3.5 w-3.5 text-ai-1" />{t('library.askAssistant')}</button>
	</Tabs>

	{#if tab === 'library'}
		<div class="grid h-[520px] grid-cols-[190px_1fr_330px]">
			<nav class="space-y-4 overflow-auto border-r border-line p-3" aria-label={t('library.nav')}>
				<ul class="space-y-0.5">
					{#each libraries as l (l)}
						<li>
							<button type="button" class="flex h-7 w-full items-center gap-2 rounded px-2 text-sm {lib === l ? 'bg-surface-3 text-fg' : 'text-fg-muted hover:bg-surface-2'}" aria-pressed={lib === l} onclick={() => (lib = l)}>
								<Icon name={libIcon(l)} class="h-3.5 w-3.5" /><span class="flex-1 text-left">{libraryLabel(l)}</span><span class="text-xs text-fg-muted">{templates.filter((x) => inLib(x, l)).length}</span>
							</button>
						</li>
					{/each}
				</ul>
				<div>
					<div class="vp-section-title mb-1 px-2">{t('library.categories')}</div>
					<ul class="space-y-0.5">
						<li>
							<button type="button" class="h-7 w-full rounded px-2 text-left text-sm {!cat ? 'bg-surface-3 text-fg' : 'text-fg-muted hover:bg-surface-2'}" aria-pressed={!cat} onclick={() => (cat = null)}>{t('library.allCategories')}</button>
						</li>
						{#each categories as c (c)}
							<li>
								<button type="button" class="h-7 w-full rounded px-2 text-left text-sm {cat === c ? 'bg-surface-3 text-fg' : 'text-fg-muted hover:bg-surface-2'}" aria-pressed={cat === c} onclick={() => (cat = c)}>{categoryLabel(c)}</button>
							</li>
						{/each}
					</ul>
				</div>
			</nav>

			<div class="flex min-h-0 flex-col border-r border-line">
				<div class="relative p-3">
					<Icon name="search" class="pointer-events-none absolute left-5 top-[19px] h-4 w-4 text-fg-subtle" />
					<input class="input vp-dense w-full !pl-7" placeholder={t('library.search')} bind:value={q} aria-label={t('library.searchLabel')} />
				</div>
				<ul class="min-h-0 flex-1 space-y-1 overflow-auto px-3 pb-3">
					{#each list as x (x.id)}
						<li class="relative">
							<button
								type="button"
								class="w-full rounded-lg border p-2.5 pr-9 text-left {currentId === x.id ? 'border-signal ring-1 ring-signal' : 'border-line-strong hover:border-line-hover'}"
								aria-pressed={currentId === x.id}
								onclick={() => choose(x.id)}
							>
								<span class="flex items-center gap-2">
									<span class="flex-1 text-sm font-medium">{tplName(x)}</span>
									<span class="text-xs text-fg-subtle">{categoryLabel(x.cat)}</span>
								</span>
								<span class="mt-0.5 block text-xs text-fg-muted">{tplDescription(x)}</span>
								<span class="mt-1.5 flex flex-wrap items-center gap-1">
									{#each x.profiles as pr (pr)}
										<HostUi name="Badge" props={{ variant: 'neutral', size: 'md', class: pr === doc.direction.mode ? '!border-signal !text-fg' : '' }}>{pr}</HostUi>
									{/each}
									{#each tplKeywords(x).slice(0, 3) as k (k)}<span class="text-xs text-fg-subtle">#{k}</span>{/each}
								</span>
							</button>
							<span class="absolute right-1.5 top-1.5">
								<HostUi
									name="IconButton"
									props={{ icon: 'star', label: t('library.favorite'), tooltip: t('library.favorite'), size: 'xs', class: x.fav ? 'vp-toggle !text-warning' : 'vp-toggle', ariaPressed: !!x.fav, onclick: () => (x.fav = !x.fav) }}
								/>
							</span>
						</li>
					{:else}
						<li>
							<HostUi
								name="EmptyState"
								props={{ compact: true, icon: hostIconName('book'), title: t('library.empty'), description: lib === 'Personnelle' || lib === 'Favoris' ? t('library.emptyHint') : undefined }}
							/>
						</li>
					{/each}
				</ul>
			</div>

			<div class="flex min-h-0 flex-col overflow-auto p-3">
				{#if current}
					<div class="text-sm font-medium">{tplName(current)}</div>
					<div class="mb-3 text-xs text-fg-subtle">
						{t('library.compatible', { profiles: current.profiles.join(', ') })}{current.profiles.includes(doc.direction.mode) ? '' : ` · ${t('library.notOptimized', { profile: doc.direction.mode })}`}
					</div>
					{#if tVars.length}
						<div class="vp-section-title mb-1.5">{t('library.variables')}</div>
						<div class="mb-3 grid grid-cols-2 gap-1.5">
							{#each tVars as v (v)}
								<label class="space-y-0.5"><span class="block text-xs text-fg-muted">{varLabel(v)}</span><input class="input vp-dense w-full" bind:value={vars[v]} oninput={() => (edited = null)} /></label>
							{/each}
						</div>
					{/if}
					<div class="vp-section-title mb-1.5">{t('library.preview')}</div>
					<textarea class="input mb-1 w-full text-sm" rows="5" value={preview} oninput={(e) => (edited = e.currentTarget.value)} aria-label={t('library.previewLabel')}></textarea>
					{#if stillMissing.length}<div class="mb-2 text-xs text-warning">{t('library.toFill', { list: stillMissing.map(varName).join(', ') })}</div>{/if}
					{@render insertControls(preview)}
					<span class="mt-1">
						<HostUi name="Button" props={{ variant: 'ghost', size: 'xs', icon: hostIconName('save'), onclick: saveCopy }}>{t('library.saveCopy')}</HostUi>
					</span>
				{/if}
			</div>
		</div>
	{:else}
		<div class="grid h-[520px] grid-cols-[1fr_360px]">
			<div class="space-y-4 overflow-auto border-r border-line p-4">
				<div class="flex items-center gap-2">
					<span class="vp-label">{t('library.profileH3')}</span>
					<HostUi name="SegmentedControl" props={{ items: profileItems, selected: profile, variant: 'toggle', ariaLabel: t('library.profileH3'), onSelect: setProfile }} />
					<span class="text-xs text-fg-subtle">{profileHint}</span>
				</div>
				{#each Object.entries(assistantParts) as [k, options], i (k)}
					<div>
						<div class="mb-1.5 flex items-center gap-2">
							<span class="flex h-4 w-4 items-center justify-center rounded-sm bg-surface-3 text-2xs font-semibold">{i + 1}</span>
							<span class="text-sm font-medium">{partLabel(k)}</span>
						</div>
						<div class="flex flex-wrap gap-1.5">
							{#each options as o (o)}
								<button type="button" class="vp-pill" aria-pressed={parts[k] === o && !custom[k]} onclick={() => pick(k, o)}>{optionLabel(o)}</button>
							{/each}
							<input
								class="input vp-dense w-40 !rounded-full"
								placeholder={t('library.other')}
								bind:value={custom[k]}
								oninput={() => (aEdited = null)}
								aria-label={t('library.customLabel', { part: partLabel(k) })}
							/>
						</div>
					</div>
				{/each}
				<div>
					<div class="mb-1.5 text-sm font-medium">{t('library.variables')}</div>
					<div class="grid grid-cols-4 gap-2">
						{#each ['subject', 'action', 'place', 'emotion'] as v (v)}
							<label class="space-y-0.5"><span class="block text-xs text-fg-muted">{varLabel(v)}</span><input class="input vp-dense w-full" bind:value={vars[v]} oninput={() => (aEdited = null)} /></label>
						{/each}
					</div>
				</div>
			</div>
			<div class="flex min-h-0 flex-col overflow-auto p-4">
				<div class="vp-section-title mb-1.5">{t('library.final')}</div>
				<textarea class="input mb-2 w-full text-sm" rows="7" value={aText} oninput={(e) => (aEdited = e.currentTarget.value)} aria-label={t('library.finalLabel')}></textarea>
				{#if aEdited != null}<button type="button" class="mb-2 min-h-6 self-start text-xs text-signal hover:underline" onclick={() => (aEdited = null)}>{t('library.recompose')}</button>{/if}
				{#if aMissing.length}<div class="mb-2 flex gap-1.5 text-xs text-warning"><Icon name="alert" class="h-3.5 w-3.5" />{t('library.missing', { list: aMissing.map(varName).join(', ') })}</div>{/if}
				<div class="vp-section-title mb-1.5">{t('library.needs')}</div>
				<ul class="mb-3 space-y-1">
					{#each needs as n, i (i)}
						<li class="flex gap-1.5 text-xs {n.ok ? 'text-fg-muted' : 'text-warning'}"><Icon name={n.ok ? 'check' : 'alert'} class="mt-px h-3.5 w-3.5 shrink-0 {n.ok ? 'text-success' : ''}" />{n.text}</li>
					{/each}
				</ul>
				<div class="mt-auto">{@render insertControls(aText)}</div>
			</div>
		</div>
	{/if}
</Modal>

{#snippet insertControls(text)}
	<div class="space-y-2">
		<HostUi name="SegmentedControl" props={{ items: modes, selected: mode, variant: 'toggle', fullWidth: true, ariaLabel: t('library.insertMode'), onSelect: (id) => (mode = id) }} />
		<HostUi name="Button" props={{ variant: 'primary', size: 'sm', class: 'w-full', disabled: !text.trim(), onclick: () => insert(text) }}>{target ? t('library.insert') : t('library.copy')}</HostUi>
	</div>
{/snippet}

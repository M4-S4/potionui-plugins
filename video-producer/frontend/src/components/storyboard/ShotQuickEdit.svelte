<script>
	import HostUi from '../../../../../../sdk/HostUi.svelte';
	import { t } from '../../i18n/index.svelte.js';
	import { ui, doc, act, secs, clipLabel, promptOf } from '../../lib/state.svelte.js';
	import { takesOf, engineChoices, engineGroups, engineLabel, soundOf, shotDurationLimit } from '../../lib/production.svelte.js';
	import { optionKey } from '../../lib/generation.js';
	import { shotEngineOf } from '../../lib/engine.js';
	import { castLabels } from '../../lib/bible.js';
	import { seamImage } from '../../lib/seam.js';
	import { stages } from '../../lib/catalog.js';
	import { hostIconName } from '../../lib/icons.js';
	import { BAND_STEP } from '../../lib/band.js';
	import { applyQuick } from '../../lib/band.svelte.js';
	import DraftsField from '../shots/DraftsField.svelte';
	import SoundNote from '../shots/SoundNote.svelte';
	import Icon from '../Icon.svelte';

	let { clip } = $props();

	let text = $state('');
	let editing = $state(false);
	const prompt = $derived(promptOf(clip)?.text ?? '');
	const index = $derived(doc.clips.indexOf(clip));
	const takes = $derived(takesOf(clip));
	const done = $derived(takes.filter((x) => x.status === 'done').length);
	const own = $derived(shotEngineOf(clip));
	const key = $derived(own.preset ? optionKey(own.preset, own.model ?? null) : '');
	const known = $derived(key ? engineChoices().some((o) => o.key === key) : true);
	const groups = $derived(engineGroups());
	const limit = $derived(shotDurationLimit(clip));
	const cast = $derived(castLabels(doc, clip));
	const sound = $derived(soundOf(clip));
	const first = $derived(seamImage(doc, clip.id, 'first'));
	const last = $derived(seamImage(doc, clip.id, 'last'));
	const changed = $derived(editing && done > 0 && text.trim() !== prompt.trim());

	$effect(() => {
		const value = prompt;
		if (!editing) text = value;
	});

	function savePrompt() {
		editing = false;
		if (text.trim() !== prompt.trim()) applyQuick(clip, { text });
	}

	function rename(e) {
		const value = e.currentTarget.value.trim();
		if (value && value !== clip.label) act(() => (clip.label = value));
	}

	function setDuration(value) {
		const dur = Number(String(value).replace(',', '.'));
		if (Number.isFinite(dur) && dur > 0) applyQuick(clip, { dur });
	}

	function pickEngine(value) {
		const { preset, model, backend, ...rest } = own;
		const option = engineChoices().find((o) => o.key === value);
		applyQuick(clip, { engine: option ? { ...rest, preset: option.preset, model: option.model, backend: option.backend } : rest });
	}

	const editor = () => (ui.modal = { type: 'shot', id: clip.id });
</script>

<div class="flex flex-col gap-2.5" data-quick-edit={clip.id}>
	<div class="flex min-w-0 items-center gap-2">
		<span class="vp-tc text-xs text-fg-subtle">{String(index + 1).padStart(2, '0')}</span>
		<input class="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1.5 py-0.5 text-md font-semibold text-fg hover:border-line-strong focus:border-signal focus:bg-surface-2 focus:outline-none" value={clipLabel(clip)} onchange={rename} aria-label={t('storyboard.shotName', { n: index + 1 })} />
		<span class="flex shrink-0 items-center gap-1.5 text-xs {stages[clip.stage].tone}"><span class="h-1.5 w-1.5 rounded-full {stages[clip.stage].dot}"></span>{stages[clip.stage].label}</span>
		<span class="vp-tc shrink-0 text-2xs text-fg-subtle">{secs(clip.start)} → {secs(clip.start + clip.dur)}</span>
	</div>

	<label class="flex flex-col gap-1">
		<span class="vp-label">{t('storyboard.quick.prompt')}</span>
		<textarea
			id="vp-quick-prompt"
			class="input text-sm leading-5"
			rows="2"
			bind:value={text}
			placeholder={t('modals.prompt.placeholder')}
			onfocus={() => (editing = true)}
			onblur={savePrompt}
			onkeydown={(e) => (e.key === 'Enter' && (e.ctrlKey || e.metaKey) ? (e.preventDefault(), e.currentTarget.blur()) : null)}
		></textarea>
		{#if changed}<span class="flex items-center gap-1.5 text-xs text-warning"><Icon name="pencil" class="h-3 w-3" />{t('modals.shot.staleWarning')}</span>{/if}
	</label>

	<div class="flex items-end gap-2.5">
		<label class="flex w-[124px] flex-col gap-1">
			<span class="vp-label">{t('storyboard.quick.duration')}</span>
			<span class="flex items-center gap-0.5">
				<HostUi name="IconButton" props={{ icon: 'minus', label: t('storyboard.quick.shorter'), size: 'xs', onclick: () => setDuration(clip.dur - BAND_STEP) }} />
				<input class="input vp-dense vp-tc min-w-0 flex-1 text-center" value={clip.dur.toFixed(1)} inputmode="decimal" onchange={(e) => setDuration(e.currentTarget.value)} aria-label={t('storyboard.quick.duration')} />
				<HostUi name="IconButton" props={{ icon: 'plus', label: t('storyboard.quick.longer'), size: 'xs', onclick: () => setDuration(clip.dur + BAND_STEP) }} />
			</span>
		</label>
		<label class="flex min-w-0 flex-1 flex-col gap-1">
			<span class="vp-label">{t('modals.shot.engineChoice')}</span>
			<select class="vp-popup w-full" value={key} onchange={(e) => pickEngine(e.currentTarget.value)}>
				<option value="">{t('modals.shot.asProject', { value: engineLabel() })}</option>
				{#if key && !known}<option value={key}>{t('generation.engine.unavailable')}</option>{/if}
				{#each groups as g (g.label)}
					<optgroup label={g.label}>
						{#each g.options as o (o.key)}<option value={o.key}>{o.label}</option>{/each}
					</optgroup>
				{/each}
			</select>
		</label>
		<div class="flex flex-col gap-1">
			<span class="vp-label">{t('generation.drafts.label')}</span>
			<DraftsField clips={[clip]} label={false} />
		</div>
	</div>
	{#if limit.by === 'engine'}<p class="text-2xs text-fg-subtle">{t('modals.shot.durationEngine', { max: secs(limit.max) })}</p>{/if}

	<div class="flex items-start gap-3">
		<div class="flex flex-col gap-1">
			<span class="vp-label">{t('storyboard.quick.frames')}</span>
			<div class="flex items-center gap-1.5 text-fg-subtle">
				{#each [[first, t('storyboard.band.first')], [last, t('storyboard.band.last')]] as [image, caption], k (k)}
					<button type="button" class="relative h-[50px] w-[88px] overflow-hidden rounded border border-line-strong {image?.src ? 'bg-black' : 'bg-surface-2'}" onclick={editor} title={t('storyboard.quick.framesTip')}>
						{#if image?.src}<img src={image.src} alt="" class="h-full w-full object-cover" />{:else}<Icon name="image" class="mx-auto h-3.5 w-3.5" />{/if}
						<span class="absolute inset-x-0 bottom-0 truncate bg-black/60 px-1 text-left text-2xs text-white">{caption}</span>
					</button>
					{#if k === 0}<Icon name="arrow-right" class="h-3 w-3" />{/if}
				{/each}
			</div>
		</div>
		<div class="flex min-w-0 flex-1 flex-col gap-1">
			<span class="vp-label">{t('storyboard.quick.cast')}</span>
			<div class="flex flex-wrap items-center gap-1">
				{#each cast as name (name)}<span class="inline-flex h-5 items-center gap-1 rounded border border-line-strong px-1.5 text-2xs text-fg-muted"><Icon name="user" class="h-3 w-3" />{name}</span>{/each}
				{#if !cast.length}<span class="text-xs text-fg-subtle">{t('storyboard.quick.noCast')}</span>{/if}
				{#if sound?.behavior}<span class="inline-flex"><SoundNote behavior={sound.behavior} compact /></span>{/if}
			</div>
		</div>
	</div>

	<div class="flex items-center gap-2">
		<div class="flex-1"></div>
		<HostUi name="Button" props={{ variant: 'ghost', size: 'sm', icon: hostIconName('pencil'), onclick: editor }}>{t('storyboard.quick.editor')}</HostUi>
	</div>
</div>
